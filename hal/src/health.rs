use axum::{Json, response::IntoResponse, http::StatusCode};
use serde::Serialize;
use tokio::process::Command;

#[derive(Serialize)]
pub struct HealthStatus {
    pub status: String,
    pub camera_available: bool,
}

pub async fn check_health() -> impl IntoResponse {
	let output = Command::new("rpicam-still")
		.arg("--list-cameras")
		.output()
		.await;
	let camera_available = match output {
        Ok(res) => {
            let stdout_and_stderr = format!(
                "{}{}", 
                String::from_utf8_lossy(&res.stdout), 
                String::from_utf8_lossy(&res.stderr)
            );
            
           res.status.success() && !stdout_and_stderr.contains("No cameras available")
        }
        Err(_) => false,
    };

    let (http_code, status_string) = if camera_available {
        (StatusCode::OK, "ok".to_string())
    } else {
        (StatusCode::SERVICE_UNAVAILABLE, "unhealthy".to_string())
    };
    (
	http_code,
	Json(HealthStatus {
		status: status_string,
		camera_available,
	})
    )
}