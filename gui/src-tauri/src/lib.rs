use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

/// 由 GUI 拉起并管理的控制层后端进程。
struct BackendProcess(Mutex<Option<Child>>);

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

/// 拉起 FastAPI 后端,返回 Child。
fn spawn_backend(project_root: &std::path::Path) -> Option<Child> {
    let server_dir = project_root.join("server");
    if !server_dir.join("app.py").exists() {
        return None;
    }
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

            // 项目根:tauri.conf.json 在 gui/ 下,仓库根是上一级
            let project_root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
                .join("..")
                .join("..");
            if let Some(child) = spawn_backend(&project_root) {
                let pid = child.id();
                app.manage(BackendProcess(Mutex::new(Some(child))));
                eprintln!("[fingerprint-browser] 后端已拉起 (pid={pid})");
            } else {
                eprintln!(
                    "[fingerprint-browser] 未找到 server/app.py,后端需自行启动 (uvicorn server.app:app --port 8000)"
                );
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            // 窗口关闭时结束后端
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
