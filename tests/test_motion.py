from __future__ import annotations

import unittest

import numpy as np

from hati.config import MotionConfig
from hati.motion import measure_motion


class MotionTests(unittest.TestCase):
    def test_large_change_inside_zone_triggers(self) -> None:
        prior = np.zeros((100, 100, 3), dtype=np.uint8)
        current = prior.copy()
        current[25:75, 25:75] = 255
        config = MotionConfig(
            changed_pixel_ratio=0.05,
            pixel_threshold=10,
            blur_size=1,
        )
        result = measure_motion(prior, current, config)
        self.assertTrue(result.triggered)
        self.assertGreater(result.changed_pixel_ratio, 0.20)

    def test_change_outside_polygon_does_not_trigger(self) -> None:
        prior = np.zeros((100, 100, 3), dtype=np.uint8)
        current = prior.copy()
        current[20:80, 70:95] = 255
        config = MotionConfig(
            zone_polygon=((0.0, 0.0), (0.5, 0.0), (0.5, 1.0), (0.0, 1.0)),
            changed_pixel_ratio=0.01,
            pixel_threshold=10,
            blur_size=1,
        )
        result = measure_motion(prior, current, config)
        self.assertFalse(result.triggered)
        self.assertEqual(0, result.changed_pixels)


if __name__ == "__main__":
    unittest.main()
