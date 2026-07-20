from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from hati.camera import (
    RtspFrameSession,
    build_rtsp_url,
    build_snapshot_url,
    resolve_camera_host,
)
from hati.config import CameraConfig


class CameraUrlTests(unittest.TestCase):
    def test_credentials_are_url_encoded(self) -> None:
        camera = CameraConfig(camera_id="test", host="192.0.2.1", port=88)
        url = build_rtsp_url(camera, "hati viewer", "p@ss/word", "videoSub")
        self.assertEqual(
            "rtsp://hati%20viewer:p%40ss%2Fword@192.0.2.1:88/videoSub", url
        )

    def test_unknown_stream_is_rejected(self) -> None:
        camera = CameraConfig(camera_id="test", host="192.0.2.1", port=88)
        with self.assertRaises(ValueError):
            build_rtsp_url(camera, "user", "password", "mystery")

    def test_snapshot_credentials_are_url_encoded(self) -> None:
        camera = CameraConfig(camera_id="test", host="192.0.2.1", port=88)
        url = build_snapshot_url(camera, "hati viewer", "p@ss/word")
        self.assertEqual(
            "http://192.0.2.1:88/cgi-bin/CGIProxy.fcgi"
            "?cmd=snapPicture2&usr=hati%20viewer&pwd=p%40ss%2Fword",
            url,
        )

    @patch("hati.camera._probe_camera_host")
    def test_camera_keeps_configured_host_when_authenticated(self, probe) -> None:
        probe.return_value = True
        camera = CameraConfig(camera_id="test", host="192.0.2.10", port=88)
        resolved = resolve_camera_host(camera, "viewer", "secret")
        self.assertIs(camera, resolved)

    @patch("hati.camera._probe_camera_host")
    def test_camera_is_rediscovered_with_authenticated_probe(self, probe) -> None:
        probe.side_effect = lambda camera, host, username, password, timeout: (
            host == "192.0.2.22"
        )
        camera = CameraConfig(camera_id="test", host="192.0.2.10", port=88)
        resolved = resolve_camera_host(
            camera,
            "viewer",
            "secret",
            candidates=["192.0.2.21", "192.0.2.22"],
        )
        self.assertEqual("192.0.2.22", resolved.host)

    def test_continuous_session_writes_latest_frame_and_clears_password(self) -> None:
        class FakeFrame:
            shape = (720, 1280, 3)

            def copy(self):
                return self

        class FakeVideo:
            def __init__(self) -> None:
                self.released = False

            def isOpened(self) -> bool:
                return True

            def set(self, _property, _value) -> bool:
                return True

            def read(self):
                return (not self.released, FakeFrame() if not self.released else None)

            def release(self) -> None:
                self.released = True

        video = FakeVideo()

        def imwrite(path: str, _frame: FakeFrame) -> bool:
            Path(path).write_bytes(b"fake-jpeg")
            return True

        fake_cv2 = SimpleNamespace(
            CAP_FFMPEG=1,
            CAP_PROP_OPEN_TIMEOUT_MSEC=2,
            CAP_PROP_READ_TIMEOUT_MSEC=3,
            CAP_PROP_BUFFERSIZE=4,
            VideoCapture=lambda *_args: video,
            imwrite=imwrite,
        )
        camera = CameraConfig(camera_id="test", host="192.0.2.1", port=88)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "frame.jpg"
            with patch.dict(sys.modules, {"cv2": fake_cv2}):
                session = RtspFrameSession(
                    camera,
                    "viewer",
                    "secret",
                    warmup_frames=0,
                    startup_timeout_seconds=1,
                )
                with session:
                    capture = session.capture(output)
            self.assertTrue(output.exists())
        self.assertEqual((1280, 720), (capture.width, capture.height))
        self.assertEqual("", session.password)
        self.assertTrue(video.released)


if __name__ == "__main__":
    unittest.main()
