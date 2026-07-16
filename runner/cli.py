from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from runner.validator import (
    MissionValidationError,
    validate_mission,
)


# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MISSIONS_ROOT = PROJECT_ROOT / "missions"
RUNTIME_ROOT = PROJECT_ROOT / "runtime"


def mission_directory(mission_name: str) -> Path:
    return MISSIONS_ROOT / mission_name


def runtime_directory(mission_name: str) -> Path:
    return RUNTIME_ROOT / mission_name


def state_path(mission_name: str) -> Path:
    return runtime_directory(mission_name) / "state.json"


def log_path(mission_name: str) -> Path:
    return runtime_directory(mission_name) / "mission.log"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# Runtime state
# ============================================================

def read_state(mission_name: str) -> dict[str, Any] | None:
    path = state_path(mission_name)

    if not path.exists():
        return None

    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(state, dict):
        return None

    return state


def write_state(
    mission_name: str,
    state: dict[str, Any],
) -> None:
    directory = runtime_directory(mission_name)
    directory.mkdir(parents=True, exist_ok=True)

    path = state_path(mission_name)
    temporary_path = path.with_suffix(".json.tmp")

    temporary_path.write_text(
        json.dumps(state, indent=2),
        encoding="utf-8",
    )

    temporary_path.replace(path)


def update_state(
    mission_name: str,
    current_state: dict[str, Any],
    **changes: Any,
) -> dict[str, Any]:
    new_state = {
        **current_state,
        **changes,
    }

    write_state(mission_name, new_state)
    return new_state


# ============================================================
# Process helpers
# ============================================================

def process_is_running(pid: int) -> bool:
    if pid <= 0:
        return False

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True

    return True


def is_mission_process_group(pid: int) -> bool:
    try:
        return os.getpgid(pid) == pid
    except (ProcessLookupError, PermissionError):
        return False


def active_pid_from_state(mission_name: str) -> int | None:
    state = read_state(mission_name)

    if state is None:
        return None

    pid = state.get("pid")

    if not isinstance(pid, int):
        return None

    if process_is_running(pid):
        return pid

    update_state(
        mission_name,
        state,
        state="FAILED",
        stopped_at=utc_now(),
        reason="stale_pid",
    )

    return None


def wait_for_process_exit(
    pid: int,
    timeout_seconds: float,
) -> bool:
    deadline = time.monotonic() + timeout_seconds

    while time.monotonic() < deadline:
        if not process_is_running(pid):
            return True

        time.sleep(0.1)

    return not process_is_running(pid)


# ============================================================
# Start mission
# ============================================================

def start_mission(mission_name: str) -> int:
    directory = mission_directory(mission_name)

    try:
        validated = validate_mission(directory)
    except MissionValidationError as exc:
        print("Mission validation failed:", file=sys.stderr)

        for issue in exc.issues:
            print(f"  - {issue.format()}", file=sys.stderr)

        return 1

    existing_pid = active_pid_from_state(mission_name)

    if existing_pid is not None:
        print(
            f"Mission {mission_name} is already running "
            f"with PID {existing_pid}"
        )
        return 1

    run_directory = runtime_directory(mission_name)
    run_directory.mkdir(parents=True, exist_ok=True)

    starting_state = {
        "mission": mission_name,
        "version": validated.manifest["version"],
        "state": "STARTING",
        "pid": None,
        "started_at": utc_now(),
    }

    write_state(mission_name, starting_state)

    try:
        log_file = log_path(mission_name).open(
            "a",
            encoding="utf-8",
        )
    except OSError as exc:
        update_state(
            mission_name,
            starting_state,
            state="FAILED",
            stopped_at=utc_now(),
            reason=f"could_not_open_log: {exc}",
        )

        print(
            f"Could not open mission log: {exc}",
            file=sys.stderr,
        )
        return 1

    try:
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(validated.entrypoint_path),
            ],
            cwd=validated.directory,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except OSError as exc:
        update_state(
            mission_name,
            starting_state,
            state="FAILED",
            stopped_at=utc_now(),
            reason=f"launch_failed: {exc}",
        )

        print(
            f"Failed to start mission: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        log_file.close()

    update_state(
        mission_name,
        starting_state,
        state="RUNNING",
        pid=process.pid,
    )

    print(
        f"Started {mission_name} "
        f"v{validated.manifest['version']} "
        f"with PID {process.pid}"
    )

    return 0


# ============================================================
# Mission status
# ============================================================

def status_mission(mission_name: str) -> int:
    state = read_state(mission_name)

    if state is None:
        print(f"Mission {mission_name} has no runtime state")
        return 1

    pid = state.get("pid")
    stored_status = state.get("state", "UNKNOWN")

    running = (
        isinstance(pid, int)
        and process_is_running(pid)
    )

    if stored_status == "RUNNING" and not running:
        state = update_state(
            mission_name,
            state,
            state="FAILED",
            stopped_at=utc_now(),
            reason="process_not_running",
        )

    print(f"Mission: {state.get('mission')}")
    print(f"Version: {state.get('version')}")
    print(f"State: {state.get('state')}")
    print(f"PID: {state.get('pid')}")
    print(f"Started: {state.get('started_at')}")

    if state.get("stopped_at"):
        print(f"Stopped: {state.get('stopped_at')}")

    if state.get("reason"):
        print(f"Reason: {state.get('reason')}")

    return 0


# ============================================================
# Mission logs
# ============================================================

def logs_mission(
    mission_name: str,
    lines: int = 50,
) -> int:
    path = log_path(mission_name)

    if not path.exists():
        print(f"No logs found for {mission_name}")
        return 1

    try:
        log_lines = path.read_text(
            encoding="utf-8",
            errors="replace",
        ).splitlines()
    except OSError as exc:
        print(
            f"Could not read logs: {exc}",
            file=sys.stderr,
        )
        return 1

    for line in log_lines[-lines:]:
        print(line)

    return 0


# ============================================================
# Stop mission
# ============================================================

def stop_mission(
    mission_name: str,
    timeout_seconds: float = 5.0,
) -> int:
    state = read_state(mission_name)

    if state is None:
        print(f"No runtime state found for {mission_name}")
        return 1

    pid = state.get("pid")

    if not isinstance(pid, int):
        print(f"Mission {mission_name} has no valid PID")
        return 1

    if not process_is_running(pid):
        update_state(
            mission_name,
            state,
            state="STOPPED",
            stopped_at=utc_now(),
            reason="process_already_stopped",
        )

        print(f"Mission {mission_name} was not running")
        return 0

    if not is_mission_process_group(pid):
        print(
            f"PID {pid} is not the expected mission process group",
            file=sys.stderr,
        )
        return 1

    update_state(
        mission_name,
        state,
        state="STOPPING",
    )

    try:
        os.killpg(pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    except PermissionError as exc:
        update_state(
            mission_name,
            state,
            state="FAILED",
            stopped_at=utc_now(),
            reason=f"stop_permission_error: {exc}",
        )

        print(
            f"Could not stop mission: {exc}",
            file=sys.stderr,
        )
        return 1

    stopped = wait_for_process_exit(
        pid,
        timeout_seconds,
    )

    if not stopped:
        print(
            f"Mission did not stop within "
            f"{timeout_seconds} seconds. "
            "Sending SIGKILL."
        )

        try:
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except PermissionError as exc:
            update_state(
                mission_name,
                state,
                state="FAILED",
                stopped_at=utc_now(),
                reason=f"kill_permission_error: {exc}",
            )

            print(
                f"Could not force-stop mission: {exc}",
                file=sys.stderr,
            )
            return 1

        stopped = wait_for_process_exit(
            pid,
            timeout_seconds=2.0,
        )

    if not stopped:
        update_state(
            mission_name,
            state,
            state="FAILED",
            stopped_at=utc_now(),
            reason="failed_to_terminate",
        )

        print(
            f"Mission {mission_name} could not be terminated",
            file=sys.stderr,
        )
        return 1

    update_state(
        mission_name,
        state,
        state="STOPPED",
        stopped_at=utc_now(),
        reason="requested_stop",
    )

    print(f"Stopped mission {mission_name}")
    return 0


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control satellite mission applications."
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    start_parser = subparsers.add_parser(
        "start",
        help="Start a mission",
    )
    start_parser.add_argument("mission_name")

    status_parser = subparsers.add_parser(
        "status",
        help="Show mission status",
    )
    status_parser.add_argument("mission_name")

    logs_parser = subparsers.add_parser(
        "logs",
        help="Show mission logs",
    )
    logs_parser.add_argument("mission_name")
    logs_parser.add_argument(
        "--lines",
        type=int,
        default=50,
    )

    stop_parser = subparsers.add_parser(
        "stop",
        help="Stop a mission",
    )
    stop_parser.add_argument("mission_name")
    stop_parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    match args.command:
        case "start":
            return start_mission(args.mission_name)

        case "status":
            return status_mission(args.mission_name)

        case "logs":
            return logs_mission(
                args.mission_name,
                lines=args.lines,
            )

        case "stop":
            return stop_mission(
                args.mission_name,
                timeout_seconds=args.timeout,
            )

        case _:
            parser.error(
                f"Unsupported command: {args.command}"
            )
            return 2


if __name__ == "__main__":
    raise SystemExit(main())
