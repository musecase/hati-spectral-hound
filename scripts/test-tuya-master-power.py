"""Perform one bounded water-only test of the diffuser's presumed master-power DP."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import tinytuya


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "tuya-device.json"
MASTER_POWER_DP = "1"
MAX_ON_SECONDS = 5.0


def _dps(response: Any) -> dict[str, Any]:
    if isinstance(response, dict) and isinstance(response.get("dps"), dict):
        return response["dps"]
    return {}


def _new_client(device: dict[str, Any], local: dict[str, Any]) -> tinytuya.Device:
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
    return client


def main() -> int:
    record = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    device = record.get("device", {})
    local = record.get("local", {})
    if not device.get("id") or len(str(device.get("key", ""))) != 16:
        raise SystemExit("Private Tuya device credentials are incomplete.")
    if not local.get("address") or not local.get("protocol_version"):
        raise SystemExit("Run the read-only local probe before this test.")

    client = _new_client(device, local)
    off_verified = False
    started_at: float | None = None
    before: dict[str, Any] = {}
    active: dict[str, Any] = {}
    try:
        before = _dps(client.status())
        if before.get(MASTER_POWER_DP) is not False:
            raise RuntimeError(
                "Safety precondition failed: DP 1 was not confirmed OFF before the test."
            )

        print("DP 1 confirmed OFF. Starting one bounded five-second water test.")
        client.set_value(MASTER_POWER_DP, True)
        started_at = time.monotonic()
        time.sleep(1.5)
        active = _dps(client.status())
        remaining = MAX_ON_SECONDS - (time.monotonic() - started_at)
        if remaining > 0:
            time.sleep(remaining)
    finally:
        # OFF is attempted even if ON, sleep, response parsing, or the operator interrupts.
        for _ in range(3):
            try:
                client.set_value(MASTER_POWER_DP, False)
                after = _dps(client.status())
                if after.get(MASTER_POWER_DP) is False:
                    off_verified = True
                    break
            except Exception:
                pass
            time.sleep(0.5)
        client.close()

    elapsed = 0.0 if started_at is None else time.monotonic() - started_at
    if not off_verified:
        raise SystemExit(
            "OFF could not be verified. Manually switch off or unplug the water-filled diffuser now."
        )
    local["last_bounded_test"] = {
        "before": before,
        "active": active,
        "off_verified": True,
    }
    record["local"] = local
    CONFIG_PATH.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    print(f"DP 1 OFF verified after {elapsed:.1f} seconds.")
    changed = sorted(
        (key, before.get(key), active.get(key))
        for key in set(before) | set(active)
        if before.get(key) != active.get(key)
    )
    print("Data points changed while active:")
    for dp_id, old_value, new_value in changed:
        print(f"  DP {dp_id}: {old_value!r} -> {new_value!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
