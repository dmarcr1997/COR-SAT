# Mission Package Contract

A generated mission package contains `mission.py` and a controller-created
`manifest.json`. The generator only returns Python source; it never reads or
writes project files through model calls.

The controller derives the manifest from a typed supported mission request and
validates it with `runner/schemas/mission-manifest.schema.json`. A package is
stored under `agents/candidates/<candidate-name>/` and can be run with:

```text
python -m runner.cli start <candidate-name> --candidate
```

Mission code must access hardware through `sat_sdk`, store created files under
`outputs/`, and use `capture.filename` as the image path. The evaluator rejects
unsafe imports and operations before executing source with its fake SDK.
