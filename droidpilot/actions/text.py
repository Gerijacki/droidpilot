"""
droidpilot.actions.text — Text input and keyboard actions.

Provides utilities for sending text and key events to Android devices via
ADB, including multi-line entry, clipboard pasting, and field clearing.

Functions
---------
type_text(device, text)
    Type a string into the currently focused input field.
type_line(device, text)
    Type text and press Enter.
clear_field(device, max_chars)
    Clear the focused text field by selecting-all then deleting.
paste_clipboard(device, text)
    Copy *text* to the device clipboard, then paste it.
press_enter(device)
    Press the Enter / Return key.
press_backspace(device, count)
    Press Backspace N times.
press_tab(device)
    Press the Tab key to advance focus.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from droidpilot.adb.device import ADBDevice

logger = logging.getLogger("droidpilot.actions.text")

# Android key codes
_KEYCODE_ENTER = 66
_KEYCODE_BACKSPACE = 67
_KEYCODE_TAB = 61
_KEYCODE_A = 29          # For select-all (CTRL+A via meta)
_KEYCODE_CTRL_A = 277    # KEYCODE_CTRL_LEFT + A — not universally available
_KEYCODE_DEL = 67


def type_text(device: "ADBDevice", text: str) -> None:
    """Type *text* into the currently focused input field.

    Characters are URL-encoded before being passed to ``adb shell input text``,
    which allows special characters and spaces to be sent reliably.

    Parameters
    ----------
    device:
        The target device.
    text:
        The string to type.  Unicode characters are supported.

    Notes
    -----
    Some special characters (e.g. ``%``, ``&``) may not be typed correctly
    on older Android versions due to shell escaping limitations.  Use
    :func:`paste_clipboard` for complex strings.
    """
    if not text:
        logger.debug("[type_text] empty string — skipping")
        return

    logger.debug(f"[type_text] {text!r} ({len(text)} chars)")
    device.type_text(text)


def type_line(device: "ADBDevice", text: str) -> None:
    """Type *text* followed by pressing Enter.

    Useful for submitting search queries or chat messages.

    Parameters
    ----------
    device:
        The target device.
    text:
        The string to type.
    """
    type_text(device, text)
    time.sleep(0.05)
    press_enter(device)


def clear_field(device: "ADBDevice", max_chars: int = 200) -> None:
    """Clear the currently focused text field.

    Strategy: select-all (CTRL+A), then delete the selection.  Falls back
    to sending *max_chars* backspace events if select-all is not available.

    Parameters
    ----------
    device:
        The target device.
    max_chars:
        Maximum number of backspace events to send as a fallback.
    """
    logger.debug(f"[clear_field] selecting all and deleting (max_chars={max_chars})")
    # Try CTRL+A first (works on most modern Android devices).
    try:
        device.shell("input keyevent --longpress 277")  # KEYCODE_CTRL_LEFT
        device.shell("input keyevent 29")               # A
        time.sleep(0.05)
        device.shell("input keyevent 67")               # BACKSPACE — delete selection
    except Exception:
        # Fallback: mash backspace.
        logger.debug(f"[clear_field] falling back to {max_chars} backspace events")
        for _ in range(max_chars):
            device.key_event(_KEYCODE_BACKSPACE)


def paste_clipboard(device: "ADBDevice", text: str) -> None:
    """Copy *text* to the device clipboard, then paste it.

    Uses ``am broadcast`` to set the clipboard content, then simulates
    a long-press paste gesture.

    Parameters
    ----------
    device:
        The target device.
    text:
        Text to paste.

    Notes
    -----
    This approach requires API level 19+ and relies on the ``ClipboardManager``
    broadcast intent.  On some ROM variants it may not work.
    """
    import shlex

    safe_text = shlex.quote(text)
    logger.debug(f"[paste_clipboard] setting clipboard to {text!r}")
    # Set clipboard via a broadcast to our helper.
    cmd = (
        f"am broadcast -a clipper.set -e text {safe_text} "
        "2>/dev/null || true"
    )
    device.shell(cmd)
    time.sleep(0.1)

    # Paste via CTRL+V (key code sequence: meta+CTRL+V is not portable).
    # Instead, use the paste key event if available.
    device.shell("input keyevent 279")  # KEYCODE_PASTE
    logger.debug("[paste_clipboard] paste key sent")


def press_enter(device: "ADBDevice") -> None:
    """Press the Enter / Return key on the virtual keyboard."""
    logger.debug("[press_enter]")
    device.key_event(_KEYCODE_ENTER)


def press_backspace(device: "ADBDevice", count: int = 1) -> None:
    """Press the Backspace key *count* times.

    Parameters
    ----------
    device:
        The target device.
    count:
        Number of backspace presses.
    """
    if count <= 0:
        return
    logger.debug(f"[press_backspace] × {count}")
    for _ in range(count):
        device.key_event(_KEYCODE_BACKSPACE)
        if count > 1:
            time.sleep(0.02)


def press_tab(device: "ADBDevice") -> None:
    """Press Tab to advance the input focus."""
    logger.debug("[press_tab]")
    device.key_event(_KEYCODE_TAB)
