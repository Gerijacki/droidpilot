"""
DroidPilot — A scriptable Android automation framework via ADB.

No device agent required. Write scripts in the DroidPilot DSL and automate
any Android device connected over USB or TCP/IP.

Example usage::

    from droidpilot.core.parser import DroidPilotParser
    from droidpilot.core.engine import ExecutionEngine
    from droidpilot.core.context import ExecutionContext
    from droidpilot.adb.device import ADBDevice

    device = ADBDevice("emulator-5554")
    ctx = ExecutionContext(device=device)
    parser = DroidPilotParser()
    engine = ExecutionEngine()

    program = parser.parse_file("my_script.dp")
    result = engine.execute(program, ctx)

    if result.success:
        print(f"Completed in {result.stats.elapsed:.2f}s")
    else:
        for err in result.errors:
            print(f"Error: {err}")
"""

from __future__ import annotations

__version__ = "0.1.0"
__author__ = "DroidPilot Contributors"
__license__ = "MIT"

__all__ = [
    "__version__",
    "__author__",
    "__license__",
    "DroidPilotParser",
    "ExecutionEngine",
    "ExecutionContext",
    "ExecutionResult",
    "ADBDevice",
    "ADBClient",
    "ParseError",
    "ExecutionError",
    "DeviceNotFoundError",
    "CommandError",
]

# Core components — imported lazily to avoid circular imports and keep startup fast.
# Users should import directly from submodules for type-checker friendliness:
#   from droidpilot.core.parser import DroidPilotParser

def __getattr__(name: str) -> object:
    """Lazy top-level attribute access for heavy imports."""
    if name == "DroidPilotParser":
        from droidpilot.core.parser import DroidPilotParser
        return DroidPilotParser
    if name == "ExecutionEngine":
        from droidpilot.core.engine import ExecutionEngine
        return ExecutionEngine
    if name == "ExecutionContext":
        from droidpilot.core.context import ExecutionContext
        return ExecutionContext
    if name == "ExecutionResult":
        from droidpilot.core.engine import ExecutionResult
        return ExecutionResult
    if name == "ADBDevice":
        from droidpilot.adb.device import ADBDevice
        return ADBDevice
    if name == "ADBClient":
        from droidpilot.adb.client import ADBClient
        return ADBClient
    if name == "ParseError":
        from droidpilot.core.parser import ParseError
        return ParseError
    if name == "ExecutionError":
        from droidpilot.core.engine import ExecutionError
        return ExecutionError
    if name == "DeviceNotFoundError":
        from droidpilot.adb.client import DeviceNotFoundError
        return DeviceNotFoundError
    if name == "CommandError":
        from droidpilot.core.engine import CommandError
        return CommandError
    raise AttributeError(f"module 'droidpilot' has no attribute {name!r}")
