from __future__ import annotations

import ast
import contextlib
import io
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

try:
    from sat_sdk.models import CaptureResponse, HealthResponse, SystemStatusResponse
except ModuleNotFoundError:
    @dataclass(frozen=True)
    class HealthResponse:
        status: str
        camera_available: bool

    @dataclass(frozen=True)
    class SystemStatusResponse:
        cpu_temp: str
        ram_use: str
        disk_use: str
        uptime: str

    @dataclass(frozen=True)
    class CaptureResponse:
        message: str
        filename: str


FORBIDDEN_IMPORTS = {
    "httpx",
    "picamera2",
    "requests",
    "RPi",
    "socket",
    "subprocess",
    "urllib",
}


@dataclass(frozen=True)
class EvaluationResult:
    passed: bool
    score: int
    failures: list[str]
    stdout: str = ""
    traceback: str | None = None


@dataclass(frozen=True)
class ExecutionRecord:
    capture_count: int
    heartbeat_count: int
    system_status_count: int
    sleep_durations: list[float]
    output_files: list[str]


@dataclass(frozen=True)
class EvaluationRun:
    result: EvaluationResult
    record: ExecutionRecord


def evaluate_source(source: str) -> EvaluationResult:
    """Run the fast syntax and safety checks for a mission source file."""
    try:
        tree = ast.parse(source, filename="mission.py")
    except SyntaxError as exc:
        return EvaluationResult(
            passed=False,
            score=0,
            failures=[f"Syntax error at line {exc.lineno}: {exc.msg}"],
        )

    failures = find_safety_failures(tree)
    return EvaluationResult(
        passed=not failures,
        score=100 if not failures else 0,
        failures=failures,
    )


def find_safety_failures(tree: ast.AST) -> list[str]:
    failures: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.split(".")[0] in FORBIDDEN_IMPORTS:
                    failures.append(f"Forbidden import: {alias.name}")

        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in FORBIDDEN_IMPORTS:
                failures.append(f"Forbidden import: {module}")

        if isinstance(node, ast.Call):
            name = dotted_name(node.func)
            if name in {"os.system", "os.popen", "subprocess.run"}:
                failures.append(f"Forbidden operation: {name}")
            if name == "cv2.VideoCapture":
                failures.append("Forbidden operation: cv2.VideoCapture")

    return sorted(set(failures))


def execute_mission(source: str) -> EvaluationRun:
    """Execute source with a recording SDK in an empty mission directory."""
    static_result = evaluate_source(source)
    if not static_result.passed:
        return EvaluationRun(static_result, empty_record())

    with tempfile.TemporaryDirectory() as temporary_directory:
        mission_directory = Path(temporary_directory)
        record = _MutableRecord(mission_directory)
        stdout = io.StringIO()
        failure: BaseException | None = None
        failure_traceback: str | None = None

        with patched_modules(record), contextlib.redirect_stdout(stdout):
            namespace = {
                "__name__": "__main__",
                "__file__": str(mission_directory / "mission.py"),
            }
            previous_directory = Path.cwd()
            try:
                import os

                os.chdir(mission_directory)
                exec(compile(source, "mission.py", "exec"), namespace)
            except SystemExit as exc:
                if exc.code not in (None, 0):
                    failure = exc
                    failure_traceback = traceback.format_exc()
            except BaseException as exc:
                failure = exc
                failure_traceback = traceback.format_exc()
            finally:
                os.chdir(previous_directory)

        result = EvaluationResult(
            passed=failure is None,
            score=100 if failure is None else 50,
            failures=[] if failure is None else [str(failure) or type(failure).__name__],
            stdout=stdout.getvalue(),
            traceback=failure_traceback,
        )
        return EvaluationRun(result, record.freeze())


def empty_record() -> ExecutionRecord:
    return ExecutionRecord(0, 0, 0, [], [])


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


class _MutableRecord:
    def __init__(self, mission_directory: Path) -> None:
        self.mission_directory = mission_directory
        self.capture_count = 0
        self.heartbeat_count = 0
        self.system_status_count = 0
        self.sleep_durations: list[float] = []

    def capture(self) -> CaptureResponse:
        self.capture_count += 1
        filename = self.mission_directory / f"capture-{self.capture_count:03d}.jpg"
        filename.write_bytes(b"fake-image")
        return CaptureResponse("captured", str(filename))

    def freeze(self) -> ExecutionRecord:
        output_directory = self.mission_directory / "outputs"
        output_files = (
            sorted(
                path.relative_to(self.mission_directory).as_posix()
                for path in output_directory.rglob("*")
                if path.is_file()
            )
            if output_directory.exists()
            else []
        )
        return ExecutionRecord(
            self.capture_count,
            self.heartbeat_count,
            self.system_status_count,
            self.sleep_durations,
            output_files,
        )


@contextlib.contextmanager
def patched_modules(record: _MutableRecord):
    previous_modules = {name: sys.modules.get(name) for name in ("sat_sdk", "time", "signal")}
    sys.modules["sat_sdk"] = fake_sdk_module(record)
    sys.modules["time"] = fake_time_module(record)
    sys.modules["signal"] = fake_signal_module()
    try:
        yield
    finally:
        for name, module in previous_modules.items():
            if module is None:
                del sys.modules[name]
            else:
                sys.modules[name] = module


def fake_sdk_module(record: _MutableRecord) -> ModuleType:
    module = ModuleType("sat_sdk")

    class FakeSatClient:
        def __init__(self, **_: object) -> None:
            self.camera = _FakeCamera(record)
            self.system = _FakeSystem(record)

        def heartbeat(self) -> HealthResponse:
            record.heartbeat_count += 1
            return HealthResponse(status="ok", camera_available=True)

    module.SatClient = FakeSatClient
    return module


class _FakeCamera:
    def __init__(self, record: _MutableRecord) -> None:
        self._record = record

    def capture(self) -> CaptureResponse:
        return self._record.capture()


class _FakeSystem:
    def __init__(self, record: _MutableRecord) -> None:
        self._record = record

    def status(self) -> SystemStatusResponse:
        self._record.system_status_count += 1
        return SystemStatusResponse("40C", "10%", "20%", "1h")


def fake_time_module(record: _MutableRecord) -> ModuleType:
    module = ModuleType("time")
    module.sleep = lambda duration: record.sleep_durations.append(float(duration))
    return module


def fake_signal_module() -> ModuleType:
    module = ModuleType("signal")
    module.SIGTERM = 15
    module.SIGINT = 2
    module.signal = lambda *_: None
    return module
