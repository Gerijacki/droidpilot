"""
DroidPilot Execution Engine.

The engine is responsible for:

1. Registering all built-in commands into an :class:`ExecutionContext`.
2. Walking and executing a :class:`ProgramNode` AST.
3. Collecting errors and statistics into an :class:`ExecutionResult`.

Built-in commands
-----------------
tap(x, y)
    Send a tap event at screen coordinates (x, y).
swipe(x1, y1, x2, y2 [, duration_ms])
    Send a swipe gesture.
type(text)
    Type *text* into the focused input field.
wait(seconds)
    Sleep for *seconds* (float supported).
screenshot(path)
    Capture the device screen and save it to *path*.
open_app(package)
    Launch an app by its package name.
device_info()
    Print device model, Android version, and screen resolution.
list_devices()
    Print all connected ADB devices.
exists(image_path)
    Return True if *image_path* is found on the current screen.
tap_image(image_path [, threshold])
    Tap the centre of the first match of *image_path* on screen.
"""

from __future__ import annotations

import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from droidpilot.core.ast_nodes import (
    AssignNode,
    CommandNode,
    IfNode,
    MacroCallNode,
    MacroDefNode,
    ProgramNode,
    RepeatNode,
)
from droidpilot.core.context import ExecutionContext, ExecutionStats


# ─── Exceptions ───────────────────────────────────────────────────────────────


class ExecutionError(Exception):
    """Raised when an error occurs during script execution.

    Attributes
    ----------
    message:
        Human-readable description.
    line:
        Source line where the error occurred (0 if unknown).
    command:
        Command name that triggered the error (empty if not a command error).
    """

    def __init__(
        self,
        message: str,
        line: int = 0,
        command: str = "",
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.command = command
        self.__cause__ = cause

    def __str__(self) -> str:
        loc = f" (line {self.line})" if self.line else ""
        cmd = f" [{self.command}]" if self.command else ""
        return f"ExecutionError{cmd}{loc}: {self.message}"


class CommandError(ExecutionError):
    """Raised when a specific command fails."""


class DeviceRequiredError(ExecutionError):
    """Raised when a command requires a device but none is connected."""


# ─── Result ───────────────────────────────────────────────────────────────────


@dataclass
class ExecutionResult:
    """The outcome of executing a DroidPilot script.

    Attributes
    ----------
    success:
        ``True`` if execution completed without unhandled errors.
    errors:
        List of :class:`ExecutionError` instances collected during the run.
    stats:
        Execution statistics (counters, timing).
    return_value:
        The return value of the last expression evaluated (rarely used).
    """

    success: bool
    errors: list[ExecutionError] = field(default_factory=list)
    stats: ExecutionStats = field(default_factory=ExecutionStats)
    return_value: Any = None

    def __bool__(self) -> bool:
        return self.success

    def __str__(self) -> str:
        status = "OK" if self.success else f"FAILED ({len(self.errors)} error(s))"
        return f"ExecutionResult({status}, {self.stats})"


# ─── Built-in command implementations ────────────────────────────────────────


def _require_device(ctx: ExecutionContext, command: str) -> Any:
    """Ensure *ctx* has a device; raise :class:`DeviceRequiredError` otherwise."""
    if ctx.device is None:
        raise DeviceRequiredError(
            f"Command '{command}' requires a connected device, but no device is set.",
            command=command,
        )
    return ctx.device


def _cmd_tap(ctx: ExecutionContext, x: Any, y: Any) -> None:
    """tap(x, y) — Tap a screen coordinate."""
    device = _require_device(ctx, "tap")
    xi, yi = int(x), int(y)
    ctx.logger.info(f"[tap] ({xi}, {yi})")
    device.tap(xi, yi)
    ctx.stats.commands_executed += 1


def _cmd_swipe(
    ctx: ExecutionContext,
    x1: Any,
    y1: Any,
    x2: Any,
    y2: Any,
    duration_ms: Any = 300,
) -> None:
    """swipe(x1, y1, x2, y2 [, duration_ms]) — Swipe gesture."""
    device = _require_device(ctx, "swipe")
    xi1, yi1, xi2, yi2, dur = int(x1), int(y1), int(x2), int(y2), int(duration_ms)
    ctx.logger.info(f"[swipe] ({xi1},{yi1}) → ({xi2},{yi2}) in {dur}ms")
    device.swipe(xi1, yi1, xi2, yi2, dur)
    ctx.stats.commands_executed += 1


def _cmd_type(ctx: ExecutionContext, text: Any) -> None:
    """type(text) — Type text into the focused field."""
    device = _require_device(ctx, "type")
    text_str = str(text)
    ctx.logger.info(f"[type] {text_str!r}")
    device.type_text(text_str)
    ctx.stats.commands_executed += 1


def _cmd_wait(ctx: ExecutionContext, seconds: Any) -> None:
    """wait(seconds) — Sleep for N seconds."""
    secs = float(seconds)
    if secs < 0:
        raise CommandError(f"wait() requires a non-negative duration, got {secs}", command="wait")
    ctx.logger.info(f"[wait] {secs:.3f}s")
    time.sleep(secs)
    ctx.stats.commands_executed += 1


def _cmd_screenshot(ctx: ExecutionContext, path: Any = "screenshot.png") -> str:
    """screenshot([path]) — Capture and save a screenshot."""
    device = _require_device(ctx, "screenshot")
    out_path = str(path)
    ctx.logger.info(f"[screenshot] saving to {out_path!r}")
    device.screenshot(out_path)
    ctx.stats.commands_executed += 1
    return out_path


def _cmd_open_app(ctx: ExecutionContext, package: Any) -> None:
    """open_app(package) — Launch an app by package name."""
    device = _require_device(ctx, "open_app")
    pkg = str(package)
    ctx.logger.info(f"[open_app] {pkg!r}")
    device.open_app(pkg)
    ctx.stats.commands_executed += 1


def _cmd_device_info(ctx: ExecutionContext) -> dict[str, str]:
    """device_info() — Print and return device information."""
    device = _require_device(ctx, "device_info")
    info = device.get_info()
    ctx.console.print(
        f"[bold cyan]Device Info[/bold cyan]\n"
        f"  Model:      {info.get('model', 'unknown')}\n"
        f"  Android:    {info.get('version', 'unknown')}\n"
        f"  Resolution: {info.get('resolution', 'unknown')}\n"
        f"  Serial:     {info.get('serial', 'unknown')}"
    )
    ctx.stats.commands_executed += 1
    return info


def _cmd_list_devices(ctx: ExecutionContext) -> list[str]:
    """list_devices() — Print all connected ADB devices."""
    from droidpilot.adb.client import ADBClient

    client = ADBClient()
    devices = client.list_devices()
    if devices:
        ctx.console.print("[bold cyan]Connected devices:[/bold cyan]")
        for dev in devices:
            ctx.console.print(f"  [green]{dev}[/green]")
    else:
        ctx.console.print("[yellow]No devices connected.[/yellow]")
    ctx.stats.commands_executed += 1
    return devices


def _cmd_exists(ctx: ExecutionContext, image_path: Any, threshold: Any = 0.8) -> bool:
    """exists(image_path [, threshold]) — Check if a template image is on screen."""
    device = _require_device(ctx, "exists")
    img_path = str(image_path)
    thresh = float(threshold)

    if not Path(img_path).exists():
        ctx.logger.warning(f"[exists] template file not found: {img_path!r}")
        return False

    ctx.logger.info(f"[exists] checking for {img_path!r} (threshold={thresh})")

    # Capture a fresh screenshot to search.
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        device.screenshot(tmp_path)
        from droidpilot.vision.matcher import TemplateMatcher

        matcher = TemplateMatcher(threshold=thresh)
        found, _loc, _score = matcher.find(screen_path=tmp_path, template_path=img_path)
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass

    ctx.logger.info(f"[exists] {img_path!r} → {'found' if found else 'not found'}")
    ctx.stats.commands_executed += 1
    return found


def _cmd_tap_image(ctx: ExecutionContext, image_path: Any, threshold: Any = 0.8) -> bool:
    """tap_image(image_path [, threshold]) — Tap centre of first template match."""
    device = _require_device(ctx, "tap_image")
    img_path = str(image_path)
    thresh = float(threshold)

    if not Path(img_path).exists():
        ctx.logger.warning(f"[tap_image] template file not found: {img_path!r}")
        return False

    ctx.logger.info(f"[tap_image] searching for {img_path!r} (threshold={thresh})")

    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        device.screenshot(tmp_path)
        from droidpilot.vision.matcher import TemplateMatcher

        matcher = TemplateMatcher(threshold=thresh)
        found, loc, score = matcher.find(screen_path=tmp_path, template_path=img_path)
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass

    if not found or loc is None:
        ctx.logger.info(f"[tap_image] {img_path!r} not found on screen")
        ctx.stats.commands_executed += 1
        return False

    x, y = loc
    ctx.logger.info(f"[tap_image] found at ({x}, {y}), score={score:.3f} — tapping")
    device.tap(x, y)
    ctx.stats.commands_executed += 1
    return True


def _cmd_key_event(ctx: ExecutionContext, keycode: Any) -> None:
    """key_event(keycode) — Send an Android key event by key code."""
    device = _require_device(ctx, "key_event")
    code = int(keycode)
    ctx.logger.info(f"[key_event] keycode={code}")
    device.shell(f"input keyevent {code}")
    ctx.stats.commands_executed += 1


def _cmd_back(ctx: ExecutionContext) -> None:
    """back() — Press the back button (keycode 4)."""
    _cmd_key_event(ctx, 4)


def _cmd_home(ctx: ExecutionContext) -> None:
    """home() — Press the home button (keycode 3)."""
    _cmd_key_event(ctx, 3)


def _cmd_recent(ctx: ExecutionContext) -> None:
    """recent() — Press the recents button (keycode 187)."""
    _cmd_key_event(ctx, 187)


def _cmd_print(ctx: ExecutionContext, *args: Any) -> None:
    """print(value, ...) — Print values to the terminal."""
    parts = [str(a) for a in args]
    ctx.console.print(" ".join(parts))
    ctx.stats.commands_executed += 1


def _cmd_stop(ctx: ExecutionContext) -> None:
    """stop() — Stop execution immediately."""
    ctx.logger.info("[stop] stop() called — halting execution")
    ctx.stop()
    ctx.stats.commands_executed += 1


# ─── Command registry ────────────────────────────────────────────────────────


BUILTIN_COMMANDS: dict[str, Any] = {
    "tap":          _cmd_tap,
    "swipe":        _cmd_swipe,
    "type":         _cmd_type,
    "wait":         _cmd_wait,
    "screenshot":   _cmd_screenshot,
    "open_app":     _cmd_open_app,
    "device_info":  _cmd_device_info,
    "list_devices": _cmd_list_devices,
    "exists":       _cmd_exists,
    "tap_image":    _cmd_tap_image,
    "key_event":    _cmd_key_event,
    "back":         _cmd_back,
    "home":         _cmd_home,
    "recent":       _cmd_recent,
    "print":        _cmd_print,
    "stop":         _cmd_stop,
}


def _register_builtins(ctx: ExecutionContext) -> None:
    """Register all built-in commands into *ctx*."""
    for name, fn in BUILTIN_COMMANDS.items():
        ctx.register_command(name, fn)


# ─── Engine ───────────────────────────────────────────────────────────────────


class ExecutionEngine:
    """Executes a :class:`ProgramNode` AST against a connected device.

    The engine is stateless between calls; all state lives in the
    :class:`ExecutionContext` that is passed to :meth:`execute`.

    Parameters
    ----------
    stop_on_error:
        If ``True`` (default) the engine stops at the first unhandled
        error.  If ``False`` it collects errors and continues.
    """

    def __init__(self, stop_on_error: bool = True) -> None:
        self.stop_on_error = stop_on_error

    # ── Public API ───────────────────────────────────────────────────────────

    def execute(
        self,
        program: ProgramNode,
        context: ExecutionContext,
    ) -> ExecutionResult:
        """Execute *program* against *context* and return an :class:`ExecutionResult`.

        Parameters
        ----------
        program:
            The root AST node to execute.
        context:
            Runtime context providing device access, variable scope, etc.

        Returns
        -------
        ExecutionResult
            Contains success flag, error list, and execution statistics.
        """
        errors: list[ExecutionError] = []

        # Register built-in commands if not already registered.
        for name, fn in BUILTIN_COMMANDS.items():
            if not context.has_command(name):
                context.register_command(name, fn)

        context.start()
        context.logger.info(
            f"[engine] starting execution of {program.source!r} "
            f"({len(program.statements)} top-level statements)"
        )

        try:
            for stmt in program.statements:
                if context.should_stop:
                    context.logger.warning("[engine] execution halted by stop signal")
                    break
                try:
                    stmt.execute(context)
                except (ExecutionError, CommandError, DeviceRequiredError) as exc:
                    context.stats.errors_encountered += 1
                    errors.append(exc)
                    context.logger.error(f"[engine] {exc}")
                    if self.stop_on_error:
                        context.complete(success=False)
                        return ExecutionResult(
                            success=False,
                            errors=errors,
                            stats=context.stats,
                        )
                except NameError as exc:
                    err = ExecutionError(str(exc), cause=exc)
                    context.stats.errors_encountered += 1
                    errors.append(err)
                    context.logger.error(f"[engine] NameError: {exc}")
                    if self.stop_on_error:
                        context.complete(success=False)
                        return ExecutionResult(
                            success=False,
                            errors=errors,
                            stats=context.stats,
                        )
                except TypeError as exc:
                    err = ExecutionError(str(exc), cause=exc)
                    context.stats.errors_encountered += 1
                    errors.append(err)
                    context.logger.error(f"[engine] TypeError: {exc}")
                    if self.stop_on_error:
                        context.complete(success=False)
                        return ExecutionResult(
                            success=False,
                            errors=errors,
                            stats=context.stats,
                        )
                except Exception as exc:
                    tb = traceback.format_exc()
                    err = ExecutionError(
                        f"Unexpected error: {exc}\n{tb}",
                        cause=exc,
                    )
                    context.stats.errors_encountered += 1
                    errors.append(err)
                    context.logger.error(f"[engine] unexpected error: {exc}")
                    if self.stop_on_error:
                        context.complete(success=False)
                        return ExecutionResult(
                            success=False,
                            errors=errors,
                            stats=context.stats,
                        )

        except KeyboardInterrupt:
            context.logger.warning("[engine] interrupted by user (Ctrl+C)")
            context.stop()
            context.complete(success=False)
            return ExecutionResult(
                success=False,
                errors=errors,
                stats=context.stats,
            )

        success = len(errors) == 0 and not context.should_stop
        context.complete(success=success)
        context.logger.info(
            f"[engine] finished: {'OK' if success else 'FAILED'} — {context.stats}"
        )
        return ExecutionResult(
            success=success,
            errors=errors,
            stats=context.stats,
        )

    def execute_source(
        self,
        source: str,
        context: ExecutionContext,
        source_name: str = "<string>",
    ) -> ExecutionResult:
        """Parse *source* and execute it.

        This is a convenience wrapper that combines parsing and execution.

        Parameters
        ----------
        source:
            DroidPilot DSL source text.
        context:
            Runtime context.
        source_name:
            Label for error messages.

        Returns
        -------
        ExecutionResult
        """
        from droidpilot.core.parser import DroidPilotParser, ParseError

        parser = DroidPilotParser()
        try:
            program = parser.parse(source, source_name=source_name)
        except ParseError as exc:
            err = ExecutionError(str(exc), cause=exc)
            context.stats.errors_encountered += 1
            return ExecutionResult(
                success=False,
                errors=[err],
                stats=context.stats,
            )
        return self.execute(program, context)

    def execute_file(
        self,
        path: str,
        context: ExecutionContext,
    ) -> ExecutionResult:
        """Read, parse, and execute the script at *path*.

        Parameters
        ----------
        path:
            File system path to the ``.dp`` script.
        context:
            Runtime context.

        Returns
        -------
        ExecutionResult
        """
        from droidpilot.core.parser import DroidPilotParser, ParseError

        parser = DroidPilotParser()
        try:
            program = parser.parse_file(path)
        except FileNotFoundError as exc:
            err = ExecutionError(str(exc), cause=exc)
            context.stats.errors_encountered += 1
            return ExecutionResult(
                success=False,
                errors=[err],
                stats=context.stats,
            )
        except ParseError as exc:
            err = ExecutionError(str(exc), cause=exc)
            context.stats.errors_encountered += 1
            return ExecutionResult(
                success=False,
                errors=[err],
                stats=context.stats,
            )
        return self.execute(program, context)
