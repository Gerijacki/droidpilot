"""
DroidPilot Event Recorder.

Records Android user input events via ``adb shell getevent`` and converts
them into a replay-able DroidPilot DSL script.

Architecture
------------
The recorder runs ``adb shell getevent -lt`` in a background subprocess.
Raw event lines are parsed by :class:`GeteventParser` into low-level
:class:`RawEvent` objects.  A :class:`TouchStateMachine` accumulates raw
events into high-level :class:`RecordedEvent` objects (tap, swipe, etc.).
Finally :class:`DSLGenerator` converts the high-level events into DSL text.

Usage::

    from droidpilot.adb.device import ADBDevice
    from droidpilot.recorder.event_recorder import EventRecorder

    device = ADBDevice("emulator-5554")
    recorder = EventRecorder(device)

    recorder.start()
    input("Press Enter to stop recording...")
    recorder.stop()

    script = recorder.to_dsl()
    print(script)
    # tap(540, 1200)
    # wait(2.1)
    # swipe(540, 1500, 540, 500, 350)
"""

from __future__ import annotations

import logging
import re
import subprocess
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from droidpilot.adb.device import ADBDevice

logger = logging.getLogger("droidpilot.recorder")


# ─── Raw event (from getevent -lt) ────────────────────────────────────────────


@dataclass
class RawEvent:
    """A single line parsed from ``adb shell getevent -lt``.

    Attributes
    ----------
    timestamp:
        Floating-point seconds since epoch (from getevent's ``[  N.NNNNN]``).
    event_type:
        Event type string, e.g. ``"EV_ABS"``, ``"EV_KEY"``, ``"EV_SYN"``.
    code:
        Event code string, e.g. ``"ABS_MT_POSITION_X"``.
    value:
        Integer event value.
    """

    timestamp: float
    event_type: str
    code: str
    value: int


# ─── High-level recorded events ───────────────────────────────────────────────


class EventKind(Enum):
    """Kinds of high-level interaction events."""

    TAP = auto()
    LONG_PRESS = auto()
    SWIPE = auto()
    KEY = auto()
    WAIT = auto()


@dataclass
class RecordedEvent:
    """A high-level user interaction extracted from raw ADB events.

    Attributes
    ----------
    kind:
        The type of interaction.
    x:
        Start (or single) X coordinate in pixels.
    y:
        Start (or single) Y coordinate in pixels.
    x2:
        End X coordinate (for swipes).
    y2:
        End Y coordinate (for swipes).
    duration_ms:
        Duration in milliseconds (for swipes / long-presses).
    keycode:
        Android keycode (for key events).
    wait_seconds:
        Wait duration (for wait events).
    timestamp:
        Wall-clock time when this event started.
    """

    kind: EventKind
    x: int = 0
    y: int = 0
    x2: int = 0
    y2: int = 0
    duration_ms: int = 0
    keycode: int = 0
    wait_seconds: float = 0.0
    timestamp: float = field(default_factory=time.monotonic)


# ─── Getevent line parser ─────────────────────────────────────────────────────


class GeteventParser:
    """Parses lines from ``adb shell getevent -lt`` into :class:`RawEvent` objects.

    The output format (with ``-lt``) looks like::

        [   1234.567890] /dev/input/event1: EV_ABS       ABS_MT_POSITION_X  00000218
        [   1234.567900] /dev/input/event1: EV_ABS       ABS_MT_POSITION_Y  000004b0
        [   1234.568000] /dev/input/event1: EV_SYN       SYN_REPORT         00000000
    """

    _LINE_RE = re.compile(
        r"\[\s*(\d+\.\d+)\]\s+\S+:\s+(\S+)\s+(\S+)\s+([0-9a-fA-F]+)"
    )

    def parse(self, line: str) -> RawEvent | None:
        """Parse a single getevent output line.

        Returns ``None`` if the line does not match the expected format.
        """
        m = self._LINE_RE.match(line.strip())
        if not m:
            return None
        timestamp = float(m.group(1))
        event_type = m.group(2)
        code = m.group(3)
        try:
            value = int(m.group(4), 16)
        except ValueError:
            return None
        return RawEvent(
            timestamp=timestamp,
            event_type=event_type,
            code=code,
            value=value,
        )


# ─── Touch state machine ──────────────────────────────────────────────────────


class TouchStateMachine:
    """Accumulates raw ADB events into high-level :class:`RecordedEvent` objects.

    Tracks multi-touch ``ABS_MT_*`` events across SYN_REPORT boundaries to
    detect tap vs. swipe gestures.

    Parameters
    ----------
    tap_max_distance_px:
        Maximum pixel movement to classify a touch as a tap (not a swipe).
    tap_max_duration_ms:
        Maximum duration (ms) to classify a touch as a tap.
    long_press_min_duration_ms:
        Minimum hold duration (ms) to classify a tap as a long press.
    """

    def __init__(
        self,
        tap_max_distance_px: int = 15,
        tap_max_duration_ms: int = 200,
        long_press_min_duration_ms: int = 500,
    ) -> None:
        self._tap_max_dist = tap_max_distance_px
        self._tap_max_dur = tap_max_duration_ms
        self._long_min_dur = long_press_min_duration_ms

        self._events: list[RecordedEvent] = []
        self._last_event_time: float | None = None

        # Current touch tracking
        self._touch_active = False
        self._touch_start_x: int = 0
        self._touch_start_y: int = 0
        self._touch_start_time: float = 0.0
        self._touch_cur_x: int = 0
        self._touch_cur_y: int = 0

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _on_touch_start(self, x: int, y: int, ts: float) -> None:
        self._touch_active = True
        self._touch_start_x = x
        self._touch_start_y = y
        self._touch_start_time = ts
        self._touch_cur_x = x
        self._touch_cur_y = y

    def _on_touch_end(self, ts: float) -> None:
        if not self._touch_active:
            return
        self._touch_active = False
        duration_ms = int((ts - self._touch_start_time) * 1000)
        dx = abs(self._touch_cur_x - self._touch_start_x)
        dy = abs(self._touch_cur_y - self._touch_start_y)
        dist = (dx**2 + dy**2) ** 0.5

        # Insert a wait event if there was a gap since the last event.
        now = time.monotonic()
        if self._last_event_time is not None:
            gap = now - self._last_event_time
            if gap >= 0.3:
                self._events.append(
                    RecordedEvent(
                        kind=EventKind.WAIT,
                        wait_seconds=round(gap, 2),
                        timestamp=self._last_event_time,
                    )
                )
        self._last_event_time = now

        if dist <= self._tap_max_dist and duration_ms <= self._tap_max_dur:
            self._events.append(
                RecordedEvent(
                    kind=EventKind.TAP,
                    x=self._touch_start_x,
                    y=self._touch_start_y,
                    timestamp=now,
                )
            )
        elif dist <= self._tap_max_dist and duration_ms >= self._long_min_dur:
            self._events.append(
                RecordedEvent(
                    kind=EventKind.LONG_PRESS,
                    x=self._touch_start_x,
                    y=self._touch_start_y,
                    duration_ms=duration_ms,
                    timestamp=now,
                )
            )
        else:
            self._events.append(
                RecordedEvent(
                    kind=EventKind.SWIPE,
                    x=self._touch_start_x,
                    y=self._touch_start_y,
                    x2=self._touch_cur_x,
                    y2=self._touch_cur_y,
                    duration_ms=max(duration_ms, 50),
                    timestamp=now,
                )
            )

    # ── Public feed interface ─────────────────────────────────────────────────

    def feed(self, raw: RawEvent) -> None:
        """Process a :class:`RawEvent` and update internal state.

        Parameters
        ----------
        raw:
            A parsed raw event from getevent.
        """
        if raw.event_type == "EV_ABS":
            if raw.code == "ABS_MT_POSITION_X":
                if not self._touch_active:
                    self._on_touch_start(raw.value, 0, raw.timestamp)
                else:
                    self._touch_cur_x = raw.value
            elif raw.code == "ABS_MT_POSITION_Y":
                if self._touch_active:
                    self._touch_cur_y = raw.value
                else:
                    self._touch_start_y = raw.value
                    self._touch_cur_y = raw.value
        elif raw.event_type == "EV_KEY" and raw.code == "BTN_TOUCH":
            if raw.value == 1:
                # Touch down
                pass
            elif raw.value == 0:
                # Touch up — finalise the gesture.
                self._on_touch_end(raw.timestamp)

    @property
    def events(self) -> list[RecordedEvent]:
        """Return the accumulated list of high-level events."""
        return list(self._events)

    def reset(self) -> None:
        """Clear all accumulated events."""
        self._events.clear()
        self._last_event_time = None
        self._touch_active = False


# ─── DSL generator ────────────────────────────────────────────────────────────


class DSLGenerator:
    """Converts a list of :class:`RecordedEvent` objects into DroidPilot DSL.

    Parameters
    ----------
    min_wait:
        Minimum wait duration (seconds) to include in the output.
        Shorter waits are omitted.
    """

    def __init__(self, min_wait: float = 0.2) -> None:
        self.min_wait = min_wait

    def generate(self, events: list[RecordedEvent]) -> str:
        """Generate a DroidPilot DSL script from *events*.

        Parameters
        ----------
        events:
            Ordered list of high-level recorded events.

        Returns
        -------
        str
            A complete DroidPilot DSL script ready to save to a ``.dp`` file.
        """
        lines: list[str] = [
            "# DroidPilot recorded script",
            "# Generated by droidpilot record",
            "",
        ]

        for evt in events:
            if evt.kind == EventKind.TAP:
                lines.append(f"tap({evt.x}, {evt.y})")
            elif evt.kind == EventKind.LONG_PRESS:
                lines.append(f"# long_press({evt.x}, {evt.y}, {evt.duration_ms})")
                lines.append(f"tap({evt.x}, {evt.y})")
            elif evt.kind == EventKind.SWIPE:
                lines.append(
                    f"swipe({evt.x}, {evt.y}, {evt.x2}, {evt.y2}, {evt.duration_ms})"
                )
            elif evt.kind == EventKind.KEY:
                lines.append(f"key_event({evt.keycode})")
            elif evt.kind == EventKind.WAIT:
                if evt.wait_seconds >= self.min_wait:
                    lines.append(f"wait({evt.wait_seconds:.1f})")

        return "\n".join(lines) + "\n"


# ─── Event Recorder ───────────────────────────────────────────────────────────


class RecorderError(Exception):
    """Raised when the recorder encounters an unrecoverable error."""


class EventRecorder:
    """Records Android input events and generates a DroidPilot DSL replay script.

    Parameters
    ----------
    device:
        The target :class:`~droidpilot.adb.device.ADBDevice` to record from.
    tap_max_distance_px:
        Pixel threshold for tap vs. swipe classification.
    tap_max_duration_ms:
        Time threshold (ms) for tap vs. long-press classification.
    """

    def __init__(
        self,
        device: "ADBDevice",
        tap_max_distance_px: int = 15,
        tap_max_duration_ms: int = 200,
        long_press_min_duration_ms: int = 500,
    ) -> None:
        self._device = device
        self._parser = GeteventParser()
        self._state = TouchStateMachine(
            tap_max_distance_px=tap_max_distance_px,
            tap_max_duration_ms=tap_max_duration_ms,
            long_press_min_duration_ms=long_press_min_duration_ms,
        )
        self._generator = DSLGenerator()

        self._proc: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._recording = False

    # ── Recording lifecycle ───────────────────────────────────────────────────

    def start(self) -> None:
        """Start recording input events from the device.

        Launches ``adb shell getevent -lt`` in a background thread.

        Raises
        ------
        RecorderError
            If a recording is already in progress.
        """
        if self._recording:
            raise RecorderError("Recording is already in progress.")

        self._state.reset()
        serial_args = ["-s", self._device.serial]
        cmd = [
            self._device.client._adb_path,
            *serial_args,
            "shell",
            "getevent",
            "-lt",
        ]

        logger.info(f"[recorder] starting getevent on {self._device.serial}")
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        self._recording = True
        self._thread = threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name="droidpilot-getevent-reader",
        )
        self._thread.start()
        logger.info("[recorder] recording started")

    def stop(self) -> None:
        """Stop recording and clean up resources.

        Safe to call even if recording was not started.
        """
        if not self._recording:
            return

        self._recording = False
        if self._proc is not None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                self._proc.kill()
            self._proc = None

        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None

        logger.info(
            f"[recorder] stopped — {len(self._state.events)} event(s) captured"
        )

    def _reader_loop(self) -> None:
        """Background thread: read getevent output and feed the state machine."""
        assert self._proc is not None
        assert self._proc.stdout is not None
        for line in self._proc.stdout:
            if not self._recording:
                break
            raw = self._parser.parse(line)
            if raw is not None:
                self._state.feed(raw)

    # ── Results ──────────────────────────────────────────────────────────────

    @property
    def events(self) -> list[RecordedEvent]:
        """Return the list of high-level events recorded so far.

        Returns
        -------
        list[RecordedEvent]
        """
        return self._state.events

    def to_dsl(self) -> str:
        """Convert recorded events to a DroidPilot DSL script string.

        Returns
        -------
        str
            The generated DSL script.
        """
        return self._generator.generate(self._state.events)

    def save_dsl(self, path: str) -> None:
        """Generate and write the DSL script to *path*.

        Parameters
        ----------
        path:
            File path to write the script to (will be overwritten).
        """
        from pathlib import Path

        script = self.to_dsl()
        Path(path).write_text(script, encoding="utf-8")
        logger.info(f"[recorder] script saved to {path!r}")

    def __enter__(self) -> "EventRecorder":
        self.start()
        return self

    def __exit__(self, *_: Any) -> None:
        self.stop()
