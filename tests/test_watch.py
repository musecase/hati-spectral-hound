from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from hati.camera import FrameCapture
from hati.config import CameraConfig, EventConfig, MotionConfig
from hati.watch import watch_once


class WatchTests(unittest.TestCase):
    def test_motion_creates_five_frame_event_and_trace(self) -> None:
        baseline = np.zeros((100, 100, 3), dtype=np.uint8)
        changed = baseline.copy()
        changed[20:80, 20:80] = 255
        frames = [baseline, changed, changed, changed, changed, changed]

        def snapshotter(camera, username, password, output_path):
            frame = frames.pop(0)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            self.assertTrue(cv2.imwrite(str(output_path), frame))
            return FrameCapture(
                path=output_path,
                width=100,
                height=100,
                captured_at=datetime.now(timezone.utc),
                stream_name="snapshot",
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "events"
            camera = CameraConfig(camera_id="test-camera", host="192.0.2.10")
            events = EventConfig(
                event_directory=root,
                protected_zones=frozenset({"TEST_ZONE"}),
                frames_per_event=5,
            )
            motion = MotionConfig(
                zone_name="TEST_ZONE",
                changed_pixel_ratio=0.05,
                pixel_threshold=10,
                blur_size=1,
                poll_interval_seconds=0,
                event_frame_interval_seconds=0,
            )
            event, trace_path, result = watch_once(
                camera,
                events,
                motion,
                "viewer",
                "secret",
                max_samples=1,
                snapshotter=snapshotter,
                sleeper=lambda seconds: None,
                status=lambda message: None,
            )
            payload = json.loads(trace_path.read_text(encoding="utf-8"))

        self.assertTrue(result.triggered)
        self.assertEqual(5, len(event.frame_paths))
        self.assertEqual(5, len(payload["frame_paths"]))
        self.assertEqual("TEST_ZONE", payload["zone"])
        self.assertTrue(payload["trigger_reason"].startswith("zone_motion:"))


if __name__ == "__main__":
    unittest.main()
