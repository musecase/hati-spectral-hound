"""Telegram operator notifications, review feedback, and owner commands."""

from __future__ import annotations

import json
import mimetypes
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol
from urllib.error import HTTPError
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
        except HTTPError as exc:
            description = ""
            try:
                error_payload = json.loads(exc.read().decode("utf-8"))
                if isinstance(error_payload, dict):
                    description = str(error_payload.get("description", ""))
            except (UnicodeDecodeError, json.JSONDecodeError):
                pass
            detail = f"HTTP {exc.code}"
            if description:
                detail += f": {description}"
            raise TelegramError(f"Telegram request failed: {detail}") from exc
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
    def button(label: str, value: str | FeedbackKind) -> dict[str, str]:
        callback_value = value.value if isinstance(value, FeedbackKind) else value
        return {
            "text": label,
            "callback_data": f"{CALLBACK_PREFIX}{event_id}:{callback_value}",
        }

    return {
        "inline_keyboard": [
            [
                button("Correct", FeedbackKind.CORRECT),
                button("False alarm", FeedbackKind.FALSE_ALARM),
            ],
            [
                button("Raccoon", "label_raccoon"),
                button("Opossum", "label_opossum"),
                button("Skunk", "label_skunk"),
            ],
            [
                button("Wrong animal", FeedbackKind.WRONG_ANIMAL),
                button("Animal unknown", "unknown"),
            ],
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
    feedback_kind: FeedbackKind | None = None


class TelegramController:
    def __init__(
        self,
        config: TelegramConfig,
        store: EventStore,
        actuator: Actuator,
        *,
        runtime_armed: bool = False,
        test_mode: bool = True,
        feedback_handler: Callable[[str, FeedbackKind], None] | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.actuator = actuator
        self.runtime_armed = runtime_armed
        self.test_mode = test_mode
        self.feedback_handler = feedback_handler

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
            if not self.runtime_armed:
                return TelegramAction("manual_deploy", False, "HATI is disarmed")
            if self.test_mode:
                return TelegramAction("manual_deploy", False, "HATI is in test mode")
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
            runtime = "armed" if self.runtime_armed else "disarmed"
            mode = "test mode" if self.test_mode else "live mode"
            return TelegramAction(
                "status",
                True,
                (
                    f"HATI operator link online; manual deployment {state}; "
                    f"runtime {runtime}; {mode}"
                ),
            )
        return TelegramAction("ignored", False, "No supported command or feedback")

    def _feedback(self, callback: dict[str, Any]) -> TelegramAction:
        data = str(callback.get("data", ""))
        if not data.startswith(CALLBACK_PREFIX):
            return TelegramAction("ignored", False, "Unknown callback")
        remainder = data[len(CALLBACK_PREFIX) :]
        feedback_note = None
        try:
            event_id, kind_raw = remainder.rsplit(":", 1)
            if kind_raw == "unknown":
                kind = FeedbackKind.WRONG_ANIMAL
                feedback_note = "expected_label=unknown"
            elif kind_raw.startswith("label_"):
                expected_label = kind_raw.removeprefix("label_")
                if expected_label not in {"raccoon", "opossum", "skunk"}:
                    raise ValueError("Unsupported expected animal")
                kind = FeedbackKind.WRONG_ANIMAL
                feedback_note = f"expected_label={expected_label}"
            else:
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
        existing_index = next(
            (
                index
                for index, item in enumerate(event.feedback)
                if item.kind is kind
                and item.source == "telegram"
                and item.actor_id == actor_id
            ),
            None,
        )
        if existing_index is not None and (
            feedback_note is None
            or event.feedback[existing_index].note == feedback_note
        ):
            if self.feedback_handler is not None:
                try:
                    self.feedback_handler(event_id, kind)
                except Exception:
                    pass
            return TelegramAction(
                "feedback",
                True,
                f"Already recorded {kind.value}",
                event_id=event_id,
                feedback_kind=kind,
            )
        feedback = HumanFeedback(
            kind=kind,
            source="telegram",
            actor_id=actor_id,
            note=feedback_note,
        )
        if existing_index is None:
            event.feedback.append(feedback)
        else:
            event.feedback[existing_index] = feedback
        self.store.save(event)
        if self.feedback_handler is not None:
            try:
                self.feedback_handler(event_id, kind)
            except Exception:
                pass
        detail = f"Recorded {kind.value}"
        if feedback_note == "expected_label=unknown":
            detail += " with unknown expected animal"
        elif feedback_note and feedback_note.startswith("expected_label="):
            detail += f" with expected animal {feedback_note.partition('=')[2]}"
        return TelegramAction(
            "feedback",
            True,
            detail,
            event_id=event_id,
            feedback_kind=kind,
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


@dataclass(frozen=True)
class TelegramBatch:
    processed: int
    next_offset: int | None
    results: tuple[dict[str, Any], ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "processed": self.processed,
            "next_offset": self.next_offset,
            "results": list(self.results),
        }


def process_updates(
    client: TelegramClient,
    controller: TelegramController,
    updates: list[dict[str, Any]],
    offset: int | None = None,
    commit_offset: Callable[[int], None] | None = None,
) -> TelegramBatch:
    """Handle one ordered batch with optional at-most-once offset commits."""
    results: list[dict[str, Any]] = []
    next_offset = offset
    for update in updates:
        update_id = int(update.get("update_id", 0))
        next_offset = max(next_offset or 0, update_id + 1)
        # Commit before any owner-command side effect. Losing a command after a
        # crash is safer than replaying a physical deployment.
        if commit_offset is not None:
            commit_offset(next_offset)
        action = controller.handle(update)
        callback = update.get("callback_query")
        callback_acknowledged: bool | None = None
        if isinstance(callback, dict) and callback.get("id"):
            try:
                client.answer_callback(str(callback["id"]), action.detail)
                callback_acknowledged = True
            except TelegramError:
                # Telegram expires callback query IDs quickly. The owner review
                # is already durably stored, so a stale UI acknowledgement must
                # not discard the feedback or block later updates.
                callback_acknowledged = False
        elif action.kind != "ignored":
            client.send_text(action.detail)
        result = {
            "update_id": update_id,
            "kind": action.kind,
            "accepted": action.accepted,
            "detail": action.detail,
            "event_id": action.event_id,
        }
        if action.feedback_kind is not None:
            result["feedback_kind"] = action.feedback_kind.value
        if callback_acknowledged is not None:
            result["callback_acknowledged"] = callback_acknowledged
        results.append(result)
    return TelegramBatch(len(results), next_offset, tuple(results))


class TelegramOffsetStore:
    """Atomic restart state so owner commands are never replayed."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> int | None:
        if not self.path.exists():
            return None
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            offset = int(raw["next_offset"])
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise TelegramError("Telegram offset state is invalid") from exc
        if offset < 0:
            raise TelegramError("Telegram offset state is invalid")
        return offset

    def save(self, offset: int) -> None:
        if offset < 0:
            raise ValueError("Telegram offset cannot be negative")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"next_offset": offset}, indent=2) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self.path)
