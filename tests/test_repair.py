import unittest

from agents.repair import build_repair_prompt, repair_mission_source


class RepairTests(unittest.TestCase):
    def test_repair_prompt_contains_source_and_concrete_failures(self) -> None:
        messages = build_repair_prompt(
            "Capture one image.",
            "print('broken')",
            ["Expected 1 captures, got 0", "Expected waits [], got [1.0]"],
            include_optical_flow=False,
        )

        content = messages[1]["content"]
        self.assertIn("print('broken')", content)
        self.assertIn("Expected 1 captures, got 0", content)
        self.assertIn("Capture one image.", content)

    def test_repair_returns_python_source(self) -> None:
        source = repair_mission_source(
            "Capture one image.",
            "broken",
            ["Syntax error"],
            include_optical_flow=False,
            model_call=lambda _: "```python\nprint('repaired')\n```",
        )

        self.assertEqual(source, "print('repaired')\n")


if __name__ == "__main__":
    unittest.main()
