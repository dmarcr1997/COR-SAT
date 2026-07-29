import unittest

from agents.evaluator import evaluate_source


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


if __name__ == "__main__":
    unittest.main()
