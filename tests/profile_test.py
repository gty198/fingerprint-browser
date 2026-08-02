#!/usr/bin/env python3
"""M2 验收脚本:Profile 模型 + 指纹自洽生成 + 稳定性 + 两 profile 指纹互异。

免费二进制限 1 并发会话,所以两个 profile 顺序启动、跑完即关。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.cloak import CloakBrowserEngine  # noqa: E402
from server.fingerprinter import ensure_fingerprint  # noqa: E402
from server.launcher import launch_profile  # noqa: E402
from server.models import ProfileStore  # noqa: E402

FINGERPRINT_JS = r"""
(async () => {
  return JSON.stringify({
    webdriver: navigator.webdriver,
    userAgent: navigator.userAgent,
    platform: navigator.platform,
    screen: screen.width + 'x' + screen.height,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    language: navigator.language,
    hardwareConcurrency: navigator.hardwareConcurrency || null,
  });
})()
"""


def check_coherent(sig: dict) -> list[str]:
    """UA 声明的平台必须和 navigator.platform 对得上。"""
    ua, plat = sig["userAgent"], sig["platform"]
    problems: list[str] = []
    if "Windows NT" in ua and "Win" not in plat:
        problems.append(f"UA 是 Windows 但 platform={plat}")
    if "X11; Linux" in ua and "Linux" not in plat:
        problems.append(f"UA 是 Linux 但 platform={plat}")
    if "Macintosh" in ua and "Mac" not in plat:
        problems.append(f"UA 是 Mac 但 platform={plat}")
    return problems


def collect(engine: CloakBrowserEngine, p, store: ProfileStore) -> dict:
    _, handle = launch_profile(p, store, engine, headless=True)
    page = handle.context.pages[0] if handle.context.pages else handle.context.new_page()
    page.goto("about:blank")
    sig = json.loads(page.evaluate(FINGERPRINT_JS))
    handle.close()
    return sig


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="fp-profiles-"))
    store = ProfileStore(db_path=tmp / "profiles.sqlite3", profiles_root=tmp)
    engine = CloakBrowserEngine()
    engine.ensure_binary()

    a = store.create("测试A")
    b = store.create("测试B")
    a = ensure_fingerprint(a, store)
    b = ensure_fingerprint(b, store)

    print("== 指纹生成(持久化后) ==")
    for p in (a, b):
        print(f"  {p.name}: ready={p.is_fingerprint_ready}")
        print(f"    UA={p.user_agent}")
        print(f"    viewport={p.viewport_width}x{p.viewport_height} {p.color_scheme}")
        print(f"    timezone={p.timezone} locale={p.locale} cores={p.hardware_concurrency}")

    # 稳定性:重读库,值必须完全一致
    a2 = store.get(a.id)
    assert a2 is not None
    assert a2.user_agent == a.user_agent and a2.viewport_width == a.viewport_width
    print("\n== 稳定性:重读库值一致 ==")
    print("  OK")

    # 互异性:两个 profile 顺序启动,指纹必须不同
    print("\n== 两个 profile 指纹对比 ==")
    sig_a = collect(engine, a, store)
    sig_b = collect(engine, b, store)
    for name, s in (("A", sig_a), ("B", sig_b)):
        print(f"  {name}: {s['userAgent'][:42]}... | {s['platform']} | {s['screen']} | {s['timezone']} | {s['language']} | cores={s['hardwareConcurrency']} | webdriver={s['webdriver']}")

    # 自洽性:UA 平台 与 navigator.platform 必须一致
    print("\n== 自洽性检查 ==")
    for name, s in (("A", sig_a), ("B", sig_b)):
        probs = check_coherent(s)
        if probs:
            print(f"  {name}: ✗ {probs}")
            raise SystemExit(f"{name} 指纹自洽性失败!")
        print(f"  {name}: OK(UA 平台与 navigator.platform 一致)")

    differing = [
        k for k in ("userAgent", "screen", "timezone", "language", "hardwareConcurrency")
        if sig_a[k] != sig_b[k]
    ]
    if differing:
        print(f"\n  指纹互异字段: {', '.join(differing)}")
    assert sig_a["webdriver"] is False and sig_b["webdriver"] is False
    assert differing, "两个 profile 指纹完全相同,互异性失败!"
    print("  OK: 两个 profile 指纹不同且 webdriver=False")
    print("\nM2 验收通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
