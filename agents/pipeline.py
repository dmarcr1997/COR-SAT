from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from agents.evaluator import EvaluationResult, EvaluationRun, execute_mission
from agents.generator import SourceGenerator, generate_mission_source, generate_two_candidates
from agents.packager import create_mission_package
from agents.repair import repair_mission_source
from agents.requirements import parse_mission_request
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


def run_mission_pipeline(
    mission_request: str,
    candidate_name: str,
    *,
    generate_source: SourceGenerator = generate_mission_source,
    repair_source: Callable[..., str] = repair_mission_source,
    package_creator: Callable[[str, str, MissionRequirements], Path] = create_mission_package,
) -> Path:
    """Generate, evaluate, repair once if needed, and package a mission."""
    requirements = parse_mission_request(mission_request)
    selection = generate_and_select(requirements, mission_request, generate_source)
    if selection.winner:
        return package_creator(candidate_name, selection.winner.candidate.source, requirements)

    if selection.best_failed is None:
        raise RuntimeError("Both mission generators failed without a candidate")

    best_failed = selection.best_failed
    repaired_source = repair_source(
        mission_request,
        best_failed.candidate.source,
        best_failed.run.result.failures,
        include_optical_flow=requirements.uses_optical_flow,
    )
    repaired_run = evaluate_candidate(repaired_source, requirements)
    if not repaired_run.result.passed:
        raise RuntimeError("Mission repair failed: " + "; ".join(repaired_run.result.failures))
    return package_creator(candidate_name, repaired_source, requirements)


def generate_and_select(
    requirements: MissionRequirements,
    mission_request: str,
    generate_source: SourceGenerator,
) -> CandidateSelection:
    evaluations: list[CandidateEvaluation] = []
    winner: CandidateEvaluation | None = None
    best_failed: CandidateEvaluation | None = None

    def evaluate_generated(variant: str, source: str) -> bool:
        nonlocal winner, best_failed
        evaluation = CandidateEvaluation(
            CandidateSource(f"candidate-{variant}", source),
            evaluate_candidate(source, requirements),
        )
        evaluations.append(evaluation)
        if evaluation.run.result.passed:
            winner = evaluation
            return True
        if best_failed is None or evaluation.run.result.score > best_failed.run.result.score:
            best_failed = evaluation
        return False

    generate_two_candidates(
        mission_request,
        include_optical_flow=requirements.uses_optical_flow,
        generate_source=generate_source,
        on_candidate=evaluate_generated,
    )
    return CandidateSelection(winner, best_failed, evaluations)


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
    if requirements.uses_optical_flow and record.optical_flow_count != requirements.optical_flow_outputs:
        failures.append("Optical flow was not calculated for every frame pair")
    if requirements.uses_optical_flow and not has_groups_of_five(source):
        failures.append("Frames were not split into groups of five")
    if requirements.require_shutdown_handling and not calls(source, "signal.signal"):
        failures.append("Shutdown signal handling is missing")
    return failures


def calls(source: str, name: str) -> bool:
    tree = ast.parse(source)
    return any(dotted_name(node.func) == name for node in ast.walk(tree) if isinstance(node, ast.Call))


def has_groups_of_five(source: str) -> bool:
    tree = ast.parse(source)
    return any(
        isinstance(node, ast.Call)
        and dotted_name(node.func) == "range"
        and any(isinstance(argument, ast.Constant) and argument.value == 5 for argument in node.args)
        for node in ast.walk(tree)
    )


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None
