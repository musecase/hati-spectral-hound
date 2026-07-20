"""Actuator boundary with dry-run and bounded Tuya diffuser implementations."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Protocol

import tinytuya


@dataclass(frozen=True)
class ActuatorResult:
    succeeded: bool
    detail: str


class Actuator(Protocol):
    @property
    def available(self) -> bool: ...

    def activate(self, event_id: str) -> ActuatorResult: ...


class DryRunActuator:
    """Records intent without sending any command to physical hardware."""

    def __init__(self) -> None:
        self._logger = logging.getLogger("hati.actuator.dry_run")

    @property
    def available(self) -> bool:
        return True

    def activate(self, event_id: str) -> ActuatorResult:
        self._logger.info(
            "Dry-run deterrence activation",
            extra={"event_id": event_id, "physical_action": False},
        )
        return ActuatorResult(
            succeeded=True,
            detail="Dry run only; no physical command was sent",
        )


class TuyaClient(Protocol):
    def status(self) -> dict[str, Any]: ...

    def set_multiple_values(
        self, data: dict[str, Any], nowait: bool = False
    ) -> dict[str, Any]: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class TuyaDeviceSettings:
    device_id: str = field(repr=False)
    local_key: str = field(repr=False)
    address: str
    protocol_version: float


def load_tuya_device_settings(path: str | Path) -> TuyaDeviceSettings:
    """Load private LAN credentials without exposing them through repr or logs."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    device = raw.get("device", {})
    local = raw.get("local", {})
    settings = TuyaDeviceSettings(
        device_id=str(device.get("id", "")),
        local_key=str(device.get("key", "")),
        address=str(local.get("address", "")),
        protocol_version=float(local.get("protocol_version", 0)),
    )
    if not settings.device_id or len(settings.local_key) != 16 or not settings.address:
        raise ValueError("Private Tuya device configuration is incomplete")
    if settings.protocol_version not in {3.1, 3.2, 3.3, 3.4, 3.5}:
        raise ValueError("Private Tuya protocol version is unsupported")
    return settings


def _tinytuya_client(settings: TuyaDeviceSettings) -> TuyaClient:
    client = tinytuya.Device(
        dev_id=settings.device_id,
        address=settings.address,
        local_key=settings.local_key,
        version=settings.protocol_version,
        connection_timeout=4,
        persist=False,
    )
    client.set_socketRetryLimit(1)
    client.set_socketTimeout(4)
    return client


def _dps(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and isinstance(response.get("dps"), dict):
        return response["dps"]
    return {}


def _rgb_matches(requested: Any, reported: Any, *, tolerance: int = 16) -> bool:
    """Compare the RGB prefix of Tuya color strings despite device normalization."""
    if not isinstance(requested, str) or not isinstance(reported, str):
        return False
    if len(requested) < 6 or len(reported) < 6:
        return False
    try:
        requested_rgb = tuple(
            int(requested[index : index + 2], 16) for index in (0, 2, 4)
        )
        reported_rgb = tuple(
            int(reported[index : index + 2], 16) for index in (0, 2, 4)
        )
    except ValueError:
        return False
    return all(
        abs(expected - actual) <= tolerance
        for expected, actual in zip(requested_rgb, reported_rgb)
    )


class TuyaDiffuserActuator:
    """Emit one time-bounded diffuser run and verify power and light shutdown."""

    MASTER_POWER_DP = "1"
    LIGHT_DP = "11"
    SPRAY_MODE_DP = "103"
    VALID_SPRAY_MODES = frozenset({"small", "middle", "large", "big"})
    VALID_LIGHT_SETTING_DPS = frozenset({"108", "109", "110", "111"})
    MAX_BURST_SECONDS = 300.0

    def __init__(
        self,
        settings: TuyaDeviceSettings,
        *,
        burst_seconds: float = 300.0,
        spray_mode: str = "big",
        light_enabled: bool = False,
        light_dps: dict[str, Any] | None = None,
        client_factory: Callable[[TuyaDeviceSettings], TuyaClient] = _tinytuya_client,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < burst_seconds <= self.MAX_BURST_SECONDS:
            raise ValueError(
                "Tuya diffuser run must be greater than 0 and at most 300 seconds"
            )
        if spray_mode not in self.VALID_SPRAY_MODES:
            raise ValueError(
                "Tuya diffuser spray mode must be small, middle, large, or big"
            )
        configured_light_dps = dict(light_dps or {})
        if light_enabled and not configured_light_dps:
            raise ValueError("Enabled Tuya light requires observed light datapoints")
        if not set(configured_light_dps).issubset(self.VALID_LIGHT_SETTING_DPS):
            raise ValueError("Tuya light settings may contain only datapoints 108-111")
        self._settings = settings
        self._burst_seconds = burst_seconds
        self._spray_mode = spray_mode
        self._light_enabled = light_enabled
        self._light_dps = configured_light_dps
        self._client_factory = client_factory
        self._sleep = sleep
        self._logger = logging.getLogger("hati.actuator.tuya_diffuser")

    @classmethod
    def from_private_config(
        cls,
        path: str | Path,
        *,
        burst_seconds: float = 300.0,
        spray_mode: str = "big",
        light_enabled: bool = False,
        light_dps: dict[str, Any] | None = None,
    ) -> "TuyaDiffuserActuator":
        return cls(
            load_tuya_device_settings(path),
            burst_seconds=burst_seconds,
            spray_mode=spray_mode,
            light_enabled=light_enabled,
            light_dps=light_dps,
        )

    @property
    def available(self) -> bool:
        return True

    def activate(self, event_id: str) -> ActuatorResult:
        client = self._client_factory(self._settings)
        activation_error: Exception | None = None
        off_verified = False
        try:
            before = _dps(client.status())
            if before.get(self.MASTER_POWER_DP) is not False:
                raise RuntimeError("Actuator power was not confirmed off before activation")
            activation_values = {
                self.MASTER_POWER_DP: True,
                self.SPRAY_MODE_DP: self._spray_mode,
                **self._light_dps,
                self.LIGHT_DP: self._light_enabled,
            }
            client.set_multiple_values(activation_values)
            active = _dps(client.status())
            expected_core = {
                self.MASTER_POWER_DP: True,
                self.SPRAY_MODE_DP: self._spray_mode,
                self.LIGHT_DP: self._light_enabled,
            }
            core_confirmed = all(
                active.get(dp) == value for dp, value in expected_core.items()
            )
            color_confirmed = (
                not self._light_enabled
                or "108" not in self._light_dps
                or _rgb_matches(self._light_dps["108"], active.get("108"))
            )
            if not core_confirmed or not color_confirmed:
                raise RuntimeError("Actuator did not confirm the requested active state")
            self._sleep(self._burst_seconds)
        except Exception as exc:
            activation_error = exc
        finally:
            for attempt in range(3):
                try:
                    client.set_multiple_values(
                        {self.MASTER_POWER_DP: False, self.LIGHT_DP: False}
                    )
                    after = _dps(client.status())
                    if (
                        after.get(self.MASTER_POWER_DP) is False
                        and after.get(self.LIGHT_DP) is False
                    ):
                        off_verified = True
                        break
                except Exception:
                    self._logger.warning(
                        "Actuator shutdown attempt failed",
                        extra={"event_id": event_id, "attempt": attempt + 1},
                    )
                if attempt < 2:
                    self._sleep(0.5)
            client.close()

        if not off_verified:
            return ActuatorResult(
                succeeded=False,
                detail="Physical activation ended without verified shutdown; inspect device",
            )
        if activation_error is not None:
            return ActuatorResult(
                succeeded=False,
                detail=f"Activation failed safely and shutdown was verified: {type(activation_error).__name__}",
            )
        self._logger.info(
            "Bounded deterrence activation completed",
            extra={
                "event_id": event_id,
                "duration_seconds": self._burst_seconds,
                "spray_mode": self._spray_mode,
                "light_enabled": self._light_enabled,
                "shutdown_verified": True,
            },
        )
        return ActuatorResult(
            succeeded=True,
            detail=(
                f"{self._spray_mode.capitalize()} run with "
                f"light {'on' if self._light_enabled else 'off'} completed for "
                f"{self._burst_seconds:g} seconds; shutdown verified"
            ),
        )
