from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    """Generate independent minimal and robust candidates concurrently."""
    variants: tuple[PromptVariant, PromptVariant] = ("minimal", "robust")
    executor = ThreadPoolExecutor(max_workers=2)
    try:
        futures = {
            executor.submit(
                generate_source,
                mission_request,
                variant,
                include_optical_flow=include_optical_flow,
                requirements=requirements,
            ): variant
            for variant in variants
        }
        results: dict[PromptVariant, str] = {}
        for future in as_completed(futures):
            variant = futures[future]
            source = future.result()
            results[variant] = source
            if on_candidate and on_candidate(variant, source):
                break
    finally:
        executor.shutdown(wait=False, cancel_futures=True)
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
        references.append(read_reference("optical_flow_example.md"))

    request_parts = [
        f"Implementation approach: {variant_instruction}",
        f"Mission request:\n{mission_request}",
    ]
    if requirements is not None:
        request_parts.append(
            "Validated requirements (authoritative; implement these exact values):\n"
            + json.dumps(asdict(requirements), indent=2)
        )
    request_parts.append("Reference material:\n" + "\n\n".join(references))

    return [
        {"role": "system", "content": PROMPTS.joinpath("generate.md").read_text(encoding="utf-8")},
        {
            "role": "user",
            "content": "\n\n".join(request_parts),
        },
    ]


def read_reference(filename: str) -> str:
    return REFERENCES.joinpath(filename).read_text(encoding="utf-8")


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
