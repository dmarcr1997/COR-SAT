from __future__ import annotations

import ast
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

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
    requirements_parser: Callable[[str], MissionRequirements] = parse_mission_request,
) -> Path:
    """Generate, evaluate, repair once if needed, and package a mission."""
    started_at = perf_counter()
    progress("Parsing natural-language mission request")
    requirements = requirements_parser(mission_request)
    progress(
        "Requirements accepted: "
        f"{requirements.capture_count} captures every {requirements.interval_seconds:g}s"
    )
    progress("Starting minimal and robust generators")
    selection = generate_and_select(requirements, mission_request, generate_source)
    if selection.winner:
        progress("Creating and validating accepted mission package")
        package = package_creator(candidate_name, selection.winner.candidate.source, requirements)
        progress(f"Mission package ready in {perf_counter() - started_at:.1f}s: {package}")
        return package

    if selection.best_failed is None:
        raise RuntimeError("Both mission generators failed without a candidate")

    best_failed = selection.best_failed
    progress(f"Both candidates failed; repairing {best_failed.candidate.name} once")
    repaired_source = repair_source(
        mission_request,
        best_failed.candidate.source,
        best_failed.run.result.failures,
        include_optical_flow=requirements.uses_optical_flow,
        requirements=requirements,
    )
    progress("Repair source received; evaluating")
    repaired_run = evaluate_candidate(repaired_source, requirements)
    if not repaired_run.result.passed:
        raise RuntimeError("Mission repair failed: " + "; ".join(repaired_run.result.failures))
    progress("Repair passed; creating and validating mission package")
    package = package_creator(candidate_name, repaired_source, requirements)
    progress(f"Mission package ready in {perf_counter() - started_at:.1f}s: {package}")
    return package


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
        progress(f"{variant} candidate received; evaluating")
        evaluation = CandidateEvaluation(
            CandidateSource(f"candidate-{variant}", source),
            evaluate_candidate(source, requirements),
        )
        evaluations.append(evaluation)
        if evaluation.run.result.passed:
            winner = evaluation
            progress(f"{variant} candidate passed with score {evaluation.run.result.score}; accepting")
            return True
        progress(
            f"{variant} candidate failed with score {evaluation.run.result.score}: "
            + "; ".join(evaluation.run.result.failures)
        )
        if best_failed is None or evaluation.run.result.score > best_failed.run.result.score:
            best_failed = evaluation
        return False

    generate_two_candidates(
        mission_request,
        include_optical_flow=requirements.uses_optical_flow,
        requirements=requirements,
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
    group_size = expected_group_size(requirements)
    if group_size is not None and not has_groups_of_size(source, group_size):
        failures.append(f"Frames were not split into groups of {group_size}")
    if requirements.require_shutdown_handling and not calls(source, "signal.signal"):
        failures.append("Shutdown signal handling is missing")
    return failures


def calls(source: str, name: str) -> bool:
    tree = ast.parse(source)
    return any(dotted_name(node.func) == name for node in ast.walk(tree) if isinstance(node, ast.Call))


def expected_group_size(requirements: MissionRequirements) -> int | None:
    if not requirements.uses_optical_flow:
        return None
    if requirements.capture_count % requirements.optical_flow_groups:
        return None
    return requirements.capture_count // requirements.optical_flow_groups


def has_groups_of_size(source: str, group_size: int) -> bool:
    tree = ast.parse(source)
    return any(
        isinstance(node, ast.Call)
        and dotted_name(node.func) == "range"
        and any(
            isinstance(argument, ast.Constant) and argument.value == group_size
            for argument in node.args
        )
        for node in ast.walk(tree)
    )


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else None
    return None


def progress(message: str) -> None:
    print(f"[mission] {message}", flush=True)
