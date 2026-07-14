use axum::{Json, response::IntoResponse, http::StatusCode};
use serde::Serialize;
use tokio::process::Command;
use chrono::Local;

#[derive(Serialize)]
pub struct CaptureResponse {
    pub message: String,
    pub filename: String,
}

pub async fn capture_image() -> Result<impl IntoResponse, StatusCode> {
   let timestamp = Local::now().format("%Y-%m-%d %H-%M-%S").to_string();
   let output_filename = format!("{}.jpg", timestamp);
   let tuning_path = "/usr/share/libcamera/ipa/rpi/pisp/imx219_noir.json";

   let output = Command::new("rpicam-still")
        .args([
            "-o", &output_filename,
            "--tuning-file", tuning_path,
            "-t", "2000",
            "--immediate"
        ])
        .output()
	.await;

    match output {
        Ok(res) if res.status.success() => {
            Ok(Json(CaptureResponse {
                message: "Image saved".to_string(),
                filename: output_filename,
            }))
        }
        Ok(res) => {
            // Log stderr to your terminal console so you can see why libcamera failed
            eprintln!("libcamera-still failed: {}", String::from_utf8_lossy(&res.stderr));
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
        Err(e) => {
            eprintln!("Failed to execute command: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}
