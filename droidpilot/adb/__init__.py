"""
droidpilot.adb — ADB client and device interface.

Public exports
--------------
ADBClient
    Low-level subprocess wrapper around the ``adb`` binary.
ADBDevice
    High-level, device-bound interface for automation.
ADBError
    Raised when an ADB command fails.
DeviceNotFoundError
    Raised when a device serial is not found.
DeviceEntry
    Dataclass representing a single ``adb devices`` entry.
"""

from droidpilot.adb.client import ADBClient, ADBError, DeviceEntry, DeviceNotFoundError
from droidpilot.adb.device import ADBDevice

__all__ = [
    "ADBClient",
    "ADBDevice",
    "ADBError",
    "DeviceNotFoundError",
    "DeviceEntry",
]
