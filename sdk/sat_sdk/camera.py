import requests
from sat_sdk.models import CaptureResponse
from sat_sdk.exceptions import SatConnectionError, SatAPIError

class CameraModule:
    def __init__(self, base_url: str, timeout: float):
        self._url = f"{base_url}/v1/camera/capture"
        self._timeout = timeout

    def capture(self) -> CaptureResponse:
        """Triggers a physical libcamera sensor frame transaction."""
        try:
            response = requests.post(self._url, timeout=self._timeout)
        except requests.RequestException as e:
            raise SatConnectionError(f"Failed to connect to HAL camera endpoint: {e}")

        if response.status_code != 200:
            raise SatAPIError(response.status_code, response.text)

        data = response.json()
        return CaptureResponse(
            message=data["message"],
            filename=data["filename"]
        )
