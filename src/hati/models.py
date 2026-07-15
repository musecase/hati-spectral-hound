"""Typed records shared by capture, vision, decision, actuation, and review."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AnimalLabel(StrEnum):
    HUMAN = "human"
    DOG = "dog"
    CAT = "cat"
    CHICKEN = "chicken"
    GOOSE = "goose"
    RACCOON = "raccoon"
    FOX = "fox"
    COYOTE = "coyote"
    OPOSSUM = "opossum"
    SKUNK = "skunk"
    UNKNOWN = "unknown"


class ProcessingState(StrEnum):
    CAPTURED = "captured"
    CLASSIFIED = "classified"
    DECIDED = "decided"
    ACTUATED = "actuated"
    FAILED = "failed"


class DecisionOutcome(StrEnum):
    AUTHORIZE = "authorize"
    DENY = "deny"
    SUPPRESS = "suppress"


class FeedbackKind(StrEnum):
    CORRECT = "correct"
    FALSE_ALARM = "false_alarm"
    WRONG_ANIMAL = "wrong_animal"
    MISSED_THREAT = "missed_threat"
    INAPPROPRIATE_ACTUATION = "inappropriate_actuation"
    EXPECTED_ACTUATION_MISSING = "expected_actuation_missing"


@dataclass(frozen=True)
class Classification:
    frame_id: str
    animal: AnimalLabel
    predator: bool
    confidence: float
    evidence: tuple[str, ...] = ()
    safe_to_deter: bool = False
    usable: bool = True

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")


@dataclass(frozen=True)
class InferenceTrace:
    provider: str
    model: str
    api: str
    image_detail: str
    reasoning_effort: str
    request_count: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class HumanFeedback:
    kind: FeedbackKind
    source: str
    actor_id: str
    recorded_at: datetime = field(default_factory=utc_now)
    note: str | None = None


@dataclass
class EventRecord:
    event_id: str
    start_time: datetime
    camera_id: str
    zone: str
    trigger_reason: str
    end_time: datetime | None = None
    frame_paths: list[Path] = field(default_factory=list)
    processing_state: ProcessingState = ProcessingState.CAPTURED
    classifications: list[Classification] = field(default_factory=list)
    inference_trace: InferenceTrace | None = None
    decision: "DecisionRecord | None" = None
    feedback: list[HumanFeedback] = field(default_factory=list)


@dataclass(frozen=True)
class SystemState:
    armed: bool
    actuator_available: bool
    cooldown_until: datetime | None = None
    event_already_actuated: bool = False


@dataclass(frozen=True)
class DecisionRecord:
    outcome: DecisionOutcome
    reason_code: str
    explanation: str
    usable_observations: int
    predator_votes: int
    consensus_label: AnimalLabel | None
    human_veto: bool
    decided_at: datetime = field(default_factory=utc_now)


def to_jsonable(value: Any) -> Any:
    """Convert HATI records to JSON-compatible values without losing structure."""
    if hasattr(value, "__dataclass_fields__"):
        return {key: to_jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_jsonable(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, StrEnum):
        return value.value
    return value
