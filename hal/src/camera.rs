use axum::{Json, http::StatusCode, response::IntoResponse};
use chrono::Local;
use serde::Serialize;
use std::path::PathBuf;
use tokio::process::Command;

#[derive(Serialize)]
pub struct CaptureResponse {
    pub message: String,
    pub filename: String,
}

fn capture_path(timestamp: &str) -> Result<PathBuf, std::io::Error> {
    Ok(std::env::current_dir()?
        .join("caps")
        .join(format!("{timestamp}.jpg")))
}

pub async fn capture_image() -> Result<impl IntoResponse, StatusCode> {
    let timestamp = Local::now().format("%Y-%m-%d %H-%M-%S").to_string();
    let output_path = capture_path(&timestamp).map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let output_directory = output_path
        .parent()
        .ok_or(StatusCode::INTERNAL_SERVER_ERROR)?;
    tokio::fs::create_dir_all(output_directory)
        .await
        .map_err(|_| StatusCode::INTERNAL_SERVER_ERROR)?;
    let output_filename = output_path.to_string_lossy().into_owned();
    let tuning_path = "/usr/share/libcamera/ipa/rpi/pisp/imx219_noir.json";

    let output = Command::new("rpicam-still")
        .args([
            "-o",
            &output_filename,
            "--tuning-file",
            tuning_path,
            "-t",
            "2000",
            "--immediate",
        ])
        .output()
        .await;

    match output {
        Ok(res) if res.status.success() => Ok(Json(CaptureResponse {
            message: "Image saved".to_string(),
            filename: output_filename,
        })),
        Ok(res) => {
            // Log stderr to your terminal console so you can see why libcamera failed
            eprintln!(
                "libcamera-still failed: {}",
                String::from_utf8_lossy(&res.stderr)
            );
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
        Err(e) => {
            eprintln!("Failed to execute command: {}", e);
            Err(StatusCode::INTERNAL_SERVER_ERROR)
        }
    }
}

#[cfg(test)]
mod tests {
    use super::capture_path;

    #[test]
    fn capture_paths_are_absolute_and_use_the_caps_directory() {
        let path = capture_path("test-capture").expect("current directory is available");

        assert!(path.is_absolute());
        assert!(path.ends_with("caps/test-capture.jpg"));
    }
}
