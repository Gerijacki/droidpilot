"""
Tests for droidpilot.core.ast_nodes.

All tests use a mock ExecutionContext so no real ADB device is required.
"""

from __future__ import annotations

import operator
from unittest.mock import MagicMock, patch

import pytest

from droidpilot.core.ast_nodes import (
    AssignNode,
    BinaryOpNode,
    BoolLiteral,
    CommandNode,
    ComparisonNode,
    FloatLiteral,
    IfNode,
    MacroCallNode,
    MacroDefNode,
    NumberLiteral,
    ProgramNode,
    RepeatNode,
    StringLiteral,
    VariableRef,
)
from droidpilot.core.context import ExecutionContext


# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture()
def ctx() -> ExecutionContext:
    """Return a bare ExecutionContext with no device."""
    return ExecutionContext(device=None, verbose=False)


# ─── Literals ─────────────────────────────────────────────────────────────────


class TestNumberLiteral:
    def test_execute_returns_int(self, ctx: ExecutionContext) -> None:
        node = NumberLiteral(value=42)
        assert node.execute(ctx) == 42

    def test_execute_returns_int_type(self, ctx: ExecutionContext) -> None:
        node = NumberLiteral(value=0)
        result = node.execute(ctx)
        assert isinstance(result, int)

    def test_line_default(self) -> None:
        node = NumberLiteral(value=1)
        assert node.line == 0

    def test_line_set(self) -> None:
        node = NumberLiteral(value=1, line=5)
        assert node.line == 5

    def test_repr(self) -> None:
        node = NumberLiteral(value=7, line=3)
        assert "NumberLiteral" in repr(node)
        assert "7" in repr(node)

    def test_negative_number(self, ctx: ExecutionContext) -> None:
        node = NumberLiteral(value=-100)
        assert node.execute(ctx) == -100


class TestFloatLiteral:
    def test_execute_returns_float(self, ctx: ExecutionContext) -> None:
        node = FloatLiteral(value=3.14)
        assert node.execute(ctx) == pytest.approx(3.14)

    def test_returns_float_type(self, ctx: ExecutionContext) -> None:
        node = FloatLiteral(value=0.0)
        assert isinstance(node.execute(ctx), float)

    def test_zero(self, ctx: ExecutionContext) -> None:
        node = FloatLiteral(value=0.0)
        assert node.execute(ctx) == 0.0


class TestStringLiteral:
    def test_execute_returns_str(self, ctx: ExecutionContext) -> None:
        node = StringLiteral(value="hello")
        assert node.execute(ctx) == "hello"

    def test_empty_string(self, ctx: ExecutionContext) -> None:
        node = StringLiteral(value="")
        assert node.execute(ctx) == ""

    def test_unicode(self, ctx: ExecutionContext) -> None:
        node = StringLiteral(value="héllo wörld")
        assert node.execute(ctx) == "héllo wörld"


class TestBoolLiteral:
    def test_true(self, ctx: ExecutionContext) -> None:
        node = BoolLiteral(value=True)
        assert node.execute(ctx) is True

    def test_false(self, ctx: ExecutionContext) -> None:
        node = BoolLiteral(value=False)
        assert node.execute(ctx) is False


# ─── VariableRef ─────────────────────────────────────────────────────────────


class TestVariableRef:
    def test_get_defined_var(self, ctx: ExecutionContext) -> None:
        ctx.set_var("x", 99)
        node = VariableRef(name="x")
        assert node.execute(ctx) == 99

    def test_undefined_raises_name_error(self, ctx: ExecutionContext) -> None:
        node = VariableRef(name="undefined")
        with pytest.raises(NameError, match="undefined"):
            node.execute(ctx)

    def test_string_var(self, ctx: ExecutionContext) -> None:
        ctx.set_var("msg", "hello")
        node = VariableRef(name="msg")
        assert node.execute(ctx) == "hello"

    def test_bool_var(self, ctx: ExecutionContext) -> None:
        ctx.set_var("flag", True)
        node = VariableRef(name="flag")
        assert node.execute(ctx) is True


# ─── BinaryOpNode ─────────────────────────────────────────────────────────────


class TestBinaryOpNode:
    def _num(self, v: int) -> NumberLiteral:
        return NumberLiteral(value=v)

    def test_addition(self, ctx: ExecutionContext) -> None:
        node = BinaryOpNode(op="+", left=self._num(3), right=self._num(4))
        assert node.execute(ctx) == 7

    def test_subtraction(self, ctx: ExecutionContext) -> None:
        node = BinaryOpNode(op="-", left=self._num(10), right=self._num(4))
        assert node.execute(ctx) == 6

    def test_multiplication(self, ctx: ExecutionContext) -> None:
        node = BinaryOpNode(op="*", left=self._num(5), right=self._num(6))
        assert node.execute(ctx) == 30

    def test_division(self, ctx: ExecutionContext) -> None:
        node = BinaryOpNode(op="/", left=self._num(10), right=self._num(4))
        assert node.execute(ctx) == pytest.approx(2.5)

    def test_division_by_zero(self, ctx: ExecutionContext) -> None:
        node = BinaryOpNode(op="/", left=self._num(5), right=self._num(0))
        with pytest.raises(ZeroDivisionError):
            node.execute(ctx)

    def test_unknown_operator(self, ctx: ExecutionContext) -> None:
        node = BinaryOpNode(op="^", left=self._num(2), right=self._num(3))
        with pytest.raises(ValueError, match="Unknown binary operator"):
            node.execute(ctx)

    def test_float_addition(self, ctx: ExecutionContext) -> None:
        left = FloatLiteral(value=1.5)
        right = FloatLiteral(value=2.5)
        node = BinaryOpNode(op="+", left=left, right=right)
        assert node.execute(ctx) == pytest.approx(4.0)

    def test_nested(self, ctx: ExecutionContext) -> None:
        # (2 + 3) * 4 == 20
        inner = BinaryOpNode(op="+", left=self._num(2), right=self._num(3))
        outer = BinaryOpNode(op="*", left=inner, right=self._num(4))
        assert outer.execute(ctx) == 20


# ─── ComparisonNode ───────────────────────────────────────────────────────────


class TestComparisonNode:
    def _num(self, v: int) -> NumberLiteral:
        return NumberLiteral(value=v)

    @pytest.mark.parametrize(
        "op, left, right, expected",
        [
            ("==", 5, 5, True),
            ("==", 5, 6, False),
            ("!=", 5, 6, True),
            ("!=", 5, 5, False),
            ("<", 3, 5, True),
            ("<", 5, 3, False),
            ("<=", 3, 3, True),
            ("<=", 4, 3, False),
            (">", 7, 2, True),
            (">", 2, 7, False),
            (">=", 7, 7, True),
            (">=", 6, 7, False),
        ],
    )
    def test_comparison(
        self,
        ctx: ExecutionContext,
        op: str,
        left: int,
        right: int,
        expected: bool,
    ) -> None:
        node = ComparisonNode(op=op, left=self._num(left), right=self._num(right))
        assert node.execute(ctx) is expected

    def test_unknown_operator(self, ctx: ExecutionContext) -> None:
        node = ComparisonNode(op="<>", left=self._num(1), right=self._num(2))
        with pytest.raises(ValueError, match="Unknown comparison operator"):
            node.execute(ctx)


# ─── AssignNode ───────────────────────────────────────────────────────────────


class TestAssignNode:
    def test_assigns_number(self, ctx: ExecutionContext) -> None:
        value_node = NumberLiteral(value=42)
        node = AssignNode(name="x", value=value_node)
        node.execute(ctx)
        assert ctx.get_var("x") == 42

    def test_assigns_string(self, ctx: ExecutionContext) -> None:
        value_node = StringLiteral(value="hello")
        node = AssignNode(name="msg", value=value_node)
        node.execute(ctx)
        assert ctx.get_var("msg") == "hello"

    def test_overwrites_existing(self, ctx: ExecutionContext) -> None:
        ctx.set_var("x", 1)
        node = AssignNode(name="x", value=NumberLiteral(value=2))
        node.execute(ctx)
        assert ctx.get_var("x") == 2

    def test_returns_none(self, ctx: ExecutionContext) -> None:
        node = AssignNode(name="y", value=NumberLiteral(value=0))
        result = node.execute(ctx)
        assert result is None


# ─── CommandNode ──────────────────────────────────────────────────────────────


class TestCommandNode:
    def test_dispatches_to_registered_command(self, ctx: ExecutionContext) -> None:
        called_with: list = []

        def my_cmd(c: ExecutionContext, x: int, y: int) -> str:
            called_with.extend([x, y])
            return "ok"

        ctx.register_command("my_cmd", my_cmd)
        node = CommandNode(
            name="my_cmd",
            args=[NumberLiteral(value=10), NumberLiteral(value=20)],
        )
        result = node.execute(ctx)
        assert result == "ok"
        assert called_with == [10, 20]

    def test_unregistered_command_raises(self, ctx: ExecutionContext) -> None:
        node = CommandNode(name="unknown_cmd", args=[])
        with pytest.raises(NameError, match="not registered"):
            node.execute(ctx)

    def test_evaluates_args(self, ctx: ExecutionContext) -> None:
        ctx.set_var("x", 55)
        received: list = []

        def recorder(c: ExecutionContext, val: int) -> None:
            received.append(val)

        ctx.register_command("recorder", recorder)
        node = CommandNode(name="recorder", args=[VariableRef(name="x")])
        node.execute(ctx)
        assert received == [55]


# ─── IfNode ───────────────────────────────────────────────────────────────────


class TestIfNode:
    def test_then_branch_when_true(self, ctx: ExecutionContext) -> None:
        executed: list[str] = []

        def action_a(c: ExecutionContext) -> None:
            executed.append("A")

        def action_b(c: ExecutionContext) -> None:
            executed.append("B")

        ctx.register_command("action_a", action_a)
        ctx.register_command("action_b", action_b)

        node = IfNode(
            condition=BoolLiteral(value=True),
            then_body=[CommandNode(name="action_a", args=[])],
            else_body=[CommandNode(name="action_b", args=[])],
        )
        node.execute(ctx)
        assert executed == ["A"]

    def test_else_branch_when_false(self, ctx: ExecutionContext) -> None:
        executed: list[str] = []

        def action_a(c: ExecutionContext) -> None:
            executed.append("A")

        def action_b(c: ExecutionContext) -> None:
            executed.append("B")

        ctx.register_command("action_a", action_a)
        ctx.register_command("action_b", action_b)

        node = IfNode(
            condition=BoolLiteral(value=False),
            then_body=[CommandNode(name="action_a", args=[])],
            else_body=[CommandNode(name="action_b", args=[])],
        )
        node.execute(ctx)
        assert executed == ["B"]

    def test_no_else_when_false(self, ctx: ExecutionContext) -> None:
        executed: list[str] = []

        def action(c: ExecutionContext) -> None:
            executed.append("X")

        ctx.register_command("action", action)
        node = IfNode(
            condition=BoolLiteral(value=False),
            then_body=[CommandNode(name="action", args=[])],
            else_body=[],
        )
        node.execute(ctx)
        assert executed == []

    def test_returns_none(self, ctx: ExecutionContext) -> None:
        node = IfNode(
            condition=BoolLiteral(value=True),
            then_body=[],
            else_body=[],
        )
        assert node.execute(ctx) is None


# ─── RepeatNode ───────────────────────────────────────────────────────────────


class TestRepeatNode:
    def test_executes_n_times(self, ctx: ExecutionContext) -> None:
        counter: list[int] = []

        def tick(c: ExecutionContext) -> None:
            counter.append(1)

        ctx.register_command("tick", tick)
        node = RepeatNode(
            count=NumberLiteral(value=5),
            body=[CommandNode(name="tick", args=[])],
        )
        node.execute(ctx)
        assert len(counter) == 5

    def test_zero_iterations(self, ctx: ExecutionContext) -> None:
        counter: list[int] = []

        def tick(c: ExecutionContext) -> None:
            counter.append(1)

        ctx.register_command("tick", tick)
        node = RepeatNode(count=NumberLiteral(value=0), body=[CommandNode(name="tick", args=[])])
        node.execute(ctx)
        assert counter == []

    def test_negative_count_raises(self, ctx: ExecutionContext) -> None:
        node = RepeatNode(count=NumberLiteral(value=-1), body=[])
        with pytest.raises(ValueError, match="non-negative"):
            node.execute(ctx)

    def test_non_number_count_raises(self, ctx: ExecutionContext) -> None:
        node = RepeatNode(count=StringLiteral(value="five"), body=[])
        with pytest.raises(TypeError):
            node.execute(ctx)

    def test_loop_index_var(self, ctx: ExecutionContext) -> None:
        indices: list[int] = []

        def capture(c: ExecutionContext) -> None:
            indices.append(c.get_var("_loop_index"))

        ctx.register_command("capture", capture)
        node = RepeatNode(
            count=NumberLiteral(value=3),
            body=[CommandNode(name="capture", args=[])],
        )
        node.execute(ctx)
        assert indices == [0, 1, 2]


# ─── MacroDefNode / MacroCallNode ─────────────────────────────────────────────


class TestMacroDef:
    def test_registers_macro(self, ctx: ExecutionContext) -> None:
        body_cmd = CommandNode(name="dummy", args=[])
        macro = MacroDefNode(name="my_macro", params=[], body=[body_cmd])
        macro.execute(ctx)
        assert ctx.has_macro("my_macro")

    def test_macro_def_returns_none(self, ctx: ExecutionContext) -> None:
        macro = MacroDefNode(name="m", params=[], body=[])
        result = macro.execute(ctx)
        assert result is None


class TestMacroCall:
    def test_calls_macro_body(self, ctx: ExecutionContext) -> None:
        executed: list[str] = []

        def my_action(c: ExecutionContext) -> None:
            executed.append("ran")

        ctx.register_command("my_action", my_action)

        macro_def = MacroDefNode(
            name="do_thing",
            params=[],
            body=[CommandNode(name="my_action", args=[])],
        )
        macro_def.execute(ctx)  # register

        call = MacroCallNode(name="do_thing", args=[])
        call.execute(ctx)
        assert executed == ["ran"]

    def test_passes_args_as_vars(self, ctx: ExecutionContext) -> None:
        received: list = []

        def grabber(c: ExecutionContext, val: int) -> None:
            received.append(val)

        ctx.register_command("grabber", grabber)

        macro_def = MacroDefNode(
            name="pass_arg",
            params=["n"],
            body=[CommandNode(name="grabber", args=[VariableRef(name="n")])],
        )
        macro_def.execute(ctx)

        call = MacroCallNode(name="pass_arg", args=[NumberLiteral(value=77)])
        call.execute(ctx)
        assert received == [77]

    def test_wrong_arg_count_raises(self, ctx: ExecutionContext) -> None:
        macro_def = MacroDefNode(name="needs_one", params=["x"], body=[])
        macro_def.execute(ctx)

        call = MacroCallNode(name="needs_one", args=[])
        with pytest.raises(TypeError, match="expects 1"):
            call.execute(ctx)

    def test_undefined_macro_raises(self, ctx: ExecutionContext) -> None:
        call = MacroCallNode(name="ghost", args=[])
        with pytest.raises(NameError, match="not defined"):
            call.execute(ctx)


# ─── ProgramNode ──────────────────────────────────────────────────────────────


class TestProgramNode:
    def test_executes_all_statements(self, ctx: ExecutionContext) -> None:
        log: list[str] = []

        def cmd_a(c: ExecutionContext) -> None:
            log.append("A")

        def cmd_b(c: ExecutionContext) -> None:
            log.append("B")

        ctx.register_command("cmd_a", cmd_a)
        ctx.register_command("cmd_b", cmd_b)

        program = ProgramNode(
            statements=[
                CommandNode(name="cmd_a", args=[]),
                CommandNode(name="cmd_b", args=[]),
            ]
        )
        program.execute(ctx)
        assert log == ["A", "B"]

    def test_stops_when_context_stopped(self, ctx: ExecutionContext) -> None:
        log: list[str] = []

        def cmd_a(c: ExecutionContext) -> None:
            log.append("A")
            c.stop()

        def cmd_b(c: ExecutionContext) -> None:
            log.append("B")

        ctx.register_command("cmd_a", cmd_a)
        ctx.register_command("cmd_b", cmd_b)
        ctx.start()  # transition to RUNNING

        program = ProgramNode(
            statements=[
                CommandNode(name="cmd_a", args=[]),
                CommandNode(name="cmd_b", args=[]),
            ]
        )
        program.execute(ctx)
        # B should not have run because stop() was called.
        assert "B" not in log

    def test_pretty_repr(self) -> None:
        program = ProgramNode(statements=[], source="test.dp")
        text = program.pretty()
        assert "ProgramNode" in text
        assert "test.dp" in text

    def test_repr_contains_source(self) -> None:
        program = ProgramNode(statements=[], source="foo.dp")
        assert "foo.dp" in repr(program)
