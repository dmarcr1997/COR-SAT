from __future__ import annotations

import contextlib
import io
import sys
import tempfile
import traceback
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from agents.evaluator import EvaluationResult, EvaluationRun, ExecutionRecord, evaluate_source

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


def execute_mission(source: str) -> EvaluationRun:
    """Execute source with a recording SDK in an empty mission directory."""
    static_result = evaluate_source(source)
    if not static_result.passed:
        return EvaluationRun(static_result, empty_record())

    with tempfile.TemporaryDirectory() as directory:
        mission_directory = Path(directory)
        record = _MutableRecord(mission_directory)
        stdout = io.StringIO()
        failure, failure_traceback = run_source(source, mission_directory, record, stdout)
        result = EvaluationResult(
            failure is None,
            100 if failure is None else 50,
            [] if failure is None else [str(failure) or type(failure).__name__],
            stdout.getvalue(),
            failure_traceback,
        )
        return EvaluationRun(result, record.freeze())


def run_source(
    source: str,
    mission_directory: Path,
    record: _MutableRecord,
    stdout: io.StringIO,
) -> tuple[BaseException | None, str | None]:
    with patched_modules(record), contextlib.redirect_stdout(stdout):
        namespace = {"__name__": "__main__", "__file__": str(mission_directory / "mission.py")}
        previous_directory = Path.cwd()
        try:
            import os

            os.chdir(mission_directory)
            exec(compile(source, "mission.py", "exec"), namespace)
        except SystemExit as exc:
            if exc.code not in (None, 0):
                return exc, traceback.format_exc()
        except BaseException as exc:
            return exc, traceback.format_exc()
        finally:
            os.chdir(previous_directory)
    return None, None


def empty_record() -> ExecutionRecord:
    return ExecutionRecord(0, 0, 0, [], [], 0)


class _MutableRecord:
    def __init__(self, mission_directory: Path) -> None:
        self.mission_directory = mission_directory
        self.capture_count = 0
        self.heartbeat_count = 0
        self.system_status_count = 0
        self.sleep_durations: list[float] = []
        self.optical_flow_count = 0

    def capture(self) -> CaptureResponse:
        self.capture_count += 1
        filename = self.mission_directory / f"capture-{self.capture_count:03d}.jpg"
        filename.write_bytes(b"fake-image")
        return CaptureResponse("captured", str(filename))

    def freeze(self) -> ExecutionRecord:
        output_directory = self.mission_directory / "outputs"
        output_files = (
            sorted(path.relative_to(self.mission_directory).as_posix() for path in output_directory.rglob("*") if path.is_file())
            if output_directory.exists()
            else []
        )
        return ExecutionRecord(
            self.capture_count, self.heartbeat_count, self.system_status_count,
            self.sleep_durations, output_files, self.optical_flow_count,
        )


@contextlib.contextmanager
def patched_modules(record: _MutableRecord):
    module_names = ("sat_sdk", "time", "signal", "cv2", "numpy")
    previous_modules = {name: sys.modules.get(name) for name in module_names}
    sys.modules.update({
        "sat_sdk": fake_sdk_module(record), "time": fake_time_module(record),
        "signal": fake_signal_module(), "cv2": fake_cv2_module(record), "numpy": ModuleType("numpy"),
    })
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
            return HealthResponse("ok", True)

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
    module.SIGTERM, module.SIGINT, module.signal = 15, 2, lambda *_: None
    return module


def fake_cv2_module(record: _MutableRecord) -> ModuleType:
    module = ModuleType("cv2")
    module.COLOR_BGR2GRAY = 6
    module.imread = lambda _: _FakeFrame()
    module.cvtColor = lambda frame, _: frame
    module.goodFeaturesToTrack = lambda *_args, **_kwargs: object()

    def calculate_flow(*_: object, **__: object) -> tuple[None, None, None]:
        record.optical_flow_count += 1
        return None, None, None

    def write_image(filename: str, _: object) -> bool:
        Path(filename).write_bytes(b"fake-jpeg")
        return True

    module.calcOpticalFlowPyrLK, module.imwrite = calculate_flow, write_image
    return module


class _FakeFrame:
    def copy(self) -> _FakeFrame:
        return _FakeFrame()
