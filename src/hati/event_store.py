"""Atomic, local-first storage for inspectable event traces."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from hati.models import (
    ActuationRecord,
    AnimalLabel,
    Classification,
    DecisionOutcome,
    DecisionRecord,
    EventRecord,
    FeedbackKind,
    HumanFeedback,
    InferenceTrace,
    LocalGateTrace,
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
        inference_trace = None
        if trace_raw:
            inference_trace = InferenceTrace(
                **{
                    **trace_raw,
                    "screening_frames": tuple(
                        int(value) for value in trace_raw.get("screening_frames", [])
                    ),
                    "completion_frames": tuple(
                        int(value) for value in trace_raw.get("completion_frames", [])
                    ),
                }
            )
        local_gate_raw = raw.get("local_gate_trace")
        local_gate_trace = None
        if local_gate_raw:
            local_gate_trace = LocalGateTrace(
                provider=str(local_gate_raw["provider"]),
                model=str(local_gate_raw["model"]),
                api=str(local_gate_raw["api"]),
                mode=str(local_gate_raw["mode"]),
                recommendation=str(local_gate_raw["recommendation"]),
                eligible_to_skip=bool(local_gate_raw["eligible_to_skip"]),
                panel_labels=tuple(
                    str(value) for value in local_gate_raw.get("panel_labels", [])
                ),
                panel_certainties=tuple(
                    str(value)
                    for value in local_gate_raw.get("panel_certainties", [])
                ),
                human_present=bool(local_gate_raw.get("human_present", False)),
                mammal_present=bool(local_gate_raw.get("mammal_present", False)),
                bird_present=bool(local_gate_raw.get("bird_present", False)),
                uncertain=bool(local_gate_raw.get("uncertain", True)),
                reason=str(local_gate_raw.get("reason", "")),
                contact_sheet_path=(
                    Path(local_gate_raw["contact_sheet_path"])
                    if local_gate_raw.get("contact_sheet_path")
                    else None
                ),
                focus_sheet_path=(
                    Path(local_gate_raw["focus_sheet_path"])
                    if local_gate_raw.get("focus_sheet_path")
                    else None
                ),
                request_count=int(local_gate_raw.get("request_count", 0)),
                latency_ms=local_gate_raw.get("latency_ms"),
                prompt_tokens=local_gate_raw.get("prompt_tokens"),
                completion_tokens=local_gate_raw.get("completion_tokens"),
                total_tokens=local_gate_raw.get("total_tokens"),
                error_type=local_gate_raw.get("error_type"),
            )
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
        actuation_raw = raw.get("actuation")
        actuation = None
        if actuation_raw:
            actuation = ActuationRecord(
                attempted_at=datetime.fromisoformat(actuation_raw["attempted_at"]),
                completed_at=(
                    datetime.fromisoformat(actuation_raw["completed_at"])
                    if actuation_raw.get("completed_at")
                    else None
                ),
                succeeded=(
                    bool(actuation_raw["succeeded"])
                    if actuation_raw.get("succeeded") is not None
                    else None
                ),
                detail=str(actuation_raw.get("detail", "")),
                physical_action=bool(actuation_raw.get("physical_action", False)),
            )
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
            local_gate_trace=local_gate_trace,
            inference_trace=inference_trace,
            decision=decision,
            actuation=actuation,
            feedback=feedback,
        )
