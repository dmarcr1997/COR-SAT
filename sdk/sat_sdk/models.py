from dataclasses import dataclass

@dataclass(frozen=True)
class HealthResponse:
    status: str
    camera_available: bool

@dataclass(frozen=True)
class SystemStatusResponse:
    cpu_temp: str
    ram_use: str
    disk_use: str
    uptime: str

@dataclass(frozen=True)
class CaptureResponse:
    message: str
    filename: str
