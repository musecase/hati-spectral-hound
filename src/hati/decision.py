"""Deterministic authorization boundary for physical actuation."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from hati.config import DecisionConfig
from hati.models import (
    AnimalLabel,
    Classification,
    DecisionOutcome,
    DecisionRecord,
    EventRecord,
    SystemState,
)


def authorize(
    event: EventRecord,
    state: SystemState,
    config: DecisionConfig,
    protected_zones: frozenset[str],
    *,
    now: datetime | None = None,
) -> DecisionRecord:
    """Return a deterministic, auditable decision. Any uncertainty fails closed."""
    decided_at = now or datetime.now(timezone.utc)
    usable = [observation for observation in event.classifications if observation.usable]
    human_veto = any(obs.animal is AnimalLabel.HUMAN for obs in usable)
    predator_observations = [
        obs
        for obs in usable
        if obs.predator
        and obs.safe_to_deter
        and obs.animal.value in config.predator_labels
    ]
    counts = Counter(obs.animal for obs in predator_observations)
    consensus_label, predator_votes = (
        counts.most_common(1)[0] if counts else (None, 0)
    )

    def result(
        outcome: DecisionOutcome, reason_code: str, explanation: str
    ) -> DecisionRecord:
        return DecisionRecord(
            outcome=outcome,
            reason_code=reason_code,
            explanation=explanation,
            usable_observations=len(usable),
            predator_votes=predator_votes,
            consensus_label=consensus_label,
            human_veto=human_veto,
            decided_at=decided_at,
        )

    # Vetoes and immutable safety boundaries are checked before operational state.
    if event.zone not in protected_zones:
        return result(DecisionOutcome.DENY, "OUTSIDE_ZONE", "Event is outside a protected zone")
    if human_veto:
        return result(DecisionOutcome.DENY, "HUMAN_VETO", "A human was identified in the event")
    if len(usable) < config.minimum_usable_observations:
        return result(
            DecisionOutcome.DENY,
            "INSUFFICIENT_OBSERVATIONS",
            "Too few usable classifications for temporal verification",
        )
    if predator_votes < config.predator_consensus_required:
        return result(
            DecisionOutcome.DENY,
            "LOW_CONSENSUS",
            "Predator observations did not reach the configured agreement threshold",
        )
    if state.event_already_actuated:
        return result(
            DecisionOutcome.SUPPRESS,
            "DUPLICATE_EVENT",
            "This event has already triggered deterrence",
        )
    if not state.armed:
        return result(DecisionOutcome.SUPPRESS, "DISARMED", "The system is disarmed")
    if not state.actuator_available:
        return result(
            DecisionOutcome.SUPPRESS,
            "ACTUATOR_UNAVAILABLE",
            "The actuator is not available",
        )
    if state.cooldown_until and decided_at < state.cooldown_until:
        remaining = int((state.cooldown_until - decided_at).total_seconds())
        return result(
            DecisionOutcome.SUPPRESS,
            "COOLDOWN_ACTIVE",
            f"Actuator cooldown has {remaining} seconds remaining",
        )

    return result(
        DecisionOutcome.AUTHORIZE,
        "PREDATOR_CONSENSUS",
        f"{consensus_label.value if consensus_label else 'Predator'} reached "
        f"{predator_votes}/{len(usable)} frame consensus",
    )
