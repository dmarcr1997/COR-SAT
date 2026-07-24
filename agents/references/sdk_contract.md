# CubeSat Python SDK Contract

Generated missions must use the CubeSat Python SDK for all hardware and system access.

Do not access the Raspberry Pi camera, GPIO, operating-system hardware interfaces, or HAL HTTP endpoints directly.

## Create the client

Initialize the SDK exactly like this:

```python
from sat_sdk import SatClient

sat = SatClient()
```

Create one client and reuse it.

Do not use `sat` before creating it.

Never assign to:

```python
sat.camera
sat.system
```

These objects are managed by `SatClient`.

## Camera capture

Capture one image with:

```python
capture = sat.camera.capture()
```

The result is a dictionary containing capture metadata.

Expected shape:

```python
{
    "path": "/absolute/path/to/captured-image.jpg"
}
```

Get the captured image path with:

```python
image_path = capture["path"]
```

Do not assume `sat.camera.capture()` returns:

- raw bytes
- a NumPy array
- an OpenCV image
- a camera device

## OpenCV processing

OpenCV may process an image after the SDK captures it.

Valid:

```python
import cv2

capture = sat.camera.capture()
image = cv2.imread(capture["path"])
```

Always check the loaded image:

```python
if image is None:
    raise RuntimeError(
        f"Could not load image: {capture['path']}"
    )
```

OpenCV must not open or configure the physical camera.

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

Do not use:

```python
sat.camera.framerate
sat.camera.resolution
sat.camera.release()
```

These properties and methods do not exist.

## System status

Read system status with:

```python
status = sat.system.status()
```

The result may be printed, inspected, or stored.

Do not invent additional system methods.

## Heartbeat

Signal mission progress with:

```python
sat.heartbeat()
```

Call it during repeated or long-running work.

Example:

```python
for capture_number in range(5):
    sat.heartbeat()
    sat.camera.capture()
```

Heartbeat and system status are different:

```python
sat.heartbeat()
sat.system.status()
```

Do not use system status as a replacement for heartbeat.

## Approved SDK calls

Only these SDK calls are currently approved:

```python
sat.camera.capture()
sat.system.status()
sat.heartbeat()
```

Do not invent:

```python
sat.camera.stream()
sat.camera.configure()
sat.camera.release()
sat.camera.optical_flow()
sat.thermal.capture()
sat.storage.upload()
sat.system.shutdown()
sat.shutdown
```

## Hardware and processing boundary

Use the SDK for hardware access.

Use approved Python libraries for local computation.

Valid flow:

```python
capture = sat.camera.capture()
image = cv2.imread(capture["path"])
processed = cv2.cvtColor(
    image,
    cv2.COLOR_BGR2GRAY,
)
```

Invalid flow:

```python
sat.camera = cv2.VideoCapture(0)
```

The mission must never overwrite SDK interfaces.

## Finite camera example

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
    sat.camera.capture()

    if capture_number < 4:
        time.sleep(2)
```

This example:

- creates the SDK client
- performs five real captures
- calls heartbeat
- handles shutdown
- waits two seconds between captures
- avoids sleeping after the final capture
- exits normally

## Failure behavior

SDK operations may raise errors.

Allow errors to propagate unless the mission request explicitly requires retry behavior.

Do not:

- fabricate results
- silently report success
- replace failed hardware calls with print statements
- create placeholder output
