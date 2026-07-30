import contextlib
import io
import unittest
import tempfile
from pathlib import Path

from agents.evaluator import EvaluationResult, EvaluationRun, ExecutionRecord, empty_record
from agents.packager import create_mission_package
from agents.pipeline import CandidateSource, behavior_failures, run_mission_pipeline, select_candidate
from agents.requirements import (
    MissionRequirements,
    build_requirement_prompt,
    parse_mission_request,
    requirements_from_json,
)


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

    def test_parser_prompt_does_not_invent_omitted_one_capture_options(self) -> None:
        system_prompt = " ".join(
            build_requirement_prompt("Capture one image.")[0]["content"].split()
        )

        self.assertIn("set `interval_seconds` to 1", system_prompt)
        self.assertIn("to false when they are not mentioned", system_prompt)

    def test_parser_rejects_unexpected_model_fields(self) -> None:
        with self.assertRaisesRegex(ValueError, "unsupported fields"):
            requirements_from_json('{"capture_count": 1}')

    def test_accepts_optical_flow_groups_of_four(self) -> None:
        requirements = MissionRequirements(12, 0.5, True, 3, 9, True)
        run = EvaluationRun(
            EvaluationResult(True, 100, []),
            ExecutionRecord(12, 12, 0, [0.5] * 11, ["outputs/flow.jpg"] * 9, 9),
        )

        failures = behavior_failures(
            "for start in range(0, len(frames), 4):\n    pass\n"
            "cv2.calcOpticalFlowPyrLK(previous, current, points, None)\n"
            "signal.signal(signal.SIGTERM, handler)\n",
            run,
            requirements,
        )

        self.assertNotIn("Frames were not split into groups of 4", failures)

    def test_pipeline_generates_evaluates_and_packages(self) -> None:
        source = "from sat_sdk import SatClient\nSatClient().camera.capture()\n"
        stdout = io.StringIO()

        with tempfile.TemporaryDirectory() as temporary_directory, contextlib.redirect_stdout(stdout):
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
        self.assertIn("Parsing natural-language mission request", stdout.getvalue())
        self.assertIn("candidate passed", stdout.getvalue())
        self.assertIn("Mission package ready", stdout.getvalue())

    def test_pipeline_passes_parsed_requirements_to_generation(self) -> None:
        source = "from sat_sdk import SatClient\nSatClient().camera.capture()\n"
        received: list[MissionRequirements] = []

        def generate(_request: str, _variant: str, **kwargs: object) -> str:
            received.append(kwargs["requirements"])
            return source

        with tempfile.TemporaryDirectory() as temporary_directory:
            run_mission_pipeline(
                "Capture one image.",
                "candidate-001",
                generate_source=generate,
                requirements_parser=lambda _: self.requirements,
                package_creator=lambda name, code, requirements: create_mission_package(
                    name,
                    code,
                    requirements,
                    candidates_root=Path(temporary_directory),
                ),
            )

        self.assertGreaterEqual(len(received), 1)
        self.assertTrue(all(item == self.requirements for item in received))

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
