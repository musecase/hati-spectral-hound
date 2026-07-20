"""Restart-safe orchestration across vision, policy, actuation, and audit storage."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Callable

from hati.actuator import Actuator
from hati.config import HatiConfig
from hati.decision import authorize
from hati.event_store import EventStore
from hati.models import (
    ActuationRecord,
    AnimalLabel,
    DecisionOutcome,
    DecisionRecord,
    EventRecord,
    LocalGateTrace,
    ProcessingState,
    SystemState,
    utc_now,
)
from hati.vision import VisionResult


Classifier = Callable[[list[Path]], VisionResult]
LocalGate = Callable[[list[Path]], LocalGateTrace]


@dataclass(frozen=True)
class PipelineResult:
    event: EventRecord
    local_gate_ran: bool
    classified: bool
    decided: bool
    actuator_called: bool
    replay_refused: bool


def _system_state(
    event: EventRecord,
    config: HatiConfig,
    store: EventStore,
    actuator: Actuator,
) -> SystemState:
    """Rebuild persistent cooldown state from inspectable event traces."""

    latest_attempt = None
    another_attempt_in_flight = False
    audit_valid = True
    try:
        paths = store.root.glob("*/event.json") if store.root.exists() else ()
        for path in paths:
            other = EventStore.load(path)
            if other.event_id == event.event_id:
                continue
            if other.processing_state is ProcessingState.ACTUATING:
                another_attempt_in_flight = True
            if other.actuation is not None and (
                latest_attempt is None or other.actuation.attempted_at > latest_attempt
            ):
                latest_attempt = other.actuation.attempted_at
    except (OSError, ValueError, KeyError):
        # An unreadable safety trace must fail closed, never erase cooldown history.
        audit_valid = False
    cooldown_until = (
        latest_attempt + timedelta(seconds=config.decision.cooldown_seconds)
        if latest_attempt is not None
        else None
    )
    return SystemState(
        armed=config.runtime.armed,
        actuator_available=(actuator.available and audit_valid and not another_attempt_in_flight),
        cooldown_until=cooldown_until,
        event_already_actuated=event.actuation is not None,
    )


def process_event(
    event: EventRecord,
    config: HatiConfig,
    store: EventStore,
    classifier: Classifier,
    actuator: Actuator,
    *,
    physical_action: bool,
    local_gate: LocalGate | None = None,
    local_gate_suppresses_luna: bool = False,
) -> PipelineResult:
    """Advance one event as far as possible without replaying paid or physical work.

    The ACTUATING state is persisted before calling the actuator. If the process dies
    after that write, a later invocation refuses to replay the physical command.
    """

    classified = False
    local_gate_ran = False
    decided = False
    actuator_called = False

    if event.processing_state is ProcessingState.CAPTURED:
        if local_gate is not None and event.local_gate_trace is None:
            event.local_gate_trace = local_gate(event.frame_paths)
            store.save(event)
            local_gate_ran = True
        if (
            local_gate_suppresses_luna
            and event.local_gate_trace is not None
            and event.local_gate_trace.eligible_to_skip
        ):
            local_human_veto = event.local_gate_trace.human_present
            consensus = (
                AnimalLabel.HUMAN
                if local_human_veto
                else (
                    AnimalLabel.GOOSE
                    if "goose" in event.local_gate_trace.panel_labels
                    else AnimalLabel.CHICKEN
                )
            )
            event.decision = DecisionRecord(
                outcome=DecisionOutcome.SUPPRESS,
                reason_code=(
                    "LOCAL_HUMAN_VETO"
                    if local_human_veto
                    else "LOCAL_CLEAR_BIRD"
                ),
                explanation=(
                    "Local gate found a clear or likely human; Luna call and deterrent "
                    "suppressed"
                    if local_human_veto
                    else (
                        "Local gate found a clear resident bird with no human, mammal, "
                        "unknown, or uncertain panel; Luna call suppressed"
                    )
                ),
                usable_observations=len(event.local_gate_trace.panel_labels),
                predator_votes=0,
                consensus_label=consensus,
                human_veto=local_human_veto,
            )
            event.processing_state = ProcessingState.DECIDED
            store.save(event)
            decided = True
        else:
            vision = classifier(event.frame_paths)
            event.classifications = list(vision.classifications)
            event.inference_trace = vision.trace
            event.processing_state = ProcessingState.CLASSIFIED
            store.save(event)
            classified = True

    if event.processing_state is ProcessingState.CLASSIFIED:
        state = _system_state(event, config, store, actuator)
        event.decision = authorize(
            event,
            state,
            config.decision,
            config.events.protected_zones,
        )
        event.processing_state = ProcessingState.DECIDED
        store.save(event)
        decided = True

    if (
        event.processing_state is ProcessingState.DECIDED
        and event.decision is not None
        and event.decision.outcome is DecisionOutcome.AUTHORIZE
    ):
        attempted_at = utc_now()
        event.actuation = ActuationRecord(
            attempted_at=attempted_at,
            completed_at=None,
            succeeded=None,
            detail="Actuator attempt reserved before command dispatch",
            physical_action=physical_action,
        )
        event.processing_state = ProcessingState.ACTUATING
        store.save(event)
        actuator_called = True
        try:
            result = actuator.activate(event.event_id)
        except KeyboardInterrupt as exc:
            event.actuation = ActuationRecord(
                attempted_at=attempted_at,
                completed_at=utc_now(),
                succeeded=False,
                detail=f"Actuator raised {type(exc).__name__}; replay disabled",
                physical_action=physical_action,
            )
            event.processing_state = ProcessingState.FAILED
            store.save(event)
            raise
        except Exception as exc:
            event.actuation = ActuationRecord(
                attempted_at=attempted_at,
                completed_at=utc_now(),
                succeeded=False,
                detail=f"Actuator raised {type(exc).__name__}; replay disabled",
                physical_action=physical_action,
            )
            event.processing_state = ProcessingState.FAILED
            store.save(event)
        else:
            event.actuation = ActuationRecord(
                attempted_at=attempted_at,
                completed_at=utc_now(),
                succeeded=result.succeeded,
                detail=result.detail,
                physical_action=physical_action,
            )
            event.processing_state = (
                ProcessingState.ACTUATED if result.succeeded else ProcessingState.FAILED
            )
            store.save(event)

    replay_refused = event.processing_state in {
        ProcessingState.ACTUATING,
        ProcessingState.ACTUATED,
        ProcessingState.FAILED,
    } and not actuator_called
    return PipelineResult(
        event=event,
        local_gate_ran=local_gate_ran,
        classified=classified,
        decided=decided,
        actuator_called=actuator_called,
        replay_refused=replay_refused,
    )
