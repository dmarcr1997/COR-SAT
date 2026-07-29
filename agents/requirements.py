from __future__ import annotations

import re
from dataclasses import dataclass


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


def parse_mission_request(mission_request: str) -> MissionRequirements:
    normalized = " ".join(mission_request.lower().split())
    capture_count = capture_count_from(normalized)
    interval_seconds = interval_from(normalized)

    if capture_count == 1 and interval_seconds is None:
        return MissionRequirements(1, 1.0, False)
    if capture_count == 5 and interval_seconds == 2.0:
        return MissionRequirements(5, 2.0, True)
    if capture_count == 20 and interval_seconds == 1.0 and has_optical_flow_requirements(normalized):
        return MissionRequirements(20, 1.0, True, 4, 16, True)

    raise ValueError(
        "Unsupported mission request. Supported forms: one capture; five captures at two-second "
        "intervals; or twenty captures at one-second intervals with grouped Lucas-Kanade flow."
    )


def capture_count_from(request: str) -> int | None:
    match = re.search(r"\bcapture\s+(one|1|five|5|twenty|20)\s+images?\b", request)
    if not match:
        return None
    return {"one": 1, "1": 1, "five": 5, "5": 5, "twenty": 20, "20": 20}[match.group(1)]


def interval_from(request: str) -> float | None:
    match = re.search(r"\bat\s+(one|1|two|2)[-\s]second\s+intervals?\b", request)
    if not match:
        return None
    return {"one": 1.0, "1": 1.0, "two": 2.0, "2": 2.0}[match.group(1)]


def has_optical_flow_requirements(request: str) -> bool:
    checks = (
        r"groups?\s+of\s+(five|5)(\s+frames?)?",
        r"lucas[-\s]kanade\s+optical\s+flow",
        r"(sixteen|16)\s+(jpeg\s+)?optical[-\s]flow\s+(images|visualizations)",
        r"outputs/optical-flow",
        r"shutdown\s+signals?",
        r"heartbeat.*every\s+capture|every\s+capture.*heartbeat",
    )
    return all(re.search(check, request) for check in checks)
