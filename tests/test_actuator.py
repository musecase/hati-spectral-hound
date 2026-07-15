from __future__ import annotations

import unittest
from typing import Any

from hati.actuator import TuyaDeviceSettings, TuyaDiffuserActuator


class FakeTuyaClient:
    def __init__(self, *, fail_activation: bool = False, sticky_power: bool = False) -> None:
        self.state: dict[str, Any] = {"1": False, "11": False, "103": "off"}
        self.commands: list[dict[str, Any]] = []
        self.fail_activation = fail_activation
        self.sticky_power = sticky_power
        self.closed = False

    def status(self) -> dict[str, Any]:
        return {"dps": dict(self.state)}

    def set_multiple_values(
        self, data: dict[str, Any], nowait: bool = False
    ) -> dict[str, Any]:
        del nowait
        self.commands.append(dict(data))
        if self.fail_activation and data.get("1") is True:
            raise OSError("synthetic activation failure")
        values = dict(data)
        if self.sticky_power and values.get("1") is False:
            values.pop("1")
        self.state.update(values)
        if self.state.get("1") is False:
            self.state["103"] = "off"
        return {"dps": dict(self.state)}

    def close(self) -> None:
        self.closed = True


def settings() -> TuyaDeviceSettings:
    return TuyaDeviceSettings(
        device_id="private-device-id",
        local_key="1234567890abcdef",
        address="192.0.2.10",
        protocol_version=3.5,
    )


class TuyaDiffuserActuatorTests(unittest.TestCase):
    def test_weak_dark_burst_shuts_down_and_verifies(self) -> None:
        client = FakeTuyaClient()
        sleeps: list[float] = []
        actuator = TuyaDiffuserActuator(
            settings(),
            burst_seconds=5,
            client_factory=lambda _: client,
            sleep=sleeps.append,
        )

        result = actuator.activate("evt-test")

        self.assertTrue(result.succeeded)
        self.assertEqual(sleeps, [5])
        self.assertEqual(
            client.commands[0], {"1": True, "103": "small", "11": False}
        )
        self.assertEqual(client.commands[-1], {"1": False, "11": False})
        self.assertFalse(client.state["1"])
        self.assertFalse(client.state["11"])
        self.assertTrue(client.closed)

    def test_activation_error_still_forces_and_verifies_off(self) -> None:
        client = FakeTuyaClient(fail_activation=True)
        actuator = TuyaDiffuserActuator(
            settings(), client_factory=lambda _: client, sleep=lambda _: None
        )

        result = actuator.activate("evt-failure")

        self.assertFalse(result.succeeded)
        self.assertIn("shutdown was verified", result.detail)
        self.assertEqual(client.commands[-1], {"1": False, "11": False})
        self.assertTrue(client.closed)

    def test_unverified_shutdown_is_a_failure(self) -> None:
        client = FakeTuyaClient(sticky_power=True)
        client.state["1"] = False
        actuator = TuyaDiffuserActuator(
            settings(), client_factory=lambda _: client, sleep=lambda _: None
        )

        # Let activation set power true; the fake then refuses every OFF update.
        result = actuator.activate("evt-sticky")

        self.assertFalse(result.succeeded)
        self.assertIn("without verified shutdown", result.detail)
        self.assertEqual(
            sum(command.get("1") is False for command in client.commands), 3
        )
        self.assertTrue(client.closed)

    def test_burst_cannot_exceed_hard_cap(self) -> None:
        with self.assertRaises(ValueError):
            TuyaDiffuserActuator(settings(), burst_seconds=5.1)

    def test_secret_fields_are_hidden_from_repr(self) -> None:
        shown = repr(settings())
        self.assertNotIn("private-device-id", shown)
        self.assertNotIn("1234567890abcdef", shown)


if __name__ == "__main__":
    unittest.main()
