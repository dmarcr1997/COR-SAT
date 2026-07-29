from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = PROJECT_ROOT / "agents" / "prompts" / "requirements.md"
ModelCall = Callable[[list[dict[str, str]]], str]


@dataclass(frozen=True)
class MissionRequirements:
    capture_count: int
    interval_seconds: float
    heartbeat_each_capture: bool
    optical_flow_groups: int = 0
    optical_flow_outputs: int = 0
    require_shutdown_handling: bool = False

    @property
    def uses_optical_flow(self) -> bool:
        return self.optical_flow_groups > 0


def parse_mission_request(
    mission_request: str,
    *,
    model_call: ModelCall | None = None,
) -> MissionRequirements:
    """Extract validated camera-mission requirements from natural language."""
    response = (model_call or call_ollama)(build_requirement_prompt(mission_request))
    return requirements_from_json(response)


def build_requirement_prompt(mission_request: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": PROMPT_PATH.read_text(encoding="utf-8")},
        {"role": "user", "content": mission_request},
    ]


def requirements_from_json(response: str) -> MissionRequirements:
    try:
        values = json.loads(strip_json_fence(response))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Mission requirement parser returned invalid JSON: {exc.msg}") from exc
    if not isinstance(values, dict):
        raise ValueError("Mission requirement parser must return a JSON object")

    required = {
        "capture_count",
        "interval_seconds",
        "heartbeat_each_capture",
        "optical_flow_groups",
        "optical_flow_outputs",
        "require_shutdown_handling",
    }
    if set(values) != required:
        raise ValueError("Mission requirement parser returned unsupported fields")

    requirements = MissionRequirements(**values)
    validate_requirements(requirements)
    return requirements


def validate_requirements(requirements: MissionRequirements) -> None:
    if type(requirements.capture_count) is not int or requirements.capture_count < 1:
        raise ValueError("capture_count must be a positive integer")
    if type(requirements.interval_seconds) not in {int, float} or requirements.interval_seconds <= 0:
        raise ValueError("interval_seconds must be positive")
    if type(requirements.heartbeat_each_capture) is not bool:
        raise ValueError("heartbeat_each_capture must be a boolean")
    if type(requirements.require_shutdown_handling) is not bool:
        raise ValueError("require_shutdown_handling must be a boolean")
    if type(requirements.optical_flow_groups) is not int or requirements.optical_flow_groups < 0:
        raise ValueError("optical_flow_groups must be a non-negative integer")
    if type(requirements.optical_flow_outputs) is not int or requirements.optical_flow_outputs < 0:
        raise ValueError("optical_flow_outputs must be a non-negative integer")
    if requirements.uses_optical_flow != (requirements.optical_flow_outputs > 0):
        raise ValueError("optical flow groups and outputs must be enabled together")
    if requirements.optical_flow_groups > requirements.capture_count:
        raise ValueError("optical_flow_groups cannot exceed capture_count")


def call_ollama(messages: list[dict[str, str]]) -> str:
    from agents.generator import call_ollama as generate_call

    return generate_call(messages)


def strip_json_fence(response: str) -> str:
    stripped = response.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1])
    return stripped
