"""控制层 FastAPI 应用 + 启动入口。

给 GUI / CLI / 脚本提供统一 HTTP 接口:
profile CRUD、指纹再生成、启动/关闭浏览器、代理 geoip 匹配、Cookie 导入导出。

两种启动方式等价:
- `python server/app.py`(GUI 用,自动把仓库根加入 sys.path)
- `uvicorn server.app:app --host 127.0.0.1 --port 8000`
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from contextlib import asynccontextmanager  # noqa: E402

from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from pydantic import BaseModel, Field  # noqa: E402

from engine.cloak import CloakBrowserEngine  # noqa: E402
from server.geoip import resolve_geoip  # noqa: E402
from server.manager import BrowserManager, NotRunningError  # noqa: E402
from server.models import ProfileStore  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "profiles"

engine = CloakBrowserEngine()
store = ProfileStore(db_path=DATA_DIR / "profiles.sqlite3", profiles_root=DATA_DIR)
manager = BrowserManager(engine=engine, store=store)

@asynccontextmanager
async def _lifespan(_: FastAPI):
    try:
        yield
    finally:
        manager.shutdown()


app = FastAPI(title="Fingerprint Browser", version="0.1.0", lifespan=_lifespan)

# Tauri 开发环境 origin 是 http://localhost:5173,生产是 tauri://localhost;开发期放开
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- 请求模型 ----------

class ProfileCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    platform: str | None = None
    timezone: str | None = None
    locale: str | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    color_scheme: str | None = None
    hardware_concurrency: int | None = None
    humanize: bool = False
    proxy_server: str | None = None
    notes: str = ""


class ProfileUpdate(BaseModel):
    name: str | None = None
    platform: str | None = None
    timezone: str | None = None
    locale: str | None = None
    viewport_width: int | None = None
    viewport_height: int | None = None
    color_scheme: str | None = None
    hardware_concurrency: int | None = None
    humanize: bool | None = None
    proxy_server: str | None = None
    notes: str | None = None


class LaunchRequest(BaseModel):
    headless: bool = False
    open_url: str | None = None


class GeoipRequest(BaseModel):
    proxy_server: str | None = None
    apply: bool = False


class CookiesRequest(BaseModel):
    cookies: list[dict[str, Any]]


class EvalRequest(BaseModel):
    expression: str


# ---------- 引擎 ----------

@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/engine")
def engine_info() -> dict:
    return {
        "name": engine.name,
        "capabilities": engine.capabilities(),
        "binary": engine.ensure_binary(),
    }


# ---------- Profiles ----------

@app.post("/api/profiles", status_code=201)
def create_profile(body: ProfileCreate) -> dict:
    p = store.create(name=body.name, **body.model_dump(exclude={"name"}))
    # 创建时就把指纹生成好,GUI 立即可见、可编辑
    from server.fingerprinter import ensure_fingerprint
    p = ensure_fingerprint(p, store)
    return p.to_dict()


@app.get("/api/profiles")
def list_profiles() -> list[dict]:
    return [p.to_dict() for p in store.list()]


@app.get("/api/profiles/{pid}")
def get_profile(pid: str) -> dict:
    p = store.get(pid)
    if p is None:
        raise HTTPException(404, "profile not found")
    return p.to_dict()


@app.patch("/api/profiles/{pid}")
def update_profile(pid: str, body: ProfileUpdate) -> dict:
    p = store.get(pid)
    if p is None:
        raise HTTPException(404, "profile not found")
    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = store.update(pid, **fields)
    return updated.to_dict()  # type: ignore[union-attr]


@app.delete("/api/profiles/{pid}", status_code=204)
def delete_profile(pid: str) -> None:
    if manager.is_running(pid):
        raise HTTPException(409, "profile is running, close it first")
    p = store.get(pid)
    if p is None:
        raise HTTPException(404, "profile not found")
    data_dir = store.data_dir(p)
    store.delete(pid)
    if data_dir.exists():
        shutil.rmtree(data_dir, ignore_errors=True)


@app.post("/api/profiles/{pid}/fingerprint/regenerate")
def regenerate_fingerprint(pid: str) -> dict:
    """清空指纹字段重新生成(避开其它 profile 以及自己旧的组合)。"""
    p = store.get(pid)
    if p is None:
        raise HTTPException(404, "profile not found")
    old = (p.platform, p.timezone, p.locale, p.viewport_width, p.viewport_height, p.hardware_concurrency)
    store.update(
        pid,
        user_agent=None, platform=None, timezone=None, locale=None,
        viewport_width=None, viewport_height=None, hardware_concurrency=None,
    )
    from server.fingerprinter import ensure_fingerprint
    fresh = store.get(pid)
    p = ensure_fingerprint(fresh, store, used_extra={old})  # type: ignore[arg-type]
    return p.to_dict()


# ---------- 启动 / 关闭 ----------

@app.post("/api/profiles/{pid}/launch")
def launch(pid: str, body: LaunchRequest) -> dict:
    if store.get(pid) is None:
        raise HTTPException(404, "profile not found")
    status = manager.launch(pid, headless=body.headless, open_url=body.open_url)
    return {"status": status, "profile_id": pid}


@app.post("/api/profiles/{pid}/close")
def close(pid: str) -> dict:
    ok = manager.close(pid)
    return {"closed": ok}


@app.get("/api/running")
def running() -> dict:
    return {"running": manager.running()}


# ---------- 代理 geoip ----------

@app.post("/api/profiles/{pid}/geoip")
def geoip(pid: str, body: GeoipRequest) -> dict:
    p = store.get(pid)
    if p is None:
        raise HTTPException(404, "profile not found")
    proxy = body.proxy_server or p.proxy_server
    if not proxy:
        raise HTTPException(400, "no proxy configured")
    info = resolve_geoip(proxy)
    if info is None:
        return {"ok": False, "reason": "geoip resolve failed (proxy 需 http(s),或网络不可用)"}
    if body.apply:
        store.update(pid, timezone=info["timezone"], locale=info["locale"] or p.locale)
    return {"ok": True, **info}


# ---------- Cookie ----------

@app.get("/api/profiles/{pid}/cookies")
def export_cookies(pid: str) -> dict:
    # Playwright 线程亲和:通过 manager.call 投递到浏览器线程执行
    try:
        cookies = manager.call(pid, lambda ctx: ctx.cookies())
    except NotRunningError:
        raise HTTPException(409, "profile not running, start it first") from None
    return {"cookies": cookies}


@app.post("/api/profiles/{pid}/eval")
def eval_js(pid: str, body: EvalRequest) -> dict:
    """在运行中的浏览器页面执行 JS(本地调试/验收用)。"""
    try:
        def _run(ctx):
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            return page.evaluate(body.expression)
        result = manager.call(pid, _run)
    except NotRunningError:
        raise HTTPException(409, "profile not running, start it first") from None
    return {"result": result}


@app.post("/api/profiles/{pid}/cookies")
def import_cookies(pid: str, body: CookiesRequest) -> dict:
    # 补全 Playwright cookie 必需字段
    normalized = []
    for c in body.cookies:
        row = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", c.get("url", "").split("/")[2] if c.get("url") else ""),
            "path": c.get("path", "/"),
        }
        for k in ("expires", "secure", "httpOnly", "sameSite"):
            if k in c:
                row[k] = c[k]
        normalized.append(row)
    try:
        manager.call(pid, lambda ctx: ctx.add_cookies(normalized))
    except NotRunningError:
        raise HTTPException(409, "profile not running, start it first") from None
    return {"imported": len(normalized)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, log_level="warning")
