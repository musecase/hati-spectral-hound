from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from hati.actuator import ActuatorResult
from hati.config import TelegramConfig
from hati.event_store import EventStore
from hati.models import FeedbackKind
from hati.simulation import build_simulated_event
from hati.telegram import (
    TelegramClient,
    TelegramController,
    feedback_keyboard,
    notification_preview,
)


class FakeTransport:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, Path | None]] = []

    def call(self, method: str, fields: dict, file_path: Path | None = None) -> dict:
        self.calls.append((method, fields, file_path))
        return {"ok": True, "result": []}


class FakeActuator:
    def __init__(self) -> None:
        self.events: list[str] = []

    @property
    def available(self) -> bool:
        return True

    def activate(self, event_id: str) -> ActuatorResult:
        self.events.append(event_id)
        return ActuatorResult(True, "bounded owner deployment completed")


def telegram_config() -> TelegramConfig:
    return TelegramConfig(
        enabled=True,
        owner_chat_id="42",
        manual_deploy_enabled=True,
        poll_timeout_seconds=0,
        token="test-token",
    )


class TelegramTests(unittest.TestCase):
    def test_preview_contains_feedback_without_sending(self) -> None:
        event = build_simulated_event("raccoon", "camera", "COOP_DOOR_ZONE")
        preview = notification_preview(event)
        self.assertIn("HATI event", preview["text"])
        self.assertEqual(2, len(preview["reply_markup"]["inline_keyboard"]))

    def test_client_sends_message_when_no_image_exists(self) -> None:
        transport = FakeTransport()
        client = TelegramClient(telegram_config(), transport)
        event = build_simulated_event("human", "camera", "COOP_DOOR_ZONE")
        client.send_event(event)
        self.assertEqual("sendMessage", transport.calls[0][0])

    def test_owner_feedback_is_stored_with_event(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = EventStore(Path(temporary))
            event = build_simulated_event("human", "camera", "COOP_DOOR_ZONE")
            store.save(event)
            controller = TelegramController(telegram_config(), store, FakeActuator())
            data = feedback_keyboard(event.event_id)["inline_keyboard"][0][0][
                "callback_data"
            ]
            result = controller.handle(
                {
                    "update_id": 7,
                    "callback_query": {
                        "data": data,
                        "from": {"id": 42},
                        "message": {"chat": {"id": 42}},
                    },
                }
            )
            loaded = store.load(Path(temporary) / event.event_id / "event.json")
        self.assertTrue(result.accepted)
        self.assertEqual(FeedbackKind.CORRECT, loaded.feedback[0].kind)

    def test_non_owner_cannot_deploy(self) -> None:
        actuator = FakeActuator()
        with tempfile.TemporaryDirectory() as temporary:
            controller = TelegramController(
                telegram_config(), EventStore(Path(temporary)), actuator
            )
            result = controller.handle(
                {"update_id": 8, "message": {"chat": {"id": 99}, "text": "/deploy"}}
            )
        self.assertFalse(result.accepted)
        self.assertEqual([], actuator.events)

    def test_owner_can_request_bounded_manual_deployment(self) -> None:
        actuator = FakeActuator()
        with tempfile.TemporaryDirectory() as temporary:
            controller = TelegramController(
                telegram_config(), EventStore(Path(temporary)), actuator
            )
            result = controller.handle(
                {"update_id": 9, "message": {"chat": {"id": 42}, "text": "/deploy"}}
            )
        self.assertTrue(result.accepted)
        self.assertEqual(["manual-telegram-9"], actuator.events)


if __name__ == "__main__":
    unittest.main()
