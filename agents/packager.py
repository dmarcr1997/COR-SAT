from __future__ import annotations

import ast
import json
from pathlib import Path

from agents.requirements import MissionRequirements
from runner.validator import MissionValidationError, validate_mission


CANDIDATES_ROOT = Path(__file__).resolve().parent / "candidates"


def build_manifest(requirements: MissionRequirements) -> dict[str, object]:
    permissions = ["camera.capture"]
    if requirements.heartbeat_each_capture:
        permissions.append("system.status")
    return {
        "schema_version": 1,
        "name": "generated-mission",
        "version": "0.1.0",
        "entrypoint": "mission.py",
        "permissions": permissions,
        "configuration": {
            "capture_interval_seconds": requirements.interval_seconds,
            "request_timeout_seconds": 30,
            "maximum_captures": requirements.capture_count,
        },
    }


def create_mission_package(
    candidate_name: str,
    source: str,
    requirements: MissionRequirements,
    *,
    candidates_root: Path = CANDIDATES_ROOT,
) -> Path:
    """Write and validate one runner-compatible mission package."""
    candidate_directory = candidate_directory_for(candidate_name, candidates_root)
    if candidate_directory.exists():
        raise RuntimeError(f"Candidate already exists: {candidate_directory}")

    ast.parse(source, filename="mission.py")
    candidate_directory.mkdir(parents=True)
    candidate_directory.joinpath("mission.py").write_text(source.rstrip() + "\n", encoding="utf-8")
    candidate_directory.joinpath("manifest.json").write_text(
        json.dumps(build_manifest(requirements), indent=2) + "\n",
        encoding="utf-8",
    )
    try:
        validate_mission(candidate_directory)
    except MissionValidationError as exc:
        raise RuntimeError(f"Generated package is invalid: {format_issues(exc)}") from exc
    return candidate_directory


def candidate_directory_for(candidate_name: str, candidates_root: Path) -> Path:
    if not candidate_name or Path(candidate_name).name != candidate_name:
        raise ValueError("Candidate name must be a single directory name")
    return candidates_root / candidate_name


def format_issues(error: MissionValidationError) -> str:
    return "; ".join(issue.format() for issue in error.issues)
