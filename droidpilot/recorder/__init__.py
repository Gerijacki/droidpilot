"""
droidpilot.recorder — Interaction recording module.

Records user interactions with an Android device via ADB getevent and
converts them to DroidPilot DSL scripts that can be replayed later.

Public exports
--------------
EventRecorder
    Main recorder class.
RecordedEvent
    Dataclass representing a single recorded input event.
DSLGenerator
    Converts a sequence of RecordedEvents to a DroidPilot script string.
"""

from droidpilot.recorder.event_recorder import DSLGenerator, EventRecorder, RecordedEvent

__all__ = [
    "EventRecorder",
    "RecordedEvent",
    "DSLGenerator",
]
