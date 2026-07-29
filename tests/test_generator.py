import threading
import unittest

from agents.generator import (
    build_generation_prompt,
    generate_mission_source,
    generate_two_candidates,
)
from agents.requirements import MissionRequirements


class GeneratorTests(unittest.TestCase):
    def test_generator_requests_source_without_tools(self) -> None:
        calls: list[list[dict[str, str]]] = []

        source = generate_mission_source(
            "Capture one image.",
            "minimal",
            model_call=lambda messages: calls.append(messages) or "```python\nprint('ok')\n```",
        )

        self.assertEqual(source, "print('ok')\n")
        self.assertEqual(len(calls), 1)
        system_prompt = calls[0][0]["content"]
        self.assertNotIn("tool", system_prompt.lower())
        self.assertNotIn("Do not invoke external functions", system_prompt)
        self.assertIn("Execute every SDK call required", " ".join(system_prompt.split()))

    def test_robust_prompt_includes_optical_flow_reference_when_requested(self) -> None:
        messages = build_generation_prompt(
            "Capture twenty images.",
            "robust",
            include_optical_flow=True,
        )

        self.assertIn("Lucas-Kanade", messages[1]["content"])
        self.assertIn("shutdown handling", messages[1]["content"])

    def test_prompt_includes_authoritative_validated_requirements(self) -> None:
        messages = build_generation_prompt(
            "Capture one image.",
            "minimal",
            include_optical_flow=False,
            requirements=MissionRequirements(1, 1.0, False),
        )

        content = messages[1]["content"]
        self.assertIn("Validated requirements (authoritative", content)
        self.assertIn('"capture_count": 1', content)
        self.assertIn('"heartbeat_each_capture": false', content)
        self.assertIn('"require_shutdown_handling": false', content)

    def test_generates_independent_candidates_concurrently(self) -> None:
        barrier = threading.Barrier(2)

        def generate(request: str, variant: str, **_: object) -> str:
            self.assertEqual(request, "Capture one image.")
            barrier.wait(timeout=1)
            return f"# {variant}\n"

        candidates = generate_two_candidates(
            "Capture one image.",
            include_optical_flow=False,
            generate_source=generate,
        )

        self.assertEqual(candidates, {"minimal": "# minimal\n", "robust": "# robust\n"})

    def test_passes_validated_requirements_to_each_generator(self) -> None:
        received: list[MissionRequirements] = []
        requirements = MissionRequirements(1, 1.0, False)

        def generate(_request: str, variant: str, **kwargs: object) -> str:
            received.append(kwargs["requirements"])
            return f"# {variant}\n"

        generate_two_candidates(
            "Capture one image.",
            include_optical_flow=False,
            requirements=requirements,
            generate_source=generate,
        )

        self.assertEqual(received, [requirements, requirements])

    def test_stops_after_consumer_accepts_a_candidate(self) -> None:
        consumed: list[str] = []

        candidates = generate_two_candidates(
            "Capture one image.",
            include_optical_flow=False,
            generate_source=lambda _request, variant, **_: f"# {variant}\n",
            on_candidate=lambda variant, _source: consumed.append(variant) or True,
        )

        self.assertEqual(len(consumed), 1)
        self.assertEqual(set(candidates), set(consumed))


if __name__ == "__main__":
    unittest.main()
