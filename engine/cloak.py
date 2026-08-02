"""CloakBrowser 适配器。

CloakBrowser = 开源包装(MIT) + 预编译隐身 Chromium(闭源二进制,free/Pro 分层)。

为什么不用 cloakbrowser.launch_persistent_context 而自己拼 Playwright:
它的 `locale` 是显式参数,只拼成 `--lang`/`--fingerprint-locale` 二进制参数
(免费二进制 v145 忽略它们,导致语言锁死宿主机 zh-CN),从不传给 Playwright
的 CDP locale emulation。实测同一个二进制用 Playwright 原生 locale 参数
语言完美生效,且 webdriver 仍为 false。

所以这里复用它的全部隐身处理(build_args / IGNORE_DEFAULT_ARGS / proxy /
webrtc / widevine),但 locale 额外走 Playwright context kwargs。
"""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

import cloakbrowser
from cloakbrowser import build_args
from cloakbrowser.browser import _append_webrtc_exit_ip, _resolve_proxy_config, _resolve_webrtc_args
from cloakbrowser.config import IGNORE_DEFAULT_ARGS
from cloakbrowser.license import build_launch_env
from cloakbrowser.widevine import seed_widevine_hint

from .base import BrowserEngine, EngineHandle, FingerprintConfig


class CloakBrowserEngine(BrowserEngine):
    name = "cloakbrowser"

    def ensure_binary(self) -> str:
        return cloakbrowser.ensure_binary()

    def capabilities(self) -> dict[str, bool]:
        """实测能力(自研 Playwright 封装后):locale 已可用。screen 仍看 platform。"""
        info = cloakbrowser.binary_info()
        return {
            "platform": True,
            "user_agent": True,
            "hardware_concurrency": True,
            "timezone": True,
            "color_scheme": True,
            "fingerprint_seed": True,
            "locale": True,            # 通过 Playwright CDP 注入,已修复
            "screen": info.get("platform") != "darwin-arm64",
        }

    def launch_persistent(
        self,
        user_data_dir: Path,
        fp: FingerprintConfig,
        headless: bool = False,
    ) -> EngineHandle:
        user_data_dir.mkdir(parents=True, exist_ok=True)
        binary_path = cloakbrowser.ensure_binary()
        proxy = fp.proxy.server if fp.proxy else None

        # 1. 拼 stealth 参数(与 CloakBrowser 一致)
        args: list[str] = list(fp.extra_args)
        if fp.platform:
            args.append(f"--fingerprint-platform={fp.platform}")
        if fp.hardware_concurrency:
            args.append(f"--fingerprint-hardware-concurrency={fp.hardware_concurrency}")

        # 2. 复刻 cloakbrowser 的 proxy / webrtc 处理
        proxy_kwargs, proxy_extra_args = _resolve_proxy_config(proxy)
        args = _resolve_webrtc_args(args, proxy)
        args = _append_webrtc_exit_ip(args, None)  # 无 geoip,exit_ip=None
        chrome_args = build_args(
            stealth_args=True,
            extra_args=(args or []) + proxy_extra_args,
            timezone=fp.timezone,
            locale=fp.locale,          # 生成 --lang(付费版生效;免费版被 CDP locale 覆盖)
            headless=headless,
        )

        # 3. context kwargs:user_agent / viewport / color_scheme / locale(关键)
        context_kwargs: dict = {}
        if fp.user_agent:
            context_kwargs["user_agent"] = fp.user_agent
        if fp.viewport:
            context_kwargs["viewport"] = fp.viewport
        if fp.color_scheme:
            context_kwargs["color_scheme"] = fp.color_scheme
        if fp.locale:
            context_kwargs["locale"] = fp.locale  # ← Playwright CDP,语言真正生效

        launch_env = build_launch_env(None)
        if launch_env:
            context_kwargs["env"] = launch_env

        seed_widevine_hint(user_data_dir, binary_path)

        # 4. 启动
        pw = sync_playwright().start()
        try:
            context = pw.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                executable_path=binary_path,
                headless=headless,
                args=chrome_args,
                ignore_default_args=IGNORE_DEFAULT_ARGS,
                **proxy_kwargs,
                **context_kwargs,
            )
        except Exception:
            pw.stop()
            raise

        # 5. patch close 同时停掉 playwright 实例(与 CloakBrowser 一致)
        _orig_close = context.close

        def _close_with_cleanup(*, reason: str | None = None) -> None:
            try:
                if reason is None:
                    _orig_close()
                else:
                    _orig_close(reason=reason)
            finally:
                pw.stop()

        context.close = _close_with_cleanup

        # 6. 行为拟人(复用 CloakBrowser 的 human 模块)
        if fp.humanize:
            from cloakbrowser.human import patch_context
            from cloakbrowser.human.config import resolve_config

            cfg = resolve_config("default")
            patch_context(context, cfg)

        return EngineHandle(browser=context, context=context, engine_name=self.name)
