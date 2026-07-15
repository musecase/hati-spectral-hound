from __future__ import annotations

import unittest
from pathlib import Path

from hati.config import DecisionConfig
from hati.evaluation import evaluate_improvement


class EvaluationTests(unittest.TestCase):
    def test_candidate_is_promoted_only_after_fix_without_regression(self) -> None:
        fixture = (
            Path(__file__).resolve().parents[1]
            / "sample_data"
            / "improvement_cases.json"
        )
        report = evaluate_improvement(
            fixture,
            DecisionConfig(),
            "COOP_DOOR_ZONE",
        )
        self.assertEqual(3, report.baseline_passed)
        self.assertEqual(4, report.candidate_passed)
        self.assertEqual(0, report.regressions)
        self.assertEqual(1, report.corrected_failures)
        self.assertTrue(report.candidate_promoted)

    def test_empty_fixture_fails_closed(self) -> None:
        with self.assertRaises(FileNotFoundError):
            evaluate_improvement(
                "missing-improvement-fixture.json",
                DecisionConfig(),
                "COOP_DOOR_ZONE",
            )


if __name__ == "__main__":
    unittest.main()
