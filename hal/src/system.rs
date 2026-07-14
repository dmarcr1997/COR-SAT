use axum::{Json, response::IntoResponse};
use serde::Serialize;
use sysinfo::{CpuRefreshKind, Disks, MemoryRefreshKind, RefreshKind, System};

#[derive(Serialize)]
pub struct SystemStatus {
    pub cpu_temp: String,
    pub ram_use: String,
    pub disk_use: String,
    pub uptime: String
}

pub async fn get_status() -> impl IntoResponse {
	let mut sys = System::new_with_specifics(
		RefreshKind::new()
			.with_memory(MemoryRefreshKind::everything())
			.with_cpu(CpuRefreshKind::new())
	);
	sys.refresh_all();

	let cpu_temp = std::fs::read_to_string("/sys/class/thermal/thermal_zone0/temp")
		.map(|val| {
			let millidegrees = val.trim().parse::<f32>().unwrap_or(0.0);
			format!("{:.2}°C", millidegrees / 1000.0)
		})
		.unwrap_or_else(|_| "N/".to_string());
	let total_seconds = sysinfo::System::uptime();

	let days = total_seconds / 86400;
	let hours = (total_seconds % 86400) / 3600;
	let minutes = (total_seconds % 3600) / 60;
	let seconds = total_seconds % 60;

	let uptime = if days > 0 {
		format!("{}d {}h {}m {}s", days, hours, minutes, seconds)
	} else {
		format!("{}h {}m {}s", hours, minutes, seconds)
	};
	
	let used_ram = sys.used_memory() as f64 / (1024.0 * 1024.0 * 1024.0);
	let total_ram = sys.total_memory() as f64 / (1024.0 * 1024.0 * 1024.0);
	let ram_percent = (used_ram / total_ram) * 100.0;
	let ram_use = format!("{:.2} GB / {:.2} GB ({:.1}%)", used_ram, total_ram, ram_percent);

	// 3. Format Disk space usage for Root directory
	let mut disk_use = "N/A".to_string();
	
	// Create and refresh a dedicated Disks list for version 0.30+
	let disks = Disks::new_with_refreshed_list();
	if let Some(root_disk) = disks.iter().find(|d| d.mount_point() == std::path::Path::new("/")) {
		let total_disk = root_disk.total_space() as f64 / (1024.0 * 1024.0 * 1024.0);
		let available_disk = root_disk.available_space() as f64 / (1024.0 * 1024.0 * 1024.0);
		let used_disk = total_disk - available_disk;
		let disk_percent = (used_disk / total_disk) * 100.0;
		disk_use = format!("{:.2} GB / {:.2} GB ({:.1}%)", used_disk, total_disk, disk_percent);
	}

	Json(SystemStatus { cpu_temp, ram_use, disk_use, uptime })
}


