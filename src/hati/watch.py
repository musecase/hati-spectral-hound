"""One-event camera watcher for the first real HATI SEE milestone."""

from __future__ import annotations

import os
import shutil
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from hati.camera import CameraError, FrameCapture, capture_snapshot
from hati.config import CameraConfig, EventConfig, MotionConfig
from hati.event_store import EventStore
from hati.models import EventRecord
from hati.motion import MotionResult, measure_motion


class Snapshotter(Protocol):
    def __call__(
        self,
        camera: CameraConfig,
        username: str,
        password: str,
        output_path: Path,
    ) -> FrameCapture: ...


class WatchError(RuntimeError):
    """Raised when the watcher cannot produce a valid motion event."""


def _read_frame(path: Path):
    try:
        import cv2
    except ImportError as exc:
        raise WatchError("OpenCV is required for the camera watcher") from exc
    frame = cv2.imread(str(path))
    if frame is None:
        raise WatchError(f"Camera sample is not a readable image: {path}")
    return frame


def _event_id(now: datetime) -> str:
    return "evt-" + now.strftime("%Y%m%dT%H%M%S%fZ")


def _capture_with_retry(
    snapshotter: Snapshotter,
    camera: CameraConfig,
    username: str,
    password: str,
    output_path: Path,
    sleeper: Callable[[float], None],
    status: Callable[[str], None],
    *,
    attempts: int = 3,
) -> FrameCapture:
    for attempt in range(1, attempts + 1):
        try:
            return snapshotter(camera, username, password, output_path)
        except CameraError as exc:
            if attempt == attempts:
                raise WatchError(
                    f"Camera snapshot failed after {attempts} attempts"
                ) from exc
            status(f"Snapshot attempt {attempt} failed; retrying.")
            sleeper(2.0)
    raise AssertionError("unreachable")


def watch_once(
    camera: CameraConfig,
    events: EventConfig,
    motion: MotionConfig,
    username: str,
    password: str,
    *,
    max_samples: int = 0,
    snapshotter: Snapshotter = capture_snapshot,
    sleeper: Callable[[float], None] = time.sleep,
    status: Callable[[str], None] = print,
) -> tuple[EventRecord, Path, MotionResult]:
    """Watch until one zone-motion event is captured, then stop safely."""
    runtime_dir = events.event_directory.parent / "runtime"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    previous_path = runtime_dir / "watch-previous.jpg"
    current_path = runtime_dir / "watch-current.jpg"

    status("Capturing baseline frame...")
    _capture_with_retry(
        snapshotter,
        camera,
        username,
        password,
        previous_path,
        sleeper,
        status,
    )
    previous = _read_frame(previous_path)
    status("Baseline ready. Walk through the camera frame now.")

    sample_count = 0
    while max_samples <= 0 or sample_count < max_samples:
        sleeper(motion.poll_interval_seconds)
        _capture_with_retry(
            snapshotter,
            camera,
            username,
            password,
            current_path,
            sleeper,
            status,
        )
        current = _read_frame(current_path)
        sample_count += 1
        result = measure_motion(previous, current, motion)
        status(
            f"Motion sample {sample_count}: "
            f"{result.changed_pixel_ratio:.3%} changed "
            f"(trigger {motion.changed_pixel_ratio:.3%})"
        )
        if not result.triggered:
            previous = current
            os.replace(current_path, previous_path)
            continue

        started = datetime.now(timezone.utc)
        event = EventRecord(
            event_id=_event_id(started),
            start_time=started,
            camera_id=camera.camera_id,
            zone=motion.zone_name,
            trigger_reason=(
                "zone_motion:"
                f"{result.changed_pixel_ratio:.6f}>={motion.changed_pixel_ratio:.6f}"
            ),
        )
        event_dir = events.event_directory / event.event_id
        event_dir.mkdir(parents=True, exist_ok=True)
        buffered_sources = (
            [current_path]
            if events.frames_per_event == 1
            else [previous_path, current_path]
        )
        for frame_number, source in enumerate(buffered_sources, start=1):
            frame_path = event_dir / f"frame-{frame_number:03d}.jpg"
            shutil.copy2(source, frame_path)
            event.frame_paths.append(frame_path)
        captured_count = len(event.frame_paths)
        status(
            f"Motion detected in {motion.zone_name}; "
            f"captured {captured_count}/{events.frames_per_event} frames "
            "including the pre-trigger frame."
        )

        for frame_number in range(captured_count + 1, events.frames_per_event + 1):
            sleeper(motion.event_frame_interval_seconds)
            frame_path = event_dir / f"frame-{frame_number:03d}.jpg"
            _capture_with_retry(
                snapshotter,
                camera,
                username,
                password,
                frame_path,
                sleeper,
                status,
            )
            event.frame_paths.append(frame_path)
            status(f"Captured event frame {frame_number}/{events.frames_per_event}.")

        event.end_time = datetime.now(timezone.utc)
        trace_path = EventStore(events.event_directory).save(event)
        status(f"Event saved: {trace_path}")
        return event, trace_path, result

    raise WatchError(f"No motion event detected after {sample_count} samples")
