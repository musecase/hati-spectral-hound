"""Atomic, local-first storage for inspectable event traces."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from hati.models import (
    AnimalLabel,
    Classification,
    DecisionOutcome,
    DecisionRecord,
    EventRecord,
    FeedbackKind,
    HumanFeedback,
    InferenceTrace,
    ProcessingState,
    to_jsonable,
)


class EventStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def save(self, event: EventRecord) -> Path:
        event_dir = self.root / event.event_id
        event_dir.mkdir(parents=True, exist_ok=True)
        destination = event_dir / "event.json"
        temporary = event_dir / "event.json.tmp"
        temporary.write_text(
            json.dumps(to_jsonable(event), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, destination)
        return destination

    @staticmethod
    def load(path: str | Path) -> EventRecord:
        """Load an inspectable trace back into the typed event model."""
        source = Path(path)
        raw = json.loads(source.read_text(encoding="utf-8"))
        classifications = [
            Classification(
                frame_id=str(item["frame_id"]),
                animal=AnimalLabel(item["animal"]),
                predator=bool(item["predator"]),
                confidence=float(item["confidence"]),
                evidence=tuple(str(value) for value in item.get("evidence", [])),
                safe_to_deter=bool(item.get("safe_to_deter", False)),
                usable=bool(item.get("usable", True)),
            )
            for item in raw.get("classifications", [])
        ]
        trace_raw = raw.get("inference_trace")
        inference_trace = InferenceTrace(**trace_raw) if trace_raw else None
        decision_raw = raw.get("decision")
        decision = None
        if decision_raw:
            consensus = decision_raw.get("consensus_label")
            decision = DecisionRecord(
                outcome=DecisionOutcome(decision_raw["outcome"]),
                reason_code=str(decision_raw["reason_code"]),
                explanation=str(decision_raw["explanation"]),
                usable_observations=int(decision_raw["usable_observations"]),
                predator_votes=int(decision_raw["predator_votes"]),
                consensus_label=AnimalLabel(consensus) if consensus else None,
                human_veto=bool(decision_raw["human_veto"]),
                decided_at=datetime.fromisoformat(decision_raw["decided_at"]),
            )
        feedback = [
            HumanFeedback(
                kind=FeedbackKind(item["kind"]),
                source=str(item["source"]),
                actor_id=str(item["actor_id"]),
                recorded_at=datetime.fromisoformat(item["recorded_at"]),
                note=str(item["note"]) if item.get("note") else None,
            )
            for item in raw.get("feedback", [])
        ]
        return EventRecord(
            event_id=str(raw["event_id"]),
            start_time=datetime.fromisoformat(raw["start_time"]),
            end_time=(
                datetime.fromisoformat(raw["end_time"])
                if raw.get("end_time")
                else None
            ),
            camera_id=str(raw["camera_id"]),
            zone=str(raw["zone"]),
            trigger_reason=str(raw["trigger_reason"]),
            frame_paths=[Path(value) for value in raw.get("frame_paths", [])],
            processing_state=ProcessingState(raw.get("processing_state", "captured")),
            classifications=classifications,
            inference_trace=inference_trace,
            decision=decision,
            feedback=feedback,
        )
