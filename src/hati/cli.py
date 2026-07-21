"""Small operator-facing commands for safe setup and controlled simulation."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
import threading
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from hati.actuator import DryRunActuator, TuyaDiffuserActuator
from hati.auto_learning import AutomaticLearningWorker
from hati.camera import (
    CameraError,
    RtspFrameSession,
    capture_frame,
    capture_snapshot,
    resolve_camera_host,
)
from hati.config import ConfigurationError, HatiConfig, load_config
from hati.decision import authorize
from hati.demo import EXPECTED, run_demo_case
from hati.event_store import EventStore
from hati.evaluation import evaluate_improvement
from hati.learning import (
    evaluate_vision_candidate,
    load_active_policy,
    load_candidate,
    review_event,
    save_evaluation,
)
from hati.local_gate import run_shadow_gate
from hati.logging_config import configure_logging
from hati.models import EventRecord, ProcessingState, SystemState, to_jsonable
from hati.pipeline import process_event
from hati.simulation import SCENARIOS, build_simulated_event
from hati.telegram import (
    TelegramClient,
    TelegramController,
    TelegramError,
    TelegramOffsetStore,
    notification_preview,
    process_updates,
)
from hati.watch import WatchError, watch_once
from hati.vision import VisionError, classify_frames


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hati", description="HATI / Spectral Hound operator utility"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Validate local configuration safely")
    doctor.add_argument("--config", type=Path, required=True)

    simulate = subparsers.add_parser(
        "simulate", help="Run controlled observations through the decision boundary"
    )
    simulate.add_argument("scenario", choices=SCENARIOS)
    simulate.add_argument("--config", type=Path, required=True)

    demo = subparsers.add_parser(
        "demo", help="Run judge-facing scenarios without a camera, API, or physical actuator"
    )
    demo.add_argument(
        "scenario", choices=("all", *EXPECTED.keys()), nargs="?", default="all"
    )
    demo.add_argument("--config", type=Path, required=True)
    demo.add_argument("--output", type=Path, default=Path("data/demo_runs"))

    evaluate = subparsers.add_parser(
        "evaluate-improvement",
        help="Compare controlled baseline and candidate behavior without an API",
    )
    evaluate.add_argument("--config", type=Path, required=True)
    evaluate.add_argument(
        "--cases", type=Path, default=Path("sample_data/improvement_cases.json")
    )

    review_feedback = subparsers.add_parser(
        "review-event-feedback",
        help="Turn owner feedback into a protected case or conservative candidate",
    )
    review_feedback.add_argument("--config", type=Path, required=True)
    review_feedback.add_argument("--event", type=Path, required=True)
    review_feedback.add_argument(
        "--output", type=Path, default=Path("data/learning/reviews")
    )

    evaluate_vision = subparsers.add_parser(
        "evaluate-vision-improvement",
        help="Rerun one reviewed candidate against bounded protected events",
    )
    evaluate_vision.add_argument("--config", type=Path, required=True)
    evaluate_vision.add_argument("--candidate", type=Path, required=True)
    evaluate_vision.add_argument("--events", type=Path, default=Path("data/events"))
    evaluate_vision.add_argument(
        "--reports", type=Path, default=Path("data/learning/reports")
    )
    evaluate_vision.add_argument("--max-protected", type=int, default=3)

    camera_probe = subparsers.add_parser(
        "camera-probe", help="Prompt locally and capture one authenticated camera frame"
    )
    camera_probe.add_argument("--config", type=Path, required=True)
    camera_probe.add_argument("--username")
    camera_probe.add_argument(
        "--stream", choices=("videoSub", "videoMain"), default="videoSub"
    )
    camera_probe.add_argument("--output", type=Path)

    capture_replay = subparsers.add_parser(
        "capture-replay",
        help="Capture five camera frames from a controlled staged replay",
    )
    capture_replay.add_argument("--config", type=Path, required=True)
    capture_replay.add_argument("--username")

    watch = subparsers.add_parser(
        "watch", help="Watch the configured zone and capture one real motion event"
    )
    watch.add_argument("--config", type=Path, required=True)
    watch.add_argument("--username")
    watch.add_argument(
        "--max-samples",
        type=int,
        default=0,
        help="Stop after this many comparisons; 0 waits until one event",
    )
    watch.add_argument(
        "--snapshot-only",
        action="store_true",
        help="Use authenticated snapshots instead of the continuous RTSP stream",
    )

    classify = subparsers.add_parser(
        "classify-event",
        help="Classify one captured five-frame event without deciding or actuating",
    )
    classify.add_argument("--config", type=Path, required=True)
    classify.add_argument("--event", type=Path, required=True)

    decide = subparsers.add_parser(
        "decide-event",
        help="Run saved classifications through deterministic authorization only",
    )
    decide.add_argument("--config", type=Path, required=True)
    decide.add_argument("--event", type=Path, required=True)

    process = subparsers.add_parser(
        "process-event",
        help="Resume one event through vision, decision, bounded actuation, and notification",
    )
    process.add_argument("--config", type=Path, required=True)
    process.add_argument("--event", type=Path, required=True)

    run_once = subparsers.add_parser(
        "run-once",
        help="Watch for one motion event and run the complete restart-safe HATI loop",
    )
    run_once.add_argument("--config", type=Path, required=True)
    run_once.add_argument("--username")
    run_once.add_argument(
        "--max-samples",
        type=int,
        default=0,
        help="Stop after this many comparisons; 0 waits until one event",
    )
    run_once.add_argument(
        "--snapshot-only",
        action="store_true",
        help="Use authenticated snapshots instead of the continuous RTSP stream",
    )

    supervise = subparsers.add_parser(
        "supervise",
        help="Continuously watch, process, notify, and recover until stopped",
    )
    supervise.add_argument("--config", type=Path, required=True)
    supervise.add_argument("--username")
    supervise.add_argument(
        "--mode",
        choices=("disarmed", "armed"),
        default="disarmed",
        help="Disarmed runs the full pipeline without physical action; armed permits it",
    )
    supervise.add_argument(
        "--confirm-armed",
        default="",
        help="Armed mode requires the exact confirmation text: ARM HATI",
    )
    supervise.add_argument(
        "--max-events",
        type=int,
        default=0,
        help="Stop after this many completed events; 0 runs until interrupted",
    )
    supervise.add_argument(
        "--max-samples",
        type=int,
        default=0,
        help="Restart the watcher after this many quiet comparisons; 0 waits indefinitely",
    )
    supervise.add_argument(
        "--snapshot-only",
        action="store_true",
        help="Use authenticated snapshots instead of the continuous RTSP stream",
    )
    supervise.add_argument("--retry-seconds", type=float, default=5.0)
    supervise.add_argument(
        "--telegram-state",
        type=Path,
        default=Path("data/runtime/telegram-offset.json"),
    )

    telegram_preview = subparsers.add_parser(
        "telegram-preview",
        help="Render an event notification without contacting Telegram",
    )
    telegram_preview.add_argument("--config", type=Path, required=True)
    telegram_preview.add_argument("--event", type=Path, required=True)

    telegram_notify = subparsers.add_parser(
        "telegram-notify", help="Send one saved event to the configured owner"
    )
    telegram_notify.add_argument("--config", type=Path, required=True)
    telegram_notify.add_argument("--event", type=Path, required=True)

    telegram_poll = subparsers.add_parser(
        "telegram-poll-once",
        help="Process one batch of owner feedback and commands",
    )
    telegram_poll.add_argument("--config", type=Path, required=True)
    telegram_poll.add_argument("--offset", type=int)

    telegram_loop = subparsers.add_parser(
        "telegram-poll",
        help="Continuously process owner commands and feedback with restart-safe offsets",
    )
    telegram_loop.add_argument("--config", type=Path, required=True)
    telegram_loop.add_argument(
        "--state",
        type=Path,
        default=Path("data/runtime/telegram-offset.json"),
    )
    telegram_loop.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Stop after this many polls; 0 runs until interrupted",
    )
    telegram_loop.add_argument("--retry-seconds", type=float, default=3.0)
    return parser


def _load(path: Path) -> HatiConfig:
    try:
        return load_config(path)
    except ConfigurationError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _doctor(config: HatiConfig) -> int:
    report = {
        "configuration": "valid",
        "camera_id": config.camera.camera_id,
        "camera_host": config.camera.host,
        "camera_port": config.camera.port,
        "camera_credentials_present": config.camera.credentials_present,
        "protected_zones": sorted(config.events.protected_zones),
        "frames_per_event": config.events.frames_per_event,
        "motion_zone": config.motion.zone_name,
        "motion_changed_pixel_ratio": config.motion.changed_pixel_ratio,
        "camera_rediscovery": config.motion.rediscover_camera,
        "consensus": (
            f"{config.decision.predator_consensus_required}/"
            f"{config.decision.minimum_usable_observations}"
        ),
        "vision_model": config.vision.model,
        "vision_image_detail": config.vision.image_detail,
        "local_gate_enabled": config.local_gate.enabled,
        "local_gate_mode": "shadow" if config.local_gate.shadow_mode else "enforcing",
        "local_gate_model": config.local_gate.model,
        "local_gate_loopback_only": True,
        "armed": config.runtime.armed,
        "test_mode": config.runtime.test_mode,
        "camera_connection_tested": False,
        "actuator_kind": config.actuator.kind,
        "actuator_burst_seconds": config.actuator.burst_seconds,
        "actuator_spray_mode": config.actuator.spray_mode,
        "actuator_private_config_present": config.actuator.private_device_config.exists(),
        "actuator_integration_present": config.actuator.kind == "tuya_diffuser",
        "telegram_enabled": config.telegram.enabled,
        "telegram_owner_present": bool(config.telegram.owner_chat_id),
        "telegram_manual_deploy_enabled": config.telegram.manual_deploy_enabled,
    }
    print(json.dumps(report, indent=2))
    return 0


def _simulate(config: HatiConfig, scenario: str) -> int:
    zone = sorted(config.events.protected_zones)[0]
    event = build_simulated_event(scenario, config.camera.camera_id, zone)
    # Simulation exercises the authorization path in an explicitly synthetic state.
    # No actuator implementation is called.
    state = SystemState(armed=True, actuator_available=True)
    event.decision = authorize(
        event,
        state,
        config.decision,
        config.events.protected_zones,
    )
    event.processing_state = ProcessingState.DECIDED
    destination = EventStore(config.events.event_directory).save(event)
    output = {
        "notice": "CONTROLLED SIMULATION — no camera, model, or actuator was used",
        "scenario": scenario,
        "event_id": event.event_id,
        "decision": to_jsonable(event.decision),
        "trace_path": str(destination),
    }
    print(json.dumps(output, indent=2))
    return 0


def _demo(config: HatiConfig, scenario: str, output: Path) -> int:
    scenarios = list(EXPECTED) if scenario == "all" else [scenario]
    store = EventStore(output)
    summaries = []
    for name in scenarios:
        result = run_demo_case(config, name)
        destination = store.save(result.event)
        summaries.append(
            {
                "scenario": name,
                "outcome": result.event.decision.outcome,
                "reason_code": result.event.decision.reason_code,
                "dry_run_called": result.dry_run_called,
                "physical_action": False,
                "passed": result.passed,
                "trace_path": str(destination),
            }
        )
    passed = all(item["passed"] for item in summaries)
    print(
        json.dumps(
            {
                "notice": (
                    "CONTROLLED JUDGE DEMO — synthetic observations, no API, "
                    "no camera, no physical actuator"
                ),
                "passed": passed,
                "scenarios": to_jsonable(summaries),
            },
            indent=2,
        )
    )
    return 0 if passed else 1


def _evaluate(config: HatiConfig, cases: Path) -> int:
    try:
        report = evaluate_improvement(
            cases,
            config.decision,
            sorted(config.events.protected_zones)[0],
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Evaluation failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.candidate_promoted else 1


def _review_event_feedback(event_path: Path, output: Path) -> int:
    event = _load_event(event_path)
    try:
        artifact, destination = review_event(event, output)
    except ValueError as exc:
        print(f"Learning review failed: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "result": "feedback_reviewed",
                "event_id": artifact.event_id,
                "feedback": artifact.feedback_kind,
                "disposition": artifact.disposition,
                "protected_regression": artifact.protected_regression,
                "candidate_id": (
                    artifact.candidate.candidate_id if artifact.candidate else None
                ),
                "reason": artifact.reason,
                "artifact_path": str(destination),
                "model_called": False,
                "physical_action": False,
            },
            indent=2,
            default=str,
        )
    )
    return 0


def _active_vision_policy(config: HatiConfig) -> tuple[str, str]:
    try:
        return load_active_policy(config.vision.active_policy_path)
    except ValueError as exc:
        print(f"Active vision policy failed closed: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _evaluate_vision_improvement(
    config: HatiConfig,
    candidate_path: Path,
    events: Path,
    reports: Path,
    max_protected: int,
) -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print(
            "Vision improvement evaluation needs the encrypted local OpenAI API key.",
            file=sys.stderr,
        )
        return 2
    try:
        candidate = load_candidate(candidate_path)
        report = evaluate_vision_candidate(
            candidate,
            config,
            events,
            lambda paths, policy_id, addendum: classify_frames(
                paths,
                config.vision,
                api_key=api_key,
                policy_id=policy_id,
                policy_addendum=addendum,
                cascade=False,
            ),
            max_protected_cases=max_protected,
        )
        report_path, active_path = save_evaluation(
            candidate,
            report,
            reports,
            config.vision.active_policy_path,
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError, VisionError) as exc:
        print(f"Vision improvement evaluation failed: {exc}", file=sys.stderr)
        return 2
    finally:
        api_key = ""
    print(
        json.dumps(
            {
                "result": "vision_improvement_evaluated",
                "candidate_id": report.candidate_id,
                "model_requests": report.policy_request_count,
                "protected_cases": report.protected_case_count,
                "corrected_failures": report.corrected_failures,
                "regressions": report.regressions,
                "candidate_promoted": report.candidate_promoted,
                "report_path": str(report_path),
                "active_policy_path": str(active_path) if active_path else None,
                "physical_action": False,
            },
            indent=2,
        )
    )
    return 0 if report.candidate_promoted else 1


def _camera_probe(
    config: HatiConfig,
    username: str,
    stream_name: str,
    output: Path | None,
) -> int:
    username = username or config.camera.username or "hati_viewer"
    password = config.camera.password
    if not password:
        if not sys.stdin.isatty():
            print(
                "Camera probe needs the encrypted local credential or an interactive terminal.",
                file=sys.stderr,
            )
            return 2
        password = getpass.getpass(f"Password for local camera user '{username}': ")
    if not password:
        print("Camera password cannot be blank.", file=sys.stderr)
        return 2
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = output or Path("data/camera_probe") / f"{stream_name}-{timestamp}.jpg"
    try:
        capture = capture_snapshot(
            config.camera,
            username,
            password,
            destination,
        )
    except CameraError as snapshot_error:
        print(
            f"Snapshot probe unavailable ({snapshot_error}); trying RTSP.",
            file=sys.stderr,
        )
        try:
            capture = capture_frame(
                config.camera,
                username,
                password,
                destination,
                stream_name=stream_name,
            )
        except CameraError as stream_error:
            print(f"Camera probe failed: {stream_error}", file=sys.stderr)
            return 1
    finally:
        password = ""
    print(
        json.dumps(
            {
                "camera_id": config.camera.camera_id,
                "stream": capture.stream_name,
                "frame_path": str(capture.path),
                "width": capture.width,
                "height": capture.height,
                "captured_at": capture.captured_at.isoformat(),
                "plaintext_credentials_stored": False,
            },
            indent=2,
        )
    )
    return 0


def _capture_motion_event(
    config: HatiConfig,
    username: str,
    password: str,
    max_samples: int,
    snapshot_only: bool = False,
):
    camera = config.camera
    if config.motion.rediscover_camera:
        print("Verifying camera address...", flush=True)
        camera = resolve_camera_host(camera, username, password)
    print(
        f"HATI SEE is watching {camera.camera_id} at {camera.host}:{camera.port} "
        f"in zone {config.motion.zone_name}.",
        flush=True,
    )
    status = lambda message: print(message, flush=True)
    if snapshot_only:
        status("Using authenticated snapshot capture for camera stability.")
        return (
            *watch_once(
                camera,
                config.events,
                config.motion,
                username,
                password,
                max_samples=max_samples,
                status=status,
            ),
            camera,
        )

    status("Opening a low-latency continuous camera stream...")
    try:
        with RtspFrameSession(camera, username, password) as stream:
            event, trace_path, motion = watch_once(
                camera,
                config.events,
                config.motion,
                username,
                password,
                max_samples=max_samples,
                snapshotter=lambda _camera, _username, _password, path: (
                    stream.capture(path)
                ),
                status=status,
            )
    except CameraError as stream_error:
        status(f"Continuous stream unavailable ({stream_error}); using snapshots.")
        event, trace_path, motion = watch_once(
            camera,
            config.events,
            config.motion,
            username,
            password,
            max_samples=max_samples,
            status=status,
        )
    return event, trace_path, motion, camera


def _camera_watch_credentials(config: HatiConfig, username: str | None):
    username = username or config.camera.username or "hati_viewer"
    password = config.camera.password
    if not password and sys.stdin.isatty():
        password = getpass.getpass(f"Password for local camera user '{username}': ")
    return username, password


def _capture_replay(config: HatiConfig, username: str | None) -> int:
    username, password = _camera_watch_credentials(config, username)
    if not password:
        print(
            "Replay capture needs the encrypted local camera credential.",
            file=sys.stderr,
        )
        return 2

    started = datetime.now(timezone.utc)
    event = EventRecord(
        event_id=f"evt-replay-{started.strftime('%Y%m%dT%H%M%S%fZ')}",
        start_time=started,
        camera_id=config.camera.camera_id,
        zone=config.motion.zone_name,
        trigger_reason="controlled_replay_capture:no_motion_claim",
    )
    event_dir = config.events.event_directory / event.event_id
    event_dir.mkdir(parents=True, exist_ok=False)
    try:
        for frame_number in range(1, config.events.frames_per_event + 1):
            if frame_number > 1:
                time.sleep(config.motion.event_frame_interval_seconds)
            frame_path = event_dir / f"frame-{frame_number:03d}.jpg"
            capture_snapshot(config.camera, username, password, frame_path)
            event.frame_paths.append(frame_path)
            print(
                f"Captured controlled replay frame "
                f"{frame_number}/{config.events.frames_per_event}.",
                flush=True,
            )
    except CameraError as exc:
        print(f"Controlled replay capture failed: {exc}", file=sys.stderr)
        return 1
    finally:
        password = ""

    event.end_time = datetime.now(timezone.utc)
    trace_path = EventStore(config.events.event_directory).save(event)
    print(
        json.dumps(
            {
                "result": "controlled_replay_captured",
                "event_id": event.event_id,
                "frame_count": len(event.frame_paths),
                "trigger_reason": event.trigger_reason,
                "trace_path": str(trace_path),
                "model_called": False,
                "actuator_called": False,
            },
            indent=2,
        )
    )
    return 0


def _watch(
    config: HatiConfig,
    username: str | None,
    max_samples: int,
    snapshot_only: bool = False,
) -> int:
    username, password = _camera_watch_credentials(config, username)
    if not password:
        print(
            "Camera watch needs the encrypted local credential or an interactive terminal.",
            file=sys.stderr,
        )
        return 2
    if max_samples < 0:
        print("--max-samples cannot be negative.", file=sys.stderr)
        return 2

    try:
        event, trace_path, motion, camera = _capture_motion_event(
            config, username, password, max_samples, snapshot_only
        )
    except (CameraError, WatchError) as exc:
        print(f"Camera watch failed: {exc}", file=sys.stderr)
        return 1
    finally:
        password = ""

    print(
        json.dumps(
            {
                "result": "motion_event_captured",
                "event_id": event.event_id,
                "camera_host": camera.host,
                "zone": event.zone,
                "changed_pixel_ratio": motion.changed_pixel_ratio,
                "frame_count": len(event.frame_paths),
                "trace_path": str(trace_path),
                "plaintext_credentials_stored": False,
            },
            indent=2,
        )
    )
    return 0


def _classify_event(config: HatiConfig, event_path: Path) -> int:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        print(
            "Vision classification needs the encrypted local OpenAI API key.",
            file=sys.stderr,
        )
        return 2
    try:
        event = EventStore.load(event_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Could not load event trace: {type(exc).__name__}", file=sys.stderr)
        return 2
    if event.processing_state is not ProcessingState.CAPTURED:
        print(
            f"Event is already {event.processing_state.value}; refusing a duplicate paid request.",
            file=sys.stderr,
        )
        return 2
    policy_id, policy_addendum = _active_vision_policy(config)
    try:
        result = classify_frames(
            event.frame_paths,
            config.vision,
            api_key=api_key,
            policy_id=policy_id,
            policy_addendum=policy_addendum,
            cascade=False,
        )
    except VisionError as exc:
        print(f"Vision classification failed: {exc}", file=sys.stderr)
        return 1
    finally:
        api_key = ""

    event.classifications = list(result.classifications)
    event.inference_trace = result.trace
    event.processing_state = ProcessingState.CLASSIFIED
    destination = EventStore(config.events.event_directory).save(event)
    print(
        json.dumps(
            {
                "result": "event_classified",
                "event_id": event.event_id,
                "model": result.trace.model,
                "api": result.trace.api,
                "request_count": result.trace.request_count,
                "image_detail": result.trace.image_detail,
                "usage": {
                    "input_tokens": result.trace.input_tokens,
                    "output_tokens": result.trace.output_tokens,
                    "total_tokens": result.trace.total_tokens,
                },
                "classifications": to_jsonable(event.classifications),
                "trace_path": str(destination),
                "decision_made": False,
                "actuator_called": False,
            },
            indent=2,
        )
    )
    return 0


def _decide_event(config: HatiConfig, event_path: Path) -> int:
    try:
        event = EventStore.load(event_path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Could not load event trace: {type(exc).__name__}", file=sys.stderr)
        return 2
    if event.processing_state is not ProcessingState.CLASSIFIED:
        print(
            f"Event must be classified before deciding; current state is "
            f"{event.processing_state.value}.",
            file=sys.stderr,
        )
        return 2

    state = SystemState(
        armed=config.runtime.armed,
        actuator_available=(
            config.actuator.kind == "tuya_diffuser"
            and config.actuator.private_device_config.exists()
        ),
    )
    event.decision = authorize(
        event,
        state,
        config.decision,
        config.events.protected_zones,
    )
    event.processing_state = ProcessingState.DECIDED
    destination = EventStore(config.events.event_directory).save(event)
    print(
        json.dumps(
            {
                "result": "event_decided",
                "event_id": event.event_id,
                "decision": to_jsonable(event.decision),
                "trace_path": str(destination),
                "actuator_called": False,
            },
            indent=2,
        )
    )
    return 0


def _pipeline_actuator(config: HatiConfig):
    if config.runtime.test_mode:
        return DryRunActuator(), False
    actuator = _configured_actuator(config)
    return actuator, config.actuator.kind == "tuya_diffuser"


def _process_event(config: HatiConfig, event_path: Path) -> int:
    event = _load_event(event_path)
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if event.processing_state is ProcessingState.CAPTURED and not api_key:
        print(
            "Vision classification needs the encrypted local OpenAI API key.",
            file=sys.stderr,
        )
        return 2
    actuator, physical_action = _pipeline_actuator(config)
    store = EventStore(config.events.event_directory)
    policy_id, policy_addendum = _active_vision_policy(config)
    try:
        result = process_event(
            event,
            config,
            store,
            lambda paths: classify_frames(
                paths,
                config.vision,
                api_key=api_key,
                policy_id=policy_id,
                policy_addendum=policy_addendum,
            ),
            actuator,
            physical_action=physical_action,
            local_gate=(
                (lambda paths: run_shadow_gate(paths, config.local_gate))
                if config.local_gate.enabled
                else None
            ),
            local_gate_suppresses_luna=(
                config.local_gate.enabled and not config.local_gate.shadow_mode
            ),
        )
    except VisionError as exc:
        print(f"Vision classification failed: {exc}", file=sys.stderr)
        return 1
    finally:
        api_key = ""

    notified = False
    progressed = result.classified or result.decided or result.actuator_called
    if config.telegram.enabled and progressed:
        try:
            _telegram_client(config).send_event(result.event)
            notified = True
        except TelegramError as exc:
            print(f"Event was saved, but {exc}", file=sys.stderr)

    destination = store.root / result.event.event_id / "event.json"
    print(
        json.dumps(
            {
                "result": "event_pipeline_complete",
                "event_id": result.event.event_id,
                "processing_state": result.event.processing_state.value,
                "local_gate_ran": result.local_gate_ran,
                "local_gate": to_jsonable(result.event.local_gate_trace),
                "classified": result.classified,
                "decision": to_jsonable(result.event.decision),
                "actuator_called": result.actuator_called,
                "actuation": to_jsonable(result.event.actuation),
                "replay_refused": result.replay_refused,
                "telegram_notified": notified,
                "trace_path": str(destination),
            },
            indent=2,
        )
    )
    return 0


def _run_once(
    config: HatiConfig,
    username: str | None,
    max_samples: int,
    snapshot_only: bool = False,
) -> int:
    username, password = _camera_watch_credentials(config, username)
    if not password:
        print(
            "Run-once needs the encrypted local camera credential or an interactive terminal.",
            file=sys.stderr,
        )
        return 2
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "Run-once needs the encrypted local OpenAI API key.",
            file=sys.stderr,
        )
        return 2
    if max_samples < 0:
        print("--max-samples cannot be negative.", file=sys.stderr)
        return 2
    try:
        _event, trace_path, _motion, _camera = _capture_motion_event(
            config, username, password, max_samples, snapshot_only
        )
    except (CameraError, WatchError) as exc:
        print(f"Camera watch failed: {exc}", file=sys.stderr)
        return 1
    finally:
        password = ""
    return _process_event(config, trace_path)


def _supervisor_config(
    config: HatiConfig,
    mode: str,
    armed_confirmation: str,
) -> HatiConfig:
    if mode == "disarmed":
        return replace(
            config,
            runtime=replace(config.runtime, armed=False, test_mode=True),
        )
    if mode != "armed":
        raise ValueError("Supervisor mode must be disarmed or armed")
    if armed_confirmation != "ARM HATI":
        raise ValueError("Armed mode requires the exact confirmation text: ARM HATI")
    if config.actuator.kind != "tuya_diffuser":
        raise ValueError("Armed mode requires actuator.kind=tuya_diffuser")
    if not config.actuator.private_device_config.is_file():
        raise ValueError("Armed mode requires the private diffuser configuration")
    return replace(
        config,
        runtime=replace(config.runtime, armed=True, test_mode=False),
    )


def _supervise(
    config: HatiConfig,
    username: str | None,
    max_events: int,
    max_samples: int,
    snapshot_only: bool,
    retry_seconds: float,
    telegram_state: Path,
    *,
    capture_event=None,
    process_path=None,
    sleeper=time.sleep,
    start_telegram: bool = True,
) -> int:
    if max_events < 0:
        print("--max-events cannot be negative.", file=sys.stderr)
        return 2
    if max_samples < 0:
        print("--max-samples cannot be negative.", file=sys.stderr)
        return 2
    if retry_seconds < 0:
        print("--retry-seconds cannot be negative.", file=sys.stderr)
        return 2

    username, password = _camera_watch_credentials(config, username)
    if not password:
        print(
            "Supervisor needs the encrypted local camera credential.",
            file=sys.stderr,
        )
        return 2
    if not os.environ.get("OPENAI_API_KEY"):
        print(
            "Supervisor needs the encrypted local OpenAI API key.",
            file=sys.stderr,
        )
        return 2

    capture_event = capture_event or _capture_motion_event
    process_path = process_path or _process_event
    physical_enabled = config.runtime.armed and not config.runtime.test_mode
    print(
        json.dumps(
            {
                "result": "hati_supervisor_started",
                "mode": "armed" if physical_enabled else "disarmed",
                "physical_action_enabled": physical_enabled,
                "actuator_duration_seconds": config.actuator.burst_seconds,
                "actuator_spray_mode": config.actuator.spray_mode,
                "local_gate_enabled": config.local_gate.enabled,
                "local_gate_mode": (
                    "shadow" if config.local_gate.shadow_mode else "enforcing"
                ),
                "local_gate_model": config.local_gate.model,
                "snapshot_only": snapshot_only,
                "max_events": max_events,
                "stop": "Press Ctrl+C",
            }
        ),
        flush=True,
    )

    if config.telegram.enabled and start_telegram:
        telegram_thread = threading.Thread(
            target=_telegram_poll_forever,
            args=(config, telegram_state, 0, retry_seconds),
            name="hati-telegram",
            daemon=True,
        )
        telegram_thread.start()

    completed = 0
    recoveries = 0
    try:
        while max_events == 0 or completed < max_events:
            try:
                _event, trace_path, _motion, _camera = capture_event(
                    config,
                    username,
                    password,
                    max_samples,
                    snapshot_only,
                )
            except (CameraError, WatchError) as exc:
                recoveries += 1
                print(
                    f"Supervisor camera cycle failed safely: {exc}; "
                    f"retrying in {retry_seconds:g} seconds",
                    file=sys.stderr,
                    flush=True,
                )
                sleeper(retry_seconds)
                continue

            while True:
                result = process_path(config, trace_path)
                if result == 0:
                    completed += 1
                    print(
                        json.dumps(
                            {
                                "result": "hati_supervisor_event_complete",
                                "event_number": completed,
                                "trace_path": str(trace_path),
                            }
                        ),
                        flush=True,
                    )
                    break
                if result == 2:
                    return 2
                recoveries += 1
                print(
                    "Supervisor event processing failed safely; retrying the same "
                    f"saved event in {retry_seconds:g} seconds",
                    file=sys.stderr,
                    flush=True,
                )
                sleeper(retry_seconds)
    except KeyboardInterrupt:
        print("HATI supervisor stopped by operator.", flush=True)
    finally:
        password = ""

    print(
        json.dumps(
            {
                "result": "hati_supervisor_stopped",
                "events_completed": completed,
                "recoveries": recoveries,
            }
        ),
        flush=True,
    )
    return 0


def _load_event(path: Path) -> EventRecord:
    try:
        return EventStore.load(path)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Could not load event trace: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2) from exc


def _telegram_preview(event_path: Path) -> int:
    event = _load_event(event_path)
    print(json.dumps(notification_preview(event), indent=2))
    return 0


def _telegram_client(config: HatiConfig) -> TelegramClient:
    if not config.telegram.enabled:
        print("Telegram is disabled in local configuration.", file=sys.stderr)
        raise SystemExit(2)
    try:
        return TelegramClient(config.telegram)
    except ValueError as exc:
        print(f"Telegram configuration error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


def _telegram_notify(config: HatiConfig, event_path: Path) -> int:
    event = _load_event(event_path)
    try:
        _telegram_client(config).send_event(event)
    except TelegramError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"result": "telegram_notification_sent", "event_id": event.event_id}))
    return 0


def _configured_actuator(config: HatiConfig):
    if config.actuator.kind == "dry_run":
        return DryRunActuator()
    try:
        return TuyaDiffuserActuator.from_private_config(
            config.actuator.private_device_config,
            burst_seconds=config.actuator.burst_seconds,
            spray_mode=config.actuator.spray_mode,
            light_enabled=config.actuator.light_enabled,
            light_dps=dict(config.actuator.light_dps),
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Actuator configuration error: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2) from exc


def _telegram_components(config: HatiConfig, feedback_handler=None):
    client = _telegram_client(config)
    controller = TelegramController(
        config.telegram,
        EventStore(config.events.event_directory),
        _configured_actuator(config),
        runtime_armed=config.runtime.armed,
        test_mode=config.runtime.test_mode,
        feedback_handler=feedback_handler,
    )
    return client, controller


def _telegram_poll(config: HatiConfig, offset: int | None) -> int:
    client, controller = _telegram_components(config)
    try:
        updates = client.get_updates(offset)
        batch = process_updates(client, controller, updates, offset)
    except TelegramError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(batch.as_dict(), indent=2))
    return 0


def _telegram_poll_forever(
    config: HatiConfig,
    state_path: Path,
    max_iterations: int,
    retry_seconds: float,
) -> int:
    if max_iterations < 0:
        print("--max-iterations cannot be negative.", file=sys.stderr)
        return 2
    if retry_seconds < 0:
        print("--retry-seconds cannot be negative.", file=sys.stderr)
        return 2
    state = TelegramOffsetStore(state_path)
    try:
        offset = state.load()
    except TelegramError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    def notify_learning(message: str) -> None:
        TelegramClient(config.telegram).send_text(message)

    learning_worker = AutomaticLearningWorker(config, notifier=notify_learning)
    learning_worker.start()
    client, controller = _telegram_components(config, learning_worker.submit)
    print(
        json.dumps(
            {
                "result": "telegram_operator_link_started",
                "state_path": str(state_path),
                "manual_deploy_enabled": config.telegram.manual_deploy_enabled,
                "armed": config.runtime.armed,
                "test_mode": config.runtime.test_mode,
            }
        ),
        flush=True,
    )
    iterations = 0
    try:
        while max_iterations == 0 or iterations < max_iterations:
            iterations += 1
            try:
                updates = client.get_updates(offset)
                batch = process_updates(
                    client,
                    controller,
                    updates,
                    offset,
                    commit_offset=state.save,
                )
                offset = batch.next_offset
                if batch.processed:
                    print(json.dumps(batch.as_dict()), flush=True)
            except TelegramError as exc:
                offset = state.load()
                print(f"{exc}; retrying in {retry_seconds:g} seconds", file=sys.stderr)
                time.sleep(retry_seconds)
                # Rebuild the transport after a network failure. In practice this
                # clears stale Windows networking state that a process restart also
                # clears, while preserving the already-committed update offset.
                client, controller = _telegram_components(
                    config,
                    learning_worker.submit,
                )
    except KeyboardInterrupt:
        print("HATI Telegram operator link stopped.", flush=True)
    finally:
        learning_worker.stop()
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = _load(args.config)
    configure_logging(config.runtime.log_level)
    if args.command == "doctor":
        return _doctor(config)
    if args.command == "simulate":
        return _simulate(config, args.scenario)
    if args.command == "demo":
        return _demo(config, args.scenario, args.output)
    if args.command == "evaluate-improvement":
        return _evaluate(config, args.cases)
    if args.command == "review-event-feedback":
        return _review_event_feedback(args.event, args.output)
    if args.command == "evaluate-vision-improvement":
        return _evaluate_vision_improvement(
            config,
            args.candidate,
            args.events,
            args.reports,
            args.max_protected,
        )
    if args.command == "camera-probe":
        return _camera_probe(config, args.username, args.stream, args.output)
    if args.command == "capture-replay":
        return _capture_replay(config, args.username)
    if args.command == "watch":
        return _watch(config, args.username, args.max_samples, args.snapshot_only)
    if args.command == "classify-event":
        return _classify_event(config, args.event)
    if args.command == "decide-event":
        return _decide_event(config, args.event)
    if args.command == "process-event":
        return _process_event(config, args.event)
    if args.command == "run-once":
        return _run_once(
            config, args.username, args.max_samples, args.snapshot_only
        )
    if args.command == "supervise":
        try:
            supervisor_config = _supervisor_config(
                config,
                args.mode,
                args.confirm_armed,
            )
        except ValueError as exc:
            print(f"Supervisor configuration error: {exc}", file=sys.stderr)
            return 2
        return _supervise(
            supervisor_config,
            args.username,
            args.max_events,
            args.max_samples,
            args.snapshot_only,
            args.retry_seconds,
            args.telegram_state,
        )
    if args.command == "telegram-preview":
        return _telegram_preview(args.event)
    if args.command == "telegram-notify":
        return _telegram_notify(config, args.event)
    if args.command == "telegram-poll-once":
        return _telegram_poll(config, args.offset)
    if args.command == "telegram-poll":
        return _telegram_poll_forever(
            config,
            args.state,
            args.max_iterations,
            args.retry_seconds,
        )
    raise AssertionError(f"Unhandled command: {args.command}")
