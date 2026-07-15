"""Small operator-facing commands for safe setup and controlled simulation."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from hati.actuator import DryRunActuator, TuyaDiffuserActuator
from hati.camera import (
    CameraError,
    capture_frame,
    capture_snapshot,
    resolve_camera_host,
)
from hati.config import ConfigurationError, HatiConfig, load_config
from hati.decision import authorize
from hati.demo import EXPECTED, run_demo_case
from hati.event_store import EventStore
from hati.evaluation import evaluate_improvement
from hati.logging_config import configure_logging
from hati.models import EventRecord, ProcessingState, SystemState, to_jsonable
from hati.simulation import SCENARIOS, build_simulated_event
from hati.telegram import (
    TelegramClient,
    TelegramController,
    TelegramError,
    notification_preview,
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

    camera_probe = subparsers.add_parser(
        "camera-probe", help="Prompt locally and capture one authenticated camera frame"
    )
    camera_probe.add_argument("--config", type=Path, required=True)
    camera_probe.add_argument("--username")
    camera_probe.add_argument(
        "--stream", choices=("videoSub", "videoMain"), default="videoSub"
    )
    camera_probe.add_argument("--output", type=Path)

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
        "armed": config.runtime.armed,
        "test_mode": config.runtime.test_mode,
        "camera_connection_tested": False,
        "actuator_kind": config.actuator.kind,
        "actuator_burst_seconds": config.actuator.burst_seconds,
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


def _watch(config: HatiConfig, username: str | None, max_samples: int) -> int:
    username = username or config.camera.username or "hati_viewer"
    password = config.camera.password
    if not password:
        if not sys.stdin.isatty():
            print(
                "Camera watch needs the encrypted local credential or an interactive terminal.",
                file=sys.stderr,
            )
            return 2
        password = getpass.getpass(f"Password for local camera user '{username}': ")
    if not password:
        print("Camera password cannot be blank.", file=sys.stderr)
        return 2
    if max_samples < 0:
        print("--max-samples cannot be negative.", file=sys.stderr)
        return 2

    try:
        camera = config.camera
        if config.motion.rediscover_camera:
            print("Verifying camera address...", flush=True)
            camera = resolve_camera_host(camera, username, password)
        print(
            f"HATI SEE is watching {camera.camera_id} at {camera.host}:{camera.port} "
            f"in zone {config.motion.zone_name}.",
            flush=True,
        )
        event, trace_path, motion = watch_once(
            camera,
            config.events,
            config.motion,
            username,
            password,
            max_samples=max_samples,
            status=lambda message: print(message, flush=True),
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
    try:
        result = classify_frames(
            event.frame_paths,
            config.vision,
            api_key=api_key,
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
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"Actuator configuration error: {type(exc).__name__}", file=sys.stderr)
        raise SystemExit(2) from exc


def _telegram_poll(config: HatiConfig, offset: int | None) -> int:
    client = _telegram_client(config)
    controller = TelegramController(
        config.telegram,
        EventStore(config.events.event_directory),
        _configured_actuator(config),
    )
    try:
        updates = client.get_updates(offset)
        results = []
        next_offset = offset
        for update in updates:
            action = controller.handle(update)
            update_id = int(update.get("update_id", 0))
            next_offset = max(next_offset or 0, update_id + 1)
            callback = update.get("callback_query")
            if isinstance(callback, dict) and callback.get("id"):
                client.answer_callback(str(callback["id"]), action.detail)
            elif action.kind != "ignored":
                client.send_text(action.detail)
            results.append(
                {
                    "update_id": update_id,
                    "kind": action.kind,
                    "accepted": action.accepted,
                    "detail": action.detail,
                    "event_id": action.event_id,
                }
            )
    except TelegramError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {"processed": len(results), "next_offset": next_offset, "results": results},
            indent=2,
        )
    )
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
    if args.command == "camera-probe":
        return _camera_probe(config, args.username, args.stream, args.output)
    if args.command == "watch":
        return _watch(config, args.username, args.max_samples)
    if args.command == "classify-event":
        return _classify_event(config, args.event)
    if args.command == "decide-event":
        return _decide_event(config, args.event)
    if args.command == "telegram-preview":
        return _telegram_preview(args.event)
    if args.command == "telegram-notify":
        return _telegram_notify(config, args.event)
    if args.command == "telegram-poll-once":
        return _telegram_poll(config, args.offset)
    raise AssertionError(f"Unhandled command: {args.command}")
