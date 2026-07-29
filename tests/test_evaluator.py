import unittest

from agents.evaluator import execute_mission, evaluate_source


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


if __name__ == "__main__":
    unittest.main()
