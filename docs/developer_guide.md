# DroidPilot Developer Guide

This guide covers how to set up a development environment, extend the framework, add new grammar constructs, and contribute to the project.

---

## Development Setup

### Prerequisites

- Python 3.11 or later
- Git
- ADB (`android-platform-tools`) on your `PATH`
- An Android device or emulator (optional — many tests run without one)

### Clone and install

```bash
git clone https://github.com/droidpilot/droidpilot.git
cd droidpilot
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

The `.[dev]` extras install:
- `pytest`, `pytest-cov`, `pytest-mock` — testing
- `black` — code formatter
- `ruff` — linter
- `mypy` — type checker

### Verify installation

```bash
droidpilot --version
droidpilot doctor
pytest --tb=short
```

---

## Project Layout

```
droidpilot/
├── cli/                 # Click CLI commands
│   └── main.py
├── core/                # Parser, AST, engine, context
│   ├── grammar.lark     # Lark LALR(1) grammar
│   ├── ast_nodes.py     # AST node dataclasses
│   ├── parser.py        # DroidPilotParser + DroidTransformer
│   ├── engine.py        # ExecutionEngine + built-in commands
│   └── context.py       # ExecutionContext + ExecutionStats
├── adb/                 # ADB subprocess wrapper
│   ├── client.py        # ADBClient
│   └── device.py        # ADBDevice (device-bound API)
├── actions/             # High-level action modules
│   ├── tap.py
│   ├── swipe.py
│   ├── text.py
│   ├── app.py
│   └── screenshot.py
├── vision/              # OpenCV template matching
│   └── matcher.py
├── recorder/            # Interaction recorder (getevent)
│   └── event_recorder.py
└── plugins/             # Plugin discovery and loading
    └── plugin_loader.py

tests/
├── test_ast_nodes.py
├── test_parser.py
├── test_engine.py
├── test_actions.py
└── test_adb_driver.py

examples/
├── basic_demo.droid
├── instagram_bot.droid
└── scroll_bot.droid

docs/
├── architecture.md
├── dsl_reference.md
├── plugin_system.md
└── developer_guide.md  ← you are here
```

---

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=droidpilot --cov-report=html

# Specific module
pytest tests/test_parser.py -v

# Specific test class or method
pytest tests/test_engine.py::TestEngineBasicExecution -v
pytest tests/test_engine.py::TestEngineBasicExecution::test_empty_program_succeeds -v
```

### Writing tests

All tests use `pytest`.  No real device is required — device calls are mocked via `unittest.mock.MagicMock`.

Example pattern for engine tests:

```python
from unittest.mock import MagicMock
from droidpilot.core.context import ExecutionContext
from droidpilot.core.engine import ExecutionEngine
from droidpilot.core.ast_nodes import ProgramNode, CommandNode, NumberLiteral

def test_my_feature() -> None:
    device = MagicMock()
    ctx = ExecutionContext(device=device)
    engine = ExecutionEngine()

    prog = ProgramNode(statements=[
        CommandNode("tap", [NumberLiteral(100), NumberLiteral(200)])
    ])
    result = engine.execute(prog, ctx)
    assert result.success
    device.tap.assert_called_once_with(100, 200)
```

---

## Code Style

### Formatting

```bash
black droidpilot/ tests/
```

### Linting

```bash
ruff check droidpilot/ tests/
```

### Type checking

```bash
mypy droidpilot/
```

Configuration is in `pyproject.toml` under `[tool.black]`, `[tool.ruff]`, and `[tool.mypy]`.

---

## Extending the Grammar

To add a new statement type, edit `droidpilot/core/grammar.lark`:

### 1. Add a grammar rule

```lark
// in grammar.lark
compound_stmt: if_stmt
             | repeat_stmt
             | macro_def_stmt
             | while_stmt          // ← new

while_stmt: "while" condition ":" _NEWLINE _INDENT statement+ _DEDENT
```

### 2. Add an AST node

In `ast_nodes.py`:

```python
@dataclass
class WhileNode(ASTNode):
    """while cond: body"""
    condition: ASTNode
    body: list[ASTNode] = field(default_factory=list)
    line: int = 0

    def execute(self, context: "ExecutionContext") -> None:
        MAX_ITERATIONS = 10_000
        i = 0
        while self.condition.execute(context):
            if i >= MAX_ITERATIONS:
                raise ExecutionError(f"while loop exceeded {MAX_ITERATIONS} iterations")
            for stmt in self.body:
                stmt.execute(context)
            i += 1
```

### 3. Add a transformer method

In `parser.py`, inside `DroidTransformer`:

```python
def while_stmt(self, condition: ASTNode, *body: ASTNode) -> WhileNode:
    return WhileNode(condition=condition, body=list(body))
```

### 4. Export from `core/__init__.py`

```python
from droidpilot.core.ast_nodes import ..., WhileNode
```

---

## Adding a New Built-in Command

In `engine.py`:

```python
def _cmd_vibrate(ctx: ExecutionContext, duration_ms: Any = 500) -> None:
    """vibrate([duration_ms]) — Vibrate the device."""
    device = _require_device(ctx, "vibrate")
    ms = int(duration_ms)
    device.shell(f"input keyevent --longpress 4")  # or use vibrator service
    ctx.stats.commands_executed += 1

# Add to BUILTIN_COMMANDS dict:
BUILTIN_COMMANDS: dict[str, Any] = {
    ...
    "vibrate": _cmd_vibrate,
}
```

No grammar changes needed — unknown names in `command_stmt` / `macro_call_stmt` are resolved at runtime via the command registry.

---

## Adding a New CLI Command

In `cli/main.py`:

```python
@cli.command("my-command")
@click.option("-d", "--device", default=None)
@click.argument("argument")
def cmd_my_command(device: str | None, argument: str) -> None:
    """Brief description shown in --help."""
    dev = _get_device(device)
    # ... your logic ...
```

---

## Modifying the ADB Layer

### ADBClient (`adb/client.py`)

`ADBClient._run()` is the single point of subprocess execution.  All ADB commands go through it.  If you need a new raw ADB operation, add a method here.

### ADBDevice (`adb/device.py`)

`ADBDevice` wraps `ADBClient` with a fixed serial.  Add convenience methods here that combine multiple `ADBClient` calls or add device-level logic.

---

## Testing with a Real Device

```bash
# List devices
adb devices

# Run tests that require a real device
pytest tests/ -m "requires_device" --device emulator-5554
```

Mark device-dependent tests with:

```python
import pytest
pytestmark = pytest.mark.requires_device
```

Register the custom marker in `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "requires_device: test requires a connected Android device",
]
```

---

## Release Process

1. Bump version in `droidpilot/__init__.py` and `pyproject.toml`.
2. Update `CHANGELOG.md`.
3. Run the full test suite: `pytest`.
4. Build the distribution: `python -m build`.
5. Check the distribution: `twine check dist/*`.
6. Upload to PyPI: `twine upload dist/*`.
7. Tag the release: `git tag v0.2.0 && git push --tags`.

---

## Continuous Integration

The CI pipeline (`.github/workflows/ci.yml`) runs on every push and pull request:

1. Matrix: Python 3.11 and 3.12 on `ubuntu-latest`.
2. Install dependencies.
3. Run `ruff check` for linting.
4. Run `mypy` for type checking.
5. Run `pytest --cov`.
6. Upload coverage to Codecov.

---

## Contribution Checklist

Before submitting a pull request:

- [ ] All new public functions have docstrings with type hints
- [ ] New features have corresponding tests in `tests/`
- [ ] `pytest` passes with no failures
- [ ] `ruff check .` reports no errors
- [ ] `black --check .` reports no formatting issues
- [ ] `mypy droidpilot/` reports no errors (or suppressions are documented)
- [ ] `docs/` updated if public API changes
- [ ] `CHANGELOG.md` entry added
