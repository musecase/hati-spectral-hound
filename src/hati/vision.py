"""Five-frame OpenAI vision classification with structured, auditable output."""

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
Analyze one chronological burst of exactly five frames. Return exactly one observation
for each numbered frame. The only allowed labels are human, dog, cat, chicken, goose,
raccoon, fox, coyote, opossum, skunk, and unknown.

Rules:
- Classify what is visibly present; never guess an animal from motion alone.
- Use human if any person or recognizable human body part is visible.
- Use unknown when the subject is absent, obscured, or not identifiable.
- Mark usable false only when the frame cannot support a visual observation.
- safe_to_deter may be true only for a clearly identified listed wild predator when no
  human is visible and no resident animal would be exposed.
- Give one to three short visual evidence phrases per frame.
- You provide observations only. You never authorize or request physical action.
"""


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


def classify_frames(
    frame_paths: list[Path],
    config: VisionConfig,
    *,
    api_key: str | None = None,
    client: Any | None = None,
) -> VisionResult:
    """Classify exactly five chronological frames in one Responses API request."""
    if len(frame_paths) != 5:
        raise VisionError(f"Vision requires exactly five frames; received {len(frame_paths)}")
    if client is None:
        if not api_key:
            raise VisionError("OPENAI_API_KEY is required for vision classification")
        client = OpenAI(api_key=api_key)

    content: list[dict[str, str]] = [
        {
            "type": "input_text",
            "text": (
                "Classify these five chronological frames. Preserve their supplied "
                "frame numbers in the structured result."
            ),
        }
    ]
    for index, path in enumerate(frame_paths, start=1):
        content.append({"type": "input_text", "text": f"Frame {index} of 5"})
        content.append(_image_part(path, config.image_detail))

    try:
        response = client.responses.parse(
            model=config.model,
            reasoning={"effort": config.reasoning_effort},
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": content},
            ],
            text_format=VisionBurst,
            max_output_tokens=config.max_output_tokens,
            store=False,
        )
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        code = getattr(exc, "code", None)
        context = ", ".join(
            item for item in (f"status {status}" if status else "", f"code {code}" if code else "") if item
        )
        suffix = f" ({context})" if context else ""
        raise VisionError(f"OpenAI request failed: {type(exc).__name__}{suffix}") from exc

    parsed = getattr(response, "output_parsed", None)
    if not isinstance(parsed, VisionBurst):
        raise VisionError("OpenAI response did not contain the required structured observations")
    by_frame = {item.frame_number: item for item in parsed.observations}
    if set(by_frame) != {1, 2, 3, 4, 5}:
        raise VisionError("Structured observations did not contain each frame exactly once")

    human_present = any(item.animal is AnimalLabel.HUMAN for item in parsed.observations)
    classifications: list[Classification] = []
    for index, path in enumerate(frame_paths, start=1):
        item = by_frame[index]
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

    usage = getattr(response, "usage", None)
    trace = InferenceTrace(
        provider="openai",
        model=config.model,
        api="responses",
        image_detail=config.image_detail,
        reasoning_effort=config.reasoning_effort,
        request_count=1,
        input_tokens=_usage_value(usage, "input_tokens"),
        output_tokens=_usage_value(usage, "output_tokens"),
        total_tokens=_usage_value(usage, "total_tokens"),
    )
    return VisionResult(classifications=tuple(classifications), trace=trace)
