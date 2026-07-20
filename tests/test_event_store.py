from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hati.event_store import EventStore
from hati.models import (
    ActuationRecord,
    EventRecord,
    InferenceTrace,
    LocalGateTrace,
    ProcessingState,
)


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

    def test_local_shadow_gate_trace_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event = EventRecord(
                event_id="event-local-gate",
                start_time=datetime(2026, 7, 18, tzinfo=timezone.utc),
                camera_id="coop-g4",
                zone="COOP_DOOR_ZONE",
                trigger_reason="motion",
                local_gate_trace=LocalGateTrace(
                    provider="lm_studio",
                    model="google/gemma-4-e4b",
                    api="openai_compatible_chat_completions",
                    mode="shadow",
                    recommendation="would_skip_luna",
                    eligible_to_skip=True,
                    panel_labels=("chicken",) * 5,
                    panel_certainties=("clear",) * 5,
                    bird_present=True,
                    uncertain=False,
                    contact_sheet_path=root / "sheet.jpg",
                    focus_sheet_path=root / "focus-sheet.jpg",
                    request_count=1,
                ),
            )
            path = EventStore(root).save(event)
            loaded = EventStore.load(path)

        self.assertIsNotNone(loaded.local_gate_trace)
        self.assertTrue(loaded.local_gate_trace.eligible_to_skip)
        self.assertEqual(("chicken",) * 5, loaded.local_gate_trace.panel_labels)
        self.assertEqual(("clear",) * 5, loaded.local_gate_trace.panel_certainties)

    def test_actuating_marker_round_trips_for_restart_safety(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            attempted = datetime(2026, 7, 15, tzinfo=timezone.utc)
            event = EventRecord(
                event_id="event-reserved",
                start_time=attempted,
                camera_id="coop-g4",
                zone="COOP_DOOR_ZONE",
                trigger_reason="motion",
                processing_state=ProcessingState.ACTUATING,
                actuation=ActuationRecord(
                    attempted_at=attempted,
                    completed_at=None,
                    succeeded=None,
                    detail="reserved",
                    physical_action=True,
                ),
            )
            path = EventStore(Path(temporary)).save(event)
            loaded = EventStore.load(path)

        self.assertEqual(ProcessingState.ACTUATING, loaded.processing_state)
        self.assertTrue(loaded.actuation.physical_action)
        self.assertIsNone(loaded.actuation.succeeded)


if __name__ == "__main__":
    unittest.main()
