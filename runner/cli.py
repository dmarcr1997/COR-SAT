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
# Configuration
# ============================================================

MAX_RESTARTS = 1
RESTART_DELAY_SECONDS = 1.0
STOP_TIMEOUT_SECONDS = 5.0
HEARTBEAT_TIMEOUT_SECONDS = 15.0
HEARTBEAT_CHECK_INTERVAL_SECONDS = 1.0


# ============================================================
# Paths
# ============================================================

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MISSIONS_ROOT = PROJECT_ROOT / "missions"
CANDIDATE_ROOT = PROJECT_ROOT / "agents/candidates"
RUNTIME_ROOT = PROJECT_ROOT / "runtime"

start_dir = MISSIONS_ROOT

def mission_directory(mission_name: str) -> Path:
	return start_dir / mission_name


def runtime_directory(mission_name: str) -> Path:
	return RUNTIME_ROOT / mission_name


def state_path(mission_name: str) -> Path:
	return runtime_directory(mission_name) / "state.json"


def log_path(mission_name: str) -> Path:
	return runtime_directory(mission_name) / "mission.log"

def heartbeat_path(mission_name: str) -> Path:
	return runtime_directory(mission_name) / "heartbeat.json"

def utc_now() -> str:
	return datetime.now(timezone.utc).isoformat()


# ============================================================
# Runtime state
# ============================================================

def read_state(
	mission_name: str,
) -> dict[str, Any] | None:
	path = state_path(mission_name)

	if not path.exists():
		return None

	try:
		state = json.loads(
			path.read_text(encoding="utf-8")
		)
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


def is_process_group_leader(pid: int) -> bool:
	try:
		return os.getpgid(pid) == pid
	except (ProcessLookupError, PermissionError):
		return False


def active_pid_from_state(
	mission_name: str,
) -> int | None:
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
		pid=None,
		stopped_at=utc_now(),
		last_exit_reason="stale_pid",
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


def terminate_process(
	process: subprocess.Popen[Any],
	timeout_seconds: float = STOP_TIMEOUT_SECONDS,
) -> int | None:
	if process.poll() is not None:
		return process.returncode

	try:
		os.killpg(
			process.pid,
			signal.SIGTERM,
		)
	except ProcessLookupError:
		return process.returncode

	try:
		return process.wait(
			timeout=timeout_seconds,
		)
	except subprocess.TimeoutExpired:
		print(
			"Mission did not stop after SIGTERM. "
			"Sending SIGKILL."
		)

	try:
		os.killpg(
			process.pid,
			signal.SIGKILL,
		)
	except ProcessLookupError:
		pass

	return process.wait()


# ============================================================
# Mission launch
# ============================================================

def launch_mission(
	mission_name: str,
	validated: Any,
) -> subprocess.Popen[Any]:
	run_directory = runtime_directory(mission_name)
	run_directory.mkdir(parents=True, exist_ok=True)

	try:
		log_file = log_path(mission_name).open(
			"a",
			encoding="utf-8",
		)
	except OSError as exc:
		raise RuntimeError(
			f"Could not open mission log: {exc}"
		) from exc

	try:
		environment = os.environ.copy()

		environment["SAT_MISSION_NAME"] = mission_name
		environment["SAT_HEARTBEAT_PATH"] = str(
			heartbeat_path(mission_name)
		)
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
			env=environment
		)
	except OSError as exc:
		raise RuntimeError(
			f"Could not launch mission: {exc}"
		) from exc
	finally:
		log_file.close()

	return process


def launch_mission_once(
	mission_name: str,
	restart_count: int = 0,
	supervisor_pid: int | None = None,
) -> subprocess.Popen[Any] | None:
	directory = mission_directory(mission_name)

	# Validate the mission before launching it.
	try:
		validated = validate_mission(directory)
	except MissionValidationError as exc:
		print(
			"Mission validation failed:",
			file=sys.stderr,
		)

		for issue in exc.issues:
			print(
				f"  - {issue.format()}",
				file=sys.stderr,
			)

		return None

	# Prevent duplicate mission processes.
	existing_pid = active_pid_from_state(mission_name)

	if existing_pid is not None:
		print(
			f"Mission {mission_name} is already running "
			f"with PID {existing_pid}"
		)
		return None

	starting_state = {
		"mission": mission_name,
		"version": validated.manifest["version"],
		"state": (
			"STARTING"
			if restart_count == 0
			else "RESTARTING"
		),
		"pid": None,
		"supervisor_pid": supervisor_pid,
		"restart_count": restart_count,
		"last_exit_code": None,
		"last_exit_reason": None,
		"started_at": utc_now(),
	}

	write_state(
		mission_name,
		starting_state,
	)
	heartbeat_path(mission_name).unlink(
		missing_ok=True
	)
	try:
		process = launch_mission(
			mission_name,
			validated,
		)
	except RuntimeError as exc:
		update_state(
			mission_name,
			starting_state,
			state="FAILED",
			stopped_at=utc_now(),
			last_exit_reason="launch_failed",
			reason=str(exc),
		)

		print(
			f"Failed to start mission: {exc}",
			file=sys.stderr,
		)
		return None

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

	return process


# ============================================================
# Start mission
# ============================================================

def start_mission(mission_name: str) -> int:
	process = launch_mission_once(mission_name)

	if process is None:
		return 1

	return 0


# ============================================================
# Supervise mission
# ============================================================

def supervise_mission(mission_name: str) -> int:
	restart_count = 0
	stop_requested = False

	def request_stop(
		signum: int,
		frame: Any,
	) -> None:
		nonlocal stop_requested

		stop_requested = True
		print(f"\nStop requested for {mission_name}")

	signal.signal(
		signal.SIGINT,
		request_stop,
	)
	signal.signal(
		signal.SIGTERM,
		request_stop,
	)

	while True:
		process = launch_mission_once(
			mission_name,
			restart_count=restart_count,
			supervisor_pid=os.getpid(),
		)

		if process is None:
			return 1

		# Remain alive while the mission runs.
		while process.poll() is None:
			if stop_requested:
				exit_code = terminate_process(process)

				update_state(
					mission_name,
					read_state(mission_name) or {},
					state="STOPPED",
					pid=None,
					supervisor_pid=None,
					stopped_at=utc_now(),
					last_exit_code=exit_code,
					last_exit_reason="requested_stop",
				)

				print(f"Stopped mission {mission_name}")
				return 0
			heartbeat_age = heartbeat_age_seconds(mission_name)
			if (
				heartbeat_age is not None
				and heartbeat_age > HEARTBEAT_TIMEOUT_SECOND
			):
				print(
					f"Mission heartbeat timed out "
					f"after {heartbeat_age:.1f} seconds"
				)

				update_state(
					mission_name,
					read_state(mission_name) or {},
					state="UNHEALTHY",
					last_exit_reason="heartbeat_timeout",
				)

				terminate_process(process)
				break
			time.sleep(0.25)

		exit_code = process.returncode

		# A zero exit code means the mission finished normally.
		if exit_code == 0:
			update_state(
				mission_name,
				read_state(mission_name) or {},
				state="STOPPED",
				pid=None,
				supervisor_pid=None,
				stopped_at=utc_now(),
				last_exit_code=exit_code,
				last_exit_reason="clean_exit",
			)

			print(
				f"Mission {mission_name} "
				"completed successfully"
			)
			return 0

		# The mission crashed too many times.
		if restart_count >= MAX_RESTARTS:
			update_state(
				mission_name,
				read_state(mission_name) or {},
				state="FAILED",
				pid=None,
				supervisor_pid=None,
				stopped_at=utc_now(),
				last_exit_code=exit_code,
				last_exit_reason="restart_limit_reached",
			)

			print(
				f"Mission {mission_name} failed with "
				f"exit code {exit_code}. "
				"Restart limit reached.",
				file=sys.stderr,
			)
			return 1

		# Record the crash and restart once.
		restart_count += 1

		update_state(
			mission_name,
			read_state(mission_name) or {},
			state="RESTARTING",
			pid=None,
			restart_count=restart_count,
			last_exit_code=exit_code,
			last_exit_reason="unexpected_exit",
		)

		print(
			f"Mission {mission_name} crashed with "
			f"exit code {exit_code}. "
			f"Restarting "
			f"({restart_count}/{MAX_RESTARTS})..."
		)

		time.sleep(RESTART_DELAY_SECONDS)


# ============================================================
# Mission status
# ============================================================

def status_mission(mission_name: str) -> int:
	state = read_state(mission_name)

	if state is None:
		print(
			f"Mission {mission_name} "
			"has no runtime state"
		)
		return 1

	pid = state.get("pid")
	stored_status = state.get(
		"state",
		"UNKNOWN",
	)

	running = (
		isinstance(pid, int)
		and process_is_running(pid)
	)

	# Only mark it failed if it claims to be running
	# and there is no active supervisor handling recovery.
	supervisor_pid = state.get("supervisor_pid")

	supervisor_running = (
		isinstance(supervisor_pid, int)
		and process_is_running(supervisor_pid)
	)

	if (
		stored_status == "RUNNING"
		and not running
		and not supervisor_running
	):
		state = update_state(
			mission_name,
			state,
			state="FAILED",
			pid=None,
			stopped_at=utc_now(),
			last_exit_reason="process_not_running",
		)

	print(f"Mission: {state.get('mission')}")
	print(f"Version: {state.get('version')}")
	print(f"State: {state.get('state')}")
	print(f"PID: {state.get('pid')}")
	print(
		f"Supervisor PID: "
		f"{state.get('supervisor_pid')}"
	)
	print(
		f"Restart count: "
		f"{state.get('restart_count', 0)}"
	)
	print(f"Started: {state.get('started_at')}")

	if state.get("stopped_at"):
		print(f"Stopped: {state.get('stopped_at')}")

	if state.get("last_exit_code") is not None:
		print(
			f"Last exit code: "
			f"{state.get('last_exit_code')}"
		)

	if state.get("last_exit_reason"):
		print(
			f"Last exit reason: "
			f"{state.get('last_exit_reason')}"
		)

	if state.get("reason"):
		print(f"Reason: {state.get('reason')}")

	return 0

def heartbeat_age_seconds(
    mission_name: str,
) -> float | None:
    path = heartbeat_path(mission_name)

    if not path.exists():
        return None

    try:
        heartbeat = json.loads(
            path.read_text(encoding="utf-8")
        )

        timestamp = datetime.fromisoformat(
            heartbeat["timestamp"]
        )
    except (
        OSError,
        json.JSONDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return None

    now = datetime.now(timezone.utc)

    return (
        now - timestamp
    ).total_seconds()

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
	timeout_seconds: float = STOP_TIMEOUT_SECONDS,
) -> int:
	state = read_state(mission_name)

	if state is None:
		print(
			f"No runtime state found for "
			f"{mission_name}"
		)
		return 1

	supervisor_pid = state.get("supervisor_pid")
	mission_pid = state.get("pid")

	# When supervised, stop the supervisor.
	# It will shut down the mission cleanly.
	if (
		isinstance(supervisor_pid, int)
		and process_is_running(supervisor_pid)
	):
		print(
			f"Stopping supervisor "
			f"{supervisor_pid}..."
		)

		try:
			os.kill(
				supervisor_pid,
				signal.SIGTERM,
			)
		except ProcessLookupError:
			pass
		except PermissionError as exc:
			print(
				f"Could not stop supervisor: {exc}",
				file=sys.stderr,
			)
			return 1

		stopped = wait_for_process_exit(
			supervisor_pid,
			timeout_seconds + 2,
		)

		if not stopped:
			print(
				"Supervisor did not stop in time",
				file=sys.stderr,
			)
			return 1

		print(f"Stopped mission {mission_name}")
		return 0

	# Otherwise stop the standalone mission process.
	if not isinstance(mission_pid, int):
		print(
			f"Mission {mission_name} "
			"has no active PID"
		)
		return 1

	if not process_is_running(mission_pid):
		update_state(
			mission_name,
			state,
			state="STOPPED",
			pid=None,
			stopped_at=utc_now(),
			last_exit_reason="process_already_stopped",
		)

		print(
			f"Mission {mission_name} "
			"was not running"
		)
		return 0

	if not is_process_group_leader(mission_pid):
		print(
			f"PID {mission_pid} is not the "
			"expected mission process group",
			file=sys.stderr,
		)
		return 1

	update_state(
		mission_name,
		state,
		state="STOPPING",
	)

	try:
		os.killpg(
			mission_pid,
			signal.SIGTERM,
		)
	except ProcessLookupError:
		pass
	except PermissionError as exc:
		update_state(
			mission_name,
			state,
			state="FAILED",
			stopped_at=utc_now(),
			last_exit_reason="stop_permission_error",
			reason=str(exc),
		)

		print(
			f"Could not stop mission: {exc}",
			file=sys.stderr,
		)
		return 1

	stopped = wait_for_process_exit(
		mission_pid,
		timeout_seconds,
	)

	if not stopped:
		print(
			"Mission did not stop after SIGTERM. "
			"Sending SIGKILL."
		)

		try:
			os.killpg(
				mission_pid,
				signal.SIGKILL,
			)
		except ProcessLookupError:
			pass
		except PermissionError as exc:
			update_state(
				mission_name,
				state,
				state="FAILED",
				stopped_at=utc_now(),
				last_exit_reason="kill_permission_error",
				reason=str(exc),
			)

			print(
				f"Could not force-stop mission: {exc}",
				file=sys.stderr,
			)
			return 1

		stopped = wait_for_process_exit(
			mission_pid,
			timeout_seconds=2.0,
		)

	if not stopped:
		update_state(
			mission_name,
			state,
			state="FAILED",
			stopped_at=utc_now(),
			last_exit_reason="failed_to_terminate",
		)

		print(
			f"Mission {mission_name} "
			"could not be terminated",
			file=sys.stderr,
		)
		return 1

	update_state(
		mission_name,
		read_state(mission_name) or state,
		state="STOPPED",
		pid=None,
		supervisor_pid=None,
		stopped_at=utc_now(),
		last_exit_reason="requested_stop",
	)

	print(f"Stopped mission {mission_name}")
	return 0


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
	parser = argparse.ArgumentParser(
		description=(
			"Control satellite mission applications."
		)
	)

	subparsers = parser.add_subparsers(
		dest="command",
		required=True,
	)

	start_parser = subparsers.add_parser(
		"start",
		help="Start a mission without supervision",
	)
	start_parser.add_argument("mission_name")

	supervise_parser = subparsers.add_parser(
		"supervise",
		help=(
			"Start a mission and restart it once "
			"after a crash"
		),
	)
	supervise_parser.add_argument("mission_name")

	status_parser = subparsers.add_parser(
		"status",
		help="Show mission status",
	)
	status_parser.add_argument("mission_name")
	status_parser.add_argument("candidate", nargs="?", default=False, help="Use candidate agent dir instead of mission dir")
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
		default=STOP_TIMEOUT_SECONDS,
	)

	return parser


def main() -> int:
	parser = build_parser()
	args = parser.parse_args()

	match args.command:
		case "start":
			return start_mission(
				args.mission_name
			)

		case "supervise":
			return supervise_mission(
				args.mission_name
			)

		case "status":
			return status_mission(
				args.mission_name
			)

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
		case "candidate":
			start_dir = CANDIDATE_ROOT

		case _:
			parser.error(
				f"Unsupported command: "
				f"{args.command}"
			)
			return 2


if __name__ == "__main__":
	raise SystemExit(main())
