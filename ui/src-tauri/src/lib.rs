// LocalFit AI — Tauri desktop shell (production, phase v4-6; ADR-031).
// Responsibilities: system tray + window lifecycle (S-7), native toast (S-6,
// ADR-027), FastAPI sidecar spawn/tree-kill (S-5), and WebView2 microphone
// permission grant for voice input (S-4, ADR-005).
//
// Sidecar note: the backend is launched via `uv run python -m app.main` from the
// dev tree (matches scripts/dev.bat). Bundling Python + models into the installer
// is deliberately out of scope (ADR-031 후순위 — a separate task); this shell
// stabilizes the dev / externally-started backend path.

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

/// S-4 fix: WebView2 raises `PermissionRequested` for `getUserMedia`. With no
/// handler the request is left at its default (deny/flaky prompt) and the mic
/// never opens — voice input (S2S/C2S) breaks. We auto-grant the MICROPHONE kind
/// so capture starts silently; everything else keeps WebView2's default.
/// Windows-only (other platforms grant mic via the OS prompt as usual).
#[cfg(windows)]
fn grant_microphone_permission(window: &tauri::WebviewWindow) {
    use webview2_com::Microsoft::Web::WebView2::Win32::{
        COREWEBVIEW2_PERMISSION_KIND_MICROPHONE, COREWEBVIEW2_PERMISSION_STATE_ALLOW,
    };
    use webview2_com::PermissionRequestedEventHandler;

    let result = window.with_webview(|webview| unsafe {
        let core = match webview.controller().CoreWebView2() {
            Ok(core) => core,
            Err(e) => {
                log::error!("WebView2 core unavailable, mic permission not wired: {e}");
                return;
            }
        };
        let handler = PermissionRequestedEventHandler::create(Box::new(|_webview, args| {
            if let Some(args) = args {
                let mut kind = Default::default();
                args.PermissionKind(&mut kind)?;
                if kind == COREWEBVIEW2_PERMISSION_KIND_MICROPHONE {
                    args.SetState(COREWEBVIEW2_PERMISSION_STATE_ALLOW)?;
                }
            }
            Ok(())
        }));
        let mut token = Default::default();
        if let Err(e) = core.add_PermissionRequested(&handler, &mut token) {
            log::error!("failed to register WebView2 PermissionRequested handler: {e}");
        } else {
            log::info!("WebView2 microphone permission auto-grant wired");
        }
    });
    if let Err(e) = result {
        log::error!("with_webview failed, mic permission not wired: {e}");
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

            // S-7: system tray with menu (open / quit). The spike's "알림 테스트"
            // item was a manual toast probe — removed now that S-6 is confirmed;
            // real scheduled notifications land in phase v4-8 (ADR-027).
            let open_i = MenuItem::with_id(app, "open", "코치 열기", true, None::<&str>)?;
            let quit_i = MenuItem::with_id(app, "quit", "종료", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open_i, &quit_i])?;

            TrayIconBuilder::with_id("main")
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("LocalFit AI")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => show_main_window(app),
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

            // S-5: spawn the backend on launch (tolerate failure — UI still loads
            // and the sidecar-down banner offers a restart; phase v4-6 6-3).
            match spawn_backend() {
                Ok(child) => {
                    log::info!("backend spawned pid={}", child.id());
                    app.state::<Backend>().0.lock().unwrap().replace(child);
                }
                Err(e) => log::error!("backend spawn failed (start it manually): {e}"),
            }

            // S-4: wire WebView2 mic permission once the main webview exists.
            #[cfg(windows)]
            if let Some(window) = app.get_webview_window("main") {
                grant_microphone_permission(&window);
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
