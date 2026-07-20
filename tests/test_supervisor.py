from __future__ import annotations

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from hati.camera import CameraError
from hati.cli import _supervise, _supervisor_config
from hati.config import load_config


def configured(root: Path):
    base = load_config(Path("config/hati.example.json"))
    private_device = root / "tuya-device.json"
    private_device.write_text("{}", encoding="utf-8")
    return replace(
        base,
        camera=replace(
            base.camera,
            username="hati_viewer",
            password="camera-secret",
        ),
        actuator=replace(
            base.actuator,
            kind="tuya_diffuser",
            private_device_config=private_device,
        ),
        telegram=replace(base.telegram, enabled=False),
    )


class SupervisorTests(unittest.TestCase):
    def test_disarmed_mode_overrides_local_runtime_safely(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = configured(Path(temporary))
            config = replace(
                config,
                runtime=replace(config.runtime, armed=True, test_mode=False),
            )
            selected = _supervisor_config(config, "disarmed", "")

        self.assertFalse(selected.runtime.armed)
        self.assertTrue(selected.runtime.test_mode)

    def test_armed_mode_requires_exact_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = configured(Path(temporary))
            with self.assertRaises(ValueError):
                _supervisor_config(config, "armed", "yes")

    def test_armed_mode_enables_the_same_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = configured(Path(temporary))
            selected = _supervisor_config(config, "armed", "ARM HATI")

        self.assertTrue(selected.runtime.armed)
        self.assertFalse(selected.runtime.test_mode)

    def test_loop_recovers_camera_and_retries_same_saved_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            config = _supervisor_config(
                configured(Path(temporary)),
                "disarmed",
                "",
            )
            trace_path = Path(temporary) / "event.json"
            capture_calls = 0
            processed: list[Path] = []
            sleeps: list[float] = []

            def capture(*_args):
                nonlocal capture_calls
                capture_calls += 1
                if capture_calls == 1:
                    raise CameraError("offline")
                return object(), trace_path, object(), object()

            def process(_config, path: Path) -> int:
                processed.append(path)
                return 1 if len(processed) == 1 else 0

            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                result = _supervise(
                    config,
                    None,
                    max_events=1,
                    max_samples=0,
                    snapshot_only=True,
                    retry_seconds=2,
                    telegram_state=Path(temporary) / "offset.json",
                    capture_event=capture,
                    process_path=process,
                    sleeper=sleeps.append,
                    start_telegram=False,
                )

        self.assertEqual(0, result)
        self.assertEqual(2, capture_calls)
        self.assertEqual([trace_path, trace_path], processed)
        self.assertEqual([2, 2], sleeps)


if __name__ == "__main__":
    unittest.main()
