"""CloakBrowser 适配器。

CloakBrowser = 开源包装(MIT) + 预编译隐身 Chromium(闭源二进制,free/Pro 分层)。
这里只通过它公开的 API 对接,不依赖其内部实现。
"""
from __future__ import annotations

from pathlib import Path

import cloakbrowser

from .base import BrowserEngine, EngineHandle, FingerprintConfig


class CloakBrowserEngine(BrowserEngine):
    name = "cloakbrowser"

    def ensure_binary(self) -> str:
        return cloakbrowser.ensure_binary()

    def launch_persistent(
        self,
        user_data_dir: Path,
        fp: FingerprintConfig,
        headless: bool = False,
    ) -> EngineHandle:
        user_data_dir.mkdir(parents=True, exist_ok=True)
        proxy_str = fp.proxy.server if fp.proxy else None

        context = cloakbrowser.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=headless,
            proxy=proxy_str,
            user_agent=fp.user_agent,
            viewport=fp.viewport,
            locale=fp.locale,
            timezone=fp.timezone,
            color_scheme=fp.color_scheme,
            humanize=fp.humanize,
            args=fp.extra_args,
        )
        # persistent context 模式下 launch_persistent_context 返回的是 context 对象
        return EngineHandle(browser=context, context=context, engine_name=self.name)
