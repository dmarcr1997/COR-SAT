import unittest
import tempfile
from pathlib import Path

from agents.evaluator import EvaluationResult, EvaluationRun, empty_record
from agents.packager import create_mission_package
from agents.pipeline import CandidateSource, run_mission_pipeline, select_candidate
from agents.requirements import parse_mission_request


class CandidateSelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.requirements = parse_mission_request("Capture one image.")

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

    def test_request_matching_is_whitespace_insensitive(self) -> None:
        requirements = parse_mission_request(" Capture five images at two-second intervals.\n")

        self.assertEqual(requirements.capture_count, 5)
        self.assertEqual(requirements.interval_seconds, 2.0)

    def test_accepts_equivalent_optical_flow_wording(self) -> None:
        requirements = parse_mission_request(
            """Capture 20 images at one-second intervals.

            Split the captured images into groups of five frames.

            For each group, calculate sparse Lucas-Kanade optical flow between consecutive frames
            and save each visualization as a JPEG inside outputs/optical-flow.

            Produce 16 optical-flow images total.

            Handle shutdown signals and call heartbeat during every capture."""
        )

        self.assertEqual(requirements.capture_count, 20)
        self.assertTrue(requirements.uses_optical_flow)

    def test_pipeline_generates_evaluates_and_packages(self) -> None:
        source = "from sat_sdk import SatClient\nSatClient().camera.capture()\n"

        with tempfile.TemporaryDirectory() as temporary_directory:
            package = run_mission_pipeline(
                "Capture one image.",
                "candidate-001",
                generate_source=lambda *_args, **_kwargs: source,
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
