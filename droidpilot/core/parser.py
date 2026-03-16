"""
DroidPilot DSL Parser.

Converts DroidPilot source text into an AST by:

1. Running the Lark LALR(1) parser with the bundled grammar.
2. Post-processing the parse tree via ``DroidTransformer`` (a Lark Transformer)
   that maps every grammar rule to a concrete AST node.

Public API
----------
>>> from droidpilot.core.parser import DroidPilotParser, ParseError
>>> parser = DroidPilotParser()
>>> program = parser.parse('tap(540, 1200)\\n')
>>> program
ProgramNode(source='<string>', statements=1)
"""

from __future__ import annotations

import importlib.resources
import os
from pathlib import Path
from typing import Any

from lark import Lark, Token, Transformer, Tree, UnexpectedInput, v_args
from lark.indenter import Indenter

from droidpilot.core.ast_nodes import (
    ASTNode,
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


# ─── Exceptions ───────────────────────────────────────────────────────────────


class ParseError(Exception):
    """Raised when the DroidPilot source cannot be parsed.

    Attributes
    ----------
    message:
        Human-readable error description.
    line:
        1-based source line where the error occurred (0 if unknown).
    column:
        1-based column where the error occurred (0 if unknown).
    source_text:
        The original source text (may be truncated for large inputs).
    """

    def __init__(
        self,
        message: str,
        line: int = 0,
        column: int = 0,
        source_text: str = "",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column
        self.source_text = source_text

    def __str__(self) -> str:
        loc = f" (line {self.line}, col {self.column})" if self.line else ""
        return f"ParseError{loc}: {self.message}"

    def __repr__(self) -> str:
        return f"ParseError({self.message!r}, line={self.line}, col={self.column})"


# ─── Indenter ─────────────────────────────────────────────────────────────────


class DroidIndenter(Indenter):
    """Injects ``_INDENT`` / ``_DEDENT`` tokens for Python-style indentation."""

    NL_type = "_NEWLINE"
    OPEN_PAREN_types: list[str] = []
    CLOSE_PAREN_types: list[str] = []
    INDENT_type = "_INDENT"
    DEDENT_type = "_DEDENT"
    tab_len = 4


# ─── Transformer ──────────────────────────────────────────────────────────────


def _line(tree_or_token: Any) -> int:
    """Extract source line number from a Lark tree or token, or return 0."""
    if isinstance(tree_or_token, Token):
        return tree_or_token.line or 0
    if isinstance(tree_or_token, Tree):
        # Try to get line from first child token.
        for child in tree_or_token.children:
            ln = _line(child)
            if ln:
                return ln
    return 0


@v_args(inline=True)
class DroidTransformer(Transformer):  # type: ignore[misc]
    """Transforms a Lark parse tree into a DroidPilot AST.

    Each method corresponds to a rule in the grammar and returns the
    appropriate :class:`~droidpilot.core.ast_nodes.ASTNode`.
    """

    # ── Top-level ────────────────────────────────────────────────────────────

    def start(self, *statements: ASTNode) -> ProgramNode:
        stmts = [s for s in statements if s is not None]
        return ProgramNode(statements=stmts)

    def statement(self, stmt: ASTNode) -> ASTNode:
        return stmt

    def simple_stmt(self, stmt: ASTNode) -> ASTNode:
        return stmt

    def compound_stmt(self, stmt: ASTNode) -> ASTNode:
        return stmt

    # ── Assignment ───────────────────────────────────────────────────────────

    def assign_stmt(self, name: Token, value: ASTNode) -> AssignNode:
        return AssignNode(name=str(name), value=value, line=name.line or 0)

    # ── Call (command or macro — unified in grammar) ─────────────────────────
    # Disambiguation is done at runtime by the execution engine: it first
    # checks the command registry, then falls back to the macro registry.

    def call_stmt(self, name: Token, *args: ASTNode) -> CommandNode:
        # We use CommandNode for all calls.  The engine will check both
        # the command registry and the macro registry at execution time.
        # When arguments are present, arg_list() returns a list which is
        # passed as a single positional arg — unwrap it.
        if args and isinstance(args[0], list):
            resolved_args: list[ASTNode] = args[0]
        else:
            resolved_args = list(args)
        return CommandNode(name=str(name), args=resolved_args, line=name.line or 0)

    def arg_list(self, *args: ASTNode) -> list[ASTNode]:
        return list(args)

    # ── Control flow ─────────────────────────────────────────────────────────

    def if_stmt(self, condition: ASTNode, *rest: Any) -> IfNode:
        # rest = then_statements... [else_clause]
        then_body: list[ASTNode] = []
        else_body: list[ASTNode] = []
        found_else = False
        for item in rest:
            if isinstance(item, list) and not found_else:
                # This is the else_clause list
                else_body = item
                found_else = True
            elif isinstance(item, ASTNode):
                then_body.append(item)
        return IfNode(condition=condition, then_body=then_body, else_body=else_body)

    def else_clause(self, *statements: ASTNode) -> list[ASTNode]:
        return list(statements)

    def repeat_stmt(self, count: ASTNode, *body: ASTNode) -> RepeatNode:
        return RepeatNode(count=count, body=list(body))

    # ── Macro definition ─────────────────────────────────────────────────────

    def macro_def_stmt(self, name: Token, *rest: Any) -> MacroDefNode:
        params: list[str] = []
        body: list[ASTNode] = []
        for item in rest:
            if isinstance(item, list):
                # param_list returns a list of strings
                params = item
            elif isinstance(item, ASTNode):
                body.append(item)
        return MacroDefNode(name=str(name), params=params, body=body, line=name.line or 0)

    def param_list(self, *names: Token) -> list[str]:
        return [str(n) for n in names]

    # ── Conditions ───────────────────────────────────────────────────────────

    def comparison(self, left: ASTNode, op: str, right: ASTNode) -> ComparisonNode:
        return ComparisonNode(op=op, left=left, right=right)

    def cmd_condition(self, cmd: CommandNode) -> CommandNode:
        return cmd

    def expr_condition(self, expr: ASTNode) -> ASTNode:
        return expr

    # Comparison operators — each returns the operator string.
    def eq(self) -> str:
        return "=="

    def ne(self) -> str:
        return "!="

    def lt(self) -> str:
        return "<"

    def le(self) -> str:
        return "<="

    def gt(self) -> str:
        return ">"

    def ge(self) -> str:
        return ">="

    def comparison_op(self, op: str) -> str:
        return op

    # ── Arithmetic expressions ────────────────────────────────────────────────

    def add(self, left: ASTNode, right: ASTNode) -> BinaryOpNode:
        return BinaryOpNode(op="+", left=left, right=right)

    def sub(self, left: ASTNode, right: ASTNode) -> BinaryOpNode:
        return BinaryOpNode(op="-", left=left, right=right)

    def mul(self, left: ASTNode, right: ASTNode) -> BinaryOpNode:
        return BinaryOpNode(op="*", left=left, right=right)

    def div(self, left: ASTNode, right: ASTNode) -> BinaryOpNode:
        return BinaryOpNode(op="/", left=left, right=right)

    def expr(self, value: ASTNode) -> ASTNode:
        return value

    def grouped(self, inner: ASTNode) -> ASTNode:
        return inner

    def atom(self, value: ASTNode) -> ASTNode:
        return value

    # ── Literals ─────────────────────────────────────────────────────────────

    def number(self, token: Token) -> NumberLiteral:
        return NumberLiteral(value=int(token), line=token.line or 0)

    def float_number(self, token: Token) -> FloatLiteral:
        return FloatLiteral(value=float(token), line=token.line or 0)

    def string(self, token: Token) -> StringLiteral:
        # Strip surrounding quotes; Lark ESCAPED_STRING includes them.
        raw = str(token)
        value = raw[1:-1].encode("raw_unicode_escape").decode("unicode_escape")
        return StringLiteral(value=value, line=token.line or 0)

    def bool_true(self) -> BoolLiteral:
        return BoolLiteral(value=True)

    def bool_false(self) -> BoolLiteral:
        return BoolLiteral(value=False)

    def var_ref(self, token: Token) -> VariableRef:
        return VariableRef(name=str(token), line=token.line or 0)


# ─── Parser ───────────────────────────────────────────────────────────────────


def _load_grammar() -> str:
    """Load the bundled grammar file content.

    Tries importlib.resources first (correct for installed packages),
    then falls back to a path relative to this module file.
    """
    try:
        pkg = importlib.resources.files("droidpilot.core")
        grammar_bytes = (pkg / "grammar.lark").read_bytes()
        return grammar_bytes.decode("utf-8")
    except (AttributeError, FileNotFoundError, ModuleNotFoundError):
        here = Path(__file__).parent
        grammar_path = here / "grammar.lark"
        if not grammar_path.exists():
            raise FileNotFoundError(
                f"DroidPilot grammar file not found at {grammar_path}. "
                "Ensure the package is installed correctly."
            )
        return grammar_path.read_text(encoding="utf-8")


class DroidPilotParser:
    """Parses DroidPilot DSL source text into an AST.

    The underlying Lark parser is created once on construction and reused
    for all subsequent ``parse`` / ``parse_file`` calls.

    Parameters
    ----------
    ambiguity:
        Lark ambiguity setting; ``"resolve"`` is recommended for LALR.
    """

    def __init__(self, ambiguity: str = "resolve") -> None:
        grammar = _load_grammar()
        self._lark = Lark(
            grammar,
            parser="lalr",
            postlex=DroidIndenter(),
            propagate_positions=True,
        )
        self._transformer = DroidTransformer()

    # ── Public API ───────────────────────────────────────────────────────────

    def parse(self, source: str, source_name: str = "<string>") -> ProgramNode:
        """Parse *source* text and return a :class:`ProgramNode`.

        Parameters
        ----------
        source:
            DroidPilot DSL source code as a string.
        source_name:
            A label used in error messages (e.g. a file path).

        Raises
        ------
        ParseError
            If the source contains a syntax error.
        """
        # Ensure source ends with a newline (Lark LALR + Indenter requires it).
        if source and not source.endswith("\n"):
            source += "\n"

        try:
            tree = self._lark.parse(source)
        except UnexpectedInput as exc:
            line = getattr(exc, "line", 0) or 0
            column = getattr(exc, "column", 0) or 0
            raise ParseError(
                message=str(exc),
                line=line,
                column=column,
                source_text=source[:500],
            ) from exc
        except Exception as exc:
            raise ParseError(
                message=f"Unexpected parse failure: {exc}",
                source_text=source[:500],
            ) from exc

        try:
            program: ProgramNode = self._transformer.transform(tree)
        except Exception as exc:
            raise ParseError(
                message=f"AST construction failed: {exc}",
                source_text=source[:500],
            ) from exc

        program.source = source_name
        return program

    def parse_file(self, path: str | os.PathLike[str]) -> ProgramNode:
        """Read *path* and parse its contents.

        Parameters
        ----------
        path:
            Path to a ``.dp`` script file.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ParseError
            If the file contains a syntax error.
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Script file not found: {file_path}")
        source = file_path.read_text(encoding="utf-8")
        return self.parse(source, source_name=str(file_path))

    def validate(self, source: str, source_name: str = "<string>") -> list[str]:
        """Validate *source* without constructing a full AST.

        Returns a list of error messages.  An empty list means the source
        is syntactically valid.

        Parameters
        ----------
        source:
            DroidPilot DSL source code as a string.
        source_name:
            Label for error messages.
        """
        errors: list[str] = []
        try:
            self.parse(source, source_name=source_name)
        except ParseError as exc:
            errors.append(str(exc))
        return errors
