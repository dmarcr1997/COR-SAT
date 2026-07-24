# CubeSat Python SDK Contract

Generated missions must use the CubeSat Python SDK for all hardware and system access.

Do not access the Raspberry Pi camera, GPIO, operating-system hardware interfaces, or HAL HTTP endpoints directly.

## Client initialization

Create the SDK client exactly once:

```python
from sat_sdk import SatClient

sat = SatClient()
```

Reuse this client for the entire mission.

Never assign to:

```python
sat.camera
sat.system
```

## Response models

SDK methods return typed dataclass objects.

They do not return dictionaries.

Use attribute access such as:

```python
capture.filename
status.cpu_temp
health.camera_available
```

Never use dictionary access such as:

```python
capture["filename"]
capture["path"]
status["cpu_temp"]
```

The SDK response models are:

```python
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


@dataclass(frozen=True)
class CapabilitiesResponse:
    capabilities: list[str]
    health_check: bool
```

These models are documentation only.

Generated mission code must not redefine them.

## Camera capture

Capture one image with:

```python
capture = sat.camera.capture()
```

The return type is:

```python
CaptureResponse
```

Available fields:

```python
capture.message
capture.filename
```

Example:

```python
capture = sat.camera.capture()

print(capture.message)
print(capture.filename)
```

For OpenCV processing:

```python
import cv2

capture = sat.camera.capture()
image = cv2.imread(capture.filename)

if image is None:
    raise RuntimeError(
        f"Could not load image: {capture.filename}"
    )
```

Do not assume camera capture returns:

- a dictionary
- raw image bytes
- a NumPy array
- an OpenCV image

Invalid:

```python
capture["path"]
capture["filename"]
```

Valid:

```python
capture.filename
```

## Heartbeat and health

Call:

```python
health = sat.heartbeat()
```

The return type is:

```python
HealthResponse
```

Available fields:

```python
health.status
health.camera_available
```

Example:

```python
health = sat.heartbeat()

if health.status != "ok":
    raise RuntimeError(
        f"CubeSat health check failed: {health.status}"
    )
```

A mission may ignore the returned value when it only needs to record progress:

```python
sat.heartbeat()
```

## System status

Read system status with:

```python
status = sat.system.status()
```

The return type is:

```python
SystemStatusResponse
```

Available fields:

```python
status.cpu_temp
status.ram_use
status.disk_use
status.uptime
```

Example:

```python
status = sat.system.status()

print(status.cpu_temp)
print(status.ram_use)
print(status.disk_use)
print(status.uptime)
```

## Capabilities

Only use this section if the SDK exposes the corresponding method.

The response type is:

```python
CapabilitiesResponse
```

Available fields:

```python
capabilities.capabilities
capabilities.health_check
```

Do not invent a capabilities method if none is documented by the SDK client.

## Approved SDK methods

Only these SDK calls are currently approved:

```python
sat.camera.capture()
sat.system.status()
sat.heartbeat()
```

Do not invent methods or properties such as:

```python
sat.camera.stream()
sat.camera.configure()
sat.camera.release()
sat.camera.optical_flow()
sat.camera.framerate
sat.camera.resolution
sat.system.shutdown()
sat.shutdown
```

## Hardware and processing boundary

Use the SDK for hardware access.

Use approved Python libraries only for local computation after receiving SDK results.

Valid:

```python
capture = sat.camera.capture()
image = cv2.imread(capture.filename)
```

Invalid:

```python
sat.camera = cv2.VideoCapture(0)
```

Invalid:

```python
camera = cv2.VideoCapture(0)
```

Invalid:

```python
from picamera2 import Picamera2
```

## Finite camera mission example

```python
import signal
import time

from sat_sdk import SatClient


shutdown_requested = False


def handle_shutdown(signum, frame):
    global shutdown_requested
    shutdown_requested = True


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)

sat = SatClient()

for capture_number in range(5):
    if shutdown_requested:
        break

    sat.heartbeat()
    capture = sat.camera.capture()

    print(
        f"Captured image: {capture.filename}"
    )

    if capture_number < 4:
        time.sleep(2)
```

This example:

- creates one SDK client
- performs exactly five captures
- accesses `CaptureResponse` through attributes
- calls heartbeat
- handles shutdown
- waits two seconds between captures
- avoids sleeping after the final capture
- exits normally

## Failure behavior

SDK operations may raise exceptions.

Allow failures to propagate unless the mission request explicitly requires retry behavior.

Do not fabricate results or replace failed hardware operations with placeholders.
