from __future__ import annotations

import ast
from dataclasses import dataclass


FORBIDDEN_IMPORTS = {
    "httpx", "picamera2", "requests", "RPi", "socket", "subprocess", "urllib",
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
    optical_flow_count: int


@dataclass(frozen=True)
class EvaluationRun:
    result: EvaluationResult
    record: ExecutionRecord


def evaluate_source(source: str) -> EvaluationResult:
    """Run the fast syntax and safety checks for a mission source file."""
    try:
        tree = ast.parse(source, filename="mission.py")
    except SyntaxError as exc:
        return EvaluationResult(False, 0, [f"Syntax error at line {exc.lineno}: {exc.msg}"])

    failures = find_safety_failures(tree)
    return EvaluationResult(not failures, 100 if not failures else 0, failures)


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
            if writes_outside_outputs(node):
                failures.append("Mission writes outside outputs/")
    return sorted(set(failures))


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def writes_outside_outputs(node: ast.Call) -> bool:
    name = dotted_name(node.func)
    if name == "open" and writes_file(node):
        return not approved_output_path(node.args[0] if node.args else None)
    if name in {"os.remove", "os.unlink", "os.rename", "os.replace"}:
        return True
    if isinstance(node.func, ast.Attribute) and node.func.attr in {
        "mkdir", "replace", "rename", "unlink", "write_bytes", "write_text",
    }:
        return not approved_output_path(node.func.value)
    return False


def writes_file(node: ast.Call) -> bool:
    mode = node.args[1] if len(node.args) > 1 else None
    for keyword in node.keywords:
        if keyword.arg == "mode":
            mode = keyword.value
    return isinstance(mode, ast.Constant) and isinstance(mode.value, str) and any(
        flag in mode.value for flag in "wax+"
    )


def approved_output_path(node: ast.AST | None) -> bool:
    value = path_literal(node)
    return value is None or value == "outputs" or value.replace("\\", "/").startswith("outputs/")


def path_literal(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Call) and dotted_name(node.func) == "Path" and node.args:
        return path_literal(node.args[0])
    return None


from agents.harness import empty_record, execute_mission  # noqa: E402
