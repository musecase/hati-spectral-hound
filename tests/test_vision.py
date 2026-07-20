from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from hati.config import VisionConfig
from hati.models import AnimalLabel
from hati.vision import FrameObservation, VisionBurst, VisionError, classify_frames


class FakeResponses:
    def __init__(self, output: VisionBurst) -> None:
        self.output = output
        self.calls: list[dict[str, Any]] = []

    def parse(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return SimpleNamespace(
            output_parsed=self.output,
            usage=SimpleNamespace(input_tokens=100, output_tokens=20, total_tokens=120),
        )


class FakeOpenAI:
    def __init__(self, output: VisionBurst) -> None:
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
                classify_frames(paths, VisionConfig(), client=FakeOpenAI(output))


if __name__ == "__main__":
    unittest.main()
