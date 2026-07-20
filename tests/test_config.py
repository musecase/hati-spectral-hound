from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hati.config import ConfigurationError, load_config


VALID_CONFIG = {
    "camera": {"camera_id": "test", "host": "192.0.2.10", "port": 88},
    "events": {
        "event_directory": "data/events",
        "protected_zones": ["COOP_DOOR_ZONE"],
        "frames_per_event": 5,
    },
    "decision": {
        "minimum_usable_observations": 5,
        "predator_consensus_required": 4,
        "cooldown_seconds": 600,
        "predator_labels": ["raccoon"],
    },
    "runtime": {"armed": False, "test_mode": True, "log_level": "INFO"},
}


class ConfigTests(unittest.TestCase):
    def write_config(self, root: Path, data: dict) -> Path:
        path = root / "config.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_credentials_come_from_environment_and_are_hidden_from_repr(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), VALID_CONFIG)
            with patch.dict(
                os.environ,
                {"HATI_CAMERA_USERNAME": "keeper", "HATI_CAMERA_PASSWORD": "secret"},
                clear=False,
            ):
                config = load_config(path)
        self.assertTrue(config.camera.credentials_present)
        self.assertNotIn("secret", repr(config.camera))
        self.assertNotIn("keeper", repr(config.camera))

    def test_consensus_cannot_exceed_observation_count(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["decision"]["predator_consensus_required"] = 6
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_human_cannot_be_configured_as_predator(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["decision"]["predator_labels"] = ["raccoon", "human"]
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_motion_defaults_to_full_configured_zone(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), VALID_CONFIG)
            config = load_config(path)
        self.assertEqual("COOP_DOOR_ZONE", config.motion.zone_name)
        self.assertEqual(4, len(config.motion.zone_polygon))

    def test_motion_polygon_must_use_normalized_coordinates(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["motion"] = {
            "zone_name": "COOP_DOOR_ZONE",
            "zone_polygon": [[0, 0], [2, 0], [0, 1]],
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_motion_rearm_quiet_samples_are_bounded(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["motion"] = {"rearm_quiet_samples": -1}
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_vision_detail_must_be_supported(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["vision"] = {"image_detail": "microscopic"}
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_actuator_spray_mode_must_be_supported(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["actuator"] = {
            "burst_seconds": 300,
            "spray_mode": "ludicrous",
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_enabled_actuator_light_requires_observed_datapoints(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["actuator"] = {"light": {"enabled": True, "dps": {}}}
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_local_gate_must_remain_on_loopback(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["local_gate"] = {
            "enabled": True,
            "base_url": "https://example.com/v1",
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_local_gate_can_enable_benign_suppression(self) -> None:
        enforcing = json.loads(json.dumps(VALID_CONFIG))
        enforcing["local_gate"] = {
            "enabled": True,
            "shadow_mode": False,
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), enforcing)
            config = load_config(path)

        self.assertTrue(config.local_gate.enabled)
        self.assertFalse(config.local_gate.shadow_mode)

    def test_local_gate_focus_box_must_be_normalized(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["local_gate"] = {"focus_box": [0, 0.2, 1.4, 1]}
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)

    def test_non_telegram_commands_can_load_without_telegram_secrets(self) -> None:
        local = json.loads(json.dumps(VALID_CONFIG))
        local["telegram"] = {"enabled": True, "manual_deploy_enabled": False}
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), local)
            with patch.dict(
                os.environ,
                {"HATI_TELEGRAM_CHAT_ID": "", "HATI_TELEGRAM_BOT_TOKEN": ""},
                clear=False,
            ):
                config = load_config(path)
        self.assertTrue(config.telegram.enabled)
        self.assertEqual("", config.telegram.owner_chat_id)
        self.assertIsNone(config.telegram.token)


if __name__ == "__main__":
    unittest.main()
