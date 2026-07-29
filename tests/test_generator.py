import unittest

from agents.generator import build_generation_prompt, generate_mission_source


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
        self.assertNotIn("tool", calls[0][0]["content"].lower())

    def test_robust_prompt_includes_optical_flow_reference_when_requested(self) -> None:
        messages = build_generation_prompt(
            "Capture twenty images.",
            "robust",
            include_optical_flow=True,
        )

        self.assertIn("Lucas-Kanade", messages[1]["content"])
        self.assertIn("shutdown handling", messages[1]["content"])


if __name__ == "__main__":
    unittest.main()
