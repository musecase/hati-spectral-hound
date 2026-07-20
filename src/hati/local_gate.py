"""Local-only Gemma shadow gate for measuring avoidable Luna calls."""

from __future__ import annotations

import base64
import json
import time
import urllib.request
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable

import cv2
import numpy as np
from pydantic import BaseModel, Field

from hati.config import LocalGateConfig
from hati.models import LocalGateTrace


class LocalGateError(RuntimeError):
    """Raised when the local shadow model cannot produce an auditable result."""


class LocalGateLabel(StrEnum):
    HUMAN = "human"
    CHICKEN = "chicken"
    GOOSE = "goose"
    MAMMAL = "mammal"
    EMPTY = "empty"
    UNKNOWN = "unknown"


class LocalGateCertainty(StrEnum):
    CLEAR = "clear"
    LIKELY = "likely"
    UNCERTAIN = "uncertain"


class LocalPanelObservation(BaseModel):
    frame_number: int = Field(ge=1, le=5)
    label: LocalGateLabel
    certainty: LocalGateCertainty


class LocalGateBurst(BaseModel):
    panels: list[LocalPanelObservation] = Field(min_length=5, max_length=5)
    human_present: bool
    mammal_present: bool
    uncertain: bool
    reason: str = Field(min_length=1, max_length=160)


Requester = Callable[[str, dict[str, Any], int], dict[str, Any]]

SYSTEM_PROMPT = """You are HATI's conservative, local-only visual triage gate.
Inspect five numbered, full-resolution chronological coop-camera frames.

For each numbered panel, choose exactly one label:
- human: any person or recognizable human body part is visible
- chicken: chicken is the most safety-relevant visible subject
- goose: goose is the most safety-relevant visible subject
- mammal: dog, cat, raccoon, fox, coyote, opossum, skunk, or any other mammal
- empty: no animal or person is visible
- unknown: the subject is small, obscured, mixed, ambiguous, or unidentifiable

For each panel, also choose exactly one bounded certainty:
- clear: visible features distinguish the label from reasonable alternatives
- likely: the label is the best fit, but the subject is small, blurred, partial, or lacks decisive features
- uncertain: multiple labels remain plausible or the subject cannot be identified

Prioritize human over mammal, mammal over bird, and uncertainty over guessing.
Set uncertain true when any panel is likely or uncertain.
Do not report numerical confidence.
Keep the reason to one short sentence under 120 characters.
You only recommend local triage labels. You never authorize physical action.
"""


def build_contact_sheet(
    frame_paths: list[Path],
    output_path: Path,
    *,
    panel_width: int = 640,
    panel_height: int = 360,
    focus_box: tuple[float, float, float, float] | None = None,
) -> Path:
    """Build one numbered 2x3 sheet while preserving each full camera frame."""
    if len(frame_paths) != 5:
        raise LocalGateError(
            f"Local gate requires exactly five frames; received {len(frame_paths)}"
        )
    sheet = np.zeros((panel_height * 3, panel_width * 2, 3), dtype=np.uint8)
    for index, path in enumerate(frame_paths, start=1):
        image = cv2.imread(str(path))
        if image is None:
            raise LocalGateError(f"Local gate frame is unreadable: {path}")
        if focus_box is not None:
            height, width = image.shape[:2]
            left, top, right, bottom = focus_box
            x1, y1 = round(left * width), round(top * height)
            x2, y2 = round(right * width), round(bottom * height)
            image = image[y1:y2, x1:x2]
            if image.size == 0:
                raise LocalGateError("Local gate focus box produced an empty crop")
        panel = cv2.resize(
            image,
            (panel_width, panel_height),
            interpolation=cv2.INTER_AREA,
        )
        cv2.rectangle(panel, (0, 0), (145, 42), (0, 0, 0), thickness=-1)
        cv2.putText(
            panel,
            f"FRAME {index}",
            (10, 29),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.72,
            (255, 255, 255),
            2,
            cv2.LINE_AA,
        )
        row, column = divmod(index - 1, 2)
        y, x = row * panel_height, column * panel_width
        sheet[y : y + panel_height, x : x + panel_width] = panel

    output_path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(
        str(output_path),
        sheet,
        [int(cv2.IMWRITE_JPEG_QUALITY), 90],
    ):
        raise LocalGateError(f"Could not write local contact sheet: {output_path}")
    return output_path


def _request_json(url: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _schema() -> dict[str, Any]:
    panel = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "frame_number": {"type": "integer", "minimum": 1, "maximum": 5},
            "label": {
                "type": "string",
                "enum": [item.value for item in LocalGateLabel],
            },
            "certainty": {
                "type": "string",
                "enum": [item.value for item in LocalGateCertainty],
            },
        },
        "required": ["frame_number", "label", "certainty"],
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "panels": {
                "type": "array",
                "minItems": 5,
                "maxItems": 5,
                "items": panel,
            },
            "human_present": {"type": "boolean"},
            "mammal_present": {"type": "boolean"},
            "uncertain": {"type": "boolean"},
            "reason": {
                "type": "string",
                "minLength": 1,
                "maxLength": 160,
            },
        },
        "required": [
            "panels",
            "human_present",
            "mammal_present",
            "uncertain",
            "reason",
        ],
    }


def _usage_value(usage: Any, name: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get(name)
    return int(value) if value is not None else None


def evaluate_local_gate(
    frame_paths: list[Path],
    config: LocalGateConfig,
    *,
    requester: Requester = _request_json,
) -> LocalGateTrace:
    """Ask local Gemma for a shadow recommendation; never suppress or actuate."""
    if len(frame_paths) != 5:
        raise LocalGateError(
            f"Local gate requires exactly five frames; received {len(frame_paths)}"
        )
    contact_sheet = build_contact_sheet(
        frame_paths,
        frame_paths[0].parent / "local-gate-contact-sheet.jpg",
    )
    focus_sheet = build_contact_sheet(
        frame_paths,
        frame_paths[0].parent / "local-gate-focus-sheet.jpg",
        focus_box=config.focus_box,
    )
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "Classify all five numbered full-resolution frames using only visible "
                "evidence. Return only the required structured result."
            ),
        }
    ]
    for index, path in enumerate(frame_paths, start=1):
        image = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append({"type": "text", "text": f"FRAME {index} OF 5"})
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{image}"},
            }
        )
    payload = {
        "model": config.model,
        "reasoning_effort": "none",
        "temperature": 0,
        "max_tokens": config.max_output_tokens,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "hati_local_gate",
                "strict": True,
                "schema": _schema(),
            },
        },
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": content,
            },
        ],
    }

    started = time.perf_counter()
    response = requester(
        f"{config.base_url}/chat/completions",
        payload,
        config.timeout_seconds,
    )
    latency_ms = round((time.perf_counter() - started) * 1000)
    try:
        content = response["choices"][0]["message"]["content"]
        burst = LocalGateBurst.model_validate_json(content)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise LocalGateError("Local model response was not valid structured output") from exc

    by_frame = {panel.frame_number: panel for panel in burst.panels}
    if set(by_frame) != {1, 2, 3, 4, 5}:
        raise LocalGateError("Local model did not classify each panel exactly once")
    labels = tuple(by_frame[index].label for index in range(1, 6))
    certainties = tuple(by_frame[index].certainty for index in range(1, 6))
    human_present = burst.human_present or LocalGateLabel.HUMAN in labels
    mammal_present = burst.mammal_present or LocalGateLabel.MAMMAL in labels
    human_veto_eligible = any(
        label is LocalGateLabel.HUMAN
        and certainty
        in {
            LocalGateCertainty.CLEAR,
            LocalGateCertainty.LIKELY,
        }
        for label, certainty in zip(labels, certainties, strict=True)
    )
    bird_count = sum(
        label in {LocalGateLabel.CHICKEN, LocalGateLabel.GOOSE} for label in labels
    )
    unknown_present = LocalGateLabel.UNKNOWN in labels
    bounded_uncertainty = any(
        certainty is not LocalGateCertainty.CLEAR for certainty in certainties
    )
    uncertain = burst.uncertain or unknown_present or bounded_uncertainty
    clear_bird_eligible = (
        not human_present
        and not mammal_present
        and not uncertain
        and bird_count >= config.minimum_bird_panels
        and all(
            label
            in {
                LocalGateLabel.CHICKEN,
                LocalGateLabel.GOOSE,
                LocalGateLabel.EMPTY,
            }
            for label in labels
        )
    )
    eligible_to_skip = human_veto_eligible or clear_bird_eligible
    usage = response.get("usage", {})
    return LocalGateTrace(
        provider="lm_studio",
        model=config.model,
        api="openai_compatible_chat_completions",
        mode="shadow" if config.shadow_mode else "enforcing",
        recommendation=(
            "would_skip_luna" if eligible_to_skip else "would_escalate_to_luna"
        ),
        eligible_to_skip=eligible_to_skip,
        panel_labels=tuple(label.value for label in labels),
        panel_certainties=tuple(certainty.value for certainty in certainties),
        human_present=human_present,
        mammal_present=mammal_present,
        bird_present=bird_count > 0,
        uncertain=uncertain,
        reason=burst.reason,
        contact_sheet_path=contact_sheet,
        focus_sheet_path=focus_sheet,
        request_count=1,
        latency_ms=latency_ms,
        prompt_tokens=_usage_value(usage, "prompt_tokens"),
        completion_tokens=_usage_value(usage, "completion_tokens"),
        total_tokens=_usage_value(usage, "total_tokens"),
    )


def run_shadow_gate(
    frame_paths: list[Path],
    config: LocalGateConfig,
    *,
    requester: Requester = _request_json,
) -> LocalGateTrace:
    """Fail open to Luna while preserving a local-gate error in the audit trace."""
    started = time.perf_counter()
    try:
        return evaluate_local_gate(frame_paths, config, requester=requester)
    except Exception as exc:
        return LocalGateTrace(
            provider="lm_studio",
            model=config.model,
            api="openai_compatible_chat_completions",
            mode="shadow" if config.shadow_mode else "enforcing",
            recommendation="would_escalate_to_luna",
            eligible_to_skip=False,
            uncertain=True,
            reason="Local shadow gate failed; Luna remains authoritative",
            request_count=0,
            latency_ms=round((time.perf_counter() - started) * 1000),
            error_type=type(exc).__name__,
        )
