from __future__ import annotations

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


BENCHMARK_MISSIONS = {
    "capture one image.": MissionRequirements(1, 1.0, False),
    "capture five images at two-second intervals.": MissionRequirements(5, 2.0, True),
    (
        "capture twenty images at one-second intervals. split the images into groups of five. "
        "for each group, calculate sparse lucas-kanade optical flow between consecutive frames. "
        "save sixteen jpeg optical-flow visualizations in outputs/optical-flow. "
        "handle shutdown signals and call heartbeat during every capture."
    ): MissionRequirements(20, 1.0, True, 4, 16, True),
}


def parse_mission_request(mission_request: str) -> MissionRequirements:
    normalized = " ".join(mission_request.lower().split())
    try:
        return BENCHMARK_MISSIONS[normalized]
    except KeyError as exc:
        supported = "\n".join(f"- {request}" for request in BENCHMARK_MISSIONS)
        raise ValueError(f"Unsupported mission request. Supported requests:\n{supported}") from exc
