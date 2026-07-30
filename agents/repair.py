from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
import json
from pathlib import Path

from agents.generator import (
    ModelCall,
    call_ollama,
    optical_flow_reference,
    read_reference,
    requirement_checklist,
    strip_code_fence,
)
from agents.requirements import MissionRequirements


PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPAIR_PROMPT = PROJECT_ROOT / "agents" / "prompts" / "repair.md"


def repair_mission_source(
    mission_request: str,
    failed_source: str,
    failures: list[str],
    *,
    include_optical_flow: bool,
    requirements: MissionRequirements | None = None,
    model_call: ModelCall | None = None,
) -> str:
    """Request one complete replacement for the best failed mission source."""
    source = (model_call or call_ollama)(
        build_repair_prompt(
            mission_request,
            failed_source,
            failures,
            include_optical_flow=include_optical_flow,
            requirements=requirements,
        )
    )
    return strip_code_fence(source)


def build_repair_prompt(
    mission_request: str,
    failed_source: str,
    failures: list[str],
    *,
    include_optical_flow: bool,
    requirements: MissionRequirements | None = None,
) -> list[dict[str, str]]:
    references = [read_reference("sdk_contract.md")]
    if include_optical_flow:
        references.append(optical_flow_reference(requirements))

    request_parts = [
        "Reference material:\n" + "\n\n".join(references),
        f"Mission request:\n{mission_request}",
    ]
    if requirements is not None:
        request_parts.append(
            "Validated requirements (authoritative; implement these exact values):\n"
            + json.dumps(asdict(requirements), indent=2)
        )
    request_parts.extend(
        [
            "Evaluator failures:\n" + "\n".join(f"- {failure}" for failure in failures),
            f"Failed mission.py:\n{failed_source}",
        ]
    )
    if requirements is not None:
        request_parts.append(requirement_checklist(requirements))

    return [
        {"role": "system", "content": REPAIR_PROMPT.read_text(encoding="utf-8")},
        {
            "role": "user",
            "content": "\n\n".join(request_parts),
        },
    ]
