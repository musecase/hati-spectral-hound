from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from hati.config import load_config
from hati.demo import EXPECTED, run_demo_case
from hati.models import DecisionOutcome


def demo_config(root: Path) -> Path:
    payload = {
        "camera": {"camera_id": "demo-camera", "host": "192.0.2.10"},
        "events": {
            "event_directory": str(root / "events"),
            "protected_zones": ["COOP_DOOR_ZONE"],
            "frames_per_event": 5,
        },
        "decision": {
            "minimum_usable_observations": 5,
            "predator_consensus_required": 4,
            "cooldown_seconds": 600,
            "predator_labels": ["raccoon", "fox", "coyote", "opossum", "skunk"],
        },
        "runtime": {"armed": False, "test_mode": True},
    }
    path = root / "demo-config.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class DemoTests(unittest.TestCase):
    def test_all_expected_scenarios_pass_without_real_actuator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = load_config(demo_config(Path(temporary)))
            results = {name: run_demo_case(config, name) for name in EXPECTED}

        self.assertTrue(all(result.passed for result in results.values()))
        self.assertTrue(results["raccoon"].dry_run_called)
        self.assertEqual(
            DecisionOutcome.AUTHORIZE, results["raccoon"].event.decision.outcome
        )
        self.assertFalse(results["human"].dry_run_called)
        self.assertEqual("HUMAN_VETO", results["human"].event.decision.reason_code)
        self.assertFalse(results["chicken"].dry_run_called)
        self.assertFalse(results["low-consensus"].dry_run_called)

    def test_published_sample_cases_match_executable_demo(self) -> None:
        sample_path = (
            Path(__file__).resolve().parents[1]
            / "sample_data"
            / "eval_cases.json"
        )
        sample = json.loads(sample_path.read_text(encoding="utf-8"))
        published = {case["scenario"]: case for case in sample["cases"]}

        with tempfile.TemporaryDirectory() as temporary:
            config = load_config(demo_config(Path(temporary)))
            results = {name: run_demo_case(config, name) for name in EXPECTED}

        self.assertEqual(set(EXPECTED), set(published))
        for name, result in results.items():
            case = published[name]
            self.assertEqual(case["expected_outcome"], result.event.decision.outcome)
            self.assertEqual(case["expected_reason"], result.event.decision.reason_code)
            self.assertEqual(case["expected_dry_run"], result.dry_run_called)


if __name__ == "__main__":
    unittest.main()
