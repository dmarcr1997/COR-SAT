from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from agents.evaluator import EvaluationResult, EvaluationRun, execute_mission
from agents.requirements import MissionRequirements


@dataclass(frozen=True)
class CandidateSource:
    name: str
    source: str


@dataclass(frozen=True)
class CandidateEvaluation:
    candidate: CandidateSource
    run: EvaluationRun


@dataclass(frozen=True)
class CandidateSelection:
    winner: CandidateEvaluation | None
    best_failed: CandidateEvaluation | None
    evaluations: list[CandidateEvaluation]


def evaluate_candidate(source: str, requirements: MissionRequirements) -> EvaluationRun:
    run = execute_mission(source)
    failures = list(run.result.failures)
    if run.result.passed:
        failures.extend(behavior_failures(source, run, requirements))

    result = EvaluationResult(
        passed=not failures,
        score=max(0, run.result.score - 10 * len(failures)),
        failures=failures,
        stdout=run.result.stdout,
        traceback=run.result.traceback,
    )
    return EvaluationRun(result, run.record)


def select_candidate(
    candidates: Iterable[CandidateSource],
    requirements: MissionRequirements,
    *,
    evaluate: Callable[[str, MissionRequirements], EvaluationRun] = evaluate_candidate,
) -> CandidateSelection:
    evaluations: list[CandidateEvaluation] = []
    best_failed: CandidateEvaluation | None = None

    for candidate in candidates:
        evaluation = CandidateEvaluation(candidate, evaluate(candidate.source, requirements))
        evaluations.append(evaluation)
        if evaluation.run.result.passed:
            return CandidateSelection(evaluation, best_failed, evaluations)
        if best_failed is None or evaluation.run.result.score > best_failed.run.result.score:
            best_failed = evaluation

    return CandidateSelection(None, best_failed, evaluations)


def behavior_failures(
    source: str,
    run: EvaluationRun,
    requirements: MissionRequirements,
) -> list[str]:
    failures: list[str] = []
    record = run.record
    if record.capture_count != requirements.capture_count:
        failures.append(f"Expected {requirements.capture_count} captures, got {record.capture_count}")
    if requirements.heartbeat_each_capture and record.heartbeat_count < requirements.capture_count:
        failures.append("Heartbeat was not called during every capture")
    expected_sleeps = [requirements.interval_seconds] * (requirements.capture_count - 1)
    if record.sleep_durations != expected_sleeps:
        failures.append(f"Expected waits {expected_sleeps}, got {record.sleep_durations}")
    if len(record.output_files) != requirements.optical_flow_outputs:
        failures.append(f"Expected {requirements.optical_flow_outputs} output files, got {len(record.output_files)}")
    if requirements.uses_optical_flow and not calls(source, "cv2.calcOpticalFlowPyrLK"):
        failures.append("Sparse Lucas-Kanade optical flow was not used")
    if requirements.require_shutdown_handling and not calls(source, "signal.signal"):
        failures.append("Shutdown signal handling is missing")
    return failures


def calls(source: str, name: str) -> bool:
    tree = ast.parse(source)
    return any(dotted_name(node.func) == name for node in ast.walk(tree) if isinstance(node, ast.Call))


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None
