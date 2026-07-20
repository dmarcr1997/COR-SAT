import requests
from sat_sdk.models import CapabilitiesResponse
from sat_sdk.exceptions import SatConnectionError, SatAPIError

class CapabilitiesModule:
    def __init__(self, base_url: str, timeout: float):
        self._url = f"{base_url}/v1/system/capabilities"
        self._timeout = timeout

    def get_capabilities(self) -> CapabilitiesResponse:
        """Fetches the current Raspberry Pi platform telemetry."""
        try:
            response = requests.get(self._url, timeout=self._timeout)
        except requests.RequestException as e:
            raise SatConnectionError(f"Failed to connect to HAL system endpoint: {e}")

        if response.status_code != 200:
            raise SatAPIError(response.status_code, response.text)

        data = response.json()
        return CapabilitiesResponse(
            capabilities=data["capabilities"],
            health_check=data["health_check"]
        )
