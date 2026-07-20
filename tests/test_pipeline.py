from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from hati.actuator import ActuatorResult
from hati.config import load_config
from hati.event_store import EventStore
from hati.models import (
    AnimalLabel,
    Classification,
    DecisionOutcome,
    EventRecord,
    InferenceTrace,
    LocalGateTrace,
    ProcessingState,
)
from hati.pipeline import process_event
from hati.simulation import build_simulated_event
from hati.vision import VisionResult


class RecordingActuator:
    def __init__(self, store: EventStore | None = None, *, fail: bool = False) -> None:
        self.store = store
        self.fail = fail
        self.events: list[str] = []
        self.state_at_dispatch: ProcessingState | None = None

    @property
    def available(self) -> bool:
        return True

    def activate(self, event_id: str) -> ActuatorResult:
        self.events.append(event_id)
        if self.store is not None:
            event = self.store.load(self.store.root / event_id / "event.json")
            self.state_at_dispatch = event.processing_state
        if self.fail:
            raise RuntimeError("simulated transport loss")
        return ActuatorResult(True, "bounded test activation")


class InterruptingActuator(RecordingActuator):
    def activate(self, event_id: str) -> ActuatorResult:
        self.events.append(event_id)
        raise KeyboardInterrupt


def _unused_classifier(_paths: list[Path]) -> VisionResult:
    raise AssertionError("classifier should not have been called")


def _config(root: Path):
    base = load_config(Path("config/hati.example.json"))
    return replace(
        base,
        events=replace(base.events, event_directory=root),
        runtime=replace(base.runtime, armed=True, test_mode=False),
    )


class PipelineTests(unittest.TestCase):
    def test_authorized_event_is_reserved_before_single_actuator_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            config = _config(store.root)
            event = build_simulated_event("raccoon", "camera", "COOP_DOOR_ZONE")
            store.save(event)
            actuator = RecordingActuator(store)

            result = process_event(
                event, config, store, _unused_classifier, actuator, physical_action=True
            )
            retry = process_event(
                EventStore.load(store.root / event.event_id / "event.json"),
                config,
                store,
                _unused_classifier,
                actuator,
                physical_action=True,
            )

        self.assertEqual(ProcessingState.ACTUATING, actuator.state_at_dispatch)
        self.assertEqual([event.event_id], actuator.events)
        self.assertEqual(ProcessingState.ACTUATED, result.event.processing_state)
        self.assertTrue(result.event.actuation.succeeded)
        self.assertTrue(retry.replay_refused)
        self.assertFalse(retry.actuator_called)

    def test_human_veto_never_calls_actuator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            event = build_simulated_event("human", "camera", "COOP_DOOR_ZONE")
            actuator = RecordingActuator()
            result = process_event(
                event,
                _config(store.root),
                store,
                _unused_classifier,
                actuator,
                physical_action=True,
            )

        self.assertEqual([], actuator.events)
        self.assertEqual("HUMAN_VETO", result.event.decision.reason_code)
        self.assertEqual(ProcessingState.DECIDED, result.event.processing_state)

    def test_actuator_exception_is_failed_and_never_replayed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            config = _config(store.root)
            event = build_simulated_event("raccoon", "camera", "COOP_DOOR_ZONE")
            actuator = RecordingActuator(store, fail=True)
            first = process_event(
                event, config, store, _unused_classifier, actuator, physical_action=True
            )
            second = process_event(
                EventStore.load(store.root / event.event_id / "event.json"),
                config,
                store,
                _unused_classifier,
                actuator,
                physical_action=True,
            )

        self.assertEqual(ProcessingState.FAILED, first.event.processing_state)
        self.assertEqual([event.event_id], actuator.events)
        self.assertTrue(second.replay_refused)

    def test_operator_interrupt_marks_reserved_actuation_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            config = _config(store.root)
            event = build_simulated_event("raccoon", "camera", "COOP_DOOR_ZONE")
            actuator = InterruptingActuator()

            with self.assertRaises(KeyboardInterrupt):
                process_event(
                    event,
                    config,
                    store,
                    _unused_classifier,
                    actuator,
                    physical_action=True,
                )
            saved = store.load(store.root / event.event_id / "event.json")

        self.assertEqual(ProcessingState.FAILED, saved.processing_state)
        self.assertFalse(saved.actuation.succeeded)
        self.assertIn("KeyboardInterrupt", saved.actuation.detail)

    def test_persistent_cooldown_suppresses_next_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            config = _config(store.root)
            actuator = RecordingActuator(store)
            first = build_simulated_event("raccoon", "camera", "COOP_DOOR_ZONE")
            process_event(
                first, config, store, _unused_classifier, actuator, physical_action=True
            )
            second = build_simulated_event("raccoon", "camera", "COOP_DOOR_ZONE")
            result = process_event(
                second, config, store, _unused_classifier, actuator, physical_action=True
            )

        self.assertEqual([first.event_id], actuator.events)
        self.assertEqual("COOLDOWN_ACTIVE", result.event.decision.reason_code)

    def test_captured_event_classifies_once_then_resumes_without_paid_call(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            config = replace(_config(store.root), runtime=replace(_config(store.root).runtime, armed=False))
            event = EventRecord(
                event_id="captured-once",
                start_time=datetime.now(timezone.utc),
                camera_id="camera",
                zone="COOP_DOOR_ZONE",
                trigger_reason="motion",
            )
            calls = 0

            def classify(_paths: list[Path]) -> VisionResult:
                nonlocal calls
                calls += 1
                observations = tuple(
                    Classification(
                        frame_id=f"frame-{index}",
                        animal=AnimalLabel.CHICKEN,
                        predator=False,
                        confidence=0.99,
                        evidence=("controlled",),
                    )
                    for index in range(5)
                )
                return VisionResult(
                    observations,
                    InferenceTrace(
                        provider="test",
                        model="test",
                        api="test",
                        image_detail="low",
                        reasoning_effort="none",
                        request_count=1,
                    ),
                )

            first = process_event(
                event, config, store, classify, RecordingActuator(), physical_action=False
            )
            second = process_event(
                EventStore.load(store.root / event.event_id / "event.json"),
                config,
                store,
                _unused_classifier,
                RecordingActuator(),
                physical_action=False,
            )

        self.assertEqual(1, calls)
        self.assertTrue(first.classified)
        self.assertFalse(second.classified)

    def test_shadow_gate_runs_once_but_never_suppresses_luna(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            config = replace(
                _config(store.root),
                runtime=replace(_config(store.root).runtime, armed=False),
            )
            event = EventRecord(
                event_id="shadow-once",
                start_time=datetime.now(timezone.utc),
                camera_id="camera",
                zone="COOP_DOOR_ZONE",
                trigger_reason="motion",
            )
            gate_calls = 0
            luna_calls = 0

            def gate(_paths: list[Path]) -> LocalGateTrace:
                nonlocal gate_calls
                gate_calls += 1
                return LocalGateTrace(
                    provider="test",
                    model="local",
                    api="test",
                    mode="shadow",
                    recommendation="would_skip_luna",
                    eligible_to_skip=True,
                    panel_labels=("chicken",) * 5,
                    bird_present=True,
                    uncertain=False,
                    request_count=1,
                )

            def classify(_paths: list[Path]) -> VisionResult:
                nonlocal luna_calls
                luna_calls += 1
                observations = tuple(
                    Classification(
                        frame_id=f"frame-{index}",
                        animal=AnimalLabel.RACCOON,
                        predator=True,
                        confidence=0.99,
                        evidence=("controlled",),
                        safe_to_deter=True,
                    )
                    for index in range(5)
                )
                return VisionResult(
                    observations,
                    InferenceTrace(
                        provider="test",
                        model="luna",
                        api="test",
                        image_detail="high",
                        reasoning_effort="low",
                        request_count=1,
                    ),
                )

            first = process_event(
                event,
                config,
                store,
                classify,
                RecordingActuator(),
                physical_action=False,
                local_gate=gate,
            )
            second = process_event(
                EventStore.load(store.root / event.event_id / "event.json"),
                config,
                store,
                _unused_classifier,
                RecordingActuator(),
                physical_action=False,
                local_gate=gate,
            )

        self.assertEqual(1, gate_calls)
        self.assertEqual(1, luna_calls)
        self.assertTrue(first.local_gate_ran)
        self.assertFalse(second.local_gate_ran)
        self.assertTrue(first.event.local_gate_trace.eligible_to_skip)
        self.assertTrue(
            all(
                item.animal is AnimalLabel.RACCOON
                for item in first.event.classifications
            )
        )

    def test_enforcing_clear_bird_gate_suppresses_luna_and_actuator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            event = EventRecord(
                event_id="local-clear-bird",
                start_time=datetime.now(timezone.utc),
                camera_id="camera",
                zone="COOP_DOOR_ZONE",
                trigger_reason="motion",
            )
            actuator = RecordingActuator()

            def gate(_paths: list[Path]) -> LocalGateTrace:
                return LocalGateTrace(
                    provider="test",
                    model="local",
                    api="test",
                    mode="enforcing",
                    recommendation="would_skip_luna",
                    eligible_to_skip=True,
                    panel_labels=("empty", "empty", "chicken", "empty", "empty"),
                    panel_certainties=("clear",) * 5,
                    bird_present=True,
                    uncertain=False,
                    request_count=1,
                )

            result = process_event(
                event,
                _config(store.root),
                store,
                _unused_classifier,
                actuator,
                physical_action=True,
                local_gate=gate,
                local_gate_suppresses_luna=True,
            )

        self.assertFalse(result.classified)
        self.assertTrue(result.decided)
        self.assertEqual(DecisionOutcome.SUPPRESS, result.event.decision.outcome)
        self.assertEqual("LOCAL_CLEAR_BIRD", result.event.decision.reason_code)
        self.assertIsNone(result.event.inference_trace)
        self.assertEqual([], actuator.events)

    def test_enforcing_likely_human_gate_suppresses_luna_and_actuator(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            event = EventRecord(
                event_id="local-likely-human",
                start_time=datetime.now(timezone.utc),
                camera_id="camera",
                zone="COOP_DOOR_ZONE",
                trigger_reason="motion",
            )
            actuator = RecordingActuator()

            def gate(_paths: list[Path]) -> LocalGateTrace:
                return LocalGateTrace(
                    provider="test",
                    model="local",
                    api="test",
                    mode="enforcing",
                    recommendation="would_skip_luna",
                    eligible_to_skip=True,
                    panel_labels=("empty", "human", "empty", "empty", "empty"),
                    panel_certainties=("clear", "likely", "clear", "clear", "clear"),
                    human_present=True,
                    uncertain=True,
                    request_count=1,
                )

            result = process_event(
                event,
                _config(store.root),
                store,
                _unused_classifier,
                actuator,
                physical_action=True,
                local_gate=gate,
                local_gate_suppresses_luna=True,
            )

        self.assertFalse(result.classified)
        self.assertTrue(result.decided)
        self.assertEqual(DecisionOutcome.SUPPRESS, result.event.decision.outcome)
        self.assertEqual("LOCAL_HUMAN_VETO", result.event.decision.reason_code)
        self.assertTrue(result.event.decision.human_veto)
        self.assertEqual(AnimalLabel.HUMAN, result.event.decision.consensus_label)
        self.assertIsNone(result.event.inference_trace)
        self.assertEqual([], actuator.events)


if __name__ == "__main__":
    unittest.main()
