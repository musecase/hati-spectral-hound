from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from hati.config import (
    ActuatorConfig,
    CameraConfig,
    DecisionConfig,
    EventConfig,
    HatiConfig,
    LocalGateConfig,
    MotionConfig,
    RuntimeConfig,
    TelegramConfig,
    VisionConfig,
)
from hati.auto_learning import (
    AutomaticLearningResult,
    AutomaticLearningWorker,
    run_automatic_learning_event,
)
from hati.decision import authorize
from hati.event_store import EventStore
from hati.learning import (
    evaluate_vision_candidate,
    load_active_policy,
    review_event,
    save_evaluation,
)
from hati.models import (
    AnimalLabel,
    Classification,
    DecisionOutcome,
    FeedbackKind,
    HumanFeedback,
    InferenceTrace,
    EventRecord,
    ProcessingState,
    SystemState,
)
from hati.vision import VisionResult


def config_for(root: Path) -> HatiConfig:
    return HatiConfig(
        camera=CameraConfig("test", "192.0.2.10"),
        events=EventConfig(root, frozenset({"COOP_DOOR_ZONE"})),
        motion=MotionConfig(),
        decision=DecisionConfig(),
        vision=VisionConfig(active_policy_path=root / "active-policy.json"),
        local_gate=LocalGateConfig(),
        actuator=ActuatorConfig(),
        telegram=TelegramConfig(),
        runtime=RuntimeConfig(),
    )


def classifications(
    label: AnimalLabel, *, safe_to_deter: bool | None = None
) -> tuple[Classification, ...]:
    predator = label is AnimalLabel.RACCOON
    safe = predator if safe_to_deter is None else safe_to_deter
    return tuple(
        Classification(
            frame_id=f"frame-{index:03d}",
            animal=label,
            predator=predator,
            confidence=0.95,
            evidence=("controlled test",),
            safe_to_deter=safe,
        )
        for index in range(1, 6)
    )


class LearningTests(unittest.TestCase):
    def _event(
        self,
        root: Path,
        event_id: str,
        label: AnimalLabel,
        feedback: FeedbackKind,
        config: HatiConfig,
        *,
        safe_to_deter: bool | None = None,
    ):
        now = datetime.now(timezone.utc)
        event = EventRecord(
            event_id=event_id,
            start_time=now,
            end_time=now,
            camera_id="test",
            zone="COOP_DOOR_ZONE",
            trigger_reason="learning test",
        )
        for index in range(1, 6):
            path = root / event_id / f"frame-{index:03d}.jpg"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"fixture")
            event.frame_paths.append(path)
        event.classifications = list(
            classifications(label, safe_to_deter=safe_to_deter)
        )
        event.processing_state = ProcessingState.CLASSIFIED
        event.decision = authorize(
            event,
            SystemState(armed=True, actuator_available=True),
            config.decision,
            config.events.protected_zones,
        )
        event.processing_state = ProcessingState.DECIDED
        event.feedback.append(HumanFeedback(feedback, "test", "owner"))
        EventStore(root).save(event)
        return event

    def test_correct_feedback_becomes_protected_without_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "events"
            config = config_for(root)
            event = self._event(root, "correct-human", AnimalLabel.HUMAN, FeedbackKind.CORRECT, config)
            artifact, path = review_event(event, Path(temporary) / "reviews")
            self.assertTrue(path.is_file())
            self.assertTrue(artifact.protected_regression)
            self.assertIsNone(artifact.candidate)

    def test_missed_threat_cannot_create_automatic_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "events"
            config = config_for(root)
            event = self._event(
                root,
                "missed",
                AnimalLabel.UNKNOWN,
                FeedbackKind.MISSED_THREAT,
                config,
            )
            artifact, _ = review_event(event, Path(temporary) / "reviews")
            self.assertEqual("manual_review_required", artifact.disposition)
            self.assertIsNone(artifact.candidate)

    def test_unknown_expected_animal_cannot_invent_replacement_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "events"
            config = config_for(root)
            event = self._event(
                root,
                "unknown-label",
                AnimalLabel.OPOSSUM,
                FeedbackKind.WRONG_ANIMAL,
                config,
            )
            event.feedback[-1] = HumanFeedback(
                FeedbackKind.WRONG_ANIMAL,
                "test",
                "owner",
                note="expected_label=unknown",
            )
            artifact, _ = review_event(event, Path(temporary) / "reviews")
            self.assertEqual("manual_review_required", artifact.disposition)
            self.assertIsNone(artifact.candidate)

    def test_corrupt_active_policy_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "active-policy.json"
            path.write_text("not-json", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_active_policy(path)

    def test_false_alarm_candidate_fixes_source_without_regressing_protected_case(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "events"
            config = config_for(root)
            source = self._event(
                root,
                "plush-source",
                AnimalLabel.RACCOON,
                FeedbackKind.FALSE_ALARM,
                config,
            )
            self._event(
                root,
                "protected-human",
                AnimalLabel.HUMAN,
                FeedbackKind.CORRECT,
                config,
            )
            artifact, _ = review_event(source, base / "reviews")
            self.assertIsNotNone(artifact.candidate)
            candidate = artifact.candidate
            assert candidate is not None

            def classifier(paths, policy_id, addendum):
                label = AnimalLabel.UNKNOWN if "plush-source" in str(paths[0]) else AnimalLabel.HUMAN
                return VisionResult(
                    classifications=classifications(label),
                    trace=InferenceTrace(
                        "test", "test", "test", "high", "low", 1, policy_id=policy_id
                    ),
                )

            report = evaluate_vision_candidate(candidate, config, root, classifier)
            self.assertTrue(report.candidate_promoted)
            self.assertEqual(1, report.corrected_failures)
            self.assertEqual(0, report.regressions)
            _, active = save_evaluation(
                candidate,
                report,
                base / "reports",
                config.vision.active_policy_path,
            )
            self.assertEqual(config.vision.active_policy_path, active)
            self.assertEqual(
                (candidate.candidate_id, candidate.prompt_addendum),
                load_active_policy(config.vision.active_policy_path),
            )

    def test_automatic_false_alarm_review_promotes_zero_regression_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "events"
            config = config_for(root)
            self._event(
                root,
                "automatic-plush",
                AnimalLabel.RACCOON,
                FeedbackKind.FALSE_ALARM,
                config,
            )
            self._event(
                root,
                "automatic-protected-human",
                AnimalLabel.HUMAN,
                FeedbackKind.CORRECT,
                config,
            )

            def classifier(paths, policy_id, addendum):
                label = (
                    AnimalLabel.UNKNOWN
                    if "automatic-plush" in str(paths[0])
                    else AnimalLabel.HUMAN
                )
                return VisionResult(
                    classifications=classifications(label),
                    trace=InferenceTrace(
                        "test", "test", "test", "high", "low", 1, policy_id=policy_id
                    ),
                )

            result = run_automatic_learning_event(
                config,
                "automatic-plush",
                classifier=classifier,
            )
            self.assertEqual("promoted", result.status)
            self.assertEqual(0, result.regressions)
            self.assertTrue(config.vision.active_policy_path.is_file())

    def test_background_worker_queues_only_conservative_feedback(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "events"
            config = config_for(root)
            completed = threading.Event()

            def runner(worker_config, event_id):
                completed.set()
                return AutomaticLearningResult(
                    event_id=event_id,
                    status="rejected",
                    candidate_id="candidate-test",
                    model_requests=2,
                    protected_cases=1,
                    corrected_failures=0,
                    regressions=0,
                    report_path=None,
                    active_policy_path=None,
                )

            worker = AutomaticLearningWorker(config, runner=runner)
            worker.start()
            try:
                self.assertFalse(worker.submit("unsafe", FeedbackKind.MISSED_THREAT))
                self.assertTrue(
                    worker.submit("safe-false-alarm", FeedbackKind.FALSE_ALARM)
                )
                self.assertTrue(completed.wait(2))
                job_path = (
                    config.vision.active_policy_path.parent
                    / "jobs"
                    / "safe-false-alarm.json"
                )
                deadline = time.monotonic() + 2
                job = {}
                while time.monotonic() < deadline:
                    job = json.loads(job_path.read_text(encoding="utf-8"))
                    if job.get("status") == "rejected":
                        break
                    time.sleep(0.01)
                self.assertEqual("rejected", job["status"])
                self.assertFalse(job["physical_action"])
            finally:
                worker.stop()

    def test_false_alarm_can_correct_label_even_when_baseline_already_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            root = base / "events"
            config = config_for(root)
            source = self._event(
                root,
                "safe-but-wrong-plush",
                AnimalLabel.RACCOON,
                FeedbackKind.FALSE_ALARM,
                config,
                safe_to_deter=False,
            )
            self.assertEqual(DecisionOutcome.DENY, source.decision.outcome)
            self._event(
                root,
                "protected-hand",
                AnimalLabel.HUMAN,
                FeedbackKind.CORRECT,
                config,
            )
            artifact, _ = review_event(source, base / "reviews")
            assert artifact.candidate is not None

            def classifier(paths, policy_id, addendum):
                label = (
                    AnimalLabel.UNKNOWN
                    if "safe-but-wrong-plush" in str(paths[0])
                    else AnimalLabel.HUMAN
                )
                return VisionResult(
                    classifications=classifications(label),
                    trace=InferenceTrace(
                        "test", "test", "test", "high", "low", 1, policy_id=policy_id
                    ),
                )

            report = evaluate_vision_candidate(
                artifact.candidate, config, root, classifier
            )
            self.assertTrue(report.candidate_promoted)
            self.assertEqual(1, report.corrected_failures)


if __name__ == "__main__":
    unittest.main()
