from __future__ import annotations

import ast
from dataclasses import dataclass


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


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None
