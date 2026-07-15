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


class TuyaDiffuserActuator:
    """Emit one weak, dark, time-bounded burst and verify shutdown."""

    MASTER_POWER_DP = "1"
    LIGHT_DP = "11"
    SPRAY_MODE_DP = "103"
    WEAK_MODE = "small"
    MAX_BURST_SECONDS = 5.0

    def __init__(
        self,
        settings: TuyaDeviceSettings,
        *,
        burst_seconds: float = 5.0,
        client_factory: Callable[[TuyaDeviceSettings], TuyaClient] = _tinytuya_client,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not 0 < burst_seconds <= self.MAX_BURST_SECONDS:
            raise ValueError("Tuya diffuser burst must be greater than 0 and at most 5 seconds")
        self._settings = settings
        self._burst_seconds = burst_seconds
        self._client_factory = client_factory
        self._sleep = sleep
        self._logger = logging.getLogger("hati.actuator.tuya_diffuser")

    @classmethod
    def from_private_config(
        cls, path: str | Path, *, burst_seconds: float = 5.0
    ) -> "TuyaDiffuserActuator":
        return cls(load_tuya_device_settings(path), burst_seconds=burst_seconds)

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
            client.set_multiple_values(
                {
                    self.MASTER_POWER_DP: True,
                    self.SPRAY_MODE_DP: self.WEAK_MODE,
                    self.LIGHT_DP: False,
                }
            )
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
            "Bounded weak, dark deterrence activation completed",
            extra={
                "event_id": event_id,
                "duration_seconds": self._burst_seconds,
                "shutdown_verified": True,
            },
        )
        return ActuatorResult(
            succeeded=True,
            detail=(
                f"Weak dark burst completed for {self._burst_seconds:g} seconds; "
                "shutdown verified"
            ),
        )
