"""
Tests for droidpilot.core.parser (DroidPilotParser).

Verifies that the Lark-based DSL parser produces the correct AST nodes
for a variety of valid and invalid inputs.
"""

from __future__ import annotations

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
from droidpilot.core.parser import DroidPilotParser, ParseError

# ─── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def parser() -> DroidPilotParser:
    """Return a module-scoped parser instance (reuse Lark object)."""
    return DroidPilotParser()


def parse(source: str) -> ProgramNode:
    """Parse *source* with a fresh parser and return the ProgramNode."""
    return DroidPilotParser().parse(source)


# ─── ProgramNode structure ────────────────────────────────────────────────────


class TestProgramNode:
    def test_empty_source_produces_empty_program(self, parser: DroidPilotParser) -> None:
        prog = parser.parse("")
        assert isinstance(prog, ProgramNode)
        assert prog.statements == []

    def test_source_name_is_preserved(self, parser: DroidPilotParser) -> None:
        prog = parser.parse("wait(1)\n", source_name="my_script.dp")
        assert prog.source == "my_script.dp"

    def test_default_source_name(self, parser: DroidPilotParser) -> None:
        prog = parser.parse("")
        assert prog.source == "<string>"

    def test_single_statement(self, parser: DroidPilotParser) -> None:
        prog = parser.parse("wait(1)\n")
        assert len(prog.statements) == 1

    def test_multiple_statements(self, parser: DroidPilotParser) -> None:
        prog = parser.parse("wait(1)\nwait(2)\nwait(3)\n")
        assert len(prog.statements) == 3

    def test_comment_only_source(self, parser: DroidPilotParser) -> None:
        prog = parser.parse("# this is a comment\n")
        assert prog.statements == []


# ─── Commands ─────────────────────────────────────────────────────────────────


class TestCommandParsing:
    def test_no_args(self) -> None:
        prog = parse("home()\n")
        assert len(prog.statements) == 1
        cmd = prog.statements[0]
        assert isinstance(cmd, (CommandNode, MacroCallNode))
        assert cmd.name == "home"
        assert cmd.args == []

    def test_single_int_arg(self) -> None:
        prog = parse("wait(5)\n")
        cmd = prog.statements[0]
        assert isinstance(cmd, (CommandNode, MacroCallNode))
        assert len(cmd.args) == 1
        assert isinstance(cmd.args[0], NumberLiteral)
        assert cmd.args[0].value == 5

    def test_multiple_int_args(self) -> None:
        prog = parse("tap(540, 1200)\n")
        cmd = prog.statements[0]
        assert isinstance(cmd, (CommandNode, MacroCallNode))
        assert len(cmd.args) == 2
        arg_values = [a.execute(None) for a in cmd.args]  # type: ignore[arg-type]
        assert arg_values == [540, 1200]

    def test_string_arg(self) -> None:
        prog = parse('open_app("com.instagram.android")\n')
        cmd = prog.statements[0]
        assert isinstance(cmd, (CommandNode, MacroCallNode))
        assert len(cmd.args) == 1
        assert isinstance(cmd.args[0], StringLiteral)
        assert cmd.args[0].value == "com.instagram.android"

    def test_float_arg(self) -> None:
        prog = parse("wait(1.5)\n")
        cmd = prog.statements[0]
        arg = cmd.args[0]
        assert isinstance(arg, FloatLiteral)
        assert arg.value == pytest.approx(1.5)

    def test_bool_true_arg(self) -> None:
        prog = parse("some_cmd(true)\n")
        cmd = prog.statements[0]
        assert isinstance(cmd.args[0], BoolLiteral)
        assert cmd.args[0].value is True

    def test_bool_false_arg(self) -> None:
        prog = parse("some_cmd(false)\n")
        cmd = prog.statements[0]
        assert isinstance(cmd.args[0], BoolLiteral)
        assert cmd.args[0].value is False

    def test_swipe_five_args(self) -> None:
        prog = parse("swipe(500, 1500, 500, 500, 300)\n")
        cmd = prog.statements[0]
        assert len(cmd.args) == 5

    def test_screenshot_string_arg(self) -> None:
        prog = parse('screenshot("feed.png")\n')
        cmd = prog.statements[0]
        assert cmd.args[0].value == "feed.png"


# ─── Assignments ──────────────────────────────────────────────────────────────


class TestAssignmentParsing:
    def test_integer_assignment(self) -> None:
        prog = parse("x = 42\n")
        node = prog.statements[0]
        assert isinstance(node, AssignNode)
        assert node.name == "x"
        assert isinstance(node.value, NumberLiteral)
        assert node.value.value == 42

    def test_string_assignment(self) -> None:
        prog = parse('msg = "hello"\n')
        node = prog.statements[0]
        assert isinstance(node, AssignNode)
        assert node.name == "msg"
        assert isinstance(node.value, StringLiteral)
        assert node.value.value == "hello"

    def test_float_assignment(self) -> None:
        prog = parse("delay = 0.5\n")
        node = prog.statements[0]
        assert isinstance(node, AssignNode)
        assert isinstance(node.value, FloatLiteral)

    def test_bool_assignment(self) -> None:
        prog = parse("flag = true\n")
        node = prog.statements[0]
        assert isinstance(node, AssignNode)
        assert isinstance(node.value, BoolLiteral)
        assert node.value.value is True

    def test_variable_ref_assignment(self) -> None:
        prog = parse("y = x\n")
        node = prog.statements[0]
        assert isinstance(node, AssignNode)
        assert isinstance(node.value, VariableRef)
        assert node.value.name == "x"

    def test_arithmetic_assignment(self) -> None:
        prog = parse("z = 2 + 3\n")
        node = prog.statements[0]
        assert isinstance(node, AssignNode)
        assert isinstance(node.value, BinaryOpNode)
        assert node.value.op == "+"


# ─── Arithmetic expressions ───────────────────────────────────────────────────


class TestArithmeticParsing:
    def test_addition(self) -> None:
        prog = parse("x = 1 + 2\n")
        node = prog.statements[0]
        assert isinstance(node.value, BinaryOpNode)
        assert node.value.op == "+"

    def test_subtraction(self) -> None:
        prog = parse("x = 10 - 3\n")
        node = prog.statements[0]
        assert node.value.op == "-"

    def test_multiplication(self) -> None:
        prog = parse("x = 4 * 5\n")
        node = prog.statements[0]
        assert node.value.op == "*"

    def test_division(self) -> None:
        prog = parse("x = 10 / 4\n")
        node = prog.statements[0]
        assert node.value.op == "/"


# ─── Control flow ─────────────────────────────────────────────────────────────


class TestRepeatParsing:
    def test_basic_repeat(self) -> None:
        src = "repeat 5:\n    wait(1)\n"
        prog = parse(src)
        node = prog.statements[0]
        assert isinstance(node, RepeatNode)
        assert isinstance(node.count, NumberLiteral)
        assert node.count.value == 5
        assert len(node.body) == 1

    def test_repeat_multiple_body_statements(self) -> None:
        src = "repeat 3:\n    tap(540, 1200)\n    wait(0.5)\n"
        prog = parse(src)
        node = prog.statements[0]
        assert isinstance(node, RepeatNode)
        assert len(node.body) == 2


class TestIfParsing:
    def test_if_without_else(self) -> None:
        src = "if x:\n    wait(1)\n"
        prog = parse(src)
        node = prog.statements[0]
        assert isinstance(node, IfNode)
        assert len(node.then_body) == 1
        assert node.else_body == []

    def test_if_with_else(self) -> None:
        src = "if x:\n    wait(1)\nelse:\n    wait(2)\n"
        prog = parse(src)
        node = prog.statements[0]
        assert isinstance(node, IfNode)
        assert len(node.then_body) == 1
        assert len(node.else_body) == 1

    def test_comparison_condition(self) -> None:
        src = "if x == 5:\n    wait(1)\n"
        prog = parse(src)
        node = prog.statements[0]
        assert isinstance(node, IfNode)
        assert isinstance(node.condition, ComparisonNode)
        assert node.condition.op == "=="

    def test_all_comparison_operators(self) -> None:
        for op in ("==", "!=", "<", "<=", ">", ">="):
            src = f"if x {op} 5:\n    wait(1)\n"
            prog = parse(src)
            node = prog.statements[0]
            assert isinstance(node.condition, ComparisonNode)
            assert node.condition.op == op


# ─── Macros ───────────────────────────────────────────────────────────────────


class TestMacroParsing:
    def test_macro_no_params(self) -> None:
        src = "macro do_thing():\n    wait(1)\n"
        prog = parse(src)
        node = prog.statements[0]
        assert isinstance(node, MacroDefNode)
        assert node.name == "do_thing"
        assert node.params == []
        assert len(node.body) == 1

    def test_macro_with_params(self) -> None:
        src = "macro swipe_up(cx, cy):\n    swipe(cx, cy, cx, 400)\n"
        prog = parse(src)
        node = prog.statements[0]
        assert isinstance(node, MacroDefNode)
        assert node.params == ["cx", "cy"]

    def test_macro_body_multiple_statements(self) -> None:
        src = "macro complex():\n    wait(1)\n    tap(540, 1200)\n    wait(0.5)\n"
        prog = parse(src)
        node = prog.statements[0]
        assert isinstance(node, MacroDefNode)
        assert len(node.body) == 3

    def test_macro_call_no_args(self) -> None:
        src = "macro do_it():\n    wait(1)\ndo_it()\n"
        prog = parse(src)
        # Second statement is the macro call.
        call = prog.statements[1]
        assert isinstance(call, (MacroCallNode, CommandNode))
        assert call.name == "do_it"


# ─── ParseError ───────────────────────────────────────────────────────────────


class TestParseErrors:
    def test_unclosed_paren(self, parser: DroidPilotParser) -> None:
        with pytest.raises(ParseError):
            parser.parse("tap(540, 1200\n")

    def test_bad_indent(self, parser: DroidPilotParser) -> None:
        # A body that de-indents before it starts should fail.
        with pytest.raises(ParseError):
            parser.parse("if x:\nwait(1)\n")

    def test_parse_error_has_message(self, parser: DroidPilotParser) -> None:
        with pytest.raises(ParseError) as exc_info:
            parser.parse("@@@invalid@@@\n")
        assert exc_info.value.message

    def test_validate_returns_errors(self, parser: DroidPilotParser) -> None:
        errors = parser.validate("@@@invalid@@@\n")
        assert len(errors) > 0

    def test_validate_returns_empty_on_valid(self, parser: DroidPilotParser) -> None:
        errors = parser.validate("tap(540, 1200)\n")
        assert errors == []

    def test_parse_file_not_found(self, parser: DroidPilotParser) -> None:
        with pytest.raises(FileNotFoundError):
            parser.parse_file("/tmp/__nonexistent_droidpilot_script__.dp")


# ─── Escape sequences in strings ─────────────────────────────────────────────


class TestStringEscapes:
    def test_newline_escape(self) -> None:
        prog = parse('x = "hello\\nworld"\n')
        node = prog.statements[0]
        assert "\n" in node.value.value

    def test_tab_escape(self) -> None:
        prog = parse('x = "col1\\tcol2"\n')
        node = prog.statements[0]
        assert "\t" in node.value.value
