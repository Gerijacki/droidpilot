"""
ADBDevice — A high-level interface to a single connected Android device.

``ADBDevice`` wraps :class:`~droidpilot.adb.client.ADBClient` and binds every
operation to a specific device serial number, so callers never need to pass
``serial=`` themselves.

Usage::

    from droidpilot.adb.device import ADBDevice

    device = ADBDevice("emulator-5554")
    device.tap(540, 1200)
    device.screenshot("screen.png")
    print(device.get_info())
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from droidpilot.adb.client import ADBClient, ADBError, DeviceNotFoundError


class ADBDevice:
    """High-level interface to a single ADB device.

    Parameters
    ----------
    serial:
        The ADB device serial (e.g. ``"emulator-5554"`` or ``"192.168.1.5:5555"``).
        If ``None`` the first available device is used.
    adb_path:
        Path to the ``adb`` binary (default: ``"adb"``).
    default_tap_delay:
        Seconds to wait after each tap (default 0.0 — no extra delay).
    timeout:
        Default subprocess timeout in seconds.
    """

    def __init__(
        self,
        serial: str | None = None,
        adb_path: str = "adb",
        default_tap_delay: float = 0.0,
        timeout: float = 30.0,
    ) -> None:
        self._client = ADBClient(adb_path=adb_path, timeout=timeout)
        self._serial: str = serial or self._client.first_device()
        self._default_tap_delay = default_tap_delay
        self._verify_device()

    # ── Private ──────────────────────────────────────────────────────────────

    def _verify_device(self) -> None:
        """Ensure the device is online and accessible."""
        entry = self._client.get_device_entry(self._serial)
        if not entry.is_online:
            raise DeviceNotFoundError(self._serial)

    # ── Properties ───────────────────────────────────────────────────────────

    @property
    def serial(self) -> str:
        """ADB device serial number."""
        return self._serial

    @property
    def client(self) -> ADBClient:
        """Underlying :class:`ADBClient` instance."""
        return self._client

    # ── Shell ─────────────────────────────────────────────────────────────────

    def shell(self, command: str, timeout: float | None = None) -> str:
        """Run a shell command and return stdout.

        Parameters
        ----------
        command:
            Shell command string.
        timeout:
            Override the default timeout.

        Returns
        -------
        str
            Stdout output, trailing whitespace stripped.
        """
        return self._client.shell(command, serial=self._serial, timeout=timeout)

    # ── Input ─────────────────────────────────────────────────────────────────

    def tap(self, x: int, y: int) -> None:
        """Tap the screen at (x, y).

        Parameters
        ----------
        x:
            Horizontal coordinate in pixels.
        y:
            Vertical coordinate in pixels.
        """
        import time

        self._client.tap(x, y, serial=self._serial)
        if self._default_tap_delay > 0:
            time.sleep(self._default_tap_delay)

    def long_press(self, x: int, y: int, duration_ms: int = 1000) -> None:
        """Long-press the screen at (x, y) for *duration_ms* milliseconds.

        Implemented as a zero-distance swipe, which ADB treats as a long press.

        Parameters
        ----------
        x:
            Horizontal coordinate in pixels.
        y:
            Vertical coordinate in pixels.
        duration_ms:
            Hold duration in milliseconds.
        """
        self._client.swipe(x, y, x, y, duration_ms=duration_ms, serial=self._serial)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
    ) -> None:
        """Swipe from (x1, y1) to (x2, y2).

        Parameters
        ----------
        x1, y1:
            Start coordinates.
        x2, y2:
            End coordinates.
        duration_ms:
            Swipe duration in milliseconds.
        """
        self._client.swipe(x1, y1, x2, y2, duration_ms=duration_ms, serial=self._serial)

    def type_text(self, text: str) -> None:
        """Type *text* into the currently focused input field."""
        self._client.type_text(text, serial=self._serial)

    def key_event(self, keycode: int) -> None:
        """Send an Android key event.

        Common key codes:
        - 3: HOME
        - 4: BACK
        - 26: POWER
        - 187: RECENT APPS
        - 24: VOLUME UP
        - 25: VOLUME DOWN
        """
        self._client.key_event(keycode, serial=self._serial)

    def press_back(self) -> None:
        """Press the back button."""
        self.key_event(4)

    def press_home(self) -> None:
        """Press the home button."""
        self.key_event(3)

    def press_recent(self) -> None:
        """Press the recent-apps button."""
        self.key_event(187)

    def press_power(self) -> None:
        """Press the power button."""
        self.key_event(26)

    def scroll_down(self, steps: int = 5) -> None:
        """Scroll down on the screen using a swipe gesture.

        Parameters
        ----------
        steps:
            Number of swipe steps (passed to ``input swipe``).
        """
        self.shell(f"input swipe 540 1400 540 600 {steps * 50}")

    def scroll_up(self, steps: int = 5) -> None:
        """Scroll up on the screen using a swipe gesture."""
        self.shell(f"input swipe 540 600 540 1400 {steps * 50}")

    def pinch_in(self, cx: int, cy: int, distance: int = 200, duration_ms: int = 400) -> None:
        """Perform a two-finger pinch-in gesture (zoom out).

        Uses ``input touchscreen swipe`` with two separate swipe commands
        started nearly simultaneously via a shell subshell.

        Parameters
        ----------
        cx, cy:
            Centre point of the pinch.
        distance:
            Finger spread distance in pixels.
        duration_ms:
            Gesture duration.
        """
        half = distance // 2
        cmd = (
            f"input touchscreen swipe {cx - half} {cy} {cx} {cy} {duration_ms} & "
            f"input touchscreen swipe {cx + half} {cy} {cx} {cy} {duration_ms}"
        )
        self.shell(cmd)

    def pinch_out(self, cx: int, cy: int, distance: int = 200, duration_ms: int = 400) -> None:
        """Perform a two-finger pinch-out gesture (zoom in)."""
        half = distance // 2
        cmd = (
            f"input touchscreen swipe {cx} {cy} {cx - half} {cy} {duration_ms} & "
            f"input touchscreen swipe {cx} {cy} {cx + half} {cy} {duration_ms}"
        )
        self.shell(cmd)

    # ── Screen capture ────────────────────────────────────────────────────────

    def screenshot(self, local_path: str) -> str:
        """Capture the screen and save to *local_path*.

        Parameters
        ----------
        local_path:
            Destination path (PNG).

        Returns
        -------
        str
            The resolved local path.
        """
        out = str(Path(local_path).resolve())
        self._client.screenshot(out, serial=self._serial)
        return out

    # ── App management ────────────────────────────────────────────────────────

    def open_app(self, package: str) -> None:
        """Launch an app by package name.

        Parameters
        ----------
        package:
            Android package name (e.g. ``"com.instagram.android"``).
        """
        self._client.open_app(package, serial=self._serial)

    def force_stop(self, package: str) -> None:
        """Force-stop a running app."""
        self._client.force_stop(package, serial=self._serial)

    def install(self, apk_path: str) -> None:
        """Install an APK."""
        self._client.install(apk_path, serial=self._serial)

    def uninstall(self, package: str) -> None:
        """Uninstall an app."""
        self._client.uninstall(package, serial=self._serial)

    def list_packages(self, filter_str: str = "") -> list[str]:
        """Return a list of installed package names."""
        return self._client.list_packages(filter_str=filter_str, serial=self._serial)

    def is_installed(self, package: str) -> bool:
        """Return ``True`` if *package* is installed on the device."""
        packages = self.list_packages(filter_str=package)
        return package in packages

    # ── Device information ────────────────────────────────────────────────────

    def get_prop(self, prop: str) -> str:
        """Return a system property value."""
        return self._client.get_prop(prop, serial=self._serial)

    def get_info(self) -> dict[str, str]:
        """Return a dict of device information.

        Returns
        -------
        dict
            Keys: ``model``, ``manufacturer``, ``version``, ``sdk``,
                  ``resolution``, ``serial``.
        """
        return self._client.get_info(serial=self._serial)

    def screen_size(self) -> tuple[int, int]:
        """Return the physical screen size as (width, height) in pixels.

        Returns
        -------
        tuple[int, int]
        """
        raw = self.shell("wm size")
        size_str = raw.replace("Physical size: ", "").strip()
        try:
            w, h = size_str.split("x")
            return int(w), int(h)
        except ValueError:
            return 0, 0

    def current_activity(self) -> str:
        """Return the currently focused activity name."""
        raw = self.shell(
            "dumpsys window windows | grep -E 'mCurrentFocus|mFocusedApp'"
        )
        return raw.strip()

    def battery_level(self) -> int:
        """Return the battery level as a percentage (0-100)."""
        raw = self.shell("dumpsys battery | grep level")
        try:
            return int(raw.strip().split(":")[1].strip())
        except (IndexError, ValueError):
            return -1

    def is_screen_on(self) -> bool:
        """Return ``True`` if the device screen is currently on."""
        raw = self.shell("dumpsys power | grep 'mWakefulness'")
        return "Awake" in raw

    def wake_screen(self) -> None:
        """Wake the device screen if it is off."""
        if not self.is_screen_on():
            self.press_power()

    # ── Convenience ──────────────────────────────────────────────────────────

    def wait_for_activity(
        self,
        activity: str,
        timeout: float = 10.0,
        poll_interval: float = 0.5,
    ) -> bool:
        """Poll until *activity* is in the foreground or *timeout* is reached.

        Parameters
        ----------
        activity:
            Substring to search for in the focused activity string.
        timeout:
            Maximum seconds to wait.
        poll_interval:
            Seconds between checks.

        Returns
        -------
        bool
            ``True`` if the activity appeared within *timeout*.
        """
        import time

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if activity in self.current_activity():
                return True
            time.sleep(poll_interval)
        return False

    def __repr__(self) -> str:
        return f"ADBDevice(serial={self._serial!r})"

    def __str__(self) -> str:
        return self._serial
