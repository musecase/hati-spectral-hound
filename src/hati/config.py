"""Human-readable configuration with secrets kept outside source control."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigurationError(ValueError):
    """Raised when configuration is missing or violates a safety invariant."""


@dataclass(frozen=True)
class CameraConfig:
    camera_id: str
    host: str
    port: int = 88
    low_bandwidth_path: str = "/videoSub"
    high_quality_path: str = "/videoMain"
    username: str | None = field(default=None, repr=False)
    password: str | None = field(default=None, repr=False)

    @property
    def credentials_present(self) -> bool:
        return bool(self.username and self.password)


@dataclass(frozen=True)
class EventConfig:
    event_directory: Path
    protected_zones: frozenset[str]
    frames_per_event: int = 5


@dataclass(frozen=True)
class MotionConfig:
    zone_name: str = "COOP_DOOR_ZONE"
    zone_polygon: tuple[tuple[float, float], ...] = (
        (0.0, 0.0),
        (1.0, 0.0),
        (1.0, 1.0),
        (0.0, 1.0),
    )
    changed_pixel_ratio: float = 0.025
    pixel_threshold: int = 25
    blur_size: int = 5
    poll_interval_seconds: float = 0.5
    event_frame_interval_seconds: float = 0.5
    rediscover_camera: bool = True


@dataclass(frozen=True)
class DecisionConfig:
    minimum_usable_observations: int = 5
    predator_consensus_required: int = 4
    cooldown_seconds: int = 600
    predator_labels: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {"raccoon", "fox", "coyote", "opossum", "skunk"}
        )
    )


@dataclass(frozen=True)
class VisionConfig:
    model: str = "gpt-5.6-luna"
    image_detail: str = "high"
    reasoning_effort: str = "low"
    max_output_tokens: int = 1200


@dataclass(frozen=True)
class RuntimeConfig:
    armed: bool = False
    test_mode: bool = True
    log_level: str = "INFO"


@dataclass(frozen=True)
class ActuatorConfig:
    kind: str = "dry_run"
    private_device_config: Path = Path("config/tuya-device.json")
    burst_seconds: float = 5.0


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    owner_chat_id: str = ""
    manual_deploy_enabled: bool = True
    poll_timeout_seconds: int = 10
    token: str | None = field(default=None, repr=False)


@dataclass(frozen=True)
class HatiConfig:
    camera: CameraConfig
    events: EventConfig
    motion: MotionConfig
    decision: DecisionConfig
    vision: VisionConfig
    actuator: ActuatorConfig
    telegram: TelegramConfig
    runtime: RuntimeConfig


def _require_mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise ConfigurationError(f"Configuration section '{key}' must be an object")
    return value


def load_config(path: str | Path) -> HatiConfig:
    """Load configuration while sourcing all secret values from the environment."""
    config_path = Path(path)
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ConfigurationError(f"Configuration file not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid JSON in {config_path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigurationError("Configuration root must be an object")

    camera_raw = _require_mapping(raw, "camera")
    events_raw = _require_mapping(raw, "events")
    motion_raw = raw.get("motion", {})
    if not isinstance(motion_raw, dict):
        raise ConfigurationError("Configuration section 'motion' must be an object")
    decision_raw = _require_mapping(raw, "decision")
    vision_raw = raw.get("vision", {})
    if not isinstance(vision_raw, dict):
        raise ConfigurationError("Configuration section 'vision' must be an object")
    actuator_raw = raw.get("actuator", {})
    if not isinstance(actuator_raw, dict):
        raise ConfigurationError("Configuration section 'actuator' must be an object")
    telegram_raw = raw.get("telegram", {})
    if not isinstance(telegram_raw, dict):
        raise ConfigurationError("Configuration section 'telegram' must be an object")
    runtime_raw = _require_mapping(raw, "runtime")

    camera = CameraConfig(
        camera_id=str(camera_raw.get("camera_id", "coop-camera")),
        host=str(camera_raw.get("host", "")).strip(),
        port=int(camera_raw.get("port", 88)),
        low_bandwidth_path=str(camera_raw.get("low_bandwidth_path", "/videoSub")),
        high_quality_path=str(camera_raw.get("high_quality_path", "/videoMain")),
        username=os.environ.get("HATI_CAMERA_USERNAME"),
        password=os.environ.get("HATI_CAMERA_PASSWORD"),
    )
    events = EventConfig(
        event_directory=Path(events_raw.get("event_directory", "data/events")),
        protected_zones=frozenset(str(v) for v in events_raw.get("protected_zones", [])),
        frames_per_event=int(events_raw.get("frames_per_event", 5)),
    )
    raw_polygon = motion_raw.get(
        "zone_polygon",
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
    )
    try:
        zone_polygon = tuple((float(point[0]), float(point[1])) for point in raw_polygon)
    except (TypeError, ValueError, IndexError) as exc:
        raise ConfigurationError(
            "motion.zone_polygon must be a list of [x, y] coordinate pairs"
        ) from exc
    motion = MotionConfig(
        zone_name=str(
            motion_raw.get(
                "zone_name",
                sorted(events.protected_zones)[0] if events.protected_zones else "",
            )
        ),
        zone_polygon=zone_polygon,
        changed_pixel_ratio=float(motion_raw.get("changed_pixel_ratio", 0.025)),
        pixel_threshold=int(motion_raw.get("pixel_threshold", 25)),
        blur_size=int(motion_raw.get("blur_size", 5)),
        poll_interval_seconds=float(motion_raw.get("poll_interval_seconds", 0.5)),
        event_frame_interval_seconds=float(
            motion_raw.get("event_frame_interval_seconds", 0.5)
        ),
        rediscover_camera=bool(motion_raw.get("rediscover_camera", True)),
    )
    decision = DecisionConfig(
        minimum_usable_observations=int(
            decision_raw.get("minimum_usable_observations", 5)
        ),
        predator_consensus_required=int(
            decision_raw.get("predator_consensus_required", 4)
        ),
        cooldown_seconds=int(decision_raw.get("cooldown_seconds", 600)),
        predator_labels=frozenset(
            str(v).lower() for v in decision_raw.get("predator_labels", [])
        ),
    )
    vision = VisionConfig(
        model=str(vision_raw.get("model", "gpt-5.6-luna")).strip(),
        image_detail=str(vision_raw.get("image_detail", "high")).strip().lower(),
        reasoning_effort=str(
            vision_raw.get("reasoning_effort", "low")
        ).strip().lower(),
        max_output_tokens=int(vision_raw.get("max_output_tokens", 1200)),
    )
    actuator = ActuatorConfig(
        kind=str(actuator_raw.get("kind", "dry_run")).strip().lower(),
        private_device_config=Path(
            actuator_raw.get("private_device_config", "config/tuya-device.json")
        ),
        burst_seconds=float(actuator_raw.get("burst_seconds", 5.0)),
    )
    telegram = TelegramConfig(
        enabled=bool(telegram_raw.get("enabled", False)),
        owner_chat_id=str(
            os.environ.get(
                "HATI_TELEGRAM_CHAT_ID", telegram_raw.get("owner_chat_id", "")
            )
        ).strip(),
        manual_deploy_enabled=bool(
            telegram_raw.get("manual_deploy_enabled", True)
        ),
        poll_timeout_seconds=int(telegram_raw.get("poll_timeout_seconds", 10)),
        token=os.environ.get("HATI_TELEGRAM_BOT_TOKEN"),
    )
    runtime = RuntimeConfig(
        armed=bool(runtime_raw.get("armed", False)),
        test_mode=bool(runtime_raw.get("test_mode", True)),
        log_level=str(runtime_raw.get("log_level", "INFO")).upper(),
    )

    _validate(camera, events, motion, decision, vision, actuator, telegram)
    return HatiConfig(
        camera=camera,
        events=events,
        motion=motion,
        decision=decision,
        vision=vision,
        actuator=actuator,
        telegram=telegram,
        runtime=runtime,
    )


def _validate(
    camera: CameraConfig,
    events: EventConfig,
    motion: MotionConfig,
    decision: DecisionConfig,
    vision: VisionConfig,
    actuator: ActuatorConfig,
    telegram: TelegramConfig,
) -> None:
    if not camera.host:
        raise ConfigurationError("camera.host must not be empty")
    if not 1 <= camera.port <= 65535:
        raise ConfigurationError("camera.port must be between 1 and 65535")
    if not events.protected_zones:
        raise ConfigurationError("At least one protected zone is required")
    if events.frames_per_event < 1:
        raise ConfigurationError("events.frames_per_event must be positive")
    if motion.zone_name not in events.protected_zones:
        raise ConfigurationError("motion.zone_name must name a configured protected zone")
    if len(motion.zone_polygon) < 3:
        raise ConfigurationError("motion.zone_polygon requires at least three points")
    if any(not (0 <= x <= 1 and 0 <= y <= 1) for x, y in motion.zone_polygon):
        raise ConfigurationError("motion.zone_polygon coordinates must be between 0 and 1")
    if not 0 < motion.changed_pixel_ratio <= 1:
        raise ConfigurationError("motion.changed_pixel_ratio must be between 0 and 1")
    if not 0 <= motion.pixel_threshold <= 255:
        raise ConfigurationError("motion.pixel_threshold must be between 0 and 255")
    if motion.blur_size < 1 or motion.blur_size % 2 == 0:
        raise ConfigurationError("motion.blur_size must be a positive odd number")
    if motion.poll_interval_seconds < 0 or motion.event_frame_interval_seconds < 0:
        raise ConfigurationError("motion intervals cannot be negative")
    if decision.minimum_usable_observations < 1:
        raise ConfigurationError("minimum_usable_observations must be positive")
    if decision.predator_consensus_required < 1:
        raise ConfigurationError("predator_consensus_required must be positive")
    if decision.predator_consensus_required > decision.minimum_usable_observations:
        raise ConfigurationError(
            "predator_consensus_required cannot exceed minimum_usable_observations"
        )
    if decision.minimum_usable_observations > events.frames_per_event:
        raise ConfigurationError(
            "minimum_usable_observations cannot exceed events.frames_per_event"
        )
    if decision.cooldown_seconds < 0:
        raise ConfigurationError("cooldown_seconds cannot be negative")
    if not decision.predator_labels:
        raise ConfigurationError("At least one predator label is required")
    if "human" in decision.predator_labels:
        raise ConfigurationError("human cannot be configured as a predator label")
    if not vision.model:
        raise ConfigurationError("vision.model must not be empty")
    if vision.image_detail not in {"low", "high", "original", "auto"}:
        raise ConfigurationError("vision.image_detail is unsupported")
    if vision.reasoning_effort not in {"none", "low", "medium", "high", "xhigh", "max"}:
        raise ConfigurationError("vision.reasoning_effort is unsupported")
    if not 1 <= vision.max_output_tokens <= 4000:
        raise ConfigurationError("vision.max_output_tokens must be between 1 and 4000")
    if actuator.kind not in {"dry_run", "tuya_diffuser"}:
        raise ConfigurationError("actuator.kind must be 'dry_run' or 'tuya_diffuser'")
    if not 0 < actuator.burst_seconds <= 5:
        raise ConfigurationError("actuator.burst_seconds must be greater than 0 and at most 5")
    if telegram.enabled and not telegram.owner_chat_id:
        raise ConfigurationError("telegram.owner_chat_id is required when Telegram is enabled")
    if telegram.enabled and not telegram.token:
        raise ConfigurationError("HATI_TELEGRAM_BOT_TOKEN is required when Telegram is enabled")
    if not 0 <= telegram.poll_timeout_seconds <= 30:
        raise ConfigurationError("telegram.poll_timeout_seconds must be between 0 and 30")
