import requests
from sat_sdk.system import SystemModule
from sat_sdk.camera import CameraModule
from sat_sdk.models import HealthResponse
from sat_sdk.capabilites import CapabilitiesModule
from sat_sdk.exceptions import SatConnectionError, SatAPIError

class SatClient:
    def __init__(self, base_url: str = "http://localhost:3000", timeout: float = 5.0):
        
        self.base_url = base_url.rstrip("/")
        
        self.timeout = max(timeout, 6.0)
        
        self.system = SystemModule(self.base_url, self.timeout)
        self.camera = CameraModule(self.base_url, self.timeout)
        self.capabilities = CapabilitiesModule(self.base_url, self.timeout)

    def health(self) -> HealthResponse:
        """Probes core system reachability and subsystem mapping state."""
        try:
            url = f"{self.base_url}/v1/system/health"
            response = requests.get(url, timeout=self.timeout)
        except requests.RequestException as e:
            raise SatConnectionError(f"Failed to communicate with health probe: {e}")

        if response.status_code not in (200, 503):
            raise SatAPIError(response.status_code, response.text)

        data = response.json()
        return HealthResponse(
            status=data["status"],
            camera_available=data["camera_available"]
        )
