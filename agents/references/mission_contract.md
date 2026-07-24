# CubeSat Mission Package Contract

A generated mission candidate contains exactly two required files:

```text
candidate-name/
├── manifest.json
└── mission.py
```

The model must write both files using the provided file tools.

Do not only print or describe the files.

Do not create additional files unless the mission request explicitly requires generated output data during execution.

## Candidate location

Generated files must be written inside:

```text
candidates/<candidate-name>/
```

The model must never modify:

```text
missions/
runner/
sdk/
hal/
agents/
```

Existing missions and reference files are read-only.

## Manifest file

The manifest filename must be:

```text
manifest.json
```

Minimum valid manifest:

```json
{
  "name": "generated-mission",
  "version": "0.1.0",
  "entrypoint": "mission.py"
}
```

Requirements:

- `name` must be a non-empty string.
- `version` must be a non-empty string.
- `entrypoint` must be exactly `mission.py`.
- The JSON must parse successfully.
- Do not include comments inside JSON.
- Do not wrap the JSON in Markdown fences when writing the file.

Use a short lowercase mission name with hyphens.

Example:

```json
{
  "name": "optical-flow-capture",
  "version": "0.1.0",
  "entrypoint": "mission.py"
}
```

## Mission file

The mission filename must be:

```text
mission.py
```

The file must contain executable Python code.

Do not include Markdown fences.

Do not include explanations before or after the Python code.

## Allowed hardware access

All hardware access must use the CubeSat Python SDK.

Read:

```text
agents/references/sdk_contract.md
```

before writing mission code.

## Approved imports

Approved standard-library modules include:

```python
import json
import os
import signal
import time
from pathlib import Path
```

Approved local processing libraries include:

```python
import cv2
import numpy as np
```

Other imports should only be used when clearly required and known to be installed.

## Forbidden behavior

Generated mission code must not:

- Use `subprocess`
- Execute shell commands
- Use `os.system`
- Open network sockets
- Make direct HTTP requests
- Modify runner code
- Modify SDK code
- Modify HAL code
- Access GPIO directly
- Access the camera directly
- Delete files outside mission-created output
- Invent SDK methods
- Pretend unsupported processing was completed

## Shutdown handling

Repeated or long-running missions must handle `SIGTERM`.

Recommended pattern:

```python
import signal


shutdown_requested = False


def handle_shutdown(signum, frame):
    global shutdown_requested
    shutdown_requested = True


signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
```

Loops should check:

```python
if shutdown_requested:
    break
```

## Heartbeat behavior

Call:

```python
sat.heartbeat()
```

during repeated mission work.

Example:

```python
for capture_number in range(20):
    if shutdown_requested:
        break

    sat.heartbeat()
    sat.camera.capture()
```

## Timing behavior

When capturing at a fixed interval, avoid sleeping after the final capture.

Example:

```python
for capture_number in range(5):
    sat.heartbeat()
    sat.camera.capture()

    if capture_number < 4:
        time.sleep(2)
```

For a one-image-per-second request, use an interval of approximately one second between captures.

## Local image processing

Generated missions may process captured files with approved local libraries.

Example:

```python
capture = sat.camera.capture()
image = cv2.imread(capture["path"])
```

Do not claim that images were processed unless the code performs the requested processing.

## Mission completion

Finite missions should exit normally after completing their requested work.

Do not keep a completed finite mission alive indefinitely.

A successful finite mission should end with process exit code `0`.

## Required tool workflow

Before writing files:

1. Read the SDK contract.
2. Read this mission contract.
3. Search for relevant examples when useful.
4. Write `manifest.json`.
5. Write `mission.py`.
6. Stop after both files are written.

Do not return the complete mission only as chat text.

The files are the output.
