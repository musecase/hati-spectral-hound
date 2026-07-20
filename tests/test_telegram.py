from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hati.actuator import ActuatorResult
from hati.config import TelegramConfig, load_config
from hati.cli import _telegram_poll_forever
from hati.event_store import EventStore
from hati.models import FeedbackKind
from hati.simulation import build_simulated_event
from hati.telegram import (
    TelegramClient,
    TelegramController,
    TelegramOffsetStore,
    TelegramError,
    feedback_keyboard,
    notification_preview,
    process_updates,
)


class FakeTransport:
    def __init__(self, timeline: list[tuple[str, int | str]] | None = None) -> None:
        self.calls: list[tuple[str, dict, Path | None]] = []
        self.timeline = timeline

    def call(self, method: str, fields: dict, file_path: Path | None = None) -> dict:
        self.calls.append((method, fields, file_path))
        if self.timeline is not None:
            self.timeline.append(("transport", method))
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
        self.assertEqual(3, len(preview["reply_markup"]["inline_keyboard"]))

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

    def test_false_alarm_feedback_notifies_automatic_learning_handler(self) -> None:
        queued: list[tuple[str, FeedbackKind]] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event = build_simulated_event("raccoon", "camera", "COOP_DOOR_ZONE")
            EventStore(root).save(event)
            controller = TelegramController(
                telegram_config(),
                EventStore(root),
                FakeActuator(),
                feedback_handler=lambda event_id, kind: queued.append((event_id, kind)),
            )
            data = feedback_keyboard(event.event_id)["inline_keyboard"][0][1][
                "callback_data"
            ]
            result = controller.handle(
                {
                    "update_id": 8,
                    "callback_query": {
                        "data": data,
                        "from": {"id": 42},
                        "message": {"chat": {"id": 42}},
                    },
                }
            )
        self.assertTrue(result.accepted)
        self.assertEqual(FeedbackKind.FALSE_ALARM, result.feedback_kind)
        self.assertEqual([(event.event_id, FeedbackKind.FALSE_ALARM)], queued)

    def test_repeated_owner_feedback_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event = build_simulated_event("human", "camera", "COOP_DOOR_ZONE")
            EventStore(root).save(event)
            controller = TelegramController(
                telegram_config(),
                EventStore(root),
                FakeActuator(),
            )
            callback = {
                "callback_query": {
                    "id": "same-button",
                    "from": {"id": 42},
                    "message": {"chat": {"id": 42}},
                    "data": feedback_keyboard(event.event_id)["inline_keyboard"][0][0][
                        "callback_data"
                    ],
                }
            }
            first = controller.handle(callback)
            second = controller.handle(callback)
            loaded = EventStore.load(root / event.event_id / "event.json")
        self.assertEqual("Recorded correct", first.detail)
        self.assertEqual("Already recorded correct", second.detail)
        self.assertEqual(1, len(loaded.feedback))

    def test_owner_can_record_unknown_expected_animal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event = build_simulated_event("raccoon", "camera", "COOP_DOOR_ZONE")
            EventStore(root).save(event)
            controller = TelegramController(
                telegram_config(),
                EventStore(root),
                FakeActuator(),
            )
            data = feedback_keyboard(event.event_id)["inline_keyboard"][2][1][
                "callback_data"
            ]
            result = controller.handle(
                {
                    "callback_query": {
                        "from": {"id": 42},
                        "message": {"chat": {"id": 42}},
                        "data": data,
                    }
                }
            )
            loaded = EventStore.load(root / event.event_id / "event.json")
        self.assertTrue(result.accepted)
        self.assertEqual(FeedbackKind.WRONG_ANIMAL, loaded.feedback[0].kind)
        self.assertEqual("expected_label=unknown", loaded.feedback[0].note)

    def test_owner_can_record_expected_animal_label(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            event = build_simulated_event("raccoon", "camera", "COOP_DOOR_ZONE")
            EventStore(root).save(event)
            controller = TelegramController(
                telegram_config(),
                EventStore(root),
                FakeActuator(),
            )
            data = feedback_keyboard(event.event_id)["inline_keyboard"][1][0][
                "callback_data"
            ]
            result = controller.handle(
                {
                    "callback_query": {
                        "from": {"id": 42},
                        "message": {"chat": {"id": 42}},
                        "data": data,
                    }
                }
            )
            loaded = EventStore.load(root / event.event_id / "event.json")
        self.assertTrue(result.accepted)
        self.assertEqual(FeedbackKind.WRONG_ANIMAL, loaded.feedback[0].kind)
        self.assertEqual("expected_label=raccoon", loaded.feedback[0].note)
        self.assertIn("expected animal raccoon", result.detail)

    def test_non_owner_cannot_deploy(self) -> None:
        actuator = FakeActuator()
        with tempfile.TemporaryDirectory() as temporary:
            controller = TelegramController(
                telegram_config(),
                EventStore(Path(temporary)),
                actuator,
                runtime_armed=True,
                test_mode=False,
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
                telegram_config(),
                EventStore(Path(temporary)),
                actuator,
                runtime_armed=True,
                test_mode=False,
            )
            result = controller.handle(
                {"update_id": 9, "message": {"chat": {"id": 42}, "text": "/deploy"}}
            )
        self.assertTrue(result.accepted)
        self.assertEqual(["manual-telegram-9"], actuator.events)

    def test_owner_cannot_deploy_while_runtime_is_disarmed(self) -> None:
        actuator = FakeActuator()
        with tempfile.TemporaryDirectory() as temporary:
            controller = TelegramController(
                telegram_config(), EventStore(Path(temporary)), actuator
            )
            result = controller.handle(
                {"update_id": 10, "message": {"chat": {"id": 42}, "text": "/deploy"}}
            )
        self.assertFalse(result.accepted)
        self.assertEqual("HATI is disarmed", result.detail)
        self.assertEqual([], actuator.events)

    def test_owner_cannot_deploy_while_in_test_mode(self) -> None:
        actuator = FakeActuator()
        with tempfile.TemporaryDirectory() as temporary:
            controller = TelegramController(
                telegram_config(),
                EventStore(Path(temporary)),
                actuator,
                runtime_armed=True,
                test_mode=True,
            )
            result = controller.handle(
                {"update_id": 11, "message": {"chat": {"id": 42}, "text": "/deploy"}}
            )
        self.assertFalse(result.accepted)
        self.assertEqual("HATI is in test mode", result.detail)
        self.assertEqual([], actuator.events)

    def test_poll_batch_advances_offset_and_replies_to_status(self) -> None:
        timeline: list[tuple[str, int | str]] = []
        transport = FakeTransport(timeline)
        client = TelegramClient(telegram_config(), transport)
        with tempfile.TemporaryDirectory() as temporary:
            controller = TelegramController(
                telegram_config(), EventStore(Path(temporary)), FakeActuator()
            )
            batch = process_updates(
                client,
                controller,
                [{"update_id": 20, "message": {"chat": {"id": 42}, "text": "/status"}}],
                18,
                commit_offset=lambda offset: timeline.append(("commit", offset)),
            )
        self.assertEqual(21, batch.next_offset)
        self.assertEqual("sendMessage", transport.calls[0][0])
        self.assertEqual(
            [("commit", 21), ("transport", "sendMessage")],
            timeline,
        )

    def test_offset_store_survives_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            state = TelegramOffsetStore(Path(temporary) / "runtime" / "offset.json")
            self.assertIsNone(state.load())
            state.save(123)
            reloaded = TelegramOffsetStore(state.path)
            self.assertEqual(123, reloaded.load())

    def test_poll_loop_rebuilds_transport_after_network_failure(self) -> None:
        class FailingClient:
            def get_updates(self, _offset):
                raise TelegramError("network unavailable")

        class RecoveredClient:
            def get_updates(self, _offset):
                return []

        config = load_config(Path("config/hati.example.json"))
        with tempfile.TemporaryDirectory() as temporary:
            state = Path(temporary) / "offset.json"
            with patch(
                "hati.cli._telegram_components",
                side_effect=[(FailingClient(), object()), (RecoveredClient(), object())],
            ) as components:
                result = _telegram_poll_forever(config, state, 2, 0)

        self.assertEqual(0, result)
        self.assertEqual(2, components.call_count)


if __name__ == "__main__":
    unittest.main()
