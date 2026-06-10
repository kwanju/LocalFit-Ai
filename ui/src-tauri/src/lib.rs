// LocalFit AI — Tauri shell (Phase v4-0 spike).
// Scope: validate native gates S-5 (sidecar), S-6 (toast), S-7 (tray).
// NOT production: backend is spawned via `uv run` from the dev tree, not a bundled binary.

use std::process::{Child, Command};
use std::sync::Mutex;

use tauri::{
    menu::{Menu, MenuItem},
    tray::TrayIconBuilder,
    Manager, RunEvent, WindowEvent,
};
use tauri_plugin_notification::NotificationExt;

/// Holds the spawned FastAPI backend so we can kill it on exit (S-5: no zombies).
#[derive(Default)]
struct Backend(Mutex<Option<Child>>);

/// Repo root resolved at compile time: ui/src-tauri -> ui -> <root>.
/// Dev-only; bundled-sidecar pathing is out of scope for the spike (§5).
fn repo_root() -> std::path::PathBuf {
    std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .and_then(|p| p.parent())
        .expect("repo root from CARGO_MANIFEST_DIR")
        .to_path_buf()
}

/// S-5: spawn the FastAPI + model backend as a child process.
/// Matches scripts/dev.bat: `uv run python -m app.main` from the repo root.
fn spawn_backend() -> std::io::Result<Child> {
    Command::new("uv")
        .args(["run", "python", "-m", "app.main"])
        .current_dir(repo_root())
        .spawn()
}

/// S-5 fix: `uv run python` makes `uv` the direct child and `python` a *grandchild*.
/// `child.kill()` only reaps `uv`, orphaning the python server (port + VRAM held).
/// On Windows, kill the whole process tree by PID, then reap our handle.
fn kill_backend(child: &mut Child) {
    let pid = child.id();
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        let _ = Command::new("taskkill")
            .args(["/PID", &pid.to_string(), "/T", "/F"])
            .creation_flags(CREATE_NO_WINDOW)
            .status();
    }
    let _ = child.kill();
    let _ = child.wait();
    log::info!("backend tree killed pid={pid}");
}

#[tauri::command]
fn start_backend(state: tauri::State<'_, Backend>) -> Result<bool, String> {
    let mut guard = state.0.lock().unwrap();
    if guard.is_some() {
        return Ok(false); // already running
    }
    match spawn_backend() {
        Ok(child) => {
            log::info!("backend spawned pid={}", child.id());
            *guard = Some(child);
            Ok(true)
        }
        Err(e) => Err(format!("failed to spawn backend: {e}")),
    }
}

#[tauri::command]
fn stop_backend(state: tauri::State<'_, Backend>) -> Result<bool, String> {
    let mut guard = state.0.lock().unwrap();
    if let Some(mut child) = guard.take() {
        kill_backend(&mut child);
        Ok(true)
    } else {
        Ok(false)
    }
}

/// S-6: fire a native Windows toast. Triggered from the UI or the tray menu.
#[tauri::command]
fn notify(app: tauri::AppHandle, title: String, body: String) -> Result<(), String> {
    app.notification()
        .builder()
        .title(title)
        .body(body)
        .show()
        .map_err(|e| e.to_string())
}

fn show_main_window(app: &tauri::AppHandle) {
    if let Some(win) = app.get_webview_window("main") {
        let _ = win.show();
        let _ = win.unminimize();
        let _ = win.set_focus();
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_notification::init())
        .manage(Backend::default())
        .invoke_handler(tauri::generate_handler![start_backend, stop_backend, notify])
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }

            // S-7: system tray with menu (open / test toast / quit).
            let open_i = MenuItem::with_id(app, "open", "코치 열기", true, None::<&str>)?;
            let notify_i = MenuItem::with_id(app, "notify", "알림 테스트", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_i, &notify_i, &quit_i])?;

            TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("LocalFit AI")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_main_window(app),
                    "notify" => {
                        let _ = app
                            .notification()
                            .builder()
                            .title("LocalFit AI")
                            .body("운동할 시간이에요 — 클릭하면 코치가 열려요.")
                            .show();
                    }
                    "quit" => {
                        if let Some(state) = app.try_state::<Backend>() {
                            if let Some(mut child) = state.0.lock().unwrap().take() {
                                kill_backend(&mut child);
                            }
                        }
                        app.exit(0);
                    }
                    _ => {}
                })
                .build(app)?;

            // S-5: spawn the backend on launch (tolerate failure — UI still loads).
            match spawn_backend() {
                Ok(child) => {
                    log::info!("backend spawned pid={}", child.id());
                    app.state::<Backend>().0.lock().unwrap().replace(child);
                }
                Err(e) => log::error!("backend spawn failed (start it manually): {e}"),
            }

            Ok(())
        })
        // S-7: closing the window hides to tray instead of quitting.
        .on_window_event(|window, event| {
            if let WindowEvent::CloseRequested { api, .. } = event {
                api.prevent_close();
                let _ = window.hide();
            }
        })
        .build(tauri::generate_context!())
        .expect("error while building tauri application")
        .run(|app, event| {
            // S-5: ensure the backend is killed on app exit (no zombie).
            if let RunEvent::Exit = event {
                if let Some(state) = app.try_state::<Backend>() {
                    if let Some(mut child) = state.0.lock().unwrap().take() {
                        kill_backend(&mut child);
                    }
                }
            }
        });
}
