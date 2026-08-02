# 指纹浏览器 (Fingerprint Browser)

简单易用的指纹浏览器:每个 Profile 一套独立指纹 + 独立浏览器数据 + 可选代理,
多开互不关联。引擎层用 [CloakBrowser](https://github.com/CloakHQ/CloakBrowser)(预编译隐身 Chromium)。

## 功能

- **Profile 管理** — 新建/编辑/删除,指纹参数自洽生成(平台↔UA↔分辨率↔并发数↔地区时区语言)
- **防关联** — 新 profile 自动避开其它 profile 已占用的指纹组合;每个 profile 独立 `user-data-dir`(cookie/localStorage/缓存完全隔离)
- **指纹自洽** — `--fingerprint-platform` 联动 UA 与 `navigator.platform`,不会出现「UA 说 Windows、platform 却报 MacIntel」的穿帮
- **代理绑定** — HTTP/SOCKS5;「按 IP 匹配」通过代理查出口 IP 的时区/语言自动回填
- **Cookie 导入/导出** — JSON 格式,运行中实时读写
- **行为拟人** — 鼠标/键盘/滚动更像真人(引擎 `humanize`)

## 架构

```
┌───────────────────────────┐
│ GUI (Tauri 2 + React)      │  启动时自动拉起后端,关窗自动结束
├───────────────────────────┤
│ 控制层 (FastAPI :8000)     │  profile CRUD / 指纹注入 / 代理 geoip / cookie
├───────────────────────────┤
│ 引擎层 (CloakBrowser)      │  每 profile 一个持久化 context + 独立 user-data-dir
└───────────────────────────┘
```

## 目录

```
fingerprint-browser/
├── engine/          # 引擎抽象(base.py)+ CloakBrowser 适配器(cloak.py)
├── server/          # FastAPI 控制层 + profile SQLite + 指纹生成 + 浏览器管理
├── gui/             # Tauri 桌面壳(src-tauri)+ React 前端(src)
└── tests/           # 验收脚本(指纹/Profile/API)
```

## 快速开始

### 依赖
- Python 3.11+ , Node 20+ , Rust toolchain(仅桌面壳需要)
- macOS / Windows / Linux

### 安装
```bash
cd fingerprint-browser
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cd gui && npm install && npm install -D @tauri-apps/cli
```

### 运行(GUI 方式,推荐)
```bash
cd gui && npx tauri dev
```
Tauri 启动时自动拉起 FastAPI 后端(8000 端口),关窗自动结束。

### 运行(无 GUI,仅后端 + 手动)
```bash
.venv/bin/python server/app.py
# API: http://127.0.0.1:8000/docs
```

## 验收测试
```bash
.venv/bin/python tests/fp_check.py --headed     # 拉起隐身窗口跑 FingerprintJS
.venv/bin/python tests/profile_test.py          # 指纹生成/稳定性/互异性
.venv/bin/python tests/api_test.py              # 控制层全链路
```

## 引擎能力说明

CloakBrowser 免费二进制 (v145) 实测支持:平台/UA、硬件并发数、时区、语言(locale)、配色、
canvas/audio/字体噪声。**不支持**:Mac 屏幕尺寸。付费 Pro 解锁更多。GUI 会按 `/api/engine`
返回的 capabilities 提示哪些维度当前不生效。

> **语言一致性说明**:`engine/cloak.py` 自研 Playwright 封装,locale 走 Playwright CDP 注入
> (CloakBrowser 原封装的 `--lang` 二进制参数在免费版被忽略)。实测 `navigator.language`、
> `navigator.languages`、`Intl`、真实 HTTP `Accept-Language` 头全部一致,`webdriver` 仍为 false。

## 已知限制
- 免费二进制限 **1 并发会话**(多开多个窗口需要 Pro 授权)
- 反检测是军备竞赛,引擎可能随时间失效,需跟进上游更新
- 引擎核心补丁为 CloakBrowser 闭源二进制(详见其 [free/Pro 授权](https://cloakbrowser.dev))
