"""
droidpilot.actions.tap — Tap and long-press actions.

Functions in this module translate high-level tap semantics into
the appropriate ADB shell ``input`` commands via :class:`ADBDevice`.

All functions accept an :class:`ADBDevice` as their first argument so
they can be tested in isolation without a full execution context.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from droidpilot.adb.device import ADBDevice

logger = logging.getLogger("droidpilot.actions.tap")


def tap(
    device: "ADBDevice",
    x: int,
    y: int,
    *,
    pre_delay: float = 0.0,
    post_delay: float = 0.0,
) -> None:
    """Tap the device screen at pixel coordinate *(x, y)*.

    Parameters
    ----------
    device:
        The target :class:`~droidpilot.adb.device.ADBDevice`.
    x:
        Horizontal pixel coordinate (0 = left edge).
    y:
        Vertical pixel coordinate (0 = top edge).
    pre_delay:
        Seconds to wait *before* sending the tap event.
    post_delay:
        Seconds to wait *after* sending the tap event.

    Raises
    ------
    ValueError
        If *x* or *y* is negative.
    droidpilot.adb.client.ADBError
        If the ADB command fails.
    """
    if x < 0 or y < 0:
        raise ValueError(f"Tap coordinates must be non-negative, got ({x}, {y})")

    if pre_delay > 0:
        time.sleep(pre_delay)

    logger.debug(f"[tap] ({x}, {y})")
    device.tap(x, y)

    if post_delay > 0:
        time.sleep(post_delay)


def long_press(
    device: "ADBDevice",
    x: int,
    y: int,
    duration_ms: int = 1000,
    *,
    post_delay: float = 0.0,
) -> None:
    """Long-press the device screen at *(x, y)* for *duration_ms* milliseconds.

    Implemented as a zero-length swipe, which Android interprets as a
    long-press gesture.

    Parameters
    ----------
    device:
        The target device.
    x:
        Horizontal pixel coordinate.
    y:
        Vertical pixel coordinate.
    duration_ms:
        Hold duration in milliseconds (default 1000).
    post_delay:
        Seconds to wait after the gesture.

    Raises
    ------
    ValueError
        If coordinates are negative or *duration_ms* is not positive.
    """
    if x < 0 or y < 0:
        raise ValueError(f"Long-press coordinates must be non-negative, got ({x}, {y})")
    if duration_ms <= 0:
        raise ValueError(f"duration_ms must be positive, got {duration_ms}")

    logger.debug(f"[long_press] ({x}, {y}) duration={duration_ms}ms")
    device.long_press(x, y, duration_ms=duration_ms)

    if post_delay > 0:
        time.sleep(post_delay)


def double_tap(
    device: "ADBDevice",
    x: int,
    y: int,
    interval_ms: int = 100,
) -> None:
    """Double-tap at *(x, y)* with *interval_ms* between the two taps.

    Parameters
    ----------
    device:
        The target device.
    x:
        Horizontal pixel coordinate.
    y:
        Vertical pixel coordinate.
    interval_ms:
        Time between the two taps in milliseconds (default 100).
    """
    if x < 0 or y < 0:
        raise ValueError(f"Double-tap coordinates must be non-negative, got ({x}, {y})")

    logger.debug(f"[double_tap] ({x}, {y}) interval={interval_ms}ms")
    device.tap(x, y)
    time.sleep(interval_ms / 1000.0)
    device.tap(x, y)


def tap_sequence(
    device: "ADBDevice",
    coordinates: list[tuple[int, int]],
    interval: float = 0.1,
) -> None:
    """Tap a sequence of screen coordinates in order.

    Parameters
    ----------
    device:
        The target device.
    coordinates:
        Ordered list of ``(x, y)`` tuples to tap.
    interval:
        Seconds to wait between consecutive taps.
    """
    for i, (x, y) in enumerate(coordinates):
        logger.debug(f"[tap_sequence] step {i + 1}/{len(coordinates)} → ({x}, {y})")
        device.tap(x, y)
        if i < len(coordinates) - 1:
            time.sleep(interval)
