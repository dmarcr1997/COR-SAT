import requests
from sat_sdk.models import SystemStatusResponse
from sat_sdk.exceptions import SatConnectionError, SatAPIError

class SystemModule:
    def __init__(self, base_url: str, timeout: float):
        self._url = f"{base_url}/v1/system/status"
        self._timeout = timeout

    def status(self) -> SystemStatusResponse:
        """Fetches the current Raspberry Pi platform telemetry."""
        try:
            response = requests.get(self._url, timeout=self._timeout)
        except requests.RequestException as e:
            raise SatConnectionError(f"Failed to connect to HAL system endpoint: {e}")

        if response.status_code != 200:
            raise SatAPIError(response.status_code, response.text)

        data = response.json()
        return SystemStatusResponse(
            cpu_temp=data["cpu_temp"],
            ram_use=data["ram_use"],
            disk_use=data["disk_use"],
            uptime=data["uptime"]
        )
