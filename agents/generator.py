from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
import json
from pathlib import Path
from typing import Literal

from agents.requirements import MissionRequirements


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPTS = PROJECT_ROOT / "agents" / "prompts"
REFERENCES = PROJECT_ROOT / "agents" / "references"
MODEL_NAME = "qwen3:4b-instruct"

PromptVariant = Literal["minimal", "robust"]
ModelCall = Callable[[list[dict[str, str]]], str]
SourceGenerator = Callable[..., str]
CandidateConsumer = Callable[[PromptVariant, str], bool]


def generate_mission_source(
    mission_request: str,
    variant: PromptVariant,
    *,
    include_optical_flow: bool = False,
    requirements: MissionRequirements | None = None,
    model_call: ModelCall | None = None,
) -> str:
    """Generate one complete mission.py source file without model tools."""
    print(f"[mission] {variant} generator: calling Ollama...", flush=True)
    prompt = build_generation_prompt(
        mission_request,
        variant,
        include_optical_flow=include_optical_flow,
        requirements=requirements,
    )
    source = (model_call or call_ollama)(prompt)
    print(f"[mission] {variant} generator: source received.", flush=True)
    return strip_code_fence(source)


def generate_two_candidates(
    mission_request: str,
    *,
    include_optical_flow: bool,
    requirements: MissionRequirements | None = None,
    generate_source: SourceGenerator = generate_mission_source,
    on_candidate: CandidateConsumer | None = None,
) -> dict[PromptVariant, str]:
    """Generate candidates until one is accepted by the evaluator."""
    variants: tuple[PromptVariant, PromptVariant] = ("minimal", "robust")
    results: dict[PromptVariant, str] = {}
    for variant in variants:
        source = generate_source(
            mission_request,
            variant,
            include_optical_flow=include_optical_flow,
            requirements=requirements,
        )
        results[variant] = source
        if on_candidate and on_candidate(variant, source):
            break
    return results


def build_generation_prompt(
    mission_request: str,
    variant: PromptVariant,
    *,
    include_optical_flow: bool,
    requirements: MissionRequirements | None = None,
) -> list[dict[str, str]]:
    variant_instruction = {
        "minimal": "Use the smallest clear implementation that meets every requirement.",
        "robust": "Prioritize shutdown handling, exact timing, and explicit error checks.",
    }[variant]
    references = [read_reference("sdk_contract.md")]
    if include_optical_flow:
        references.append(optical_flow_reference(requirements))

    request_parts = [
        "Reference material:\n" + "\n\n".join(references),
        f"Implementation approach: {variant_instruction}",
        f"Mission request:\n{mission_request}",
    ]
    if requirements is not None:
        request_parts.append(
            "Validated requirements (authoritative; implement these exact values):\n"
            + json.dumps(asdict(requirements), indent=2)
        )
        request_parts.append(requirement_checklist(requirements))

    return [
        {"role": "system", "content": PROMPTS.joinpath("generate.md").read_text(encoding="utf-8")},
        {
            "role": "user",
            "content": "\n\n".join(request_parts),
        },
    ]


def read_reference(filename: str) -> str:
    return REFERENCES.joinpath(filename).read_text(encoding="utf-8")


def optical_flow_reference(requirements: MissionRequirements | None) -> str:
    if requirements is None or not requirements.uses_optical_flow:
        group_size, group_count, capture_count, output_count = 5, 4, 20, 16
    else:
        group_size = requirements.capture_count // requirements.optical_flow_groups
        group_count = requirements.optical_flow_groups
        capture_count = requirements.capture_count
        output_count = requirements.optical_flow_outputs
    return (
        read_reference("optical_flow_example.md")
        .replace("$GROUP_SIZE", str(group_size))
        .replace("$GROUP_COUNT", str(group_count))
        .replace("$CAPTURE_COUNT", str(capture_count))
        .replace("$FLOW_OUTPUT_COUNT", str(output_count))
        .replace("$PAIR_COUNT", str(group_size - 1))
    )


def requirement_checklist(requirements: MissionRequirements) -> str:
    lines = [
        "Implementation checklist (mandatory; validate this before returning source):",
        f"- Make exactly {requirements.capture_count} captures.",
        f"- Call time.sleep({requirements.interval_seconds:g}) exactly {requirements.capture_count - 1} times, never after the final capture.",
    ]
    if requirements.heartbeat_each_capture:
        lines.append("- Call sat.heartbeat() before every capture.")
    if requirements.uses_optical_flow:
        group_size = requirements.capture_count // requirements.optical_flow_groups
        lines.extend([
            f"- Split frames into {requirements.optical_flow_groups} groups of {group_size}.",
            f"- Make exactly {requirements.optical_flow_outputs} Lucas-Kanade calls and write exactly that many JPEG files.",
        ])
    if requirements.require_shutdown_handling:
        lines.append("- Register SIGTERM and SIGINT handlers.")
    lines.append("Do not copy fixed counts from the reference when they differ from this checklist.")
    return "\n".join(lines)


def call_ollama(messages: list[dict[str, str]]) -> str:
    try:
        from ollama import chat
    except ModuleNotFoundError as exc:
        raise RuntimeError("Ollama Python package is required for mission generation") from exc

    response = chat(
        model=MODEL_NAME,
        messages=messages,
        stream=False,
        think=False,
        options={"temperature": 0.2, "top_p": 0.9},
        keep_alive="10m",
    )
    return response.message.content


def strip_code_fence(source: str) -> str:
    stripped = source.strip()
    if not stripped.startswith("```"):
        return stripped + "\n"

    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip() + "\n"
    return stripped + "\n"
