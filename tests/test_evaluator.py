import unittest

from agents.evaluator import execute_mission, evaluate_source
from agents.pipeline import evaluate_candidate
from agents.requirements import MissionRequirements


class EvaluatorSyntaxTests(unittest.TestCase):
    def test_rejects_invalid_python(self) -> None:
        result = evaluate_source("def broken(:\n")

        self.assertFalse(result.passed)
        self.assertEqual(result.score, 0)
        self.assertIn("Syntax error", result.failures[0])

    def test_rejects_forbidden_import(self) -> None:
        result = evaluate_source("import subprocess\n")

        self.assertFalse(result.passed)
        self.assertEqual(result.failures, ["Forbidden import: subprocess"])

    def test_rejects_direct_camera_access(self) -> None:
        result = evaluate_source("import cv2\ncv2.VideoCapture(0)\n")

        self.assertFalse(result.passed)
        self.assertEqual(result.failures, ["Forbidden operation: cv2.VideoCapture"])

    def test_rejects_obvious_writes_outside_outputs(self) -> None:
        result = evaluate_source("from pathlib import Path\nPath('mission.py').write_text('changed')\n")

        self.assertFalse(result.passed)
        self.assertEqual(result.failures, ["Mission writes outside outputs/"])

    def test_accepts_sdk_mission_source(self) -> None:
        result = evaluate_source(
            "from sat_sdk import SatClient\n"
            "sat = SatClient()\n"
            "capture = sat.camera.capture()\n"
            "print(capture.filename)\n"
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.score, 100)
        self.assertEqual(result.failures, [])


class EvaluatorExecutionTests(unittest.TestCase):
    def test_records_sdk_calls_sleeps_and_outputs(self) -> None:
        run = execute_mission(
            "import time\n"
            "from pathlib import Path\n"
            "from sat_sdk import SatClient\n"
            "sat = SatClient()\n"
            "sat.heartbeat()\n"
            "capture = sat.camera.capture()\n"
            "sat.system.status()\n"
            "Path('outputs/result.txt').parent.mkdir(parents=True)\n"
            "Path('outputs/result.txt').write_text(capture.filename)\n"
            "time.sleep(2)\n"
        )

        self.assertTrue(run.result.passed)
        self.assertEqual(run.record.capture_count, 1)
        self.assertEqual(run.record.heartbeat_count, 1)
        self.assertEqual(run.record.system_status_count, 1)
        self.assertEqual(run.record.sleep_durations, [2.0])
        self.assertEqual(run.record.output_files, ["outputs/result.txt"])

    def test_missing_time_import_remains_a_runtime_failure(self) -> None:
        run = execute_mission("time.sleep(0.5)\n")

        self.assertFalse(run.result.passed)
        self.assertEqual(run.result.failures, ["name 'time' is not defined"])

    def test_fake_opencv_arrays_support_lucas_kanade_operations(self) -> None:
        run = execute_mission(
            "import cv2\n"
            "previous = cv2.imread('previous.jpg')\n"
            "current = cv2.imread('current.jpg')\n"
            "previous_points = cv2.goodFeaturesToTrack(previous, maxCorners=100)\n"
            "assert len(previous_points) == 2\n"
            "next_points, status, error = cv2.calcOpticalFlowPyrLK(previous, current, previous_points, None)\n"
            "assert error is None\n"
            "successful = status.flatten() == 1\n"
            "assert len(successful) == 2\n"
            "good_previous = previous_points[successful]\n"
            "good_next = next_points[successful]\n"
            "for previous_point, next_point in zip(good_previous, good_next):\n"
            "    cv2.line(current, previous_point.ravel(), next_point.ravel(), (0, 255, 0), 1)\n"
            "    cv2.circle(current, next_point.ravel(), 2, (0, 0, 255), -1)\n"
        )

        self.assertTrue(run.result.passed, run.result.failures)
        self.assertEqual(run.record.optical_flow_count, 1)

    def test_generated_style_lucas_kanade_mission_runs_without_opencv(self) -> None:
        source = """\
import time
from pathlib import Path

import cv2
from sat_sdk import SatClient

sat = SatClient()
frames = []
for index in range(15):
    sat.heartbeat()
    frames.append(sat.camera.capture().filename)
    if index < 14:
        time.sleep(0.5)

output_directory = Path("outputs/optical-flow")
for group_start in range(0, len(frames), 5):
    group = frames[group_start:group_start + 5]
    for index in range(len(group) - 1):
        previous = cv2.imread(group[index])
        current = cv2.imread(group[index + 1])
        previous_points = cv2.goodFeaturesToTrack(previous, maxCorners=100)
        next_points, status, _ = cv2.calcOpticalFlowPyrLK(
            previous, current, previous_points, None
        )
        for previous_point, next_point in zip(
            previous_points[status.flatten() == 1],
            next_points[status.flatten() == 1],
        ):
            cv2.line(current, previous_point.ravel(), next_point.ravel(), (0, 255, 0), 1)
            cv2.circle(current, next_point.ravel(), 2, (0, 0, 255), -1)
        cv2.imwrite(str(output_directory / f"flow_{group_start + index:03d}.jpg"), current)
"""

        requirements = MissionRequirements(15, 0.5, True, 3, 12, False)
        run = evaluate_candidate(source, requirements)

        self.assertTrue(run.result.passed, run.result.failures)
        self.assertEqual(run.record.capture_count, 15)
        self.assertEqual(run.record.heartbeat_count, 15)
        self.assertEqual(run.record.sleep_durations, [0.5] * 14)
        self.assertEqual(run.record.optical_flow_count, 12)
        self.assertEqual(len(run.record.output_files), 12)


if __name__ == "__main__":
    unittest.main()
