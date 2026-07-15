from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


SUPPORTED_SCHEMA_VERSION = 1

ALLOWED_PERMISSIONS = {
    "camera.capture",
    "system.status",
}


@dataclass(frozen=True)
class ValidationIssue:
    message: str
    location: str | None = None

    def format(self) -> str:
        if self.location:
            return f"{self.location}: {self.message}"

        return self.message


@dataclass(frozen=True)
class ValidatedMission:
    directory: Path
    manifest_path: Path
    entrypoint_path: Path
    manifest: dict[str, Any]


class MissionValidationError(Exception):
    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        super().__init__("Mission validation failed")


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MissionValidationError(
            [ValidationIssue(f"File not found: {path}")]
        ) from exc
    except OSError as exc:
        raise MissionValidationError(
            [ValidationIssue(f"Could not read {path}: {exc}")]
        ) from exc

    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise MissionValidationError(
            [
                ValidationIssue(
                    message=exc.msg,
                    location=f"{path}:{exc.lineno}:{exc.colno}",
                )
            ]
        ) from exc

    if not isinstance(value, dict):
        raise MissionValidationError(
            [ValidationIssue("Manifest root must be a JSON object")]
        )

    return value


def load_schema() -> dict[str, Any]:
    schema_path = (
        Path(__file__).parent
        / "schemas"
        / "mission-manifest.schema.json"
    )

    schema = load_json_file(schema_path)

    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise RuntimeError(f"Internal manifest schema is invalid: {exc}") from exc

    return schema


def format_json_path(path_parts: list[Any]) -> str:
    if not path_parts:
        return "$"

    result = "$"

    for part in path_parts:
        if isinstance(part, int):
            result += f"[{part}]"
        else:
            result += f".{part}"

    return result


def validate_against_schema(
    manifest: dict[str, Any],
    schema: dict[str, Any],
) -> list[ValidationIssue]:
    validator = Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(manifest),
        key=lambda error: list(error.absolute_path),
    )

    issues: list[ValidationIssue] = []

    for error in errors:
        location = format_json_path(list(error.absolute_path))

        issues.append(
            ValidationIssue(
                message=error.message,
                location=location,
            )
        )

    return issues


def validate_entrypoint(
    mission_directory: Path,
    entrypoint: str,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []

    entrypoint_path = mission_directory / entrypoint

    try:
        resolved_mission_directory = mission_directory.resolve(strict=True)
    except FileNotFoundError:
        return [
            ValidationIssue(
                f"Mission directory does not exist: {mission_directory}"
            )
        ]

    try:
        resolved_entrypoint = entrypoint_path.resolve(strict=True)
    except FileNotFoundError:
        return [
            ValidationIssue(
                f"Entrypoint does not exist: {entrypoint}",
                location="$.entrypoint",
            )
        ]

    if resolved_entrypoint.parent != resolved_mission_directory:
        issues.append(
            ValidationIssue(
                "Entrypoint must be directly inside the mission directory",
                location="$.entrypoint",
            )
        )

    if resolved_entrypoint.suffix != ".py":
        issues.append(
            ValidationIssue(
                "Entrypoint must be a Python file",
                location="$.entrypoint",
            )
        )

    if resolved_entrypoint.is_symlink():
        issues.append(
            ValidationIssue(
                "Entrypoint may not be a symbolic link",
                location="$.entrypoint",
            )
        )

    if not resolved_entrypoint.is_file():
        issues.append(
            ValidationIssue(
                "Entrypoint must be a regular file",
                location="$.entrypoint",
            )
        )

    return issues


def validate_permissions(
    manifest: dict[str, Any],
) -> list[ValidationIssue]:
    permissions = manifest.get("permissions")

    if not isinstance(permissions, list):
        return []

    issues: list[ValidationIssue] = []

    for index, permission in enumerate(permissions):
        if isinstance(permission, str) and permission not in ALLOWED_PERMISSIONS:
            issues.append(
                ValidationIssue(
                    f"Unknown permission: {permission}",
                    location=f"$.permissions[{index}]",
                )
            )

    return issues


def validate_mission(mission_directory: Path) -> ValidatedMission:
    mission_directory = mission_directory.resolve()
    manifest_path = mission_directory / "manifest.json"

    if not mission_directory.exists():
        raise MissionValidationError(
            [
                ValidationIssue(
                    f"Mission directory does not exist: {mission_directory}"
                )
            ]
        )

    if not mission_directory.is_dir():
        raise MissionValidationError(
            [
                ValidationIssue(
                    f"Mission path is not a directory: {mission_directory}"
                )
            ]
        )

    manifest = load_json_file(manifest_path)
    schema = load_schema()

    issues: list[ValidationIssue] = []

    issues.extend(validate_against_schema(manifest, schema))

    # Only perform semantic checks when the relevant values exist
    # and have the expected basic type.
    entrypoint = manifest.get("entrypoint")

    if isinstance(entrypoint, str):
        issues.extend(
            validate_entrypoint(
                mission_directory=mission_directory,
                entrypoint=entrypoint,
            )
        )

    issues.extend(validate_permissions(manifest))

    if manifest.get("schema_version") not in {
        None,
        SUPPORTED_SCHEMA_VERSION,
    }:
        issues.append(
            ValidationIssue(
                (
                    "Unsupported schema version: "
                    f"{manifest.get('schema_version')}"
                ),
                location="$.schema_version",
            )
        )

    if issues:
        raise MissionValidationError(issues)

    assert isinstance(entrypoint, str)

    return ValidatedMission(
        directory=mission_directory,
        manifest_path=manifest_path,
        entrypoint_path=(mission_directory / entrypoint).resolve(),
        manifest=manifest,
    )


def print_success(result: ValidatedMission) -> None:
    permissions = result.manifest["permissions"]

    permission_text = (
        ", ".join(permissions)
        if permissions
        else "none"
    )

    print("✓ Manifest valid")
    print(f"✓ Entrypoint found: {result.entrypoint_path.name}")
    print(f"✓ Permissions valid: {permission_text}")
    print(
        "✓ Mission ready: "
        f"{result.manifest['name']} "
        f"v{result.manifest['version']}"
    )


def print_failure(exc: MissionValidationError) -> None:
    print("✗ Mission validation failed", file=sys.stderr)

    for issue in exc.issues:
        print(f"  - {issue.format()}", file=sys.stderr)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate a satellite mission package."
    )

    parser.add_argument(
        "mission_directory",
        type=Path,
        help="Path to the mission directory",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        result = validate_mission(args.mission_directory)
    except MissionValidationError as exc:
        print_failure(exc)
        return 1

    print_success(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
