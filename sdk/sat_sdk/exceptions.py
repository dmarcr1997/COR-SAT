class SatSDKError(Exception):
    """Base exception for all Satellites SDK issues."""
    pass

class SatConnectionError(SatSDKError):
    """Raised when the HAL service cannot be reached or times out."""
    pass

class SatAPIError(SatSDKError):
    """Raised when the HAL service returns a non-200 failure status code."""
    def __init__(self, status_code: int, message: str):
        super().__init__(f"API Error [{status_code}]: {message}")
        self.status_code = status_code
