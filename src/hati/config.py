"""Human-readable configuration with secrets kept outside source control."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


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
    rearm_quiet_samples: int = 0
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
    active_policy_path: Path = Path("data/learning/active-policy.json")


@dataclass(frozen=True)
class LocalGateConfig:
    enabled: bool = False
    shadow_mode: bool = True
    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = "google/gemma-4-e4b"
    timeout_seconds: int = 120
    max_output_tokens: int = 240
    minimum_bird_panels: int = 1
    focus_box: tuple[float, float, float, float] = (0.0, 0.28, 1.0, 0.9)


@dataclass(frozen=True)
class RuntimeConfig:
    armed: bool = False
    test_mode: bool = True
    log_level: str = "INFO"


@dataclass(frozen=True)
class ActuatorConfig:
    kind: str = "dry_run"
    private_device_config: Path = Path("config/tuya-device.json")
    burst_seconds: float = 300.0
    spray_mode: str = "big"
    light_enabled: bool = False
    light_dps: tuple[tuple[str, Any], ...] = ()


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
    local_gate: LocalGateConfig
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
    local_gate_raw = raw.get("local_gate", {})
    if not isinstance(local_gate_raw, dict):
        raise ConfigurationError("Configuration section 'local_gate' must be an object")
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
        rearm_quiet_samples=int(motion_raw.get("rearm_quiet_samples", 0)),
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
        active_policy_path=Path(
            vision_raw.get("active_policy_path", "data/learning/active-policy.json")
        ),
    )
    local_gate = LocalGateConfig(
        enabled=bool(local_gate_raw.get("enabled", False)),
        shadow_mode=bool(local_gate_raw.get("shadow_mode", True)),
        base_url=str(
            local_gate_raw.get("base_url", "http://127.0.0.1:1234/v1")
        ).rstrip("/"),
        model=str(local_gate_raw.get("model", "google/gemma-4-e4b")).strip(),
        timeout_seconds=int(local_gate_raw.get("timeout_seconds", 120)),
        max_output_tokens=int(local_gate_raw.get("max_output_tokens", 240)),
        minimum_bird_panels=int(local_gate_raw.get("minimum_bird_panels", 1)),
        focus_box=tuple(
            float(value)
            for value in local_gate_raw.get("focus_box", [0.0, 0.28, 1.0, 0.9])
        ),
    )
    light_raw = actuator_raw.get("light", {})
    if not isinstance(light_raw, dict):
        raise ConfigurationError("Configuration section 'actuator.light' must be an object")
    light_dps_raw = light_raw.get("dps", {})
    if not isinstance(light_dps_raw, dict):
        raise ConfigurationError("actuator.light.dps must be an object")
    actuator = ActuatorConfig(
        kind=str(actuator_raw.get("kind", "dry_run")).strip().lower(),
        private_device_config=Path(
            actuator_raw.get("private_device_config", "config/tuya-device.json")
        ),
        burst_seconds=float(actuator_raw.get("burst_seconds", 300.0)),
        spray_mode=str(actuator_raw.get("spray_mode", "big")).strip().lower(),
        light_enabled=bool(light_raw.get("enabled", False)),
        light_dps=tuple((str(key), value) for key, value in light_dps_raw.items()),
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
        token=os.environ.get("HATI_TELEGRAM_BOT_TOKEN") or None,
    )
    runtime = RuntimeConfig(
        armed=bool(runtime_raw.get("armed", False)),
        test_mode=bool(runtime_raw.get("test_mode", True)),
        log_level=str(runtime_raw.get("log_level", "INFO")).upper(),
    )

    _validate(
        camera,
        events,
        motion,
        decision,
        vision,
        local_gate,
        actuator,
        telegram,
    )
    return HatiConfig(
        camera=camera,
        events=events,
        motion=motion,
        decision=decision,
        vision=vision,
        local_gate=local_gate,
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
    local_gate: LocalGateConfig,
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
    if not 0 <= motion.rearm_quiet_samples <= 120:
        raise ConfigurationError("motion.rearm_quiet_samples must be between 0 and 120")
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
    gate_url = urlparse(local_gate.base_url)
    if gate_url.scheme != "http" or gate_url.hostname not in {
        "127.0.0.1",
        "localhost",
        "::1",
    }:
        raise ConfigurationError("local_gate.base_url must be a loopback HTTP address")
    if not local_gate.model:
        raise ConfigurationError("local_gate.model must not be empty")
    if not 1 <= local_gate.timeout_seconds <= 600:
        raise ConfigurationError("local_gate.timeout_seconds must be between 1 and 600")
    if not 32 <= local_gate.max_output_tokens <= 1000:
        raise ConfigurationError(
            "local_gate.max_output_tokens must be between 32 and 1000"
        )
    if not 1 <= local_gate.minimum_bird_panels <= events.frames_per_event:
        raise ConfigurationError(
            "local_gate.minimum_bird_panels must fit within one event"
        )
    if (
        len(local_gate.focus_box) != 4
        or any(not 0 <= value <= 1 for value in local_gate.focus_box)
        or local_gate.focus_box[0] >= local_gate.focus_box[2]
        or local_gate.focus_box[1] >= local_gate.focus_box[3]
    ):
        raise ConfigurationError(
            "local_gate.focus_box must be normalized [left, top, right, bottom]"
        )
    if actuator.kind not in {"dry_run", "tuya_diffuser"}:
        raise ConfigurationError("actuator.kind must be 'dry_run' or 'tuya_diffuser'")
    if not 0 < actuator.burst_seconds <= 300:
        raise ConfigurationError(
            "actuator.burst_seconds must be greater than 0 and at most 300"
        )
    if actuator.spray_mode not in {"small", "middle", "large", "big"}:
        raise ConfigurationError(
            "actuator.spray_mode must be small, middle, large, or big"
        )
    light_dps = dict(actuator.light_dps)
    if actuator.light_enabled and not light_dps:
        raise ConfigurationError(
            "actuator.light.dps must contain the observed light settings when enabled"
        )
    if not set(light_dps).issubset({"108", "109", "110", "111"}):
        raise ConfigurationError(
            "actuator.light.dps may contain only Tuya light datapoints 108-111"
        )
    if any(
        isinstance(value, (dict, list)) or value is None for value in light_dps.values()
    ):
        raise ConfigurationError("actuator.light.dps values must be JSON scalars")
    if not 0 <= telegram.poll_timeout_seconds <= 30:
        raise ConfigurationError("telegram.poll_timeout_seconds must be between 0 and 30")
