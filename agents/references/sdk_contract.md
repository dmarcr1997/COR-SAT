# CubeSat Python SDK Contract

Generated mission applications must use the CubeSat Python SDK for all hardware and system access.

Do not access the Raspberry Pi camera, GPIO, operating system hardware interfaces, or HAL HTTP endpoints directly.

## Creating the client

```python
from sat_sdk import SatClient

sat = SatClient()
```

Create one client and reuse it for the entire mission.

## Camera capture

```python
capture = sat.camera.capture()
```

The camera capture operation takes one image using the CubeSat camera.

The returned value is a dictionary containing capture information.

Expected shape:

```python
{
    "path": "/absolute/path/to/captured-image.jpg"
}
```

Access the image path with:

```python
image_path = capture["path"]
```

Generated missions may use the returned image path with approved local processing libraries such as OpenCV.

Do not assume that `camera.capture()` returns raw image bytes, a NumPy array, or an OpenCV image.

Load the image from the returned path when image processing is required.

Example:

```python
import cv2

capture = sat.camera.capture()
image = cv2.imread(capture["path"])
```

## System status

```python
status = sat.system.status()
```

This returns the current CubeSat system status.

Generated missions may print, inspect, or store the returned status.

Do not invent additional system methods.

## Heartbeat

```python
sat.heartbeat()
```

The heartbeat tells the runtime that the mission is still making progress.

Call it during repeated or long-running mission work.

Example:

```python
for capture_number in range(5):
    sat.heartbeat()
    sat.camera.capture()
```

A heartbeat does not replace system status.

These are different operations:

```python
sat.heartbeat()
sat.system.status()
```

## Available SDK methods

Only the following SDK calls are currently approved:

```python
sat.camera.capture()
sat.system.status()
sat.heartbeat()
```

Do not invent methods such as:

```python
sat.camera.stream()
sat.camera.optical_flow()
sat.thermal.capture()
sat.storage.upload()
sat.system.shutdown()
```

## Hardware access rule

Use the SDK for hardware access.

Use approved Python libraries for local computation.

Valid pattern:

```python
capture = sat.camera.capture()
image = cv2.imread(capture["path"])
```

Invalid pattern:

```python
from picamera2 import Picamera2
camera = Picamera2()
```

## Failure handling

SDK operations may fail.

Generated missions should allow failures to raise normally unless the mission request specifically requires retry behavior.

Do not silently fabricate results when an SDK operation fails.
