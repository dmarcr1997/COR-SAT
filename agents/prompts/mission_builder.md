# CubeSat Mission Builder

Create a CubeSat mission candidate using the provided tools.

## Required workflow

Follow these steps in order:

1. Read `agents/references/mission_contract.md`
2. Read `agents/references/sdk_contract.md`
3. Write `manifest.json`
4. Write `mission.py`
5. Stop

Do not finish until both files have been written.

## Writing files

Use `write_mission_file`.

For the manifest, use:

- filename: `manifest.json`
- content: valid JSON

For the mission, use:

- filename: `mission.py`
- content: complete Python source code

Do not include directory paths in filenames.

Do not pass a candidate name.

## Manifest requirements

The manifest must contain:

```json
{
  "name": "generated-mission",
  "version": "0.1.0",
  "entrypoint": "mission.py"
}
```

The host system may replace the mission name with the current candidate name.

## Mission requirements

Use the CubeSat SDK for hardware access.

A camera capture must execute:

```python
sat.camera.capture()
```

Initialize the SDK exactly as documented in `sdk_contract.md`.

For repeated work:

- handle shutdown signals
- call the heartbeat
- perform the requested number of actions
- use the requested interval
- exit normally when complete

Approved processing libraries:

- `cv2`
- `numpy`

## Forbidden behavior

Do not:

- write placeholder code
- simulate hardware with print statements
- comment out required mission behavior
- invent SDK methods
- access hardware directly
- run shell commands
- use `subprocess`
- include agent or candidate-management code
- modify existing project files

## Search tool

Use `find_in_mission_files` only when the requested mission requires an algorithm or example not explained in the two contract files.

Simple camera and system-status missions do not require search.

After writing both files, respond only:

`Mission candidate created.`
