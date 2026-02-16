"""
Human-like timing utilities for realistic browser automation.

Implements probabilistic timing delays using normal distribution to mimic
natural human behavior while optimizing for speed in competitive scenarios.
"""

import random
import threading
from typing import Literal


# Thread-local random number generator for thread safety
_thread_local = threading.local()


def _get_random() -> random.Random:
    """Get a thread-local Random instance for thread-safe random generation."""
    if not hasattr(_thread_local, 'random'):
        _thread_local.random = random.Random()
    return _thread_local.random


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
        rng = _get_random()
        delay = rng.gauss(mean, stddev)

        # Clamp to realistic bounds (prevents outliers)
        delay = max(min_delay, min(max_delay, delay))

        return delay

    @staticmethod
    def get_page_wait(expected_ms: int = None) -> float:
        """
        Generate a page load wait time with network variance.

        Args:
            expected_ms: Expected base wait time in milliseconds.
                        If None, uses TimingConfig.PAGE_LOAD_MEAN.

        Returns:
            Wait time in milliseconds with natural variance

        Adds realistic variance (±25%) to simulate network conditions,
        browser rendering time, and other real-world factors.
        """
        from app.config import TimingConfig

        # Use configured default if not specified
        if expected_ms is None:
            expected_ms = TimingConfig.PAGE_LOAD_MEAN

        # Use configured variance or default to ±25%
        stddev = TimingConfig.PAGE_LOAD_STDDEV

        # Sample from normal distribution centered on expected time
        rng = _get_random()
        delay = rng.gauss(expected_ms, stddev)

        # Keep reasonable bounds (at least 500ms, max 3x expected)
        min_delay = max(500, expected_ms * 0.5)
        max_delay = expected_ms * 2.0
        delay = max(min_delay, min(max_delay, delay))

        return delay

    @staticmethod
    def get_ui_interaction_delay() -> float:
        """
        Generate a delay for UI interactions that need stabilization.
        
        Returns:
            Delay in milliseconds for UI animations/transitions
        
        Used after dismissing modals, banners, or other UI elements that
        may have animations or need time to fully disappear and update DOM.
        Range: 300-700ms (shorter than page load, longer than click)
        """
        from app.config import TimingConfig
        
        # Use a moderate delay with variance
        mean = TimingConfig.UI_INTERACTION_MEAN
        stddev = TimingConfig.UI_INTERACTION_STDDEV
        
        rng = _get_random()
        delay = rng.gauss(mean, stddev)
        
        # Keep within reasonable bounds for UI animations
        min_delay = 300
        max_delay = 700
        delay = max(min_delay, min(max_delay, delay))
        
        return delay
