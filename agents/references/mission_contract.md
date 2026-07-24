# CubeSat Mission Package Contract

A generated mission candidate contains exactly two required files:

```text
candidate-name/
├── manifest.json
└── mission.py
```

The model must write both files using the provided tools.

The files are the output.

Do not only print or describe them.

## Candidate boundaries

Generated files are written inside the current candidate directory.

The model must never modify:

```text
missions/
runner/
sdk/
hal/
agents/
runtime/
```

Existing missions, contracts, and examples are read-only.

## manifest.json

The filename must be exactly:

```text
manifest.json
```

Minimum valid content:

```json
{
  "name": "generated-mission",
  "version": "0.1.0",
  "entrypoint": "mission.py"
}
```

Requirements:

- `name` must be a non-empty string
- `version` must be a non-empty string
- `entrypoint` must be exactly `mission.py`
- content must be valid JSON
- JSON must not contain comments
- content must not contain Markdown fences
- the filename must not contain a directory path

Do not replace `entrypoint` with:

```text
mission
file
script
description
```

## mission.py

The filename must be exactly:

```text
mission.py
```

It must contain complete executable Python code.

Do not include:

- Markdown fences
- explanations
- placeholder implementations
- TODO comments
- agent code
- candidate-management code
- validator code

## SDK initialization

Every mission that uses CubeSat hardware or system services must create the client:

```python
from sat_sdk import SatClient

sat = SatClient()
```

Create one client and reuse it.

Do not call `sat` before creating it.

## Hardware access

All hardware access must use the CubeSat Python SDK.

Read:

```text
agents/references/sdk_contract.md
```

before writing mission code.

A camera mission must call:

```python
sat.camera.capture()
```

Do not replace hardware calls with:

- print statements
- comments
- sleeps
- fake return values
- OpenCV camera access

## Approved imports

Approved standard-library imports include:

```python
import json
import os
import signal
import time
from pathlib import Path
```

Approved local processing imports include:

```python
import cv2
import numpy as np
```

Use OpenCV and NumPy only for processing data already obtained through the SDK.

## Forbidden behavior

Generated mission code must not:

- use `subprocess`
- execute shell commands
- use `os.system`
- open network sockets
- make direct HTTP requests
- modify project source code
- access GPIO directly
- access the camera directly
- use `cv2.VideoCapture`
- use `Picamera2`
- assign to `sat.camera`
- assign to `sat.system`
- invent SDK methods or properties
- delete files outside mission-created output
- claim processing occurred when it did not

Never use or invent:

```python
sat.shutdown
sat.camera.framerate
sat.camera.resolution
sat.camera.release()
sat.camera.stream()
sat.system.shutdown()
```

## Shutdown handling

Repeated or long-running missions must handle `SIGTERM`.

Use this pattern:

```python
import signal


shutdown_requested = False


def handle_shutdown(signum, frame):
    global shutdown_requested
    shutdown_requested = True


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
```

Repeated work must check:

```python
if shutdown_requested:
    break
```

Do not invent a shutdown property on the SDK.

Invalid:

```python
if sat.shutdown:
    break
```

## Heartbeat

Call:

```python
sat.heartbeat()
```

during repeated or long-running mission work.

Example:

```python
for capture_number in range(5):
    if shutdown_requested:
        break

    sat.heartbeat()
    sat.camera.capture()
```

Heartbeat and system status are different operations.

Do not replace the heartbeat with:

```python
sat.system.status()
```

## Timing

For fixed-interval work, do not sleep after the final action.

Example:

```python
for capture_number in range(5):
    if shutdown_requested:
        break

    sat.heartbeat()
    sat.camera.capture()

    if capture_number < 4:
        time.sleep(2)
```

A request for five captures must perform no more than five capture calls.

A finite mission must not use an infinite loop.

## Local image processing

Use the SDK to capture an image:

```python
capture = sat.camera.capture()
```

Use the returned path for local processing:

```python
image = cv2.imread(capture["path"])
```

Check that loading succeeded:

```python
if image is None:
    raise RuntimeError(
        f"Could not load image: {capture['path']}"
    )
```

OpenCV may process captured files.

OpenCV must not open or configure the CubeSat camera.

## Mission completion

Finite missions must exit normally after completing the requested work.

Do not keep a completed mission alive indefinitely.

A successful finite mission should end with exit code `0`.

## Required workflow

Before writing files:

1. Read this contract
2. Read `agents/references/sdk_contract.md`
3. Write `manifest.json`
4. Write `mission.py`
5. Stop

Search for an example only when a required algorithm is not explained in the contracts.
