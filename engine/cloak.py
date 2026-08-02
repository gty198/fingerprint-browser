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

    def capabilities(self) -> dict[str, bool]:
        """v145 免费二进制实测:platform/UA/并发数/时区/噪声种子可控;locale 与 macos 屏幕锁宿主机。"""
        info = cloakbrowser.binary_info()
        return {
            "platform": True,
            "user_agent": True,
            "hardware_concurrency": True,
            "timezone": True,
            "color_scheme": True,
            "fingerprint_seed": True,   # canvas/audio/字体噪声
            "locale": False,            # --fingerprint-locale 未在免费二进制生效
            "screen": info.get("platform") != "darwin-arm64",  # 非 mac 平台 screen 随 platform 变
        }

    def launch_persistent(
        self,
        user_data_dir: Path,
        fp: FingerprintConfig,
        headless: bool = False,
    ) -> EngineHandle:
        user_data_dir.mkdir(parents=True, exist_ok=True)
        proxy_str = fp.proxy.server if fp.proxy else None

        # platform / 并发数没有独立参数,通过 --fingerprint-* 二进制参数注入
        extra = list(fp.extra_args)
        if fp.platform:
            extra.append(f"--fingerprint-platform={fp.platform}")
        if fp.hardware_concurrency:
            extra.append(f"--fingerprint-hardware-concurrency={fp.hardware_concurrency}")

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
            args=extra,
        )
        # persistent context 模式下 launch_persistent_context 返回的是 context 对象
        return EngineHandle(browser=context, context=context, engine_name=self.name)
