"""代理 → 地理/时区/语言解析。

通过代理发一个请求到 ipapi.co(免费、免 key),拿出口 IP 对应的
时区和语言,回填到 profile,避免「IP 在美国、时区却在中国」的穿帮。
失败静默返回 None(GUI 可以提示手动设置)。
"""
from __future__ import annotations

import httpx


def resolve_geoip(proxy_server: str) -> dict | None:
    """通过代理请求 ipapi.co。返回 {timezone, locale, country, ip} 或 None。"""
    if not proxy_server or not proxy_server.startswith(("http://", "https://")):
        # socks 代理 httpx 默认不支持(需 socks extra),这里只支持 http(s)
        return None
    try:
        with httpx.Client(proxy=proxy_server, timeout=10) as client:
            r = client.get("https://ipapi.co/json/")
            r.raise_for_status()
            data = r.json()
        tz = data.get("timezone")
        if not tz:
            return None
        langs = (data.get("languages") or "").split(",")
        locale = langs[0].strip() or None if langs else None
        return {
            "timezone": tz,
            "locale": locale,
            "country": data.get("country_name"),
            "ip": data.get("ip"),
        }
    except Exception:  # noqa: BLE001 - 网络/代理不可用都静默
        return None
