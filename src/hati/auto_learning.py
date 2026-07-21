"""Restart-visible background evaluation for conservative owner feedback.

Telegram feedback is stored on the event before this worker is notified.  Only
feedback that can make HATI *less* willing to act is eligible for automatic
evaluation.  The worker never invokes an actuator and cannot edit deterministic
authorization policy.
"""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from hati.config import HatiConfig
from hati.event_store import EventStore
from hati.learning import (
    evaluate_vision_candidate,
    review_event,
    save_evaluation,
)
from hati.models import FeedbackKind
from hati.vision import VisionError, classify_frames


SAFE_EVENT_ID = re.compile(r"^[A-Za-z0-9_-]+$")
CONSERVATIVE_FEEDBACK = frozenset(
    {
        FeedbackKind.FALSE_ALARM,
        FeedbackKind.INAPPROPRIATE_ACTUATION,
    }
)


class AutomaticLearningError(RuntimeError):
    """Raised when a queued learning review cannot finish safely."""


@dataclass(frozen=True)
class AutomaticLearningResult:
    event_id: str
    status: str
    candidate_id: str | None
    model_requests: int
    protected_cases: int
    corrected_failures: int
    regressions: int
    report_path: Path | None
    active_policy_path: Path | None
    physical_action: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "status": self.status,
            "candidate_id": self.candidate_id,
            "model_requests": self.model_requests,
            "protected_cases": self.protected_cases,
            "corrected_failures": self.corrected_failures,
            "regressions": self.regressions,
            "report_path": str(self.report_path) if self.report_path else None,
            "active_policy_path": (
                str(self.active_policy_path) if self.active_policy_path else None
            ),
            "physical_action": self.physical_action,
        }


def _atomic_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    for attempt in range(10):
        try:
            os.replace(temporary, path)
            break
        except PermissionError:
            if attempt == 9:
                raise
            # Windows briefly locks a JSON file while an operator/status reader
            # has it open. Preserve atomic replacement and retry the rename.
            time.sleep(0.01)
    return path


def run_automatic_learning_event(
    config: HatiConfig,
    event_id: str,
    *,
    classifier: Callable[[list[Path], str, str], Any] | None = None,
) -> AutomaticLearningResult:
    """Evaluate one reviewed event and promote only a zero-regression safeguard."""

    if not SAFE_EVENT_ID.fullmatch(event_id):
        raise AutomaticLearningError("Automatic learning received an invalid event ID")

    event_path = config.events.event_directory / event_id / "event.json"
    try:
        event = EventStore.load(event_path)
        review, review_path = review_event(
            event,
            config.vision.active_policy_path.parent / "reviews",
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise AutomaticLearningError(
            f"Could not review event {event_id}: {type(exc).__name__}"
        ) from exc

    if review.feedback_kind not in CONSERVATIVE_FEEDBACK or review.candidate is None:
        return AutomaticLearningResult(
            event_id=event_id,
            status="no_change",
            candidate_id=None,
            model_requests=0,
            protected_cases=0,
            corrected_failures=0,
            regressions=0,
            report_path=review_path,
            active_policy_path=None,
        )

    api_key = ""
    if classifier is None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise AutomaticLearningError(
                "Automatic learning needs the encrypted local OpenAI API key"
            )

        def classifier(paths: list[Path], policy_id: str, addendum: str):
            return classify_frames(
                paths,
                config.vision,
                api_key=api_key,
                policy_id=policy_id,
                policy_addendum=addendum,
                cascade=False,
            )

    try:
        report = evaluate_vision_candidate(
            review.candidate,
            config,
            config.events.event_directory,
            classifier,
            max_protected_cases=3,
        )
        report_path, active_path = save_evaluation(
            review.candidate,
            report,
            config.vision.active_policy_path.parent / "reports",
            config.vision.active_policy_path,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError, VisionError) as exc:
        raise AutomaticLearningError(
            f"Conservative evaluation stopped safely: {exc}"
        ) from exc
    finally:
        api_key = ""

    return AutomaticLearningResult(
        event_id=event_id,
        status="promoted" if report.candidate_promoted else "rejected",
        candidate_id=report.candidate_id,
        model_requests=report.policy_request_count,
        protected_cases=report.protected_case_count,
        corrected_failures=report.corrected_failures,
        regressions=report.regressions,
        report_path=report_path,
        active_policy_path=active_path,
    )


class AutomaticLearningWorker:
    """Single-filed background worker with durable, idempotent job records."""

    def __init__(
        self,
        config: HatiConfig,
        *,
        notifier: Callable[[str], None] | None = None,
        runner: Callable[[HatiConfig, str], AutomaticLearningResult] | None = None,
    ) -> None:
        self.config = config
        self.notifier = notifier
        self.runner = runner or run_automatic_learning_event
        self.job_directory = config.vision.active_policy_path.parent / "jobs"
        self._queue: queue.Queue[str] = queue.Queue()
        self._scheduled: set[str] = set()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = threading.Thread(
            target=self._work,
            name="hati-automatic-learning",
            daemon=True,
        )

    def start(self) -> None:
        self.job_directory.mkdir(parents=True, exist_ok=True)
        for path in sorted(self.job_directory.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if raw.get("status") in {"queued", "running"}:
                self._schedule(str(raw.get("event_id", "")))
        self._thread.start()

    def submit(self, event_id: str, feedback: FeedbackKind) -> bool:
        if feedback not in CONSERVATIVE_FEEDBACK:
            return False
        if not SAFE_EVENT_ID.fullmatch(event_id):
            return False

        path = self.job_directory / f"{event_id}.json"
        if path.exists():
            try:
                status = json.loads(path.read_text(encoding="utf-8")).get("status")
            except (OSError, json.JSONDecodeError):
                status = "failed"
            if status not in {"queued", "running"}:
                return False
        else:
            _atomic_json(
                path,
                {
                    "event_id": event_id,
                    "feedback": feedback.value,
                    "status": "queued",
                    "physical_action": False,
                },
            )
        queued = self._schedule(event_id)
        if queued:
            self._notify(
                "✨ Feedback saved. HATI queued a conservative learning check "
                "(at most four five-frame model requests; physical action locked out)."
            )
        return queued

    def stop(self) -> None:
        self._stop.set()

    def _schedule(self, event_id: str) -> bool:
        if not SAFE_EVENT_ID.fullmatch(event_id):
            return False
        with self._lock:
            if event_id in self._scheduled:
                return False
            self._scheduled.add(event_id)
        self._queue.put(event_id)
        return True

    def _work(self) -> None:
        while not self._stop.is_set():
            try:
                event_id = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            path = self.job_directory / f"{event_id}.json"
            try:
                _atomic_json(
                    path,
                    {
                        "event_id": event_id,
                        "status": "running",
                        "physical_action": False,
                    },
                )
                result = self.runner(self.config, event_id)
                _atomic_json(path, result.as_dict())
                if result.status == "promoted":
                    self._notify(
                        "✨ HATI promoted the conservative observer safeguard after "
                        f"{result.model_requests} model requests and zero regressions. "
                        "It will apply to the next event."
                    )
                elif result.status == "rejected":
                    self._notify(
                        "HATI tested the conservative safeguard but rejected it; "
                        f"{result.regressions} regression(s), prompt unchanged."
                    )
                else:
                    self._notify("HATI reviewed the feedback; no prompt change was needed.")
            except Exception as exc:
                _atomic_json(
                    path,
                    {
                        "event_id": event_id,
                        "status": "failed",
                        "detail": str(exc),
                        "physical_action": False,
                    },
                )
                self._notify(f"HATI learning stopped safely; prompt unchanged. {exc}")
            finally:
                with self._lock:
                    self._scheduled.discard(event_id)
                self._queue.task_done()

    def _notify(self, message: str) -> None:
        if self.notifier is None:
            return
        try:
            self.notifier(message)
        except Exception:
            # Learning state is already durable. A Telegram outage must not turn
            # a completed evaluation into a retry or hide its audit record.
            return
