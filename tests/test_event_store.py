from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hati.event_store import EventStore
from hati.models import EventRecord, InferenceTrace, ProcessingState


class EventStoreTests(unittest.TestCase):
    def test_event_is_written_as_inspectable_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            event = EventRecord(
                event_id="event-001",
                start_time=datetime(2026, 7, 13, tzinfo=timezone.utc),
                camera_id="coop-g4",
                zone="COOP_DOOR_ZONE",
                trigger_reason="motion",
            )
            path = EventStore(Path(temporary)).save(event)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("event-001", payload["event_id"])
            self.assertEqual("captured", payload["processing_state"])
            self.assertFalse((path.parent / "event.json.tmp").exists())

    def test_saved_classified_event_round_trips_with_inference_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            event = EventRecord(
                event_id="event-vision",
                start_time=datetime(2026, 7, 14, tzinfo=timezone.utc),
                camera_id="coop-g4",
                zone="COOP_DOOR_ZONE",
                trigger_reason="motion",
                processing_state=ProcessingState.CLASSIFIED,
                inference_trace=InferenceTrace(
                    provider="openai",
                    model="gpt-5.6-luna",
                    api="responses",
                    image_detail="high",
                    reasoning_effort="low",
                    request_count=1,
                    total_tokens=120,
                ),
            )
            path = EventStore(Path(temporary)).save(event)

            loaded = EventStore.load(path)

        self.assertEqual(ProcessingState.CLASSIFIED, loaded.processing_state)
        self.assertIsNotNone(loaded.inference_trace)
        self.assertEqual("gpt-5.6-luna", loaded.inference_trace.model)


if __name__ == "__main__":
    unittest.main()
