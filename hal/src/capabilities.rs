use axum::{Json, response::IntoResponse, http::StatusCode};
use serde::Serialize;

#[derive(Serialize)]
pub struct CapabilitiesResponse {
    capabilities: Vec<String>,
    health_check: bool
}

pub async fn get_capabilities() -> Result<impl IntoResponse, StatusCode> {
    let capabilities = vec![
        "camera.capture".to_string(),
        "system.status".to_string()
    ];

    Ok((
        StatusCode::OK,
        Json(CapabilitiesResponse { capabilities, health_check: true }),
    ))
}

