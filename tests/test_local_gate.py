from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from hati.config import LocalGateConfig
from hati.local_gate import (
    LocalGateError,
    build_contact_sheet,
    evaluate_local_gate,
    run_shadow_gate,
)


def frames(root: Path) -> list[Path]:
    paths = []
    for index in range(1, 6):
        image = np.full((180, 320, 3), index * 25, dtype=np.uint8)
        path = root / f"frame-{index:03d}.jpg"
        assert cv2.imwrite(str(path), image)
        paths.append(path)
    return paths


def response(
    labels: list[str],
    *,
    certainties: list[str] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    certainties = certainties or ["clear"] * 5
    content = {
        "panels": [
            {
                "frame_number": index,
                "label": label,
                "certainty": certainty,
            }
            for index, (label, certainty) in enumerate(
                zip(labels, certainties, strict=True),
                start=1,
            )
        ],
        "human_present": False,
        "mammal_present": False,
        "uncertain": False,
        "reason": "controlled local test",
    }
    content.update(overrides)
    return {
        "choices": [{"message": {"content": __import__("json").dumps(content)}}],
        "usage": {
            "prompt_tokens": 300,
            "completion_tokens": 40,
            "total_tokens": 340,
        },
    }


class LocalGateTests(unittest.TestCase):
    def test_contact_sheet_contains_five_numbered_panels(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = build_contact_sheet(frames(root), root / "sheet.jpg")
            image = cv2.imread(str(output))

        self.assertIsNotNone(image)
        self.assertEqual((1080, 1280), image.shape[:2])

    def test_confirmed_bird_only_event_is_shadow_skip_candidate(self) -> None:
        calls: list[dict[str, Any]] = []

        def requester(url: str, payload: dict[str, Any], timeout: int):
            calls.append({"url": url, "payload": payload, "timeout": timeout})
            return response(["chicken", "chicken", "chicken", "goose", "empty"])

        with tempfile.TemporaryDirectory() as temporary:
            trace = evaluate_local_gate(
                frames(Path(temporary)),
                LocalGateConfig(enabled=True),
                requester=requester,
            )

        self.assertTrue(trace.eligible_to_skip)
        self.assertEqual("would_skip_luna", trace.recommendation)
        self.assertTrue(trace.bird_present)
        self.assertEqual(("clear",) * 5, trace.panel_certainties)
        self.assertEqual(1, trace.request_count)
        self.assertEqual(340, trace.total_tokens)
        self.assertEqual("none", calls[0]["payload"]["reasoning_effort"])
        self.assertIn("127.0.0.1", calls[0]["url"])
        schema = calls[0]["payload"]["response_format"]["json_schema"]["schema"]
        self.assertEqual(160, schema["properties"]["reason"]["maxLength"])
        image_parts = [
            part
            for part in calls[0]["payload"]["messages"][1]["content"]
            if part["type"] == "image_url"
        ]
        user_prompt = calls[0]["payload"]["messages"][1]["content"][0]["text"]
        self.assertIn("using only visible evidence", user_prompt)
        self.assertNotIn("poultry", user_prompt.lower())
        self.assertEqual(5, len(image_parts))

    def test_clear_human_suppresses_while_unknown_escalates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            human = evaluate_local_gate(
                frames(root),
                LocalGateConfig(enabled=True),
                requester=lambda *_: response(
                    ["chicken", "human", "chicken", "chicken", "empty"],
                    human_present=False,
                ),
            )
            unknown = evaluate_local_gate(
                frames(root),
                LocalGateConfig(enabled=True),
                requester=lambda *_: response(
                    ["chicken", "chicken", "unknown", "chicken", "empty"]
                ),
            )

        self.assertTrue(human.eligible_to_skip)
        self.assertTrue(human.human_present)
        self.assertEqual("would_skip_luna", human.recommendation)
        self.assertFalse(unknown.eligible_to_skip)
        self.assertTrue(unknown.uncertain)

    def test_likely_human_suppresses_but_uncertain_human_escalates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            likely = evaluate_local_gate(
                frames(root),
                LocalGateConfig(enabled=True),
                requester=lambda *_: response(
                    ["empty", "human", "empty", "empty", "empty"],
                    certainties=["clear", "likely", "clear", "clear", "clear"],
                    human_present=True,
                    uncertain=True,
                ),
            )
            uncertain = evaluate_local_gate(
                frames(root),
                LocalGateConfig(enabled=True),
                requester=lambda *_: response(
                    ["empty", "human", "empty", "empty", "empty"],
                    certainties=["clear", "uncertain", "clear", "clear", "clear"],
                    human_present=True,
                    uncertain=True,
                ),
            )

        self.assertTrue(likely.eligible_to_skip)
        self.assertEqual("would_skip_luna", likely.recommendation)
        self.assertFalse(uncertain.eligible_to_skip)
        self.assertEqual("would_escalate_to_luna", uncertain.recommendation)

    def test_likely_bird_escalates_instead_of_skipping(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            trace = evaluate_local_gate(
                frames(Path(temporary)),
                LocalGateConfig(enabled=True),
                requester=lambda *_: response(
                    ["chicken"] * 5,
                    certainties=["clear", "clear", "likely", "clear", "clear"],
                    uncertain=False,
                ),
            )

        self.assertFalse(trace.eligible_to_skip)
        self.assertEqual("would_escalate_to_luna", trace.recommendation)
        self.assertTrue(trace.uncertain)

    def test_one_clear_bird_with_clear_empty_frames_is_enough_to_skip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            trace = evaluate_local_gate(
                frames(Path(temporary)),
                LocalGateConfig(enabled=True),
                requester=lambda *_: response(
                    ["empty", "empty", "chicken", "empty", "empty"],
                ),
            )

        self.assertTrue(trace.eligible_to_skip)
        self.assertEqual("would_skip_luna", trace.recommendation)
        self.assertEqual(("clear",) * 5, trace.panel_certainties)

    def test_duplicate_panel_numbers_fail_closed(self) -> None:
        duplicate = response(["chicken"] * 5)
        content = __import__("json").loads(duplicate["choices"][0]["message"]["content"])
        content["panels"][4]["frame_number"] = 4
        duplicate["choices"][0]["message"]["content"] = __import__("json").dumps(content)

        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(LocalGateError):
                evaluate_local_gate(
                    frames(Path(temporary)),
                    LocalGateConfig(enabled=True),
                    requester=lambda *_: duplicate,
                )

    def test_shadow_failure_records_escalation_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            trace = run_shadow_gate(
                frames(Path(temporary)),
                LocalGateConfig(enabled=True),
                requester=lambda *_: (_ for _ in ()).throw(TimeoutError()),
            )

        self.assertFalse(trace.eligible_to_skip)
        self.assertEqual("would_escalate_to_luna", trace.recommendation)
        self.assertEqual("TimeoutError", trace.error_type)
