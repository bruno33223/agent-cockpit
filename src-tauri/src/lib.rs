use tauri::Manager;

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

      #[cfg(target_os = "linux")]
      {
        if let Some(window) = app.get_webview_window("main") {
          let _ = window.with_webview(|webview| {
            use webkit2gtk::{PermissionRequestExt, WebViewExt};
            webview.inner().connect_permission_request(|_, req| {
              req.allow();
              true
            });
          });
        }
      }

      Ok(())
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
