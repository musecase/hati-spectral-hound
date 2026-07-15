"""Read-only local protocol and DPS discovery for the HATI diffuser."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import tinytuya


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "config" / "tuya-device.json"
PROTOCOLS = (3.3, 3.4, 3.5, 3.2, 3.1)


def _valid_status(value: Any) -> bool:
    return isinstance(value, dict) and isinstance(value.get("dps"), dict) and bool(value["dps"])


def main() -> int:
    if not CONFIG_PATH.exists():
        raise SystemExit("Private Tuya device configuration is missing; run discovery first.")
    record = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    device_record = record.get("device", {})
    device_id = str(device_record.get("id", ""))
    local_key = str(device_record.get("key", ""))
    if not device_id or len(local_key) != 16:
        raise SystemExit("Private Tuya device ID or 16-character local key is missing.")

    address = (
        sys.argv[1]
        if len(sys.argv) > 1
        else str(record.get("local", {}).get("address", ""))
    )
    if not address:
        raise SystemExit(
            "Supply the diffuser's private-LAN address as the first argument or "
            "store it under local.address in the ignored Tuya device configuration."
        )
    attempts: list[dict[str, Any]] = []
    matched_version: float | None = None
    status: dict[str, Any] | None = None

    for version in PROTOCOLS:
        client = tinytuya.Device(
            dev_id=device_id,
            address=address,
            local_key=local_key,
            version=version,
            connection_timeout=4,
            persist=False,
        )
        client.set_socketRetryLimit(1)
        client.set_socketTimeout(4)
        try:
            response = client.status()
            ok = _valid_status(response)
            attempts.append({"version": version, "ok": ok})
            if ok:
                matched_version = version
                status = response
                break
        except Exception as exc:  # TinyTuya raises several socket/protocol exception types.
            attempts.append({"version": version, "ok": False, "error_type": type(exc).__name__})
        finally:
            client.close()

    if matched_version is None or status is None:
        tried = ", ".join(str(item["version"]) for item in attempts)
        raise SystemExit(
            "No valid local status response. Tried protocols " + tried + ". "
            "Keep Smart Life fully closed and confirm the diffuser is online at " + address + "."
        )

    dps = status["dps"]
    record["local"] = {
        "address": address,
        "protocol_version": matched_version,
        "last_read_only_status": status,
        "probe_attempts": attempts,
    }
    CONFIG_PATH.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    print(f"Local read-only status succeeded using Tuya protocol {matched_version}.")
    print(f"Reported {len(dps)} data points:")
    for dp_id in sorted(dps, key=lambda item: int(item) if str(item).isdigit() else str(item)):
        value = dps[dp_id]
        print(f"  DP {dp_id}: {type(value).__name__} = {value!r}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
