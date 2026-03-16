# DroidPilot — Architecture

## Overview

DroidPilot follows a layered architecture with clean separation of concerns:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            DroidPilot                                    │
│                                                                          │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────────────────┐   │
│  │  CLI Layer   │   │  DSL Layer   │   │  Plugin Layer              │   │
│  │  (Click)     │   │  (.droid)    │   │  (entry-points / files)    │   │
│  └──────┬───────┘   └──────┬───────┘   └─────────────┬──────────────┘   │
│         │                  │                          │                  │
│         └──────────────────▼──────────────────────────▼                  │
│                    ┌────────────────────────────────────┐                │
│                    │           Core Layer               │                │
│                    │  ┌──────────┐  ┌────────────────┐  │                │
│                    │  │  Parser  │  │  Execution     │  │                │
│                    │  │  (Lark)  │──▶  Engine        │  │                │
│                    │  └──────────┘  └───────┬────────┘  │                │
│                    │  ┌──────────┐          │           │                │
│                    │  │   AST    │  ┌────────▼────────┐  │                │
│                    │  │  Nodes   │  │  Execution     │  │                │
│                    │  └──────────┘  │  Context       │  │                │
│                    │               └────────┬────────┘  │                │
│                    └────────────────────────┼────────────┘                │
│                                            │                             │
│                    ┌────────────────────────▼────────────────────────┐   │
│                    │              Actions Layer                       │   │
│                    │  tap · swipe · type · app · screenshot           │   │
│                    └───────────────────────┬─────────────────────────┘   │
│                                           │                             │
│                    ┌───────────────────────▼─────────────────────────┐   │
│                    │              ADB Layer                           │   │
│                    │  ┌──────────────┐   ┌──────────────────────┐    │   │
│                    │  │  ADBClient   │   │  ADBDevice           │    │   │
│                    │  │ (subprocess) │   │  (device-bound API)  │    │   │
│                    │  └──────────────┘   └──────────────────────┘    │   │
│                    └────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    Cross-cutting Concerns                        │    │
│  │  Vision (OpenCV) · Recorder (getevent) · Rich Logging           │    │
│  └─────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Layers

### 1. DSL Layer (`droidpilot/core/`)

The scripting language layer responsible for turning human-readable `.droid` files into an executable AST.

#### Grammar (`grammar.lark`)

Written in Lark's EBNF-like syntax, targeting the LALR(1) parser.  Uses the built-in `Indenter` post-lexer to handle Python-style indentation.

Key grammar constructs:
- `command_stmt` — built-in or plugin command calls
- `assign_stmt` — variable assignments
- `if_stmt / else_clause` — conditional branching
- `repeat_stmt` — counted loops
- `macro_def_stmt` — reusable macro definitions
- `macro_call_stmt` — macro invocations

#### AST Nodes (`ast_nodes.py`)

Each grammar rule maps to a dataclass node inheriting from `ASTNode`.  Every node implements `execute(context: ExecutionContext)`.

| Node | Represents |
|------|-----------|
| `ProgramNode` | Root — list of top-level statements |
| `CommandNode` | Built-in or plugin command call |
| `AssignNode` | Variable assignment `x = expr` |
| `MacroDefNode` | Macro definition `macro foo(a, b): ...` |
| `MacroCallNode` | Macro invocation `foo(1, 2)` |
| `IfNode` | Conditional `if cond: ... else: ...` |
| `RepeatNode` | Loop `repeat N: ...` |
| `NumberLiteral / FloatLiteral / StringLiteral / BoolLiteral` | Literal values |
| `VariableRef` | Reference to a named variable |
| `BinaryOpNode` | Arithmetic: `+`, `-`, `*`, `/` |
| `ComparisonNode` | Comparison: `==`, `!=`, `<`, `<=`, `>`, `>=` |

#### Parser (`parser.py`)

`DroidPilotParser` wraps the Lark instance and `DroidTransformer`.

- `parse(source, source_name)` — parse a string, return `ProgramNode`
- `parse_file(path)` — read and parse a file
- `validate(source)` — return a list of error strings (empty = valid)

The `DroidTransformer` is a Lark `Transformer` subclass that maps each grammar rule to its AST node during tree construction.

---

### 2. Core Layer — Execution

#### ExecutionContext (`context.py`)

The central runtime state object, passed to every `node.execute()` call.

Responsibilities:
- Variable scope stack (lexical scoping via push/pop)
- Macro registry (`define_macro` / `get_macro`)
- Command registry (`register_command` / `get_command`)
- Execution lifecycle state (`IDLE → RUNNING → COMPLETED / ERRORED`)
- `ExecutionStats` counters
- Reference to the active `ADBDevice`
- Rich logging via `RichHandler`

#### ExecutionEngine (`engine.py`)

Stateless orchestrator that:
1. Registers all built-in commands into the context.
2. Calls `program.execute(context)` which tree-walks the AST.
3. Catches and collects exceptions into `ExecutionResult`.

Built-in commands registered:

| Command | Function |
|---------|----------|
| `tap(x, y)` | `_cmd_tap` |
| `swipe(x1,y1,x2,y2[,dur])` | `_cmd_swipe` |
| `type(text)` | `_cmd_type` |
| `wait(seconds)` | `_cmd_wait` |
| `screenshot([path])` | `_cmd_screenshot` |
| `open_app(package)` | `_cmd_open_app` |
| `device_info()` | `_cmd_device_info` |
| `list_devices()` | `_cmd_list_devices` |
| `exists(img[,threshold])` | `_cmd_exists` |
| `tap_image(img[,threshold])` | `_cmd_tap_image` |
| `key_event(code)` | `_cmd_key_event` |
| `back()` | `_cmd_back` |
| `home()` | `_cmd_home` |
| `recent()` | `_cmd_recent` |
| `print(...)` | `_cmd_print` |
| `stop()` | `_cmd_stop` |

---

### 3. ADB Layer (`droidpilot/adb/`)

#### ADBClient (`client.py`)

Thin subprocess wrapper around the `adb` binary.

- All commands use `subprocess.run(capture_output=True)` — no shell injection possible.
- `type_text` URL-encodes the input string before passing to `adb shell input text`.
- `screenshot` uses the 3-step screencap → pull → cleanup strategy.

#### ADBDevice (`device.py`)

Higher-level device-bound API.  Wraps `ADBClient` with a fixed `serial` so callers never need to pass `serial=` on every method call.

Provides convenience methods not in `ADBClient`:
- `long_press`, `double_tap` (zero-length swipes)
- `scroll_up`, `scroll_down`
- `pinch_in`, `pinch_out`
- `wake_screen`, `battery_level`, `is_screen_on`
- `wait_for_activity` (polling loop)

---

### 4. Actions Layer (`droidpilot/actions/`)

Thin wrappers adding validation, logging, and sensible defaults on top of `ADBDevice` methods.  Used both by the engine and directly in Python code.

| Module | Purpose |
|--------|---------|
| `tap.py` | `tap`, `long_press`, `double_tap`, `tap_sequence` |
| `swipe.py` | `swipe`, `scroll_down/up`, `fling_down/up`, `horizontal_swipe_*` |
| `text.py` | `type_text`, `type_line`, `clear_field`, `press_*` |
| `app.py` | `open_app`, `force_stop_app`, `restart_app`, `install_apk`, `is_installed` |
| `screenshot.py` | `capture_screenshot`, `capture_to_bytes`, `capture_timestamped` |

---

### 5. Vision Layer (`droidpilot/vision/`)

OpenCV-powered template matching.

**`TemplateMatcher`** workflow:
1. Load screen PNG and template PNG via `cv2.imread`.
2. Optionally convert to grayscale (faster, more robust for icon matching).
3. Run `cv2.matchTemplate` with `TM_CCOEFF_NORMED`.
4. Compare best score against configurable `threshold` (default 0.8).
5. Return `(found: bool, centre: (x, y) | None, score: float)`.

The `find_all` method uses non-maximum suppression (10px deduplication radius) to return multiple non-overlapping matches.

---

### 6. Recorder (`droidpilot/recorder/`)

**`EventRecorder`** architecture:

```
adb shell getevent -lt
        │
        ▼
GeteventParser        ← parses raw text lines into RawEvent objects
        │
        ▼
TouchStateMachine     ← accumulates EV_ABS / EV_KEY events into gestures
        │
        ▼
[RecordedEvent list]  ← tap / swipe / long_press / key / wait
        │
        ▼
DSLGenerator          ← produces a .droid script string
```

The recorder runs `getevent` in a background subprocess with a reader thread.  When `stop()` is called, the process is terminated and the thread joined.

---

### 7. Plugin Layer (`droidpilot/plugins/`)

**Discovery**: via `importlib.metadata` entry points under the `"droidpilot.plugins"` group.

**Activation**: `PluginLoader._activate` supports two styles:
1. `COMMANDS: dict` — maps command names to callables.
2. `register(ctx: ExecutionContext)` — called with the live context.

After loading, all new commands are tracked in a `PluginManifest`.

---

### 8. CLI Layer (`droidpilot/cli/`)

Built with Click.  All commands are lazy-importing to keep `--help` fast.

| Command | Description |
|---------|-------------|
| `droidpilot run <script>` | Parse and execute a `.droid` script |
| `droidpilot devices` | List connected ADB devices |
| `droidpilot screenshot [output]` | Capture a device screenshot |
| `droidpilot validate <script>` | Validate a script without running it |
| `droidpilot info` | Print device information |
| `droidpilot shell [cmd]` | Interactive or one-shot ADB shell |
| `droidpilot record` | Record interactions to a `.droid` script |
| `droidpilot doctor` | System health check |

---

## Data Flow — Script Execution

```
user writes script.droid
        │
        ▼
DroidPilotParser.parse_file(script.droid)
        │
        ▼  (DroidTransformer)
ProgramNode (AST)
        │
        ▼
ExecutionEngine.execute(program, context)
        │
        ├──▶ for each statement:
        │        stmt.execute(context)
        │           │
        │           ├── CommandNode → context.get_command(name)(*args)
        │           │       └──▶ _cmd_tap(ctx, x, y)
        │           │                └──▶ ctx.device.tap(x, y)
        │           │                         └──▶ adb shell input tap x y
        │           │
        │           ├── AssignNode → context.set_var(name, value)
        │           ├── IfNode → evaluate condition, branch to then/else
        │           ├── RepeatNode → loop body N times
        │           └── MacroCallNode → push scope, execute body, pop scope
        │
        ▼
ExecutionResult(success, errors, stats)
```

---

## Error Hierarchy

```
Exception
└── ADBError
    └── DeviceNotFoundError
└── ParseError
└── ExecutionError
    ├── CommandError
    └── DeviceRequiredError
└── PluginError
└── RecorderError
```
