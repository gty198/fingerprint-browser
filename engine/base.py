"""浏览器引擎抽象层：把「指纹浏览器」需要的引擎能力定义成统一接口。

上层(server / gui)只依赖本模块里的 dataclass 和接口，
不直接 import 具体引擎(cloakbrowser / camoufox / ...)。
这样后续想换引擎或自维护补丁时，只需新增一个适配器。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass
class ProxyConfig:
    """代理配置。server 形如 http://user:pass@host:port 或 socks5://host:port"""

    server: str

    def __post_init__(self) -> None:
        if not re.match(r"^(https?|socks4|socks5)://", self.server, re.I):
            raise ValueError(f"proxy server 必须是 http(s)/socks 开头, got: {self.server!r}")

    def as_playwright_dict(self) -> dict[str, str]:
        """拆成 Playwright proxy 字典。"""
        # server 形如 scheme://[user:pass@]host:port
        d: dict[str, str] = {"server": self.server}
        m = re.match(r"^(?P<scheme>https?|socks4|socks5)://(?:(?P<user>[^:]+):(?P<pass>[^@]*)@)?(?P<host>[^/]+)$", self.server, re.I)
        if m and m.group("user"):
            d["server"] = f"{m.group('scheme')}://{m.group('host')}"
            d["username"] = m.group("user")
            d["password"] = m.group("pass") or ""
        return d


@dataclass
class FingerprintConfig:
    """一份 profile 的指纹参数。None 表示交给引擎自洽生成/默认。"""

    user_agent: str | None = None
    viewport: dict[str, int] | None = None          # {"width":.., "height":..}
    locale: str | None = None                       # BCP47, e.g. en-US / zh-CN
    timezone: str | None = None                     # IANA, e.g. Asia/Shanghai
    color_scheme: str | None = None                 # light / dark / no-preference
    proxy: ProxyConfig | None = None
    humanize: bool = False
    extra_args: list[str] = field(default_factory=list)


@dataclass
class EngineHandle:
    """一次启动的句柄：浏览器对象 + 是否需要显式 close。"""

    browser: Any          # 具体引擎返回的浏览器对象
    context: Any = None   # persistent context(若引擎用它)
    engine_name: str = ""

    def close(self) -> None:
        try:
            if self.context is not None:
                self.context.close()
            elif self.browser is not None:
                self.browser.close()
        except Exception:
            pass


class BrowserEngine(Protocol):
    """引擎必须实现的能力。"""

    name: str

    def ensure_binary(self) -> str:
        """下载/校验引擎二进制,返回可执行路径。"""
        ...

    def launch_persistent(
        self,
        user_data_dir: Path,
        fp: FingerprintConfig,
        headless: bool = False,
    ) -> EngineHandle:
        """以指定 user-data-dir + 指纹参数启动一个持久化浏览器。"""
        ...
