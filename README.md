# COR-SAT

COR-SAT generates small CubeSat mission packages for the existing runner.

## Mission generation

```text
request → two independent sources → deterministic evaluation → package
                                       ↓ (only if both fail)
                                      one repair → evaluation
```

`python -m agents.cli "Capture one image."` generates two source-only Ollama
responses concurrently. The evaluator accepts the first source that passes
syntax, safety, fake-SDK execution, and mission-specific checks. If neither
passes, it repairs the highest-scoring failure once. `manifest.json` is derived
by the controller and validated with the existing runner schema.

The first version explicitly supports these benchmark requests:

- `Capture one image.`
- `Capture five images at two-second intervals.`
- The twenty-image optical-flow request in `tests/test_acceptance_missions.py`.

Generated packages are written to `agents/candidates/<candidate-name>/` and can
be launched with `python -m runner.cli start <candidate-name> --candidate`.

## Tests

```text
python -m unittest discover -s tests -v
```

The unit suite mocks model calls and does not require Ollama or camera hardware.
