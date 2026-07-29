# COR-SAT

COR-SAT generates small CubeSat mission packages for the existing runner.

## Mission generation

```text
request → two independent sources → deterministic evaluation → package
                                       ↓ (only if both fail)
                                      one repair → evaluation
```

`python -m agents.cli "Capture seven images at three-second intervals."` first
extracts a validated camera-mission requirement object, then generates two
source-only Ollama responses concurrently. The evaluator accepts the first
source that passes syntax, safety, fake-SDK execution, and mission-specific
checks. If neither passes, it repairs the highest-scoring failure once.
`manifest.json` is derived by the controller and validated with the existing
runner schema.

The natural-language extractor currently supports camera capture timing,
heartbeats, shutdown handling, and sparse Lucas-Kanade optical-flow requests.
Communications, IMU, and actuator requirements are rejected until their SDK and
evaluator support are added.

Generated packages are written to `agents/candidates/<candidate-name>/` and can
be launched with `python -m runner.cli start <candidate-name> --candidate`.

## Tests

```text
python -m unittest discover -s tests -v
```

The unit suite mocks model calls and does not require Ollama or camera hardware.
