import unittest

from agents.evaluator import EvaluationResult, EvaluationRun, empty_record
from agents.pipeline import CandidateSource, select_candidate
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


if __name__ == "__main__":
    unittest.main()
