"""Staged OpenAI vision classification with structured, auditable output."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, Field

from hati.config import VisionConfig
from hati.models import AnimalLabel, Classification, InferenceTrace


class VisionError(RuntimeError):
    """Raised when a vision event cannot be classified safely."""


class FrameObservation(BaseModel):
    frame_number: int = Field(ge=1, le=5)
    animal: AnimalLabel
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(min_length=1, max_length=3)
    safe_to_deter: bool
    usable: bool


class VisionBurst(BaseModel):
    observations: list[FrameObservation] = Field(min_length=5, max_length=5)


class VisionScreen(BaseModel):
    observations: list[FrameObservation] = Field(min_length=2, max_length=2)


class VisionCompletion(BaseModel):
    observations: list[FrameObservation] = Field(min_length=3, max_length=3)


@dataclass(frozen=True)
class VisionResult:
    classifications: tuple[Classification, ...]
    trace: InferenceTrace


PREDATORS = frozenset(
    {
        AnimalLabel.RACCOON,
        AnimalLabel.FOX,
        AnimalLabel.COYOTE,
        AnimalLabel.OPOSSUM,
        AnimalLabel.SKUNK,
    }
)

SYSTEM_PROMPT = """You are HATI's visual observer for a fixed poultry-coop camera.
Analyze the supplied frames from one chronological five-frame event. Return exactly one
observation for each supplied frame number. The only allowed labels are empty, human,
dog, cat, chicken, goose, raccoon, fox, coyote, opossum, skunk, and unknown.

Rules:
- Classify what is visibly present; never guess an animal from motion alone.
- Use human if any person or recognizable human body part is visible.
- Use empty only when the protected area is clearly visible and contains no person or animal.
- Use unknown when the subject is absent, obscured, or not identifiable.
- Mark usable false only when the frame cannot support a visual observation.
- safe_to_deter may be true only for a clearly identified listed wild predator when no
  human is visible and no resident animal would be exposed.
- Give one to three short visual evidence phrases per frame.
- You provide observations only. You never authorize or request physical action.
"""

SCREENING_FRAMES = (2, 4)
COMPLETION_FRAMES = (1, 3, 5)
BENIGN_SCREEN_LABELS = frozenset(
    {
        AnimalLabel.EMPTY,
        AnimalLabel.HUMAN,
        AnimalLabel.DOG,
        AnimalLabel.CAT,
        AnimalLabel.CHICKEN,
        AnimalLabel.GOOSE,
    }
)
BENIGN_SCREEN_CONFIDENCE = 0.85


def _image_part(path: Path, detail: str) -> dict[str, str]:
    if not path.is_file():
        raise VisionError(f"Event frame is missing: {path}")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return {
        "type": "input_image",
        "image_url": f"data:{mime};base64,{payload}",
        "detail": detail,
    }


def _usage_value(usage: Any, name: str) -> int | None:
    value = getattr(usage, name, None) if usage is not None else None
    return int(value) if value is not None else None


def _sum_usage(*values: int | None) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _request_frames(
    frame_paths: list[Path],
    frame_numbers: tuple[int, ...],
    config: VisionConfig,
    client: Any,
    system_prompt: str,
    output_model: type[BaseModel],
) -> tuple[list[FrameObservation], Any]:
    supplied = ", ".join(str(number) for number in frame_numbers)
    content: list[dict[str, str]] = [
        {
            "type": "input_text",
            "text": (
                f"Classify supplied event frames {supplied}. Preserve these exact "
                "frame numbers in the structured result."
            ),
        }
    ]
    for frame_number in frame_numbers:
        content.append(
            {"type": "input_text", "text": f"Frame {frame_number} of 5"}
        )
        content.append(_image_part(frame_paths[frame_number - 1], config.image_detail))

    try:
        response = client.responses.parse(
            model=config.model,
            reasoning={"effort": config.reasoning_effort},
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content},
            ],
            text_format=output_model,
            max_output_tokens=config.max_output_tokens,
            store=False,
        )
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        code = getattr(exc, "code", None)
        context = ", ".join(
            item
            for item in (
                f"status {status}" if status else "",
                f"code {code}" if code else "",
            )
            if item
        )
        suffix = f" ({context})" if context else ""
        raise VisionError(f"OpenAI request failed: {type(exc).__name__}{suffix}") from exc

    parsed = getattr(response, "output_parsed", None)
    if not isinstance(parsed, output_model):
        raise VisionError("OpenAI response did not contain the required structured observations")
    observations = list(getattr(parsed, "observations", ()))
    by_frame = {item.frame_number: item for item in observations}
    if len(by_frame) != len(observations) or set(by_frame) != set(frame_numbers):
        raise VisionError("Structured observations did not match the supplied frame numbers")
    return [by_frame[number] for number in frame_numbers], getattr(response, "usage", None)


def _screen_is_conclusively_benign(observations: list[FrameObservation]) -> bool:
    return all(
        item.usable
        and item.animal in BENIGN_SCREEN_LABELS
        and item.confidence >= BENIGN_SCREEN_CONFIDENCE
        and not item.safe_to_deter
        for item in observations
    )


def _to_classifications(
    observations: list[FrameObservation], frame_paths: list[Path]
) -> tuple[Classification, ...]:
    human_present = any(item.animal is AnimalLabel.HUMAN for item in observations)
    classifications: list[Classification] = []
    for item in sorted(observations, key=lambda observation: observation.frame_number):
        path = frame_paths[item.frame_number - 1]
        predator = item.animal in PREDATORS
        classifications.append(
            Classification(
                frame_id=path.stem,
                animal=item.animal,
                predator=predator,
                confidence=item.confidence,
                evidence=tuple(item.evidence),
                safe_to_deter=(item.safe_to_deter and predator and not human_present),
                usable=item.usable,
            )
        )
    return tuple(classifications)


def classify_frames(
    frame_paths: list[Path],
    config: VisionConfig,
    *,
    api_key: str | None = None,
    client: Any | None = None,
    policy_id: str = "baseline",
    policy_addendum: str = "",
    cascade: bool = True,
) -> VisionResult:
    """Screen frames 2 and 4, completing all five only when dismissal is unsafe."""
    if len(frame_paths) != 5:
        raise VisionError(f"Vision requires exactly five frames; received {len(frame_paths)}")
    if client is None:
        if not api_key:
            raise VisionError("OPENAI_API_KEY is required for vision classification")
        client = OpenAI(api_key=api_key)

    system_prompt = SYSTEM_PROMPT
    if policy_addendum.strip():
        system_prompt = (
            f"{SYSTEM_PROMPT}\n\nPromoted reviewed policy ({policy_id}):\n"
            f"{policy_addendum.strip()}"
        )

    if not cascade:
        observations, usage = _request_frames(
            frame_paths,
            (1, 2, 3, 4, 5),
            config,
            client,
            system_prompt,
            VisionBurst,
        )
        classifications = _to_classifications(observations, frame_paths)
        trace = InferenceTrace(
            provider="openai",
            model=config.model,
            api="responses",
            image_detail=config.image_detail,
            reasoning_effort=config.reasoning_effort,
            request_count=1,
            policy_id=policy_id,
            input_tokens=_usage_value(usage, "input_tokens"),
            output_tokens=_usage_value(usage, "output_tokens"),
            total_tokens=_usage_value(usage, "total_tokens"),
            image_count=5,
            completion_frames=(1, 2, 3, 4, 5),
        )
        return VisionResult(classifications=classifications, trace=trace)

    screening, screen_usage = _request_frames(
        frame_paths,
        SCREENING_FRAMES,
        config,
        client,
        system_prompt,
        VisionScreen,
    )
    dismissed = _screen_is_conclusively_benign(screening)
    completion: list[FrameObservation] = []
    completion_usage = None
    if not dismissed:
        completion, completion_usage = _request_frames(
            frame_paths,
            COMPLETION_FRAMES,
            config,
            client,
            system_prompt,
            VisionCompletion,
        )
    classifications = _to_classifications(screening + completion, frame_paths)
    trace = InferenceTrace(
        provider="openai",
        model=config.model,
        api="responses",
        image_detail=config.image_detail,
        reasoning_effort=config.reasoning_effort,
        request_count=1 if dismissed else 2,
        policy_id=policy_id,
        input_tokens=_sum_usage(
            _usage_value(screen_usage, "input_tokens"),
            _usage_value(completion_usage, "input_tokens"),
        ),
        output_tokens=_sum_usage(
            _usage_value(screen_usage, "output_tokens"),
            _usage_value(completion_usage, "output_tokens"),
        ),
        total_tokens=_sum_usage(
            _usage_value(screen_usage, "total_tokens"),
            _usage_value(completion_usage, "total_tokens"),
        ),
        image_count=2 if dismissed else 5,
        screening_frames=SCREENING_FRAMES,
        completion_frames=() if dismissed else COMPLETION_FRAMES,
        screen_dismissed=dismissed,
    )
    return VisionResult(classifications=classifications, trace=trace)
