"""
Tests for droidpilot.core.engine (ExecutionEngine).

All tests use a mock device or no device, so no physical ADB connection
is required.
"""

from __future__ import annotations

import pytest

from droidpilot.core.ast_nodes import (
    CommandNode,
    NumberLiteral,
    ProgramNode,
    StringLiteral,
)
from droidpilot.core.context import ExecutionContext, ExecutionState
from droidpilot.core.engine import (
    BUILTIN_COMMANDS,
    CommandError,
    ExecutionEngine,
    ExecutionError,
    ExecutionResult,
)

# ─── Helpers ──────────────────────────────────────────────────────────────────


def _make_ctx(device=None, verbose=False) -> ExecutionContext:
    return ExecutionContext(device=device, verbose=verbose)


def _make_program(*statements) -> ProgramNode:
    return ProgramNode(statements=list(statements))


def _cmd(name: str, *args) -> CommandNode:
    """Shorthand for creating a CommandNode."""
    arg_nodes = [
        NumberLiteral(value=a) if isinstance(a, int) else StringLiteral(value=a) for a in args
    ]
    return CommandNode(name=name, args=arg_nodes)


# ─── ExecutionResult ──────────────────────────────────────────────────────────


class TestExecutionResult:
    def test_truthy_on_success(self) -> None:
        result = ExecutionResult(success=True)
        assert bool(result) is True

    def test_falsy_on_failure(self) -> None:
        result = ExecutionResult(success=False)
        assert bool(result) is False

    def test_str_ok(self) -> None:
        result = ExecutionResult(success=True)
        assert "OK" in str(result)

    def test_str_failed(self) -> None:
        err = ExecutionError("something broke")
        result = ExecutionResult(success=False, errors=[err])
        assert "FAILED" in str(result)
        assert "1" in str(result)


# ─── Engine basic execution ───────────────────────────────────────────────────


class TestEngineBasicExecution:
    def test_empty_program_succeeds(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        prog = _make_program()
        result = engine.execute(prog, ctx)
        assert result.success is True
        assert result.errors == []

    def test_registers_builtin_commands(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        engine.execute(_make_program(), ctx)
        for name in BUILTIN_COMMANDS:
            assert ctx.has_command(name), f"missing builtin: {name}"

    def test_state_becomes_completed_on_success(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        engine.execute(_make_program(), ctx)
        assert ctx.state == ExecutionState.COMPLETED

    def test_state_becomes_errored_on_failure(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        prog = _make_program(_cmd("nonexistent_cmd"))
        result = engine.execute(prog, ctx)
        assert result.success is False
        assert ctx.state == ExecutionState.ERRORED

    def test_custom_command_is_called(self) -> None:
        calls: list[list] = []

        def my_cmd(c: ExecutionContext, x: int, y: int) -> None:
            calls.append([x, y])

        engine = ExecutionEngine()
        ctx = _make_ctx()
        ctx.register_command("my_cmd", my_cmd)
        prog = _make_program(CommandNode(name="my_cmd", args=[NumberLiteral(5), NumberLiteral(10)]))
        result = engine.execute(prog, ctx)
        assert result.success is True
        assert calls == [[5, 10]]

    def test_stats_commands_executed(self) -> None:
        # stats.commands_executed is incremented by built-in commands only.
        # Custom user commands don't auto-increment unless they do so explicitly.
        # Use the built-in "wait" command (which calls _cmd_wait → increments counter).
        engine = ExecutionEngine()
        ctx = _make_ctx()
        prog = _make_program(
            CommandNode(name="wait", args=[NumberLiteral(0)]),
            CommandNode(name="wait", args=[NumberLiteral(0)]),
            CommandNode(name="wait", args=[NumberLiteral(0)]),
        )
        result = engine.execute(prog, ctx)
        assert result.stats.commands_executed == 3


# ─── Error handling ───────────────────────────────────────────────────────────


class TestEngineErrorHandling:
    def test_stop_on_first_error_by_default(self) -> None:
        order: list[str] = []

        def fail_cmd(c: ExecutionContext) -> None:
            order.append("fail")
            raise CommandError("boom")

        def ok_cmd(c: ExecutionContext) -> None:
            order.append("ok")

        engine = ExecutionEngine(stop_on_error=True)
        ctx = _make_ctx()
        ctx.register_command("fail_cmd", fail_cmd)
        ctx.register_command("ok_cmd", ok_cmd)
        prog = _make_program(_cmd("fail_cmd"), _cmd("ok_cmd"))
        result = engine.execute(prog, ctx)

        assert result.success is False
        assert "fail" in order
        assert "ok" not in order  # stopped after fail

    def test_continue_on_error_collects_all_errors(self) -> None:
        def bad(c: ExecutionContext) -> None:
            raise CommandError("error")

        engine = ExecutionEngine(stop_on_error=False)
        ctx = _make_ctx()
        ctx.register_command("bad", bad)
        prog = _make_program(_cmd("bad"), _cmd("bad"), _cmd("bad"))
        result = engine.execute(prog, ctx)

        assert result.success is False
        assert len(result.errors) == 3

    def test_name_error_for_unknown_command(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        prog = _make_program(_cmd("ghost_cmd"))
        result = engine.execute(prog, ctx)
        assert result.success is False
        assert len(result.errors) == 1

    def test_device_required_error_without_device(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx(device=None)
        prog = _make_program(
            CommandNode(name="tap", args=[NumberLiteral(540), NumberLiteral(1200)])
        )
        result = engine.execute(prog, ctx)
        assert result.success is False

    def test_execute_source_parse_failure_returns_error(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        result = engine.execute_source("@@@invalid@@@\n", ctx)
        assert result.success is False
        assert len(result.errors) == 1

    def test_execute_file_not_found(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        result = engine.execute_file("/tmp/__nonexistent__.dp", ctx)
        assert result.success is False

    def test_stats_errors_encountered(self) -> None:
        def bad(c: ExecutionContext) -> None:
            raise CommandError("oops")

        engine = ExecutionEngine(stop_on_error=False)
        ctx = _make_ctx()
        ctx.register_command("bad", bad)
        prog = _make_program(_cmd("bad"), _cmd("bad"))
        result = engine.execute(prog, ctx)
        assert result.stats.errors_encountered == 2


# ─── Wait command ─────────────────────────────────────────────────────────────


class TestWaitCommand:
    def test_wait_sleeps(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        prog = _make_program(CommandNode(name="wait", args=[NumberLiteral(0)]))
        result = engine.execute(prog, ctx)
        assert result.success is True

    def test_wait_negative_raises(self) -> None:
        from droidpilot.core.engine import _cmd_wait

        ctx = _make_ctx()
        with pytest.raises(CommandError):
            _cmd_wait(ctx, -1)


# ─── Print command ────────────────────────────────────────────────────────────


class TestPrintCommand:
    def test_print_does_not_raise(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        prog = _make_program(CommandNode(name="print", args=[StringLiteral("hello world")]))
        result = engine.execute(prog, ctx)
        assert result.success is True


# ─── Stop command ─────────────────────────────────────────────────────────────


class TestStopCommand:
    def test_stop_halts_subsequent_commands(self) -> None:
        order: list[str] = []

        def after_stop(c: ExecutionContext) -> None:
            order.append("after")

        engine = ExecutionEngine()
        ctx = _make_ctx()
        ctx.register_command("after_stop", after_stop)
        prog = _make_program(
            CommandNode(name="stop", args=[]),
            _cmd("after_stop"),
        )
        engine.execute(prog, ctx)
        assert "after" not in order


# ─── execute_source / execute_file ────────────────────────────────────────────


class TestEngineConvenienceMethods:
    def test_execute_source_success(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        result = engine.execute_source("wait(0)\n", ctx)
        assert result.success is True

    def test_execute_source_with_source_name(self) -> None:
        engine = ExecutionEngine()
        ctx = _make_ctx()
        result = engine.execute_source("wait(0)\n", ctx, source_name="test.dp")
        assert result.success is True

    def test_execute_file_success(self, tmp_path) -> None:
        script = tmp_path / "test.dp"
        script.write_text("wait(0)\n", encoding="utf-8")
        engine = ExecutionEngine()
        ctx = _make_ctx()
        result = engine.execute_file(str(script), ctx)
        assert result.success is True
