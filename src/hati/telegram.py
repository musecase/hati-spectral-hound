"""Telegram operator notifications, review feedback, and owner commands."""

from __future__ import annotations

import json
import mimetypes
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from hati.actuator import Actuator, ActuatorResult, DryRunActuator
from hati.config import TelegramConfig
from hati.event_store import EventStore
from hati.models import (
    DecisionOutcome,
    EventRecord,
    FeedbackKind,
    HumanFeedback,
)


CALLBACK_PREFIX = "hati:feedback:"
SAFE_EVENT_ID = re.compile(r"^[A-Za-z0-9_-]+$")


class TelegramError(RuntimeError):
    """Raised when Telegram rejects or cannot complete a request."""


class TelegramTransport(Protocol):
    def call(
        self,
        method: str,
        fields: dict[str, Any],
        file_path: Path | None = None,
    ) -> dict[str, Any]: ...


class UrlLibTelegramTransport:
    """Small Bot API transport that keeps the token out of logs and reprs."""

    def __init__(self, token: str) -> None:
        if not token:
            raise ValueError("Telegram bot token cannot be blank")
        self._base_url = f"https://api.telegram.org/bot{token}"

    def call(
        self,
        method: str,
        fields: dict[str, Any],
        file_path: Path | None = None,
    ) -> dict[str, Any]:
        if file_path is None:
            body = urlencode(
                {
                    key: json.dumps(value) if isinstance(value, (dict, list)) else value
                    for key, value in fields.items()
                }
            ).encode("utf-8")
            request = Request(
                f"{self._base_url}/{method}",
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        else:
            body, content_type = _multipart_body(fields, file_path)
            request = Request(
                f"{self._base_url}/{method}",
                data=body,
                headers={"Content-Type": content_type},
            )
        try:
            with urlopen(request, timeout=35) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise TelegramError(f"Telegram request failed: {type(exc).__name__}") from exc
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            raise TelegramError("Telegram rejected the request")
        return payload


def _multipart_body(fields: dict[str, Any], file_path: Path) -> tuple[bytes, str]:
    boundary = f"hati-{uuid.uuid4().hex}"
    parts: list[bytes] = []
    for key, value in fields.items():
        rendered = json.dumps(value) if isinstance(value, (dict, list)) else str(value)
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode(),
                rendered.encode("utf-8"),
                b"\r\n",
            ]
        )
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    parts.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                'Content-Disposition: form-data; name="photo"; '
                f'filename="{file_path.name}"\r\n'
            ).encode(),
            f"Content-Type: {mime}\r\n\r\n".encode(),
            file_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


def event_message(event: EventRecord) -> str:
    decision = event.decision
    label = (
        decision.consensus_label.value
        if decision and decision.consensus_label
        else "no predator consensus"
    )
    votes = decision.predator_votes if decision else 0
    outcome = decision.outcome.value.upper() if decision else "PENDING"
    reason = decision.reason_code if decision else "NOT_DECIDED"
    action = "Deterrent authorized" if decision and decision.outcome is DecisionOutcome.AUTHORIZE else "No deterrent"
    return (
        f"HATI event: {label}\n"
        f"{votes}/{len(event.classifications)} predator votes · {event.zone}\n"
        f"Decision: {outcome} ({reason})\n"
        f"{action}\n"
        f"Event: {event.event_id}"
    )


def feedback_keyboard(event_id: str) -> dict[str, Any]:
    def button(label: str, kind: FeedbackKind) -> dict[str, str]:
        return {
            "text": label,
            "callback_data": f"{CALLBACK_PREFIX}{event_id}:{kind.value}",
        }

    return {
        "inline_keyboard": [
            [
                button("Correct", FeedbackKind.CORRECT),
                button("False alarm", FeedbackKind.FALSE_ALARM),
            ],
            [button("Wrong animal", FeedbackKind.WRONG_ANIMAL)],
        ]
    }


def notification_preview(event: EventRecord) -> dict[str, Any]:
    return {
        "chat_id": "<owner-chat-id>",
        "text": event_message(event),
        "reply_markup": feedback_keyboard(event.event_id),
        "photo": str(event.frame_paths[-1]) if event.frame_paths else None,
    }


class TelegramClient:
    def __init__(
        self,
        config: TelegramConfig,
        transport: TelegramTransport | None = None,
    ) -> None:
        if not config.token or not config.owner_chat_id:
            raise ValueError("Telegram token and owner chat ID are required")
        self.config = config
        self.transport = transport or UrlLibTelegramTransport(config.token)

    def send_event(self, event: EventRecord) -> dict[str, Any]:
        markup = feedback_keyboard(event.event_id)
        image = next(
            (path for path in reversed(event.frame_paths) if path.exists()),
            None,
        )
        if image:
            return self.transport.call(
                "sendPhoto",
                {
                    "chat_id": self.config.owner_chat_id,
                    "caption": event_message(event),
                    "reply_markup": markup,
                },
                image,
            )
        return self.send_text(event_message(event), reply_markup=markup)

    def send_text(
        self, text: str, reply_markup: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "chat_id": self.config.owner_chat_id,
            "text": text,
        }
        if reply_markup:
            fields["reply_markup"] = reply_markup
        return self.transport.call("sendMessage", fields)

    def get_updates(self, offset: int | None = None) -> list[dict[str, Any]]:
        fields: dict[str, Any] = {
            "timeout": self.config.poll_timeout_seconds,
            "allowed_updates": ["message", "callback_query"],
        }
        if offset is not None:
            fields["offset"] = offset
        payload = self.transport.call("getUpdates", fields)
        result = payload.get("result", [])
        return result if isinstance(result, list) else []

    def answer_callback(self, callback_id: str, text: str) -> dict[str, Any]:
        return self.transport.call(
            "answerCallbackQuery",
            {"callback_query_id": callback_id, "text": text},
        )


@dataclass(frozen=True)
class TelegramAction:
    kind: str
    accepted: bool
    detail: str
    event_id: str | None = None
    actuator_result: ActuatorResult | None = None


class TelegramController:
    def __init__(
        self,
        config: TelegramConfig,
        store: EventStore,
        actuator: Actuator,
    ) -> None:
        self.config = config
        self.store = store
        self.actuator = actuator

    def handle(self, update: dict[str, Any]) -> TelegramAction:
        chat_id = _chat_id(update)
        if chat_id != self.config.owner_chat_id:
            return TelegramAction("ignored", False, "Update was not from the owner")

        callback = update.get("callback_query")
        if isinstance(callback, dict):
            return self._feedback(callback)

        message = update.get("message")
        text = str(message.get("text", "")).strip() if isinstance(message, dict) else ""
        command = text.split(maxsplit=1)[0].split("@", 1)[0].lower()
        if command == "/deploy":
            if not self.config.manual_deploy_enabled:
                return TelegramAction("manual_deploy", False, "Manual deployment is disabled")
            update_id = str(update.get("update_id", "unknown"))
            result = self.actuator.activate(f"manual-telegram-{update_id}")
            return TelegramAction(
                "manual_deploy",
                result.succeeded,
                result.detail,
                actuator_result=result,
            )
        if command == "/test":
            result = DryRunActuator().activate(
                f"telegram-test-{update.get('update_id', 'unknown')}"
            )
            return TelegramAction(
                "test_burst", True, result.detail, actuator_result=result
            )
        if command == "/status":
            state = "enabled" if self.config.manual_deploy_enabled else "disabled"
            return TelegramAction(
                "status", True, f"HATI operator link online; manual deployment {state}"
            )
        return TelegramAction("ignored", False, "No supported command or feedback")

    def _feedback(self, callback: dict[str, Any]) -> TelegramAction:
        data = str(callback.get("data", ""))
        if not data.startswith(CALLBACK_PREFIX):
            return TelegramAction("ignored", False, "Unknown callback")
        remainder = data[len(CALLBACK_PREFIX) :]
        try:
            event_id, kind_raw = remainder.rsplit(":", 1)
            kind = FeedbackKind(kind_raw)
        except (ValueError, TypeError):
            return TelegramAction("feedback", False, "Invalid feedback payload")
        if not SAFE_EVENT_ID.fullmatch(event_id):
            return TelegramAction("feedback", False, "Invalid event ID")
        path = self.store.root / event_id / "event.json"
        try:
            event = self.store.load(path)
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return TelegramAction("feedback", False, "Event trace was not found")
        actor_id = str(callback.get("from", {}).get("id", self.config.owner_chat_id))
        event.feedback.append(
            HumanFeedback(kind=kind, source="telegram", actor_id=actor_id)
        )
        self.store.save(event)
        return TelegramAction(
            "feedback", True, f"Recorded {kind.value}", event_id=event_id
        )


def _chat_id(update: dict[str, Any]) -> str:
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        message = callback.get("message", {})
        if isinstance(message, dict):
            chat = message.get("chat", {})
            if isinstance(chat, dict):
                return str(chat.get("id", ""))
    message = update.get("message")
    if isinstance(message, dict):
        chat = message.get("chat", {})
        if isinstance(chat, dict):
            return str(chat.get("id", ""))
    return ""
