import unittest
import tempfile
from pathlib import Path

from agents.packager import create_mission_package
from agents.pipeline import evaluate_candidate
from agents.requirements import MissionRequirements
from runner.validator import validate_mission


ONE_CAPTURE = """
from sat_sdk import SatClient

sat = SatClient()
capture = sat.camera.capture()
print(capture.filename)
"""
ONE_REQUIREMENTS = MissionRequirements(1, 1.0, False)

FIVE_CAPTURES = """
import time

from sat_sdk import SatClient

sat = SatClient()
for index in range(5):
    sat.heartbeat()
    capture = sat.camera.capture()
    print(capture.filename)
    if index < 4:
        time.sleep(2)
"""
FIVE_REQUIREMENTS = MissionRequirements(5, 2.0, True)

OPTICAL_FLOW = """
import signal
import time
from pathlib import Path

import cv2
from sat_sdk import SatClient

shutdown_requested = False

def handle_shutdown(_signum, _frame):
    global shutdown_requested
    shutdown_requested = True

def calculate_flow(previous_path, current_path):
    previous = cv2.imread(previous_path)
    current = cv2.imread(current_path)
    points = cv2.goodFeaturesToTrack(previous, maxCorners=100)
    cv2.calcOpticalFlowPyrLK(previous, current, points, None)
    return current.copy()

signal.signal(signal.SIGTERM, handle_shutdown)
signal.signal(signal.SIGINT, handle_shutdown)
sat = SatClient()
frames = []
for index in range(20):
    if shutdown_requested:
        break
    sat.heartbeat()
    frames.append(sat.camera.capture().filename)
    if index < 19:
        time.sleep(1)

output_directory = Path("outputs/optical-flow")
output_directory.mkdir(parents=True, exist_ok=True)
flow_index = 0
for group_start in range(0, len(frames), 5):
    group = frames[group_start:group_start + 5]
    for frame_index in range(len(group) - 1):
        image = calculate_flow(group[frame_index], group[frame_index + 1])
        cv2.imwrite(str(output_directory / f"flow_{flow_index:03d}.jpg"), image)
        flow_index += 1
"""
OPTICAL_FLOW_REQUIREMENTS = MissionRequirements(20, 1.0, True, 4, 16, True)


class AcceptanceMissionTests(unittest.TestCase):
    def test_capture_one_image(self) -> None:
        run = evaluate_candidate(ONE_CAPTURE, ONE_REQUIREMENTS)

        self.assertTrue(run.result.passed, run.result.failures)
        self.assertEqual(run.record.capture_count, 1)

    def test_capture_five_images_at_two_second_intervals(self) -> None:
        run = evaluate_candidate(
            FIVE_CAPTURES,
            FIVE_REQUIREMENTS,
        )

        self.assertTrue(run.result.passed, run.result.failures)
        self.assertEqual(run.record.capture_count, 5)
        self.assertEqual(run.record.heartbeat_count, 5)
        self.assertEqual(run.record.sleep_durations, [2.0] * 4)

    def test_capture_twenty_images_and_create_optical_flow(self) -> None:
        request = """Capture twenty images at one-second intervals.

Split the images into groups of five.

For each group, calculate sparse Lucas-Kanade optical flow between consecutive frames.

Save sixteen JPEG optical-flow visualizations in outputs/optical-flow.

Handle shutdown signals and call heartbeat during every capture."""
        run = evaluate_candidate(OPTICAL_FLOW, OPTICAL_FLOW_REQUIREMENTS)

        self.assertTrue(run.result.passed, run.result.failures)
        self.assertEqual(run.record.capture_count, 20)
        self.assertEqual(run.record.heartbeat_count, 20)
        self.assertEqual(run.record.sleep_durations, [1.0] * 19)
        self.assertEqual(run.record.optical_flow_count, 16)
        self.assertEqual(len(run.record.output_files), 16)
        self.assertTrue(all(path.startswith("outputs/optical-flow/") for path in run.record.output_files))

        with tempfile.TemporaryDirectory() as temporary_directory:
            package = create_mission_package(
                "optical-flow",
                OPTICAL_FLOW,
                OPTICAL_FLOW_REQUIREMENTS,
                candidates_root=Path(temporary_directory),
            )
            self.assertEqual(validate_mission(package).entrypoint_path.name, "mission.py")


if __name__ == "__main__":
    unittest.main()
