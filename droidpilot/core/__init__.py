"""
droidpilot.core — Core parsing, AST, and execution components.

Public exports
--------------
DroidPilotParser
    Parses DroidPilot DSL source text into a ProgramNode AST.

ParseError
    Raised on syntax errors.

ExecutionEngine
    Walks and executes a ProgramNode AST.

ExecutionResult
    Dataclass returned by ExecutionEngine.execute().

ExecutionError, CommandError, DeviceRequiredError
    Exceptions raised during execution.

ExecutionContext
    Runtime state holder (variables, macros, commands, device ref).

All AST node types
    ProgramNode, AssignNode, CommandNode, MacroDefNode, MacroCallNode,
    IfNode, RepeatNode, NumberLiteral, FloatLiteral, StringLiteral,
    BoolLiteral, VariableRef, BinaryOpNode, ComparisonNode.
"""

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
from droidpilot.core.context import ExecutionContext, ExecutionState, ExecutionStats
from droidpilot.core.engine import (
    BUILTIN_COMMANDS,
    CommandError,
    DeviceRequiredError,
    ExecutionEngine,
    ExecutionError,
    ExecutionResult,
)
from droidpilot.core.parser import DroidPilotParser, ParseError

__all__ = [
    # Parser
    "DroidPilotParser",
    "ParseError",
    # Engine
    "ExecutionEngine",
    "ExecutionResult",
    "ExecutionError",
    "CommandError",
    "DeviceRequiredError",
    "BUILTIN_COMMANDS",
    # Context
    "ExecutionContext",
    "ExecutionState",
    "ExecutionStats",
    # AST nodes
    "ASTNode",
    "ProgramNode",
    "AssignNode",
    "CommandNode",
    "MacroDefNode",
    "MacroCallNode",
    "IfNode",
    "RepeatNode",
    "NumberLiteral",
    "FloatLiteral",
    "StringLiteral",
    "BoolLiteral",
    "VariableRef",
    "BinaryOpNode",
    "ComparisonNode",
]
