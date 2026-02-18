"""
Human-like timing utilities for realistic browser automation.

Implements probabilistic timing delays using normal distribution to mimic
natural human behavior while optimizing for speed in competitive scenarios.
"""

import math
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
            mode: "racing" for aggressive ticket-grabbing (80-300ms range),
                  "normal" for scheduled automation (150-600ms range)

        Returns:
            Delay in milliseconds, sampled from normal distribution with bounds

        Racing mode (80-300ms):
            - Mean: 180ms (fast but realistic human reaction time)
            - Std dev: 40ms (natural variance)
            - Mimics someone actively watching and clicking competitively

        Normal mode (150-600ms):
            - Mean: 350ms (comfortable, relaxed clicking speed)
            - Std dev: 80ms (natural variance)
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

        # Keep reasonable bounds (at least 100ms, max 3x expected)
        min_delay = max(100, expected_ms * 0.5)
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
        min_delay = 50
        max_delay = 700
        delay = max(min_delay, min(max_delay, delay))
        
        return delay

    @staticmethod
    def generate_mouse_path(
        start_x: float, start_y: float,
        end_x: float, end_y: float,
        steps: int = None
    ) -> list[tuple[float, float]]:
        """
        Generate a human-like mouse movement path using Bézier curve interpolation.
        
        Args:
            start_x, start_y: Starting mouse position
            end_x, end_y: Target position (element center)
            steps: Number of intermediate points (auto-calculated if None)
        
        Returns:
            List of (x, y) coordinate tuples forming the path
        """
        distance = math.sqrt((end_x - start_x) * (end_x - start_x) + 
                             (end_y - start_y) * (end_y - start_y))
        
        if steps is None:
            # More steps for longer distances, minimum 8, max ~25
            steps = max(2, min(15, int(distance / 60)))
        
        rng = _get_random()
        
        # Generate control point for quadratic Bézier curve
        # Offset by ~10% of distance to create natural curvature
        # (mimics slight arc of natural hand movement)
        mid_x = (start_x + end_x) / 2 + rng.gauss(0, distance * 0.1)
        mid_y = (start_y + end_y) / 2 + rng.gauss(0, distance * 0.1)
        
        path = []
        for i in range(steps + 1):
            t = i / steps
            # Quadratic Bézier: B(t) = (1-t)²·P0 + 2(1-t)t·P1 + t²·P2
            x = (1 - t) ** 2 * start_x + 2 * (1 - t) * t * mid_x + t ** 2 * end_x
            y = (1 - t) ** 2 * start_y + 2 * (1 - t) * t * mid_y + t ** 2 * end_y
            # Add small jitter (±1-2 pixels) to simulate hand tremor
            x += rng.gauss(0, 1.5)
            y += rng.gauss(0, 1.5)
            path.append((x, y))
        
        return path

    @staticmethod
    def get_mouse_move_delay() -> float:
        """
        Generate delay between mouse movement steps (in ms).
        Simulates the speed of natural hand movement.
        Range: 5-15ms per step (results in ~50-375ms total movement time)
        """
        rng = _get_random()
        return max(5, min(15, rng.gauss(8, 2)))
