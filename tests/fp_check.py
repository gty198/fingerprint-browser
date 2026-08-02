#!/usr/bin/env python3
"""M1 验收脚本：拉起一个带独立指纹的隐身浏览器窗口,跑 FingerprintJS + 手工信号采集。

用法:
    .venv/bin/python tests/fp_check.py --profile /tmp/fp-check-profile --headed
    .venv/bin/python tests/fp_check.py --profile /tmp/fp-check-profile --headless
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine.base import FingerprintConfig  # noqa: E402
from engine.cloak import CloakBrowserEngine  # noqa: E402

# 页面内执行的指纹采集 JS：FingerprintJS(CDN) + 手工信号
FINGERPRINT_JS = r"""
(async () => {
  const manual = () => {
    const canvas = document.createElement('canvas');
    canvas.width = 200; canvas.height = 50;
    const ctx = canvas.getContext('2d');
    ctx.textBaseline = 'top';
    ctx.font = '14px Arial';
    ctx.fillStyle = '#f60';
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = '#069';
    ctx.fillText('Cwm fjordbank glyphs vext quiz, 😃', 2, 15);
    ctx.fillStyle = 'rgba(102, 204, 0, 0.7)';
    ctx.fillText('Cwm fjordbank glyphs vext quiz, 😃', 4, 17);
    let canvasHash = '';
    try { canvasHash = canvas.toDataURL().slice(0, 200); } catch (e) { canvasHash = 'err:' + e.message; }
    const gl = document.createElement('canvas').getContext('webgl');
    let webglRenderer = 'n/a', webglVendor = 'n/a';
    if (gl) {
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      if (dbg) {
        webglRenderer = gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL);
        webglVendor = gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL);
      }
    }
    return {
      webdriver: navigator.webdriver,
      userAgent: navigator.userAgent,
      platform: navigator.platform,
      hardwareConcurrency: navigator.hardwareConcurrency || null,
      deviceMemory: navigator.deviceMemory ?? null,
      screen: screen.width + 'x' + screen.height + ' (dpr=' + (window.devicePixelRatio || 1) + ')',
      availScreen: screen.availWidth + 'x' + screen.availHeight,
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      timezoneOffset: new Date().getTimezoneOffset(),
      language: navigator.language,
      languages: JSON.stringify(navigator.languages),
      canvasHash: canvasHash.slice(0, 80) + '...',
      webglVendor: webglVendor,
      webglRenderer: webglRenderer,
      colorDepth: screen.colorDepth,
      plugins: Array.from(navigator.plugins || []).map(p => p.name).length,
    };
  };

  let fp = null, fpError = null;
  try {
    await new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdn.jsdelivr.net/npm/@fingerprintjs/fingerprintjs@4/dist/fp.min.js';
      s.onload = resolve; s.onerror = () => reject(new Error('script load failed'));
      document.head.appendChild(s);
    });
    const agent = await window.FingerprintJS.load();
    const r = await agent.get();
    fp = { visitorId: r.visitorId, confidence: r.confidence, components: Object.keys(r.components) };
  } catch (e) { fpError = String(e); }

  return JSON.stringify({ manual: manual(), fp: fp, fpError: fpError });
})()
"""


def run(profile_dir: Path, headless: bool, keep_open: bool) -> None:
    engine = CloakBrowserEngine()
    print(f"[1/4] 准备引擎二进制 ...")
    bin_path = engine.ensure_binary()
    print(f"      引擎二进制: {bin_path}")

    fp = FingerprintConfig(extra_args=["--no-first-run"])

    print(f"[2/4] 启动隐身浏览器 (headed={not headless}) ...")
    handle = engine.launch_persistent(profile_dir, fp, headless=headless)
    page = handle.context.pages[0] if handle.context.pages else handle.context.new_page()

    print("[3/4] 打开空页运行指纹采集 JS ...")
    page.goto("about:blank")
    result = json.loads(page.evaluate(FINGERPRINT_JS))

    print("[4/4] 结果:")
    m, fp = result["manual"], result["fp"]
    print("  —— 手工信号 ——")
    for k, v in m.items():
        print(f"    {k:<18}: {v}")
    if fp:
        print("  —— FingerprintJS ——")
        print(f"    visitorId     : {fp['visitorId']}")
        print(f"    confidence    : {fp['confidence']}")
        print(f"    组件数        : {len(fp['components'])}")
        print(f"    组件清单      : {', '.join(fp['components'])}")
    if result.get("fpError"):
        print(f"  [WARN] FingerprintJS 加载失败(可能没网/被墙): {result['fpError']}")
        print("         手工信号仍可作为基础验收依据。")

    if keep_open:
        print("\n窗口保持打开,按 Enter 关闭 ...", end="", flush=True)
        input()
    handle.close()
    print("\n验收完成。")


def main() -> int:
    ap = argparse.ArgumentParser(description="M1 指纹浏览器引擎验收")
    ap.add_argument("--profile", default=None, help="user-data-dir(默认用临时目录)")
    ap.add_argument("--headed", action="store_true", help="有头模式(默认无头)")
    ap.add_argument("--keep-open", action="store_true", help="跑完不立即关闭窗口")
    args = ap.parse_args()

    profile_dir = Path(args.profile) if args.profile else Path(tempfile.mkdtemp(prefix="fp-check-"))
    try:
        run(profile_dir, headless=not args.headed, keep_open=args.keep_open)
    except KeyboardInterrupt:
        return 1
    except Exception as e:  # noqa: BLE001
        print(f"\n[FAIL] {type(e).__name__}: {e}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
