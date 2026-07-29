import tempfile
import unittest
from pathlib import Path

from agents.packager import build_manifest, create_mission_package
from agents.requirements import MissionRequirements
from runner.validator import validate_mission


class PackagerTests(unittest.TestCase):
    def test_builds_a_valid_manifest_for_repeated_mission(self) -> None:
        manifest = build_manifest(MissionRequirements(5, 2.0, True))

        self.assertEqual(manifest["permissions"], ["camera.capture", "system.status"])
        self.assertEqual(manifest["configuration"]["maximum_captures"], 5)
        self.assertEqual(manifest["configuration"]["capture_interval_seconds"], 2.0)

    def test_creates_runner_valid_package(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            package = create_mission_package(
                "candidate-001",
                "from sat_sdk import SatClient\nSatClient().camera.capture()\n",
                MissionRequirements(1, 1.0, False),
                candidates_root=Path(temporary_directory),
            )

            validated = validate_mission(package)

        self.assertEqual(validated.entrypoint_path.name, "mission.py")


if __name__ == "__main__":
    unittest.main()
