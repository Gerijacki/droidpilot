"""
DroidPilot AST node definitions.

Every node in the DroidPilot abstract syntax tree is represented as a
dataclass inheriting from ``ASTNode``.  Nodes know how to execute
themselves given an ``ExecutionContext``, enabling a simple tree-walk
interpreter pattern.

Node hierarchy
--------------
ASTNode (abstract)
├── ProgramNode          – root of the tree; list of top-level statements
├── AssignNode           – variable assignment  (name = expr)
├── CommandNode          – built-in command call (tap(x, y))
├── MacroDefNode         – macro definition     (macro foo(): ...)
├── MacroCallNode        – macro invocation     (foo())
├── IfNode               – conditional          (if cond: ... else: ...)
├── RepeatNode           – counted loop         (repeat N: ...)
└── Value nodes (expressions / literals)
    ├── NumberLiteral    – integer literal
    ├── FloatLiteral     – float literal
    ├── StringLiteral    – string literal
    ├── BoolLiteral      – boolean literal
    ├── VariableRef      – variable reference
    ├── BinaryOpNode     – arithmetic expression
    └── ComparisonNode   – comparison expression
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    # Avoid circular imports — ExecutionContext is only needed for type hints.
    from droidpilot.core.context import ExecutionContext


# ─── Abstract base ───────────────────────────────────────────────────────────


class ASTNode(abc.ABC):
    """Abstract base for all DroidPilot AST nodes.

    All concrete nodes must implement ``execute(context)`` which performs
    the node's action and returns an optional result value.  The ``line``
    attribute records the 1-based source line where the node originated,
    used for error messages.
    """

    #: Source line number (1-based); 0 means unknown.
    line: int = 0

    @abc.abstractmethod
    def execute(self, context: "ExecutionContext") -> Any:
        """Execute this node against *context*.

        Returns:
            The semantic result of the node (e.g. the value of a literal,
            the result of a command, or ``None`` for statements).
        """

    def __repr__(self) -> str:  # pragma: no cover
        return f"{type(self).__name__}(line={self.line})"


# ─── Value / expression nodes ────────────────────────────────────────────────


@dataclass
class NumberLiteral(ASTNode):
    """An integer numeric literal, e.g. ``42``."""

    value: int
    line: int = 0

    def execute(self, context: "ExecutionContext") -> int:
        return self.value

    def __repr__(self) -> str:
        return f"NumberLiteral({self.value}, line={self.line})"


@dataclass
class FloatLiteral(ASTNode):
    """A floating-point numeric literal, e.g. ``1.5``."""

    value: float
    line: int = 0

    def execute(self, context: "ExecutionContext") -> float:
        return self.value

    def __repr__(self) -> str:
        return f"FloatLiteral({self.value}, line={self.line})"


@dataclass
class StringLiteral(ASTNode):
    """A string literal, e.g. ``"hello"``."""

    value: str
    line: int = 0

    def execute(self, context: "ExecutionContext") -> str:
        return self.value

    def __repr__(self) -> str:
        return f"StringLiteral({self.value!r}, line={self.line})"


@dataclass
class BoolLiteral(ASTNode):
    """A boolean literal: ``true`` or ``false``."""

    value: bool
    line: int = 0

    def execute(self, context: "ExecutionContext") -> bool:
        return self.value

    def __repr__(self) -> str:
        return f"BoolLiteral({self.value}, line={self.line})"


@dataclass
class VariableRef(ASTNode):
    """A reference to a named variable, e.g. ``x``."""

    name: str
    line: int = 0

    def execute(self, context: "ExecutionContext") -> Any:
        return context.get_var(self.name)

    def __repr__(self) -> str:
        return f"VariableRef({self.name!r}, line={self.line})"


@dataclass
class BinaryOpNode(ASTNode):
    """An arithmetic binary operation: ``+``, ``-``, ``*``, ``/``.

    Attributes:
        op:    Operator string: ``"+"`` | ``"-"`` | ``"*"`` | ``"/"``
        left:  Left-hand operand expression node.
        right: Right-hand operand expression node.
    """

    op: str
    left: ASTNode
    right: ASTNode
    line: int = 0

    def execute(self, context: "ExecutionContext") -> Any:
        lv = self.left.execute(context)
        rv = self.right.execute(context)
        if self.op == "+":
            return lv + rv
        if self.op == "-":
            return lv - rv
        if self.op == "*":
            return lv * rv
        if self.op == "/":
            if rv == 0:
                raise ZeroDivisionError(f"Division by zero at line {self.line}")
            return lv / rv
        raise ValueError(f"Unknown binary operator {self.op!r} at line {self.line}")

    def __repr__(self) -> str:
        return f"BinaryOpNode({self.op!r}, {self.left!r}, {self.right!r}, line={self.line})"


@dataclass
class ComparisonNode(ASTNode):
    """A comparison expression: ``==``, ``!=``, ``<``, ``<=``, ``>``, ``>=``.

    Attributes:
        op:    Comparison operator string.
        left:  Left-hand expression node.
        right: Right-hand expression node.
    """

    op: str
    left: ASTNode
    right: ASTNode
    line: int = 0

    _OP_MAP: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        import operator as _op

        self._OP_MAP = {
            "==": _op.eq,
            "!=": _op.ne,
            "<": _op.lt,
            "<=": _op.le,
            ">": _op.gt,
            ">=": _op.ge,
        }

    def execute(self, context: "ExecutionContext") -> bool:
        lv = self.left.execute(context)
        rv = self.right.execute(context)
        fn = self._OP_MAP.get(self.op)
        if fn is None:
            raise ValueError(f"Unknown comparison operator {self.op!r} at line {self.line}")
        return bool(fn(lv, rv))

    def __repr__(self) -> str:
        return f"ComparisonNode({self.op!r}, {self.left!r}, {self.right!r}, line={self.line})"


# ─── Statement nodes ─────────────────────────────────────────────────────────


@dataclass
class AssignNode(ASTNode):
    """Variable assignment: ``name = expr``.

    Attributes:
        name:  The variable name being assigned.
        value: Expression node whose result is stored.
    """

    name: str
    value: ASTNode
    line: int = 0

    def execute(self, context: "ExecutionContext") -> None:
        result = self.value.execute(context)
        context.set_var(self.name, result)
        context.logger.debug(f"[assign] {self.name} = {result!r}")

    def __repr__(self) -> str:
        return f"AssignNode({self.name!r}, {self.value!r}, line={self.line})"


@dataclass
class CommandNode(ASTNode):
    """A command invocation: ``tap(540, 1200)``.

    Attributes:
        name: Command name (built-in or plugin-registered).
        args: Ordered list of argument expression nodes.
    """

    name: str
    args: list[ASTNode] = field(default_factory=list)
    line: int = 0

    def execute(self, context: "ExecutionContext") -> Any:
        evaluated = [arg.execute(context) for arg in self.args]
        context.logger.debug(f"[command] {self.name}({', '.join(repr(a) for a in evaluated)})")
        # Try command registry first, then macro registry for unified call_stmt dispatch.
        if context.has_command(self.name):
            fn = context.get_command(self.name)
            return fn(context, *evaluated)
        if context.has_macro(self.name):
            macro_def = context.get_macro(self.name)
            if len(evaluated) != len(macro_def.params):
                raise TypeError(
                    f"Macro {self.name!r} expects {len(macro_def.params)} argument(s), "
                    f"got {len(evaluated)} at line {self.line}"
                )
            context.logger.debug(
                f"[macro_call] {self.name}({', '.join(repr(a) for a in evaluated)})"
            )
            with context.scoped_vars({p: v for p, v in zip(macro_def.params, evaluated)}):
                for stmt in macro_def.body:
                    stmt.execute(context)
            return None
        raise NameError(f"Command or macro {self.name!r} is not registered (line {self.line})")

    def __repr__(self) -> str:
        args_repr = ", ".join(repr(a) for a in self.args)
        return f"CommandNode({self.name!r}, [{args_repr}], line={self.line})"


@dataclass
class MacroDefNode(ASTNode):
    """Macro definition: ``macro name(params): body``.

    Attributes:
        name:   The macro name.
        params: Ordered list of parameter names.
        body:   List of statement nodes forming the macro body.
    """

    name: str
    params: list[str] = field(default_factory=list)
    body: list[ASTNode] = field(default_factory=list)
    line: int = 0

    def execute(self, context: "ExecutionContext") -> None:
        context.define_macro(self.name, self)
        context.logger.debug(f"[macro] defined {self.name!r} ({len(self.params)} params)")

    def __repr__(self) -> str:
        return f"MacroDefNode({self.name!r}, params={self.params!r}, line={self.line})"


@dataclass
class MacroCallNode(ASTNode):
    """A macro invocation: ``name(arg1, arg2)``.

    Attributes:
        name: The macro name to call.
        args: Ordered list of argument expression nodes.
    """

    name: str
    args: list[ASTNode] = field(default_factory=list)
    line: int = 0

    def execute(self, context: "ExecutionContext") -> Any:
        macro_def = context.get_macro(self.name)
        evaluated = [arg.execute(context) for arg in self.args]

        if len(evaluated) != len(macro_def.params):
            raise TypeError(
                f"Macro {self.name!r} expects {len(macro_def.params)} argument(s), "
                f"got {len(evaluated)} at line {self.line}"
            )

        context.logger.debug(f"[macro_call] {self.name}({', '.join(repr(a) for a in evaluated)})")

        # Push a new variable scope for the macro invocation.
        with context.scoped_vars({p: v for p, v in zip(macro_def.params, evaluated)}):
            for stmt in macro_def.body:
                stmt.execute(context)

    def __repr__(self) -> str:
        args_repr = ", ".join(repr(a) for a in self.args)
        return f"MacroCallNode({self.name!r}, [{args_repr}], line={self.line})"


@dataclass
class IfNode(ASTNode):
    """Conditional statement: ``if cond: ... else: ...``.

    Attributes:
        condition: Expression or ComparisonNode that evaluates to a bool.
        then_body: Statements executed when condition is truthy.
        else_body: Statements executed when condition is falsy (may be empty).
    """

    condition: ASTNode
    then_body: list[ASTNode] = field(default_factory=list)
    else_body: list[ASTNode] = field(default_factory=list)
    line: int = 0

    def execute(self, context: "ExecutionContext") -> None:
        result = self.condition.execute(context)
        context.logger.debug(f"[if] condition evaluated to {result!r} at line {self.line}")
        if result:
            for stmt in self.then_body:
                stmt.execute(context)
        else:
            for stmt in self.else_body:
                stmt.execute(context)

    def __repr__(self) -> str:
        return (
            f"IfNode(cond={self.condition!r}, "
            f"then={len(self.then_body)} stmts, "
            f"else={len(self.else_body)} stmts, "
            f"line={self.line})"
        )


@dataclass
class RepeatNode(ASTNode):
    """Counted loop: ``repeat N: body``.

    Attributes:
        count: Expression node that evaluates to a non-negative integer.
        body:  List of statement nodes to execute each iteration.
    """

    count: ASTNode
    body: list[ASTNode] = field(default_factory=list)
    line: int = 0

    def execute(self, context: "ExecutionContext") -> None:
        n = self.count.execute(context)
        if not isinstance(n, (int, float)):
            raise TypeError(
                f"repeat count must be a number, got {type(n).__name__!r} at line {self.line}"
            )
        n = int(n)
        if n < 0:
            raise ValueError(f"repeat count must be non-negative, got {n} at line {self.line}")
        context.logger.debug(f"[repeat] {n} iterations at line {self.line}")
        for i in range(n):
            context.set_var("_loop_index", i)
            for stmt in self.body:
                stmt.execute(context)

    def __repr__(self) -> str:
        return f"RepeatNode(count={self.count!r}, body={len(self.body)} stmts, line={self.line})"


# ─── Root node ───────────────────────────────────────────────────────────────


@dataclass
class ProgramNode(ASTNode):
    """Root node of the DroidPilot AST.

    Attributes:
        statements: Ordered list of top-level statement nodes.
        source:     Optional source file path for diagnostics.
    """

    statements: list[ASTNode] = field(default_factory=list)
    source: str = "<string>"
    line: int = 0

    def execute(self, context: "ExecutionContext") -> None:
        context.logger.debug(f"[program] executing {len(self.statements)} top-level statements")
        for stmt in self.statements:
            if context.should_stop:
                context.logger.warning("[program] execution stopped by context signal")
                break
            stmt.execute(context)

    def __repr__(self) -> str:
        return f"ProgramNode(source={self.source!r}, " f"statements={len(self.statements)})"

    def pretty(self, indent: int = 0) -> str:
        """Return a pretty-printed string representation of the AST."""
        pad = "  " * indent
        lines = [f"{pad}ProgramNode(source={self.source!r})"]
        for stmt in self.statements:
            lines.append(f"{pad}  {stmt!r}")
        return "\n".join(lines)
