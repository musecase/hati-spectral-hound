"""Feedback-derived, regression-gated vision policy improvements.

Only conservative false-alarm feedback can create an automatic prompt candidate.
Feedback that could make physical activation more permissive is retained for manual
review and can never promote through this path.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from hati.config import HatiConfig
from hati.decision import authorize
from hati.event_store import EventStore
from hati.models import (
    Classification,
    DecisionOutcome,
    DecisionRecord,
    EventRecord,
    FeedbackKind,
    ProcessingState,
    SystemState,
    to_jsonable,
)
from hati.vision import VisionResult


SCHEMA_VERSION = 1
CONSERVATIVE_FALSE_ALARM_ADDENDUM = """Operator-reviewed false-alarm safeguard:
Treat a possible toy, plush animal, decoy, statue, printed/displayed animal,
reflection, or other nonliving representation as unknown unless multiple frames show
clear features of a live animal. When those live-animal features are not clear,
safe_to_deter must be false. Never infer a predator only from silhouette or motion."""


@dataclass(frozen=True)
class PromptCandidate:
    candidate_id: str
    source_event_id: str
    source_feedback: FeedbackKind
    expected_outcome: DecisionOutcome
    prompt_addendum: str
    created_at: datetime
    status: str = "proposed"
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class ReviewArtifact:
    event_id: str
    feedback_kind: FeedbackKind
    disposition: str
    reason: str
    protected_regression: bool
    candidate: PromptCandidate | None
    created_at: datetime
    schema_version: int = SCHEMA_VERSION


@dataclass(frozen=True)
class VisionCaseResult:
    event_id: str
    role: str
    expected_outcome: DecisionOutcome
    baseline_outcome: DecisionOutcome
    candidate_outcome: DecisionOutcome
    passed: bool
    corrected: bool
    regressed: bool


@dataclass(frozen=True)
class VisionImprovementReport:
    candidate_id: str
    source_event_id: str
    policy_request_count: int
    protected_case_count: int
    corrected_failures: int
    regressions: int
    candidate_promoted: bool
    evaluated_at: datetime
    cases: tuple[VisionCaseResult, ...]
    schema_version: int = SCHEMA_VERSION


CandidateClassifier = Callable[[list[Path], str, str], VisionResult]


def _atomic_json(path: Path, value: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(to_jsonable(value), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)
    return path


def _latest_feedback(event: EventRecord):
    if not event.feedback:
        raise ValueError("Event has no owner feedback")
    return max(event.feedback, key=lambda item: item.recorded_at)


def review_event(event: EventRecord, output_directory: Path) -> tuple[ReviewArtifact, Path]:
    """Convert the latest owner review into a protected case or safe candidate."""

    feedback = _latest_feedback(event)
    now = datetime.now(timezone.utc)
    candidate = None
    protected = False

    if feedback.kind is FeedbackKind.CORRECT:
        disposition = "protected_regression"
        reason = "Correct owner feedback protects this behavior against future candidates"
        protected = True
    elif feedback.kind in {
        FeedbackKind.FALSE_ALARM,
        FeedbackKind.INAPPROPRIATE_ACTUATION,
    }:
        disposition = "candidate_proposed"
        reason = "A conservative false-alarm safeguard can be evaluated without loosening safety"
        candidate = PromptCandidate(
            candidate_id=f"candidate-{event.event_id}-false-alarm",
            source_event_id=event.event_id,
            source_feedback=feedback.kind,
            expected_outcome=DecisionOutcome.DENY,
            prompt_addendum=CONSERVATIVE_FALSE_ALARM_ADDENDUM,
            created_at=now,
        )
    elif feedback.kind in {
        FeedbackKind.MISSED_THREAT,
        FeedbackKind.EXPECTED_ACTUATION_MISSING,
    }:
        disposition = "manual_review_required"
        reason = (
            "Feedback could make actuation more permissive; automatic proposal is forbidden"
        )
    elif feedback.kind is FeedbackKind.WRONG_ANIMAL and (
        feedback.note == "expected_label=unknown"
    ):
        disposition = "manual_review_required"
        reason = (
            "Operator confirmed the animal label is wrong but does not know the "
            "replacement label; automatic relabeling is forbidden"
        )
    else:
        disposition = "label_required"
        reason = "Wrong-animal feedback needs the operator's expected label before evaluation"

    artifact = ReviewArtifact(
        event_id=event.event_id,
        feedback_kind=feedback.kind,
        disposition=disposition,
        reason=reason,
        protected_regression=protected,
        candidate=candidate,
        created_at=now,
    )
    path = output_directory / f"{event.event_id}.json"
    return artifact, _atomic_json(path, artifact)


def load_candidate(path: Path) -> PromptCandidate:
    raw = json.loads(path.read_text(encoding="utf-8"))
    candidate_raw = raw.get("candidate", raw)
    if not isinstance(candidate_raw, dict):
        raise ValueError("Learning artifact does not contain a candidate")
    return PromptCandidate(
        candidate_id=str(candidate_raw["candidate_id"]),
        source_event_id=str(candidate_raw["source_event_id"]),
        source_feedback=FeedbackKind(candidate_raw["source_feedback"]),
        expected_outcome=DecisionOutcome(candidate_raw["expected_outcome"]),
        prompt_addendum=str(candidate_raw["prompt_addendum"]),
        created_at=datetime.fromisoformat(candidate_raw["created_at"]),
        status=str(candidate_raw.get("status", "proposed")),
        schema_version=int(candidate_raw.get("schema_version", SCHEMA_VERSION)),
    )


def load_active_policy(path: Path) -> tuple[str, str]:
    """Return only a promoted policy; missing means baseline, malformed fails closed."""

    if not path.is_file():
        return "baseline", ""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("status") != "promoted":
            raise ValueError("Active vision policy is not marked promoted")
        policy_id = str(raw["policy_id"])
        addendum = str(raw["prompt_addendum"]).strip()
        if not policy_id or not addendum:
            raise ValueError("Active vision policy is incomplete")
        return policy_id, addendum
    except (OSError, TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError("Active vision policy is unreadable") from exc


def _candidate_decision(
    event: EventRecord,
    classifications: tuple[Classification, ...],
    config: HatiConfig,
) -> DecisionRecord:
    trial = EventRecord(
        event_id=f"learning-{event.event_id}",
        start_time=event.start_time,
        end_time=event.end_time,
        camera_id=event.camera_id,
        zone=event.zone,
        trigger_reason="reviewed candidate evaluation",
        frame_paths=list(event.frame_paths),
        processing_state=ProcessingState.CLASSIFIED,
        classifications=list(classifications),
    )
    decision = authorize(
        trial,
        SystemState(armed=True, actuator_available=True),
        config.decision,
        config.events.protected_zones,
    )
    return decision


def _reviewed_events(root: Path) -> list[EventRecord]:
    events: list[EventRecord] = []
    if not root.exists():
        return events
    for path in root.glob("*/event.json"):
        try:
            event = EventStore.load(path)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            continue
        if event.feedback and event.decision is not None and len(event.frame_paths) == 5:
            events.append(event)
    return events


def evaluate_vision_candidate(
    candidate: PromptCandidate,
    config: HatiConfig,
    event_root: Path,
    classifier: CandidateClassifier,
    *,
    max_protected_cases: int = 3,
) -> VisionImprovementReport:
    """Rerun one bounded candidate and promote only after correction, without regressions."""

    if candidate.source_feedback not in {
        FeedbackKind.FALSE_ALARM,
        FeedbackKind.INAPPROPRIATE_ACTUATION,
    }:
        raise ValueError("Only conservative false-alarm candidates may be auto-evaluated")
    if max_protected_cases < 1:
        raise ValueError("At least one protected regression case is required")

    events = _reviewed_events(event_root)
    by_id = {event.event_id: event for event in events}
    source = by_id.get(candidate.source_event_id)
    if source is None or source.decision is None:
        raise ValueError("Candidate source event was not found with a saved decision")

    protected = [
        event
        for event in events
        if event.event_id != source.event_id
        and _latest_feedback(event).kind is FeedbackKind.CORRECT
    ]
    protected.sort(key=lambda event: event.start_time, reverse=True)
    protected = protected[:max_protected_cases]
    if not protected:
        raise ValueError("No correct reviewed event is available as a protected regression case")

    cases: list[VisionCaseResult] = []
    for role, event, expected in (
        [("source", source, candidate.expected_outcome)]
        + [
            ("protected", event, event.decision.outcome)
            for event in protected
            if event.decision is not None
        ]
    ):
        result = classifier(
            event.frame_paths,
            candidate.candidate_id,
            candidate.prompt_addendum,
        )
        decision = _candidate_decision(event, result.classifications, config)
        outcome = decision.outcome
        baseline = event.decision.outcome
        if role == "source":
            baseline_misclassified = any(item.predator for item in event.classifications)
            candidate_still_predator = any(
                item.predator or item.safe_to_deter for item in result.classifications
            )
            passed = outcome is expected and not candidate_still_predator
            corrected = passed and (baseline is not expected or baseline_misclassified)
            regressed = False
        else:
            preserves_human_veto = (
                not event.decision.human_veto or decision.human_veto
            )
            preserves_consensus = (
                event.decision.consensus_label is None
                or decision.consensus_label is event.decision.consensus_label
            )
            passed = outcome is expected and preserves_human_veto and preserves_consensus
            corrected = False
            regressed = not passed
        cases.append(
            VisionCaseResult(
                event_id=event.event_id,
                role=role,
                expected_outcome=expected,
                baseline_outcome=baseline,
                candidate_outcome=outcome,
                passed=passed,
                corrected=corrected,
                regressed=regressed,
            )
        )

    corrected = sum(item.corrected for item in cases)
    regressions = sum(item.regressed for item in cases)
    return VisionImprovementReport(
        candidate_id=candidate.candidate_id,
        source_event_id=candidate.source_event_id,
        policy_request_count=len(cases),
        protected_case_count=len(protected),
        corrected_failures=corrected,
        regressions=regressions,
        candidate_promoted=corrected > 0 and regressions == 0 and all(
            item.passed for item in cases
        ),
        evaluated_at=datetime.now(timezone.utc),
        cases=tuple(cases),
    )


def save_evaluation(
    candidate: PromptCandidate,
    report: VisionImprovementReport,
    report_directory: Path,
    active_policy_path: Path,
) -> tuple[Path, Path | None]:
    report_path = report_directory / f"{candidate.candidate_id}.json"
    _atomic_json(report_path, report)
    if not report.candidate_promoted:
        return report_path, None
    active = {
        "schema_version": SCHEMA_VERSION,
        "status": "promoted",
        "policy_id": candidate.candidate_id,
        "prompt_addendum": candidate.prompt_addendum,
        "source_event_id": candidate.source_event_id,
        "source_feedback": candidate.source_feedback,
        "promoted_at": report.evaluated_at,
        "evaluation_report": str(report_path),
        "immutable_boundaries": [
            "human veto",
            "protected zone",
            "five-frame consensus",
            "cooldown",
            "one actuation attempt per event",
        ],
    }
    return report_path, _atomic_json(active_policy_path, active)
