"""Authenticated local camera access with credential-safe diagnostics."""

from __future__ import annotations

import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from dataclasses import replace
from datetime import datetime, timezone
from ipaddress import ip_network
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from hati.config import CameraConfig


class CameraError(RuntimeError):
    """Raised when a local camera stream cannot produce a usable frame."""


@dataclass(frozen=True)
class FrameCapture:
    path: Path
    width: int
    height: int
    captured_at: datetime
    stream_name: str


class RtspFrameSession:
    """Continuously drain RTSP and expose only the newest decoded frame."""

    def __init__(
        self,
        camera: CameraConfig,
        username: str,
        password: str,
        *,
        stream_name: str = "videoSub",
        warmup_frames: int = 60,
        startup_timeout_seconds: float = 12.0,
        frame_timeout_seconds: float = 8.0,
    ) -> None:
        self.camera = camera
        self.username = username
        self.password = password
        self.stream_name = stream_name
        self.warmup_frames = warmup_frames
        self.startup_timeout_seconds = startup_timeout_seconds
        self.frame_timeout_seconds = frame_timeout_seconds
        self._condition = threading.Condition()
        self._stop = threading.Event()
        self._video = None
        self._thread: threading.Thread | None = None
        self._frame = None
        self._sequence = 0
        self._delivered_sequence = 0
        self._failure: str | None = None
        self._cv2 = None

    def __enter__(self) -> "RtspFrameSession":
        try:
            import cv2
        except ImportError as exc:
            raise CameraError(
                "OpenCV is not installed. Run scripts/setup.ps1 first."
            ) from exc

        url = build_rtsp_url(
            self.camera,
            self.username,
            self.password,
            self.stream_name,
        )
        previous_options = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
        os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
            "rtsp_transport;tcp|fflags;nobuffer"
        )
        parameters = [
            cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
            8_000,
            cv2.CAP_PROP_READ_TIMEOUT_MSEC,
            8_000,
        ]
        video = None
        try:
            video = cv2.VideoCapture(url, cv2.CAP_FFMPEG, parameters)
        finally:
            if previous_options is None:
                os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
            else:
                os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = previous_options
            url = ""
        if video is None or not video.isOpened():
            if video is not None:
                video.release()
            raise CameraError("The continuous camera stream did not open")
        video.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self._cv2 = cv2
        self._video = video
        self._thread = threading.Thread(
            target=self._read_forever,
            name="hati-rtsp-reader",
            daemon=True,
        )
        self._thread.start()

        deadline = time.monotonic() + self.startup_timeout_seconds
        with self._condition:
            while self._frame is None and self._failure is None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
        if self._frame is None:
            detail = self._failure or "no decoded frame arrived before timeout"
            self.close()
            raise CameraError(f"The continuous camera stream produced no usable frame: {detail}")
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _read_forever(self) -> None:
        successful_frames = 0
        consecutive_failures = 0
        while not self._stop.is_set():
            succeeded, frame = self._video.read()
            if not succeeded or frame is None:
                consecutive_failures += 1
                if consecutive_failures >= 30:
                    with self._condition:
                        self._failure = "the stream stopped returning decoded frames"
                        self._condition.notify_all()
                    return
                continue
            consecutive_failures = 0
            successful_frames += 1
            if successful_frames <= self.warmup_frames:
                continue
            with self._condition:
                self._frame = frame
                self._sequence += 1
                self._condition.notify_all()

    def capture(self, output_path: Path) -> FrameCapture:
        """Write a fresh frame without reopening or falling behind the stream."""
        deadline = time.monotonic() + self.frame_timeout_seconds
        with self._condition:
            while (
                self._sequence <= self._delivered_sequence
                and self._failure is None
            ):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._condition.wait(remaining)
            if self._sequence <= self._delivered_sequence or self._frame is None:
                detail = self._failure or "a fresh frame did not arrive before timeout"
                raise CameraError(f"Continuous camera capture failed: {detail}")
            frame = self._frame.copy()
            self._delivered_sequence = self._sequence

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(output_path.stem + ".tmp" + output_path.suffix)
        if not self._cv2.imwrite(str(temporary), frame):
            raise CameraError(f"Failed to encode captured frame for {output_path}")
        os.replace(temporary, output_path)
        height, width = frame.shape[:2]
        return FrameCapture(
            path=output_path,
            width=int(width),
            height=int(height),
            captured_at=datetime.now(timezone.utc),
            stream_name=self.stream_name,
        )

    def close(self) -> None:
        self._stop.set()
        if self._video is not None:
            self._video.release()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.password = ""


def _probe_camera_host(
    camera: CameraConfig,
    host: str,
    username: str,
    password: str,
    timeout_seconds: float,
) -> bool:
    encoded_username = quote(username, safe="")
    encoded_password = quote(password, safe="")
    url = (
        f"http://{host}:{camera.port}/cgi-bin/CGIProxy.fcgi"
        f"?cmd=getProductModel&usr={encoded_username}&pwd={encoded_password}"
    )
    try:
        with urlopen(url, timeout=timeout_seconds) as response:
            payload = response.read(4096)
    except (HTTPError, URLError, TimeoutError, OSError):
        return False
    return b"<result>0</result>" in payload


def resolve_camera_host(
    camera: CameraConfig,
    username: str,
    password: str,
    *,
    candidates: Iterable[str] | None = None,
    timeout_seconds: float = 0.8,
) -> CameraConfig:
    """Return the authenticated camera, rediscovering it within the local /24."""
    if _probe_camera_host(
        camera, camera.host, username, password, timeout_seconds
    ):
        return camera

    if candidates is None:
        network = ip_network(f"{camera.host}/24", strict=False)
        candidate_hosts = [str(host) for host in network.hosts()]
    else:
        candidate_hosts = [str(host) for host in candidates]
    candidate_hosts = [host for host in candidate_hosts if host != camera.host]

    def authenticated(host: str) -> str | None:
        if _probe_camera_host(camera, host, username, password, timeout_seconds):
            return host
        return None

    with ThreadPoolExecutor(max_workers=min(64, max(1, len(candidate_hosts)))) as pool:
        matches = [host for host in pool.map(authenticated, candidate_hosts) if host]
    if not matches:
        raise CameraError(
            "The configured camera was unavailable and authenticated rediscovery found no match"
        )
    if len(matches) > 1:
        raise CameraError(
            "Authenticated rediscovery found multiple matching cameras; configure a unique camera user"
        )
    return replace(camera, host=matches[0])


def build_rtsp_url(
    camera: CameraConfig, username: str, password: str, stream_name: str
) -> str:
    """Build a credential-bearing URL that must never be logged or persisted."""
    if stream_name not in {"videoSub", "videoMain"}:
        raise ValueError("stream_name must be videoSub or videoMain")
    encoded_username = quote(username, safe="")
    encoded_password = quote(password, safe="")
    return (
        f"rtsp://{encoded_username}:{encoded_password}@"
        f"{camera.host}:{camera.port}/{stream_name}"
    )


def build_snapshot_url(camera: CameraConfig, username: str, password: str) -> str:
    """Build Foscam's authenticated snapshot URL without persisting credentials."""
    encoded_username = quote(username, safe="")
    encoded_password = quote(password, safe="")
    return (
        f"http://{camera.host}:{camera.port}/cgi-bin/CGIProxy.fcgi"
        f"?cmd=snapPicture2&usr={encoded_username}&pwd={encoded_password}"
    )


def capture_snapshot(
    camera: CameraConfig,
    username: str,
    password: str,
    output_path: Path,
    *,
    timeout_seconds: float = 15.0,
) -> FrameCapture:
    """Capture one authenticated JPEG when continuous RTSP is unavailable."""
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise CameraError(
            "OpenCV is not installed. Run scripts/setup.ps1 first."
        ) from exc

    request = Request(
        build_snapshot_url(camera, username, password),
        headers={"User-Agent": "HATI-Spectral-Hound/0.1"},
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            jpeg = response.read()
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise CameraError("The camera snapshot endpoint did not respond") from exc

    frame = cv2.imdecode(np.frombuffer(jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
    if frame is None:
        raise CameraError("The camera snapshot endpoint returned an invalid image")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.stem + ".tmp" + output_path.suffix)
    if not cv2.imwrite(str(temporary), frame):
        raise CameraError(f"Failed to encode captured frame for {output_path}")
    os.replace(temporary, output_path)
    height, width = frame.shape[:2]
    return FrameCapture(
        path=output_path,
        width=int(width),
        height=int(height),
        captured_at=datetime.now(timezone.utc),
        stream_name="snapshot",
    )


def capture_frame(
    camera: CameraConfig,
    username: str,
    password: str,
    output_path: Path,
    *,
    stream_name: str = "videoSub",
    warmup_frames: int = 4,
) -> FrameCapture:
    """Capture one frame over RTSP/TCP without retaining camera credentials."""
    try:
        import cv2
    except ImportError as exc:
        raise CameraError(
            "OpenCV is not installed. Run scripts/setup.ps1 first."
        ) from exc

    url = build_rtsp_url(camera, username, password, stream_name)
    previous_options = os.environ.get("OPENCV_FFMPEG_CAPTURE_OPTIONS")
    os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "rtsp_transport;tcp"
    parameters = [
        cv2.CAP_PROP_OPEN_TIMEOUT_MSEC,
        8_000,
        cv2.CAP_PROP_READ_TIMEOUT_MSEC,
        8_000,
    ]
    video = cv2.VideoCapture(url, cv2.CAP_FFMPEG, parameters)
    try:
        if not video.isOpened():
            raise CameraError(
                "The camera stream did not open. Check the local username, password, and network."
            )
        frame = None
        for _ in range(max(1, warmup_frames + 1)):
            succeeded, candidate = video.read()
            if succeeded and candidate is not None:
                frame = candidate
        if frame is None:
            raise CameraError("The camera stream opened but returned no usable frame")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = output_path.with_name(output_path.stem + ".tmp" + output_path.suffix)
        if not cv2.imwrite(str(temporary), frame):
            raise CameraError(f"Failed to encode captured frame for {output_path}")
        os.replace(temporary, output_path)
        height, width = frame.shape[:2]
        return FrameCapture(
            path=output_path,
            width=int(width),
            height=int(height),
            captured_at=datetime.now(timezone.utc),
            stream_name=stream_name,
        )
    finally:
        video.release()
        if previous_options is None:
            os.environ.pop("OPENCV_FFMPEG_CAPTURE_OPTIONS", None)
        else:
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = previous_options
