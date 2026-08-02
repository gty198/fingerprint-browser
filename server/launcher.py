"""把 Profile → 引擎:生成指纹 → 映射成引擎参数 → 启动。"""
from __future__ import annotations

from pathlib import Path

from engine.base import BrowserEngine, EngineHandle, FingerprintConfig, ProxyConfig
from server.fingerprinter import ensure_fingerprint
from server.models import Profile, ProfileStore


def to_fingerprint_config(p: Profile) -> FingerprintConfig:
    fp = FingerprintConfig(
        platform=p.platform,
        user_agent=p.user_agent,
        viewport={"width": p.viewport_width, "height": p.viewport_height}
        if p.viewport_width and p.viewport_height
        else None,
        locale=p.locale,
        timezone=p.timezone,
        color_scheme=p.color_scheme,
        hardware_concurrency=p.hardware_concurrency,
        humanize=p.humanize,
    )
    if p.proxy_server:
        fp.proxy = ProxyConfig(p.proxy_server)
    return fp


def launch_profile(
    p: Profile,
    store: ProfileStore,
    engine: BrowserEngine,
    headless: bool = False,
) -> tuple[Profile, EngineHandle]:
    """补全指纹(若缺)→ 启动。返回补全后的 profile 与引擎句柄。"""
    p = ensure_fingerprint(p, store)
    handle = engine.launch_persistent(store.data_dir(p), to_fingerprint_config(p), headless=headless)
    return p, handle
