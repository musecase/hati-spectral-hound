"""Controlled observations for exercising decision logic without wildlife or hardware."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from hati.models import AnimalLabel, Classification, EventRecord, ProcessingState


SCENARIOS = ("raccoon", "human", "chicken", "low-consensus")


def _classification(frame: int, animal: AnimalLabel) -> Classification:
    predator = animal in {
        AnimalLabel.RACCOON,
        AnimalLabel.FOX,
        AnimalLabel.COYOTE,
        AnimalLabel.OPOSSUM,
        AnimalLabel.SKUNK,
    }
    return Classification(
        frame_id=f"frame-{frame:02d}",
        animal=animal,
        predator=predator,
        confidence=0.93 if animal is not AnimalLabel.UNKNOWN else 0.25,
        evidence=("controlled simulation",),
        safe_to_deter=predator,
    )


def build_simulated_event(
    scenario: str, camera_id: str, zone: str
) -> EventRecord:
    if scenario not in SCENARIOS:
        raise ValueError(f"Unknown scenario: {scenario}")

    labels: dict[str, list[AnimalLabel]] = {
        "raccoon": [AnimalLabel.RACCOON] * 4 + [AnimalLabel.UNKNOWN],
        "human": [AnimalLabel.RACCOON] * 4 + [AnimalLabel.HUMAN],
        "chicken": [AnimalLabel.CHICKEN] * 5,
        "low-consensus": [
            AnimalLabel.RACCOON,
            AnimalLabel.RACCOON,
            AnimalLabel.UNKNOWN,
            AnimalLabel.CHICKEN,
            AnimalLabel.UNKNOWN,
        ],
    }
    now = datetime.now(timezone.utc)
    return EventRecord(
        event_id=f"sim-{now:%Y%m%dT%H%M%S}-{uuid4().hex[:8]}",
        start_time=now,
        end_time=now,
        camera_id=camera_id,
        zone=zone,
        trigger_reason=f"controlled simulation: {scenario}",
        processing_state=ProcessingState.CLASSIFIED,
        classifications=[
            _classification(index, label)
            for index, label in enumerate(labels[scenario], start=1)
        ],
    )
