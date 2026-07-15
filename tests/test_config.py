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

    def test_vision_detail_must_be_supported(self) -> None:
        invalid = json.loads(json.dumps(VALID_CONFIG))
        invalid["vision"] = {"image_detail": "microscopic"}
        with tempfile.TemporaryDirectory() as temporary:
            path = self.write_config(Path(temporary), invalid)
            with self.assertRaises(ConfigurationError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
