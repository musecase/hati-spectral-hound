"""Read-only Tuya discovery for HATI.

Cloud credentials arrive through the process environment and are never written by
this script. Device identifiers and the LAN local key are written only to the
Git-ignored local configuration file.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import tinytuya


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = PROJECT_ROOT / "config" / "tuya-device.json"


def _cloud_error(value: Any) -> str | None:
    if not isinstance(value, dict):
        return "Tuya returned an unexpected response."
    if value.get("success") is False or "Error" in value or "Err" in value:
        return str(value.get("Payload") or value.get("msg") or "Tuya cloud request failed.")
    return None


def _status_codes(status: Any) -> list[str]:
    if not isinstance(status, dict):
        return []
    result = status.get("result")
    if not isinstance(result, list):
        return []
    return [str(item["code"]) for item in result if isinstance(item, dict) and "code" in item]


def main() -> int:
    access_id = os.environ.get("HATI_TUYA_ACCESS_ID", "").strip()
    access_secret = os.environ.get("HATI_TUYA_ACCESS_SECRET", "")
    target_name = os.environ.get("HATI_TUYA_DEVICE_NAME", "").strip()
    if not access_id or not access_secret:
        raise SystemExit("Tuya cloud credentials were not supplied by the secure wrapper.")
    if not target_name:
        raise SystemExit("The Smart Life device name was not supplied by the secure wrapper.")

    cloud = tinytuya.Cloud(
        apiRegion="us",
        apiKey=access_id,
        apiSecret=access_secret,
        apiDeviceID=None,
    )
    if cloud.error:
        raise SystemExit("Tuya authentication failed: " + (_cloud_error(cloud.error) or "unknown error"))

    devices = cloud.getdevices(verbose=False, include_map=True)
    if isinstance(devices, dict):
        error = _cloud_error(devices)
        raise SystemExit("Tuya device discovery failed: " + (error or "unexpected response"))
    if not isinstance(devices, list):
        raise SystemExit("Tuya device discovery returned an unexpected response.")

    matches = [
        device
        for device in devices
        if str(device.get("name", "")).casefold() == target_name.casefold()
    ]
    if len(matches) != 1:
        names = sorted(str(d.get("name") or "unnamed") for d in devices)
        visible = ", ".join(names) if names else "none"
        raise SystemExit(
            f"Expected exactly one device named {target_name!r}; found {len(matches)}. "
            f"Visible device names: {visible}"
        )

    device = matches[0]
    device_id = str(device.get("id", ""))
    if not device_id:
        raise SystemExit("The matched Tuya device did not include a device ID.")

    status = cloud.getstatus(device_id)
    functions = cloud.getfunctions(device_id)
    properties = cloud.getproperties(device_id)
    specifications = cloud.getdps(device_id)

    record = {
        "device": device,
        "cloud": {
            "region": "us",
            "status": status,
            "functions": functions,
            "properties": properties,
            "specifications": specifications,
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")

    local_key_present = bool(device.get("key"))
    version = device.get("version") or "not reported"
    codes = _status_codes(status)
    print(f"Matched device: {target_name}")
    print(f"Local key available: {str(local_key_present).lower()}")
    print(f"Protocol version reported by cloud: {version}")
    print("Cloud status codes: " + (", ".join(codes) if codes else "none reported"))
    print("Saved private device metadata to config\\tuya-device.json (ignored by Git).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
