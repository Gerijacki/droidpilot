"""
droidpilot.actions — High-level action modules.

Each module wraps a specific category of ADB operations and exposes a
clean Python function that can be called directly or registered as a
DroidPilot DSL command.

Modules
-------
tap         Tap and long-press at screen coordinates.
swipe       Swipe and scroll gestures.
text        Keyboard input and text entry.
app         App lifecycle management (launch, stop, install).
screenshot  Screen capture utilities.
"""

from droidpilot.actions.app import force_stop_app, open_app
from droidpilot.actions.screenshot import capture_screenshot
from droidpilot.actions.swipe import scroll_down, scroll_up, swipe
from droidpilot.actions.tap import long_press, tap
from droidpilot.actions.text import clear_field, type_line, type_text

__all__ = [
    "tap",
    "long_press",
    "swipe",
    "scroll_down",
    "scroll_up",
    "type_text",
    "clear_field",
    "type_line",
    "open_app",
    "force_stop_app",
    "capture_screenshot",
]
