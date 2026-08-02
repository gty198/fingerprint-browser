"""运行中的浏览器管理:每个 profile 一个守护线程,launch 秒回、close 信号关闭。

为什么用线程:CloakBrowser 底层是 Playwright 同步 API,直接放进 FastAPI
事件循环会阻塞。每个浏览器实例跑在自己的 daemon 线程里。

⚠️ Playwright 同步 API 是线程亲和的:context 在哪个线程创建就必须在哪个
线程调用。所以对外只暴露 ``call(pid, fn)`` —— 由浏览器线程执行 fn(context),
结果经队列回传。任何其它线程直接调 context 都会 "Cannot switch to a different thread"。
"""
from __future__ import annotations

import queue
import threading
import time
from typing import Any, Callable

from engine.base import BrowserEngine, EngineHandle
from server.fingerprinter import ensure_fingerprint
from server.launcher import to_fingerprint_config
from server.models import ProfileStore

CallFn = Callable[[Any], Any]


class _Running:
    def __init__(
        self,
        profile_id: str,
        handle: EngineHandle,
        thread: threading.Thread,
        stop: threading.Event,
        call_queue: "queue.Queue[tuple[queue.Queue, CallFn]]",
    ):
        self.profile_id = profile_id
        self.handle = handle
        self.thread = thread
        self.stop = stop
        self.call_queue = call_queue
        self.started_at = time.time()


class NotRunningError(RuntimeError):
    pass


class BrowserManager:
    def __init__(self, engine: BrowserEngine, store: ProfileStore):
        self.engine = engine
        self.store = store
        self._running: dict[str, _Running] = {}
        self._lock = threading.Lock()

    # ---------- 生命周期 ----------

    def launch(self, profile_id: str, headless: bool = False, open_url: str | None = None) -> str:
        with self._lock:
            if profile_id in self._running:
                return "already_running"
        stop = threading.Event()
        thread = threading.Thread(
            target=self._run_browser,
            args=(profile_id, headless, open_url, stop),
            name=f"browser-{profile_id}",
            daemon=True,
        )
        thread.start()
        # 等浏览器真正起来再返回(最多 60s),GUI 才知道"启动成功"
        deadline = time.time() + 60
        while time.time() < deadline:
            with self._lock:
                if profile_id in self._running:
                    return "launched"
            if not thread.is_alive():
                return "launch_failed"
            time.sleep(0.1)
        return "timeout"

    def _run_browser(
        self,
        profile_id: str,
        headless: bool,
        open_url: str | None,
        stop: threading.Event,
    ) -> None:
        p = self.store.get(profile_id)
        if p is None:
            return
        p = ensure_fingerprint(p, self.store)
        handle = self.engine.launch_persistent(
            self.store.data_dir(p), to_fingerprint_config(p), headless=headless
        )
        call_queue: "queue.Queue[tuple[queue.Queue, CallFn]]" = queue.Queue()
        with self._lock:
            self._running[profile_id] = _Running(profile_id, handle, threading.current_thread(), stop, call_queue)

        try:
            if open_url:
                page = handle.context.pages[0] if handle.context.pages else handle.context.new_page()
                page.goto(open_url)
            # 持续运行:处理 stop + 排队的跨线程调用
            while True:
                while True:
                    try:
                        result_q, fn = call_queue.get_nowait()
                    except queue.Empty:
                        break
                    try:
                        result_q.put(("ok", fn(handle.context)))
                    except Exception as e:  # noqa: BLE001 - 回传异常给调用方
                        result_q.put(("err", e))
                if stop.wait(0.05):
                    break
        finally:
            handle.close()
            with self._lock:
                self._running.pop(profile_id, None)

    def close(self, profile_id: str) -> bool:
        with self._lock:
            r = self._running.get(profile_id)
        if r is None:
            return False
        r.stop.set()
        r.thread.join(timeout=10)
        if r.thread.is_alive():
            # 兜底:浏览器卡死时强杀(可能抛线程亲和错误,忽略)
            try:
                r.handle.close()
            except Exception:
                pass
        with self._lock:
            self._running.pop(profile_id, None)
        return True

    # ---------- 跨线程调用(浏览器线程执行) ----------

    def call(self, profile_id: str, fn: CallFn, timeout: float = 30.0) -> Any:
        """在浏览器线程执行 fn(context),返回结果。浏览器没在跑抛 NotRunningError。"""
        with self._lock:
            r = self._running.get(profile_id)
        if r is None:
            raise NotRunningError(profile_id)
        result_q: queue.Queue = queue.Queue()
        r.call_queue.put((result_q, fn))
        status, value = result_q.get(timeout=timeout)
        if status == "err":
            raise value
        return value

    # ---------- 查询 ----------

    def is_running(self, profile_id: str) -> bool:
        with self._lock:
            return profile_id in self._running

    def running(self) -> list[dict]:
        with self._lock:
            now = time.time()
            return [
                {
                    "profile_id": r.profile_id,
                    "engine": self.engine.name,
                    "uptime_seconds": int(now - r.started_at),
                }
                for r in self._running.values()
            ]

    def shutdown(self) -> None:
        for pid in list(self._running.keys()):
            self.close(pid)
