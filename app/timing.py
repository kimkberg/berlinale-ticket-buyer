"""
Human-like timing utilities for realistic browser automation.

Implements probabilistic timing delays using normal distribution to mimic
natural human behavior while optimizing for speed in competitive scenarios.
"""

import random
from typing import Literal


class HumanTiming:
    """Provides realistic human-like timing delays with statistical variance."""

    @staticmethod
    def get_click_delay(mode: Literal["racing", "normal"] = "racing") -> float:
        """
        Generate a realistic click delay with natural variance.

        Args:
            mode: "racing" for aggressive ticket-grabbing (20-50ms range),
                  "normal" for scheduled automation (50-150ms range)

        Returns:
            Delay in milliseconds, sampled from normal distribution with bounds

        Racing mode (20-50ms):
            - Mean: 35ms (center of realistic human clicking speed)
            - Std dev: 8ms (natural variance)
            - Mimics someone actively watching and clicking fast

        Normal mode (50-150ms):
            - Mean: 120ms (comfortable human reaction time)
            - Std dev: 30ms (natural variance)
            - Mimics scheduled automation with realistic delays
        """
        from app.config import TimingConfig

        if mode == "racing":
            mean = TimingConfig.RACING_CLICK_MEAN
            stddev = TimingConfig.RACING_CLICK_STDDEV
            min_delay = TimingConfig.RACING_CLICK_MIN
            max_delay = TimingConfig.RACING_CLICK_MAX
        else:  # normal
            mean = TimingConfig.NORMAL_CLICK_MEAN
            stddev = TimingConfig.NORMAL_CLICK_STDDEV
            min_delay = TimingConfig.NORMAL_CLICK_MIN
            max_delay = TimingConfig.NORMAL_CLICK_MAX

        # Sample from normal distribution
        delay = random.gauss(mean, stddev)

        # Clamp to realistic bounds (prevents outliers)
        delay = max(min_delay, min(max_delay, delay))

        return delay

    @staticmethod
    def get_page_wait(expected_ms: int = 1200) -> float:
        """
        Generate a page load wait time with network variance.

        Args:
            expected_ms: Expected base wait time in milliseconds

        Returns:
            Wait time in milliseconds with natural variance

        Adds realistic variance (±25%) to simulate network conditions,
        browser rendering time, and other real-world factors.
        """
        from app.config import TimingConfig

        # Use configured variance or default to ±25%
        stddev = TimingConfig.PAGE_LOAD_STDDEV

        # Sample from normal distribution centered on expected time
        delay = random.gauss(expected_ms, stddev)

        # Keep reasonable bounds (at least 500ms, max 3x expected)
        min_delay = max(500, expected_ms * 0.5)
        max_delay = expected_ms * 2.0
        delay = max(min_delay, min(max_delay, delay))

        return delay
