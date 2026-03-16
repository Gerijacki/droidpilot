"""
ExecutionContext — runtime state for a DroidPilot script execution.

The context object is the central hub that the execution engine and all AST
nodes interact with.  It holds:

- A reference to the connected ADB device.
- The current variable scope (a stack of dicts).
- The macro registry (name → MacroDefNode).
- The command registry (name → callable).
- Execution control signals (stop, pause).
- Execution statistics.
- A Rich logger for structured terminal output.
"""

from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Generator
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TYPE_CHECKING, Any, Callable

from rich.console import Console
from rich.logging import RichHandler

if TYPE_CHECKING:
    from droidpilot.adb.device import ADBDevice
    from droidpilot.core.ast_nodes import MacroDefNode


# ─── Execution state ─────────────────────────────────────────────────────────


class ExecutionState(Enum):
    """Lifecycle states of a script execution."""

    IDLE = auto()
    RUNNING = auto()
    PAUSED = auto()
    STOPPED = auto()
    COMPLETED = auto()
    ERRORED = auto()


# ─── Statistics ──────────────────────────────────────────────────────────────


@dataclass
class ExecutionStats:
    """Counters and timing accumulated during a script run."""

    commands_executed: int = 0
    macro_calls: int = 0
    errors_encountered: int = 0
    start_time: float = field(default_factory=time.monotonic)
    end_time: float | None = None

    @property
    def elapsed(self) -> float:
        """Elapsed time in seconds since execution started."""
        if self.end_time is not None:
            return self.end_time - self.start_time
        return time.monotonic() - self.start_time

    def finish(self) -> None:
        """Mark the execution as finished and record the end time."""
        self.end_time = time.monotonic()

    def __str__(self) -> str:
        return (
            f"ExecutionStats("
            f"commands={self.commands_executed}, "
            f"macro_calls={self.macro_calls}, "
            f"errors={self.errors_encountered}, "
            f"elapsed={self.elapsed:.3f}s)"
        )


# ─── Context ─────────────────────────────────────────────────────────────────


class ExecutionContext:
    """Central runtime state for a single DroidPilot script execution.

    Parameters
    ----------
    device:
        The connected ADB device to send commands to.  May be ``None``
        for dry-run / validation-only execution.
    verbose:
        If ``True`` the logger will emit DEBUG-level messages.
    console:
        A :class:`rich.console.Console` instance to use for output.
        If ``None`` a default console is created.
    """

    def __init__(
        self,
        device: "ADBDevice | None" = None,
        verbose: bool = False,
        console: Console | None = None,
    ) -> None:
        self.device = device
        self.verbose = verbose

        # ── Console / logging ──────────────────────────────────────────────
        self._console = console or Console()
        _log_level = logging.DEBUG if verbose else logging.INFO
        logging.basicConfig(
            level=_log_level,
            handlers=[
                RichHandler(
                    console=self._console,
                    show_time=True,
                    rich_tracebacks=True,
                    markup=True,
                )
            ],
        )
        self.logger = logging.getLogger("droidpilot.runtime")
        self.logger.setLevel(_log_level)

        # ── Variable scope stack ───────────────────────────────────────────
        # Index 0 is the global scope; higher indices are macro call frames.
        self._var_stack: list[dict[str, Any]] = [{}]

        # ── Registries ────────────────────────────────────────────────────
        self._macros: dict[str, "MacroDefNode"] = {}
        self._commands: dict[str, Callable[..., Any]] = {}

        # ── Execution state ────────────────────────────────────────────────
        self._state: ExecutionState = ExecutionState.IDLE
        self.stats: ExecutionStats = ExecutionStats()

    # ── State control ────────────────────────────────────────────────────────

    @property
    def state(self) -> ExecutionState:
        """Current execution lifecycle state."""
        return self._state

    def start(self) -> None:
        """Transition to RUNNING state and reset statistics."""
        self._state = ExecutionState.RUNNING
        self.stats = ExecutionStats()

    def stop(self) -> None:
        """Signal the execution to stop after the current statement."""
        self.logger.info("[context] stop signal received")
        self._state = ExecutionState.STOPPED

    def pause(self) -> None:
        """Pause execution (the engine polls ``should_stop``)."""
        self.logger.info("[context] pause signal received")
        self._state = ExecutionState.PAUSED

    def resume(self) -> None:
        """Resume a paused execution."""
        if self._state == ExecutionState.PAUSED:
            self.logger.info("[context] resuming execution")
            self._state = ExecutionState.RUNNING

    def complete(self, success: bool = True) -> None:
        """Mark execution as completed."""
        self._state = ExecutionState.COMPLETED if success else ExecutionState.ERRORED
        self.stats.finish()

    @property
    def should_stop(self) -> bool:
        """``True`` if execution has been signalled to stop."""
        return self._state in (ExecutionState.STOPPED, ExecutionState.ERRORED)

    @property
    def is_running(self) -> bool:
        """``True`` if execution is currently active."""
        return self._state == ExecutionState.RUNNING

    # ── Variable scope ───────────────────────────────────────────────────────

    def set_var(self, name: str, value: Any) -> None:
        """Set *name* to *value* in the innermost scope frame.

        Parameters
        ----------
        name:
            Variable name.
        value:
            Value to store.  Any Python object is accepted.
        """
        self._var_stack[-1][name] = value

    def set_global_var(self, name: str, value: Any) -> None:
        """Set *name* to *value* in the global (outermost) scope frame."""
        self._var_stack[0][name] = value

    def get_var(self, name: str) -> Any:
        """Retrieve *name* from the nearest enclosing scope.

        Scopes are searched from innermost (most recently pushed) outward,
        matching Python-like variable lookup.

        Raises
        ------
        NameError
            If the variable has not been defined in any scope.
        """
        for frame in reversed(self._var_stack):
            if name in frame:
                return frame[name]
        raise NameError(f"Variable {name!r} is not defined")

    def has_var(self, name: str) -> bool:
        """Return ``True`` if *name* is defined in any scope."""
        return any(name in frame for frame in self._var_stack)

    def _push_scope(self, initial: dict[str, Any] | None = None) -> None:
        """Push a new variable scope frame."""
        self._var_stack.append(dict(initial or {}))

    def _pop_scope(self) -> dict[str, Any]:
        """Pop and return the innermost scope frame.

        The global scope (index 0) cannot be popped.
        """
        if len(self._var_stack) <= 1:
            raise RuntimeError("Cannot pop the global variable scope")
        return self._var_stack.pop()

    @contextlib.contextmanager
    def scoped_vars(self, initial: dict[str, Any] | None = None) -> Generator[None, None, None]:
        """Context manager that pushes a new scope and pops it on exit.

        Parameters
        ----------
        initial:
            Optional mapping of name → value to pre-populate the new scope.
        """
        self._push_scope(initial)
        try:
            yield
        finally:
            self._pop_scope()

    @property
    def variables(self) -> dict[str, Any]:
        """Flat view of all variables visible from the current scope.

        Outer-scope values are overridden by inner-scope values with the
        same name, matching Python's variable shadowing rules.
        """
        merged: dict[str, Any] = {}
        for frame in self._var_stack:
            merged.update(frame)
        return merged

    # ── Macro registry ───────────────────────────────────────────────────────

    def define_macro(self, name: str, node: "MacroDefNode") -> None:
        """Register a macro definition.

        Parameters
        ----------
        name:
            The macro name.
        node:
            The :class:`~droidpilot.core.ast_nodes.MacroDefNode` to store.
        """
        if name in self._macros:
            self.logger.warning(f"[context] redefining macro {name!r}")
        self._macros[name] = node

    def get_macro(self, name: str) -> "MacroDefNode":
        """Retrieve a registered macro by name.

        Raises
        ------
        NameError
            If no macro with *name* has been defined.
        """
        if name not in self._macros:
            raise NameError(f"Macro {name!r} is not defined")
        return self._macros[name]

    def has_macro(self, name: str) -> bool:
        """Return ``True`` if a macro named *name* is registered."""
        return name in self._macros

    @property
    def macros(self) -> dict[str, "MacroDefNode"]:
        """Read-only view of registered macros."""
        return dict(self._macros)

    # ── Command registry ─────────────────────────────────────────────────────

    def register_command(self, name: str, fn: Callable[..., Any]) -> None:
        """Register *fn* as the handler for command *name*.

        The callable signature must be::

            def my_command(ctx: ExecutionContext, *args) -> Any: ...

        Parameters
        ----------
        name:
            The command name as used in DSL scripts.
        fn:
            Callable that implements the command.
        """
        if name in self._commands:
            self.logger.warning(f"[context] overriding command {name!r}")
        self._commands[name] = fn

    def get_command(self, name: str) -> Callable[..., Any]:
        """Retrieve a registered command handler by name.

        Raises
        ------
        NameError
            If no command with *name* has been registered.
        """
        if name not in self._commands:
            raise NameError(f"Command {name!r} is not registered")
        return self._commands[name]

    def has_command(self, name: str) -> bool:
        """Return ``True`` if a command named *name* is registered."""
        return name in self._commands

    @property
    def commands(self) -> dict[str, Callable[..., Any]]:
        """Read-only view of registered command handlers."""
        return dict(self._commands)

    # ── Convenience ──────────────────────────────────────────────────────────

    @property
    def console(self) -> Console:
        """The Rich console used for terminal output."""
        return self._console

    def print(self, *args: Any, **kwargs: Any) -> None:
        """Forward to ``console.print`` for rich-formatted output."""
        self._console.print(*args, **kwargs)

    def __repr__(self) -> str:
        return (
            f"ExecutionContext("
            f"state={self._state.name}, "
            f"vars={len(self.variables)}, "
            f"macros={len(self._macros)}, "
            f"commands={len(self._commands)})"
        )
