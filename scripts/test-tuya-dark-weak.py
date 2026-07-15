"""Validate the intended weak-mist, lights-off HATI command with water only."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import tinytuya


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "tuya-device.json"
MAX_ON_SECONDS = 5.0


def _dps(value: Any) -> dict[str, Any]:
    if isinstance(value, dict) and isinstance(value.get("dps"), dict):
        return value["dps"]
    return {}


def main() -> int:
    record = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    device = record["device"]
    local = record["local"]
    client = tinytuya.Device(
        dev_id=str(device["id"]),
        address=str(local["address"]),
        local_key=str(device["key"]),
        version=float(local["protocol_version"]),
        connection_timeout=4,
        persist=False,
    )
    client.set_socketRetryLimit(1)
    client.set_socketTimeout(4)

    off_verified = False
    active: dict[str, Any] = {}
    started_at: float | None = None
    try:
        before = _dps(client.status())
        if before.get("1") is not False or before.get("11") is not False:
            raise RuntimeError("Safety precondition failed: power and light were not both OFF.")

        print("Starting weak-mist, lights-off water test for at most five seconds.")
        client.set_multiple_values({"1": True, "103": "small", "11": False})
        started_at = time.monotonic()
        time.sleep(1.5)
        active = _dps(client.status())
        remaining = MAX_ON_SECONDS - (time.monotonic() - started_at)
        if remaining > 0:
            time.sleep(remaining)
    finally:
        for _ in range(3):
            try:
                client.set_multiple_values({"1": False, "11": False})
                after = _dps(client.status())
                if after.get("1") is False and after.get("11") is False:
                    off_verified = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        client.close()

    elapsed = 0.0 if started_at is None else time.monotonic() - started_at
    if not off_verified:
        raise SystemExit("OFF could not be verified. Manually unplug the water-filled diffuser now.")
    print(f"Power and light OFF verified after {elapsed:.1f} seconds.")
    print(
        "Active state: "
        f"power={active.get('1')!r}, spray={active.get('103')!r}, light={active.get('11')!r}"
    )
    if not (
        active.get("1") is True
        and active.get("103") == "small"
        and active.get("11") is False
    ):
        raise SystemExit("The active data points did not match the intended safe command.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
