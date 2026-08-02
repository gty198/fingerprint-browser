use std::io::{Read, Write};
use std::net::TcpStream;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;
use tauri::Manager;

/// 由 GUI 拉起并管理的控制层后端进程。None = 未由本实例拉起(可能已有后端在跑)。
struct BackendProcess(Mutex<Option<Child>>);

/// 控制层默认端口。
const BACKEND_PORT: u16 = 8000;

/// 探测 :8000 是否已有健康后端,避免重复拉起 / 端口冲突。
fn backend_already_running() -> bool {
    if let Ok(mut stream) = TcpStream::connect(("127.0.0.1", BACKEND_PORT)) {
        let _ = stream.set_read_timeout(Some(Duration::from_millis(800)));
        let _ = stream.write_all(b"GET /api/health HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n");
        let mut buf = [0u8; 64];
        // 能读到响应体即认为后端可用;读不到也不算失败(后端可能刚起)
        let _ = stream.read(&mut buf);
        let text = String::from_utf8_lossy(&buf);
        return text.contains("200 OK") || text.contains("status");
    }
    false
}

/// 找可用的 python:优先项目 venv,否则 PATH 里的 python3。
fn resolve_python(project_root: &std::path::Path) -> Option<std::path::PathBuf> {
    let venv = project_root.join(".venv/bin/python");
    if venv.exists() {
        return Some(venv);
    }
    let venv2 = project_root.join(".venv/bin/python3");
    if venv2.exists() {
        return Some(venv2);
    }
    None
}

/// 定位控制层代码目录:
/// 1) 源码树(开发 + 本机打包,venv 在仓库根)
/// 2) 应用资源目录内嵌的 server/(未来分发自包含时的兜底)
fn find_server_dir(app: &tauri::AppHandle) -> Option<std::path::PathBuf> {
    // 源码树:tauri.conf.json 在 gui/ 下,仓库根是上一级
    let source_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let source_server = source_root.join("server");
    if source_server.join("app.py").exists() {
        return Some(source_server);
    }
    // 打包资源内嵌 server/
    if let Ok(res_dir) = app.path().resource_dir() {
        let bundled = res_dir.join("server");
        if bundled.join("app.py").exists() {
            return Some(bundled);
        }
    }
    None
}

/// 拉起 FastAPI 后端,返回 Child。返回 None 表示未找到代码或启动失败。
fn spawn_backend(app: &tauri::AppHandle) -> Option<Child> {
    let server_dir = find_server_dir(app)?;
    let project_root = server_dir
        .parent()
        .expect("server 目录必有父级");

    let mut cmd;
    if let Some(py) = resolve_python(project_root) {
        cmd = Command::new(py);
        cmd.arg(server_dir.join("app.py"));
    } else {
        cmd = Command::new("python3");
        cmd.arg(server_dir.join("app.py"));
    }
    cmd.current_dir(&server_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    cmd.spawn().ok()
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            if backend_already_running() {
                eprintln!("[fingerprint-browser] 检测到已有后端在 :{BACKEND_PORT},复用之,不再拉起。");
                app.manage(BackendProcess(Mutex::new(None)));
            } else if let Some(child) = spawn_backend(app.handle()) {
                let pid = child.id();
                app.manage(BackendProcess(Mutex::new(Some(child))));
                eprintln!("[fingerprint-browser] 后端已拉起 (pid={pid})");
            } else {
                eprintln!(
                    "[fingerprint-browser] 未找到后端代码,需自行启动 (uvicorn server.app:app --port {BACKEND_PORT})"
                );
                app.manage(BackendProcess(Mutex::new(None)));
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // 窗口关闭时,只结束由本实例拉起的后端
            if let tauri::WindowEvent::Destroyed = event {
                if let Some(state) = window.try_state::<BackendProcess>() {
                    let mut guard = state.0.lock().unwrap();
                    if let Some(mut child) = guard.take() {
                        let _ = child.kill();
                        let _ = child.wait();
                        eprintln!("[fingerprint-browser] 后端已随窗口结束");
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
