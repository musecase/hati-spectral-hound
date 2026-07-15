"""Deterministic local motion measurement inside a configured image polygon."""

from __future__ import annotations

from dataclasses import dataclass

from hati.config import MotionConfig


@dataclass(frozen=True)
class MotionResult:
    triggered: bool
    changed_pixel_ratio: float
    changed_pixels: int
    zone_pixels: int


def measure_motion(previous, current, config: MotionConfig) -> MotionResult:
    """Compare two BGR frames and measure changed pixels within the protected zone."""
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("OpenCV is required for motion detection") from exc

    if previous is None or current is None:
        raise ValueError("Motion detection requires two usable frames")
    if previous.shape[:2] != current.shape[:2]:
        raise ValueError("Motion detection frames must have identical dimensions")

    height, width = current.shape[:2]
    polygon = np.array(
        [
            [
                min(width - 1, round(x * (width - 1))),
                min(height - 1, round(y * (height - 1))),
            ]
            for x, y in config.zone_polygon
        ],
        dtype=np.int32,
    )
    zone_mask = np.zeros((height, width), dtype=np.uint8)
    cv2.fillPoly(zone_mask, [polygon], 255)

    prior_gray = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    if config.blur_size > 1:
        kernel = (config.blur_size, config.blur_size)
        prior_gray = cv2.GaussianBlur(prior_gray, kernel, 0)
        current_gray = cv2.GaussianBlur(current_gray, kernel, 0)

    difference = cv2.absdiff(prior_gray, current_gray)
    _, changed_mask = cv2.threshold(
        difference, config.pixel_threshold, 255, cv2.THRESH_BINARY
    )
    changed_in_zone = cv2.bitwise_and(changed_mask, zone_mask)
    changed_pixels = int(cv2.countNonZero(changed_in_zone))
    zone_pixels = int(cv2.countNonZero(zone_mask))
    changed_ratio = changed_pixels / zone_pixels if zone_pixels else 0.0
    return MotionResult(
        triggered=changed_ratio >= config.changed_pixel_ratio,
        changed_pixel_ratio=changed_ratio,
        changed_pixels=changed_pixels,
        zone_pixels=zone_pixels,
    )
