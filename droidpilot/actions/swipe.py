"""
droidpilot.actions.swipe — Swipe and scroll gesture actions.

Translates high-level swipe/scroll semantics into ADB shell commands via
:class:`~droidpilot.adb.device.ADBDevice`.

Functions
---------
swipe(device, x1, y1, x2, y2, duration_ms)
    Generic swipe from one coordinate to another.
scroll_down(device, steps, cx)
    Scroll down the current view using a swipe gesture.
scroll_up(device, steps, cx)
    Scroll up the current view using a swipe gesture.
fling_down(device, cx)
    Fast fling-downward gesture.
fling_up(device, cx)
    Fast fling-upward gesture.
horizontal_swipe_left(device)
    Swipe left (go to next page / dismiss right).
horizontal_swipe_right(device)
    Swipe right (go to previous page / dismiss left).
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from droidpilot.adb.device import ADBDevice

logger = logging.getLogger("droidpilot.actions.swipe")

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_SCREEN_WIDTH = 1080
_DEFAULT_SCREEN_HEIGHT = 2340
_DEFAULT_SWIPE_DURATION_MS = 300
_DEFAULT_SCROLL_DISTANCE_PX = 800


def swipe(
    device: "ADBDevice",
    x1: int,
    y1: int,
    x2: int,
    y2: int,
    duration_ms: int = _DEFAULT_SWIPE_DURATION_MS,
    *,
    post_delay: float = 0.0,
) -> None:
    """Swipe from *(x1, y1)* to *(x2, y2)* over *duration_ms* milliseconds.

    Parameters
    ----------
    device:
        The target :class:`~droidpilot.adb.device.ADBDevice`.
    x1, y1:
        Start coordinates in pixels.
    x2, y2:
        End coordinates in pixels.
    duration_ms:
        Swipe duration in milliseconds (default 300).
    post_delay:
        Seconds to wait after the gesture completes.

    Raises
    ------
    ValueError
        If any coordinate is negative or *duration_ms* is not positive.
    """
    if any(c < 0 for c in (x1, y1, x2, y2)):
        raise ValueError(
            f"Swipe coordinates must be non-negative, got "
            f"({x1}, {y1}) → ({x2}, {y2})"
        )
    if duration_ms <= 0:
        raise ValueError(f"duration_ms must be positive, got {duration_ms}")

    logger.debug(f"[swipe] ({x1},{y1}) → ({x2},{y2}) duration={duration_ms}ms")
    device.swipe(x1, y1, x2, y2, duration_ms=duration_ms)

    if post_delay > 0:
        time.sleep(post_delay)


def scroll_down(
    device: "ADBDevice",
    steps: int = 5,
    cx: int | None = None,
    duration_ms: int = 300,
) -> None:
    """Scroll down by swiping upward on the screen.

    Parameters
    ----------
    device:
        The target device.
    steps:
        Number of scroll steps.  Each step swipes approximately
        ``_DEFAULT_SCROLL_DISTANCE_PX / steps`` pixels.
    cx:
        Horizontal centre coordinate for the swipe.  Defaults to the
        middle of the screen based on the device's reported screen width.
    duration_ms:
        Duration per swipe in milliseconds.
    """
    try:
        width, height = device.screen_size()
    except Exception:
        width, height = _DEFAULT_SCREEN_WIDTH, _DEFAULT_SCREEN_HEIGHT

    if cx is None:
        cx = width // 2

    start_y = int(height * 0.75)
    end_y = int(height * 0.25)

    logger.debug(f"[scroll_down] steps={steps} cx={cx}")
    for _ in range(steps):
        device.swipe(cx, start_y, cx, end_y, duration_ms=duration_ms)
        time.sleep(0.1)


def scroll_up(
    device: "ADBDevice",
    steps: int = 5,
    cx: int | None = None,
    duration_ms: int = 300,
) -> None:
    """Scroll up by swiping downward on the screen.

    Parameters
    ----------
    device:
        The target device.
    steps:
        Number of scroll steps.
    cx:
        Horizontal centre coordinate.  Defaults to screen mid-width.
    duration_ms:
        Duration per swipe in milliseconds.
    """
    try:
        width, height = device.screen_size()
    except Exception:
        width, height = _DEFAULT_SCREEN_WIDTH, _DEFAULT_SCREEN_HEIGHT

    if cx is None:
        cx = width // 2

    start_y = int(height * 0.25)
    end_y = int(height * 0.75)

    logger.debug(f"[scroll_up] steps={steps} cx={cx}")
    for _ in range(steps):
        device.swipe(cx, start_y, cx, end_y, duration_ms=duration_ms)
        time.sleep(0.1)


def fling_down(device: "ADBDevice", cx: int | None = None) -> None:
    """Perform a fast fling-down gesture (very fast upward swipe).

    Parameters
    ----------
    device:
        The target device.
    cx:
        Horizontal centre coordinate for the swipe.
    """
    try:
        width, height = device.screen_size()
    except Exception:
        width, height = _DEFAULT_SCREEN_WIDTH, _DEFAULT_SCREEN_HEIGHT

    if cx is None:
        cx = width // 2

    logger.debug(f"[fling_down] cx={cx}")
    device.swipe(cx, int(height * 0.9), cx, int(height * 0.1), duration_ms=80)


def fling_up(device: "ADBDevice", cx: int | None = None) -> None:
    """Perform a fast fling-up gesture (very fast downward swipe)."""
    try:
        width, height = device.screen_size()
    except Exception:
        width, height = _DEFAULT_SCREEN_WIDTH, _DEFAULT_SCREEN_HEIGHT

    if cx is None:
        cx = width // 2

    logger.debug(f"[fling_up] cx={cx}")
    device.swipe(cx, int(height * 0.1), cx, int(height * 0.9), duration_ms=80)


def horizontal_swipe_left(
    device: "ADBDevice",
    cy: int | None = None,
    duration_ms: int = 300,
) -> None:
    """Swipe horizontally leftward (e.g. advance to the next page).

    Parameters
    ----------
    device:
        The target device.
    cy:
        Vertical centre coordinate.  Defaults to mid-screen height.
    duration_ms:
        Swipe duration in milliseconds.
    """
    try:
        width, height = device.screen_size()
    except Exception:
        width, height = _DEFAULT_SCREEN_WIDTH, _DEFAULT_SCREEN_HEIGHT

    if cy is None:
        cy = height // 2

    logger.debug(f"[horizontal_swipe_left] cy={cy}")
    device.swipe(int(width * 0.8), cy, int(width * 0.2), cy, duration_ms=duration_ms)


def horizontal_swipe_right(
    device: "ADBDevice",
    cy: int | None = None,
    duration_ms: int = 300,
) -> None:
    """Swipe horizontally rightward (e.g. go back to the previous page).

    Parameters
    ----------
    device:
        The target device.
    cy:
        Vertical centre coordinate.  Defaults to mid-screen height.
    duration_ms:
        Swipe duration in milliseconds.
    """
    try:
        width, height = device.screen_size()
    except Exception:
        width, height = _DEFAULT_SCREEN_WIDTH, _DEFAULT_SCREEN_HEIGHT

    if cy is None:
        cy = height // 2

    logger.debug(f"[horizontal_swipe_right] cy={cy}")
    device.swipe(int(width * 0.2), cy, int(width * 0.8), cy, duration_ms=duration_ms)
