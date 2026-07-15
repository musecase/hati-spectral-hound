from __future__ import annotations

import unittest
from unittest.mock import patch

from hati.camera import build_rtsp_url, build_snapshot_url, resolve_camera_host
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


if __name__ == "__main__":
    unittest.main()
