from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hati.config import VisionConfig
from hati.models import AnimalLabel
from hati.vision import (
    FrameObservation,
    VisionBurst,
    VisionCompletion,
    VisionError,
    VisionScreen,
    classify_frames,
)


class FakeResponses:
    def __init__(self, output: Any | list[Any]) -> None:
        self.outputs = output if isinstance(output, list) else [output]
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=self.outputs[len(self.calls) - 1],
            usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
        )


class FakeOpenAI:
    def __init__(self, output: Any | list[Any]) -> None:
        self.responses = FakeResponses(output)


def observation(
    frame: int,
    animal: AnimalLabel,
    *,
    safe_to_deter: bool = False,
) -> FrameObservation:
    return FrameObservation(
        frame_number=frame,
        animal=animal,
        confidence=0.9,
        evidence=["synthetic visual cue"],
        safe_to_deter=safe_to_deter,
        usable=True,
    )


class VisionTests(unittest.TestCase):
    def test_five_frames_are_sent_once_with_bounded_detail_and_structured_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for index in range(1, 6):
                path = Path(temporary) / f"frame-{index:03d}.jpg"
                path.write_bytes(b"synthetic-jpeg")
                paths.append(path)
            output = VisionBurst(
                observations=[
                    observation(1, AnimalLabel.RACCOON, safe_to_deter=True),
                    observation(2, AnimalLabel.RACCOON, safe_to_deter=True),
                    observation(3, AnimalLabel.HUMAN),
                    observation(4, AnimalLabel.RACCOON, safe_to_deter=True),
                    observation(5, AnimalLabel.UNKNOWN),
                ]
            )
            client = FakeOpenAI(output)

            result = classify_frames(
                paths,
                VisionConfig(),
                client=client,
                policy_id="candidate-test",
                policy_addendum="Treat plush decoys as unknown.",
                cascade=False,
            )

        self.assertEqual(1, len(client.responses.calls))
        request = client.responses.calls[0]
        self.assertEqual("gpt-5.6-luna", request["model"])
        self.assertEqual({"effort": "low"}, request["reasoning"])
        self.assertIn("Treat plush decoys as unknown", request["input"][0]["content"])
        self.assertFalse(request["store"])
        content = request["input"][1]["content"]
        image_parts = [part for part in content if part["type"] == "input_image"]
        self.assertEqual(5, len(image_parts))
        self.assertTrue(all(part["detail"] == "high" for part in image_parts))
        self.assertTrue(
            all(part["image_url"].startswith("data:image/jpeg;base64,") for part in image_parts)
        )
        self.assertEqual(AnimalLabel.HUMAN, result.classifications[2].animal)
        self.assertTrue(result.classifications[0].predator)
        self.assertFalse(result.classifications[0].safe_to_deter)
        self.assertEqual(1, result.trace.request_count)
        self.assertEqual("candidate-test", result.trace.policy_id)
        self.assertEqual(120, result.trace.total_tokens)
        self.assertEqual(5, result.trace.image_count)
        self.assertFalse(result.trace.screen_dismissed)

    def test_frames_two_and_four_can_dismiss_a_benign_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for index in range(1, 6):
                path = Path(temporary) / f"frame-{index:03d}.jpg"
                path.write_bytes(b"synthetic-jpeg")
                paths.append(path)
            client = FakeOpenAI(
                VisionScreen(
                    observations=[
                        observation(2, AnimalLabel.CHICKEN),
                        observation(4, AnimalLabel.EMPTY),
                    ]
                )
            )

            result = classify_frames(paths, VisionConfig(), client=client)

        self.assertEqual(1, len(client.responses.calls))
        content = client.responses.calls[0]["input"][1]["content"]
        image_parts = [part for part in content if part["type"] == "input_image"]
        labels = [part["text"] for part in content if part["type"] == "input_text"]
        self.assertEqual(2, len(image_parts))
        self.assertIn("Frame 2 of 5", labels)
        self.assertIn("Frame 4 of 5", labels)
        self.assertEqual(("frame-002", "frame-004"), tuple(
            item.frame_id for item in result.classifications
        ))
        self.assertEqual(1, result.trace.request_count)
        self.assertEqual(2, result.trace.image_count)
        self.assertEqual((2, 4), result.trace.screening_frames)
        self.assertTrue(result.trace.screen_dismissed)

    def test_uncertain_screen_requests_remaining_frames_and_combines_all_five(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for index in range(1, 6):
                path = Path(temporary) / f"frame-{index:03d}.jpg"
                path.write_bytes(b"synthetic-jpeg")
                paths.append(path)
            client = FakeOpenAI(
                [
                    VisionScreen(
                        observations=[
                            observation(2, AnimalLabel.RACCOON, safe_to_deter=True),
                            observation(4, AnimalLabel.UNKNOWN),
                        ]
                    ),
                    VisionCompletion(
                        observations=[
                            observation(1, AnimalLabel.RACCOON, safe_to_deter=True),
                            observation(3, AnimalLabel.RACCOON, safe_to_deter=True),
                            observation(5, AnimalLabel.RACCOON, safe_to_deter=True),
                        ]
                    ),
                ]
            )

            result = classify_frames(paths, VisionConfig(), client=client)

        self.assertEqual(2, len(client.responses.calls))
        image_counts = [
            len(
                [
                    part
                    for part in call["input"][1]["content"]
                    if part["type"] == "input_image"
                ]
            )
            for call in client.responses.calls
        ]
        self.assertEqual([2, 3], image_counts)
        self.assertEqual(
            tuple(f"frame-{index:03d}" for index in range(1, 6)),
            tuple(item.frame_id for item in result.classifications),
        )
        self.assertEqual(2, result.trace.request_count)
        self.assertEqual(5, result.trace.image_count)
        self.assertEqual((1, 3, 5), result.trace.completion_frames)
        self.assertEqual(240, result.trace.total_tokens)
        self.assertFalse(result.trace.screen_dismissed)

    def test_exactly_five_frames_are_required_before_any_request(self) -> None:
        client = FakeOpenAI(
            VisionBurst(
                observations=[
                    observation(index, AnimalLabel.UNKNOWN) for index in range(1, 6)
                ]
            )
        )
        with self.assertRaises(VisionError):
            classify_frames([], VisionConfig(), client=client)
        self.assertEqual([], client.responses.calls)

    def test_duplicate_frame_numbers_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = []
            for index in range(1, 6):
                path = Path(temporary) / f"frame-{index:03d}.jpg"
                path.write_bytes(b"synthetic-jpeg")
                paths.append(path)
            output = VisionBurst(
                observations=[
                    observation(1, AnimalLabel.UNKNOWN),
                    observation(1, AnimalLabel.UNKNOWN),
                    observation(3, AnimalLabel.UNKNOWN),
                    observation(4, AnimalLabel.UNKNOWN),
                    observation(5, AnimalLabel.UNKNOWN),
                ]
            )
            with self.assertRaises(VisionError):
                classify_frames(
                    paths,
                    VisionConfig(),
                    client=FakeOpenAI(output),
                    cascade=False,
                )


if __name__ == "__main__":
    unittest.main()
