"""Offline, review-gated comparison of baseline and candidate behavior."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from hati.config import DecisionConfig
from hati.decision import authorize
from hati.models import (
    AnimalLabel,
    Classification,
    DecisionOutcome,
    EventRecord,
    ProcessingState,
    SystemState,
    to_jsonable,
)


PREDATOR_LABELS = {
    AnimalLabel.RACCOON,
    AnimalLabel.FOX,
    AnimalLabel.COYOTE,
    AnimalLabel.OPOSSUM,
    AnimalLabel.SKUNK,
}


@dataclass(frozen=True)
class EvaluationCaseResult:
    name: str
    expected_outcome: DecisionOutcome
    baseline_outcome: DecisionOutcome
    candidate_outcome: DecisionOutcome
    baseline_passed: bool
    candidate_passed: bool
    regressed: bool
    corrected: bool


@dataclass(frozen=True)
class EvaluationReport:
    fixture_notice: str
    case_count: int
    baseline_passed: int
    candidate_passed: int
    regressions: int
    corrected_failures: int
    candidate_promoted: bool
    cases: tuple[EvaluationCaseResult, ...]

    def as_dict(self) -> dict:
        return to_jsonable(self)


def evaluate_improvement(
    path: str | Path,
    decision_config: DecisionConfig,
    protected_zone: str,
) -> EvaluationReport:
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    cases_raw = raw.get("cases", [])
    if not isinstance(cases_raw, list) or not cases_raw:
        raise ValueError("Evaluation fixture must contain at least one case")

    results: list[EvaluationCaseResult] = []
    for item in cases_raw:
        expected = DecisionOutcome(str(item["expected_outcome"]))
        baseline = _outcome(
            str(item["name"]),
            item["baseline_labels"],
            decision_config,
            protected_zone,
        )
        candidate = _outcome(
            str(item["name"]),
            item["candidate_labels"],
            decision_config,
            protected_zone,
        )
        baseline_passed = baseline is expected
        candidate_passed = candidate is expected
        results.append(
            EvaluationCaseResult(
                name=str(item["name"]),
                expected_outcome=expected,
                baseline_outcome=baseline,
                candidate_outcome=candidate,
                baseline_passed=baseline_passed,
                candidate_passed=candidate_passed,
                regressed=baseline_passed and not candidate_passed,
                corrected=not baseline_passed and candidate_passed,
            )
        )

    baseline_total = sum(result.baseline_passed for result in results)
    candidate_total = sum(result.candidate_passed for result in results)
    regressions = sum(result.regressed for result in results)
    corrected = sum(result.corrected for result in results)
    return EvaluationReport(
        fixture_notice=str(raw.get("notice", "controlled offline fixture")),
        case_count=len(results),
        baseline_passed=baseline_total,
        candidate_passed=candidate_total,
        regressions=regressions,
        corrected_failures=corrected,
        candidate_promoted=(
            candidate_total > baseline_total and regressions == 0 and corrected > 0
        ),
        cases=tuple(results),
    )


def _outcome(
    name: str,
    labels_raw: list[str],
    config: DecisionConfig,
    protected_zone: str,
) -> DecisionOutcome:
    labels = [AnimalLabel(value) for value in labels_raw]
    if len(labels) != 5:
        raise ValueError(f"Evaluation case {name!r} must have exactly five labels")
    now = datetime.now(timezone.utc)
    classifications = [
        Classification(
            frame_id=f"frame-{index:02d}",
            animal=label,
            predator=label in PREDATOR_LABELS,
            confidence=0.95,
            evidence=("controlled offline evaluation",),
            safe_to_deter=label in PREDATOR_LABELS,
        )
        for index, label in enumerate(labels, start=1)
    ]
    event = EventRecord(
        event_id=f"eval-{name}",
        start_time=now,
        end_time=now,
        camera_id="evaluation-camera",
        zone=protected_zone,
        trigger_reason="controlled offline evaluation",
        processing_state=ProcessingState.CLASSIFIED,
        classifications=classifications,
    )
    decision = authorize(
        event,
        SystemState(armed=True, actuator_available=True),
        config,
        frozenset({protected_zone}),
    )
    return decision.outcome
