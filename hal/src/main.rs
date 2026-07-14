use axum::{
    routing::{get, post},
    Router,
};

mod health;
mod camera;
mod system;

#[tokio::main]
async fn main() {
    let app = Router::new()
	.route("/v1/system/health", get(health::check_health))
        .route("/v1/system/status", get(system::get_status))
        .route("/v1/camera/capture", post(camera::capture_image));

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000")
        .await
        .unwrap();
    
    println!("HAL service running on port 3000...");
    axum::serve(listener, app).await.unwrap();
}
