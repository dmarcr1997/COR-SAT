import unittest
import tempfile
from pathlib import Path

from agents.evaluator import EvaluationResult, EvaluationRun, empty_record
from agents.packager import create_mission_package
from agents.pipeline import CandidateSource, run_mission_pipeline, select_candidate
from agents.requirements import MissionRequirements, parse_mission_request, requirements_from_json


class CandidateSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requirements = MissionRequirements(1, 1.0, False)

    def test_first_passing_candidate_wins_without_evaluating_later_source(self) -> None:
        evaluated: list[str] = []

        def evaluate(source: str, _requirements: object) -> EvaluationRun:
            evaluated.append(source)
            return EvaluationRun(EvaluationResult(True, 100, []), empty_record())

        selection = select_candidate(
            [CandidateSource("first", "one"), CandidateSource("second", "two")],
            self.requirements,
            evaluate=evaluate,
        )

        self.assertEqual(selection.winner.candidate.name, "first")
        self.assertEqual(evaluated, ["one"])

    def test_best_failed_candidate_has_highest_score(self) -> None:
        scores = {"weak": 10, "strong": 40}

        def evaluate(source: str, _requirements: object) -> EvaluationRun:
            return EvaluationRun(EvaluationResult(False, scores[source], ["failed"]), empty_record())

        selection = select_candidate(
            [CandidateSource("weak", "weak"), CandidateSource("strong", "strong")],
            self.requirements,
            evaluate=evaluate,
        )

        self.assertIsNone(selection.winner)
        self.assertEqual(selection.best_failed.candidate.name, "strong")

    def test_parser_accepts_general_camera_requirements(self) -> None:
        requirements = parse_mission_request(
            "Capture 7 images every 3 seconds and heartbeat after each capture.",
            model_call=lambda _: """{
                "capture_count": 7,
                "interval_seconds": 3,
                "heartbeat_each_capture": true,
                "optical_flow_groups": 0,
                "optical_flow_outputs": 0,
                "require_shutdown_handling": false
            }""",
        )

        self.assertEqual(requirements, MissionRequirements(7, 3.0, True))

    def test_parser_rejects_unexpected_model_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            requirements_from_json('{"capture_count": 1}')

    def test_pipeline_generates_evaluates_and_packages(self) -> None:
        source = "from sat_sdk import SatClient\nSatClient().camera.capture()\n"

        with tempfile.TemporaryDirectory() as temporary_directory:
            package = run_mission_pipeline(
                "Capture one image.",
                "candidate-001",
                generate_source=lambda *_args, **_kwargs: source,
                requirements_parser=lambda _: self.requirements,
                package_creator=lambda name, code, requirements: create_mission_package(
                    name,
                    code,
                    requirements,
                    candidates_root=Path(temporary_directory),
                ),
            )

            self.assertTrue(Path(package, "mission.py").is_file())
            self.assertTrue(Path(package, "manifest.json").is_file())

    def test_pipeline_repairs_the_best_failed_candidate_once(self) -> None:
        repaired = "from sat_sdk import SatClient\nSatClient().camera.capture()\n"
        repair_calls: list[list[str]] = []

        with tempfile.TemporaryDirectory() as temporary_directory:
            package = run_mission_pipeline(
                "Capture one image.",
                "candidate-001",
                generate_source=lambda *_args, **_kwargs: "print('missing capture')\n",
                requirements_parser=lambda _: self.requirements,
                repair_source=lambda _request, _source, failures, **_kwargs: repair_calls.append(failures) or repaired,
                package_creator=lambda name, code, requirements: create_mission_package(
                    name,
                    code,
                    requirements,
                    candidates_root=Path(temporary_directory),
                ),
            )

            self.assertTrue(Path(package, "mission.py").is_file())
        self.assertEqual(len(repair_calls), 1)


if __name__ == "__main__":
    unittest.main()
