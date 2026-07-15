"""Judge-runnable, no-hardware demonstration of HATI's safety boundary."""

from __future__ import annotations

from dataclasses import dataclass

from hati.actuator import ActuatorResult, DryRunActuator
from hati.config import HatiConfig
from hati.decision import authorize
from hati.models import DecisionOutcome, EventRecord, ProcessingState, SystemState
from hati.simulation import build_simulated_event


EXPECTED: dict[str, tuple[DecisionOutcome, str]] = {
    "raccoon": (DecisionOutcome.AUTHORIZE, "PREDATOR_CONSENSUS"),
    "human": (DecisionOutcome.DENY, "HUMAN_VETO"),
    "chicken": (DecisionOutcome.DENY, "LOW_CONSENSUS"),
    "low-consensus": (DecisionOutcome.DENY, "LOW_CONSENSUS"),
}


@dataclass(frozen=True)
class DemoResult:
    scenario: str
    event: EventRecord
    dry_run_called: bool
    actuator_result: ActuatorResult | None
    passed: bool


def run_demo_case(config: HatiConfig, scenario: str) -> DemoResult:
    """Exercise classify-shaped data, authorization, and only the dry-run actuator."""
    if scenario not in EXPECTED:
        raise ValueError(f"Unknown demo scenario: {scenario}")
    zone = sorted(config.events.protected_zones)[0]
    event = build_simulated_event(scenario, config.camera.camera_id, zone)
    state = SystemState(armed=True, actuator_available=True)
    event.decision = authorize(
        event,
        state,
        config.decision,
        config.events.protected_zones,
    )
    event.processing_state = ProcessingState.DECIDED

    dry_run_called = event.decision.outcome is DecisionOutcome.AUTHORIZE
    actuator_result = None
    if dry_run_called:
        actuator_result = DryRunActuator().activate(event.event_id)
        event.processing_state = (
            ProcessingState.ACTUATED if actuator_result.succeeded else ProcessingState.FAILED
        )

    expected_outcome, expected_reason = EXPECTED[scenario]
    passed = (
        event.decision.outcome is expected_outcome
        and event.decision.reason_code == expected_reason
        and (not dry_run_called or bool(actuator_result and actuator_result.succeeded))
    )
    return DemoResult(
        scenario=scenario,
        event=event,
        dry_run_called=dry_run_called,
        actuator_result=actuator_result,
        passed=passed,
    )
