#!/usr/bin/env python3
"""M3 验收:控制层 API 全链路。

覆盖:引擎信息 → 建 profile → 列表 → 更新 → 指纹再生成 → 真实启动(无头)
→ running → Cookie 导入/导出往返 → 关闭 → 删除。
用 headless 避免测试时弹窗。跑完自动清理测试 profile。
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from server.app import app  # noqa: E402

client = TestClient(app)
created: list[str] = []


def step(name: str, ok: bool, detail: str = "") -> None:
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise SystemExit(f"FAIL at: {name} {detail}")


def main() -> int:
    print("[1] 引擎信息")
    r = client.get("/api/engine")
    step("GET /api/engine", r.status_code == 200, f"capabilities={r.json()['capabilities']}")
    assert "platform" in r.json()["capabilities"]

    print("[2] 创建 profile(应自动生成指纹)")
    r = client.post("/api/profiles", json={"name": "API测试", "notes": "m3"})
    step("POST /api/profiles", r.status_code == 201, f"id={r.json()['id']}")
    p = r.json()
    created.append(p["id"])
    step("指纹已生成", p["fingerprint_ready"] is True, f"{p['platform']} {p['timezone']}")

    print("[3] 列表 / 单个 / 更新")
    r = client.get("/api/profiles")
    step("GET /api/profiles", any(x["id"] == p["id"] for x in r.json()), f"共 {len(r.json())} 个")
    r = client.get(f"/api/profiles/{p['id']}")
    step("GET /api/profiles/{id}", r.status_code == 200)
    r = client.patch(f"/api/profiles/{p['id']}", json={"name": "API测试-改名", "proxy_server": "http://127.0.0.1:8888"})
    step("PATCH 改名+代理", r.status_code == 200 and r.json()["name"] == "API测试-改名")

    print("[4] 指纹再生成")
    before = client.get(f"/api/profiles/{p['id']}").json()
    r = client.post(f"/api/profiles/{p['id']}/fingerprint/regenerate")
    step("POST fingerprint/regenerate", r.status_code == 200 and r.json()["fingerprint_ready"])
    after = r.json()
    step("指纹确实变了", (before.get("platform"), before.get("timezone")) != (after.get("platform"), after.get("timezone")),
         f"{before['platform']}/{before['timezone']} → {after['platform']}/{after['timezone']}")

    print("[5] 真实启动(无头)")
    r = client.post(f"/api/profiles/{p['id']}/launch", json={"headless": True, "open_url": "about:blank"})
    step("POST launch", r.status_code == 200 and r.json()["status"] == "launched", str(r.json()))
    r = client.get("/api/running")
    step("GET /api/running 包含该 profile", any(x["profile_id"] == p["id"] for x in r.json()["running"]))

    print("[6] Cookie 导入/导出往返")
    cookie = [{"name": "m3_test", "value": "ok123", "domain": "example.com", "path": "/"}]
    r = client.post(f"/api/profiles/{p['id']}/cookies", json={"cookies": cookie})
    step("POST cookies", r.status_code == 200 and r.json()["imported"] == 1)
    r = client.get(f"/api/profiles/{p['id']}/cookies")
    got = [c for c in r.json()["cookies"] if c.get("name") == "m3_test"]
    step("GET cookies 读回", len(got) == 1 and got[0]["value"] == "ok123", f"value={got[0]['value'] if got else 'N/A'}")

    print("[7] 关闭 / 删除")
    r = client.post(f"/api/profiles/{p['id']}/close")
    step("POST close", r.status_code == 200 and r.json()["closed"] is True)
    r = client.delete(f"/api/profiles/{p['id']}")
    step("DELETE profile", r.status_code == 204)
    created.remove(p["id"])

    print("\nM3 验收通过 ✅")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    finally:
        # 清理未删的测试 profile
        for pid in list(created):
            try:
                client.post(f"/api/profiles/{pid}/close")
                client.delete(f"/api/profiles/{pid}")
            except Exception:
                pass
