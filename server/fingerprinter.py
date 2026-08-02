"""指纹自洽生成器。

目标:给一个 profile 补齐缺失的指纹参数,让它们彼此「说得通」——
平台↔UA↔分辨率↔硬件并发数,以及地区↔时区↔语言。避免出现
「Windows 的 UA + 只有 Mac 的分辨率 + 中文时区却英文语言」这种穿帮组合。

防关联设计:新建 profile 时**逐维度避开其它 profile 已占用的值**
(平台/时区/分辨率/并发数/UA),避免两个「不同用户」撞成几乎相同的指纹。

关键:参数生成一次后由 ProfileStore 持久化。之后每次启动读库复用,
保证同一 profile 每次启动指纹一致(指纹忽变本身就是暴露信号)。
"""
from __future__ import annotations

import random

from .models import Profile, ProfileStore

# ---- 平台 → UA 池(真实 Chrome 版本) ----

UA_POOL: dict[str, list[str]] = {
    "macos": [
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Safari/537.36",
    ],
    "windows": [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36",
    ],
    "linux": [
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    ],
}

# ---- 地区 → 时区 + 语言 ----

REGIONS: dict[str, dict[str, str]] = {
    "us_east":   {"timezone": "America/New_York",    "locale": "en-US"},
    "us_west":   {"timezone": "America/Los_Angeles", "locale": "en-US"},
    "eu_london": {"timezone": "Europe/London",       "locale": "en-GB"},
    "eu_berlin": {"timezone": "Europe/Berlin",       "locale": "de-DE"},
    "sg":        {"timezone": "Asia/Singapore",      "locale": "en-SG"},
    "tokyo":     {"timezone": "Asia/Tokyo",          "locale": "ja-JP"},
    "shanghai":  {"timezone": "Asia/Shanghai",       "locale": "zh-CN"},
    "sydney":    {"timezone": "Australia/Sydney",    "locale": "en-AU"},
}

# ---- 平台 → 常见分辨率 / 硬件并发数 ----

VIEWPORTS: dict[str, list[tuple[int, int]]] = {
    "macos":   [(1440, 900), (1512, 982), (1728, 1117)],
    "windows": [(1920, 1080), (1366, 768), (1536, 864), (1280, 720)],
    "linux":   [(1920, 1080), (1366, 768)],
}
CONCURRENCY: dict[str, list[int]] = {
    "macos":   [8, 10, 12],
    "windows": [4, 8, 16],
    "linux":   [4, 8, 16],
}


def _rng(profile: Profile) -> random.Random:
    # 用 profile id 做种子:同一 profile 补全缺失字段时结果确定
    return random.Random(int(profile.id, 16))


def _pick_unique(rng: random.Random, values: list, used: set) -> object:
    pool = [v for v in values if v not in used]
    return rng.choice(pool if pool else values)


def ensure_fingerprint(p: Profile, store: ProfileStore, used_extra: set | None = None) -> Profile:
    """补齐 profile 缺失的指纹字段并持久化,返回完整 Profile。

    used_extra:额外要避开的组合(如「指纹再生成」时避开自己旧的组合)。
    """
    updates: dict[str, object] = {}
    rng = _rng(p)

    others = [x for x in store.list() if x.id != p.id]
    used_platform = {x.platform for x in others if x.platform}
    used_tz = {x.timezone for x in others if x.timezone}
    used_locale = {x.locale for x in others if x.locale}
    used_region = {(x.timezone, x.locale) for x in others if x.timezone and x.locale}
    used_viewport = {(x.viewport_width, x.viewport_height) for x in others if x.viewport_width}
    used_cores = {x.hardware_concurrency for x in others if x.hardware_concurrency}
    used_ua = {x.user_agent for x in others if x.user_agent}

    for item in used_extra or ():
        # item 可能是 (platform, tz, locale, w, h, cores) 或单值,统一并入
        if isinstance(item, tuple) and len(item) == 6:
            used_platform.add(item[0])
            used_tz.add(item[1])
            used_locale.add(item[2])
            used_viewport.add((item[3], item[4]))
            used_cores.add(item[5])
        elif item:
            used_platform.add(item)

    # 平台
    if not p.platform:
        updates["platform"] = _pick_unique(rng, list(UA_POOL.keys()), used_platform)
    platform = p.platform or updates["platform"]

    # UA(与平台匹配,且尽量不撞其它 profile)
    if not p.user_agent:
        updates["user_agent"] = _pick_unique(rng, UA_POOL[platform], used_ua)

    # 地区:时区+语言配对,避开已用组合
    if not p.timezone or not p.locale:
        candidates = [
            k for k, v in REGIONS.items()
            if (v["timezone"], v["locale"]) not in used_region
            and v["timezone"] not in used_tz and v["locale"] not in used_locale
        ]
        key = _pick_unique(rng, list(REGIONS.keys()), {k for k in REGIONS if k not in candidates})
        r = REGIONS[key]
        updates.setdefault("timezone", r["timezone"])
        updates.setdefault("locale", r["locale"])

    # 分辨率 / 并发数(随平台)
    if not p.viewport_width or not p.viewport_height:
        updates["viewport_width"], updates["viewport_height"] = _pick_unique(rng, VIEWPORTS[platform], used_viewport)
    if not p.hardware_concurrency:
        updates["hardware_concurrency"] = _pick_unique(rng, CONCURRENCY[platform], used_cores)

    if not p.color_scheme:
        updates["color_scheme"] = rng.choice(["light", "dark"])

    if updates:
        updated = store.update(p.id, **updates)
        assert updated is not None
        return updated
    return p
