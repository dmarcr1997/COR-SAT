import contextlib
import io
import sys
import unittest
from unittest.mock import patch

from agents import cli


class CliTests(unittest.TestCase):
    def test_reports_requirement_errors_without_a_traceback(self) -> None:
        stderr = io.StringIO()
        with (
            patch.object(sys, "argv", ["cli.py", "Capture an unknown thing."]),
            patch("agents.cli.run_mission_pipeline", side_effect=ValueError("Unsupported hardware")),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = cli.main()

        self.assertEqual(exit_code, 1)
        self.assertIn("Mission generation failed: Unsupported hardware", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
