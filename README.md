# DroidPilot

[![PyPI version](https://badge.fury.io/py/droidpilot.svg)](https://badge.fury.io/py/droidpilot)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

**DroidPilot** is a scriptable Android automation framework that operates entirely over ADB — no device agent, no app installation, no root required. Write simple, readable scripts in the DroidPilot DSL and automate any Android device connected via USB or TCP/IP.

---

## Overview

DroidPilot bridges the gap between low-level `adb shell` commands and heavyweight automation frameworks like Appium. It provides:

- A **clean domain-specific language (DSL)** for expressing automation workflows
- A **template image matching engine** powered by OpenCV for visually-driven automation
- A **plugin system** for extending built-in commands with your own Python functions
- A **rich CLI** for running scripts, inspecting devices, and taking screenshots
- **Zero device-side requirements** — everything runs over standard ADB

Whether you're automating UI tests, building social media bots, or stress-testing your own app, DroidPilot gives you a readable, maintainable way to script Android interactions.

---

## Features

- **Pure ADB**: No Appium server, no UiAutomator daemon, no device-side APKs required
- **DSL Scripting**: Python-like indentation-based syntax with variables, macros, if/else, and loops
- **Image Matching**: Find and tap UI elements using template image matching (OpenCV)
- **Device Management**: Enumerate connected devices, select by serial or index
- **Screenshot Support**: Capture and save device screenshots via ADB
- **Rich Terminal Output**: Colour-coded progress, structured logging, real-time stats
- **Plugin API**: Register custom commands in Python and call them from DSL scripts
- **Extensible Architecture**: Swap out the ADB backend, add new AST node types, or extend the grammar
- **Type-safe Internals**: Full `pydantic` and `mypy --strict` coverage

---

## Installation

```bash
git clone https://github.com/Gerijacki/droidpilot.git
cd droidpilot
pip install -e ".[dev]"
```

### Prerequisites

- Python 3.11 or later
- ADB installed and in your `PATH` (`android-platform-tools`)
- A physical Android device or emulator connected via USB or TCP/IP

Verify ADB is working:

```bash
adb devices
```

---

## Quick Start

### 1. Connect a device

```bash
adb devices
# List of devices attached
# emulator-5554   device
```

### 2. Write a script

Create a file called `hello.dp`:

```
# hello.dp — basic DroidPilot script

tap(540, 1200)
wait(1.5)
type("Hello from DroidPilot!")
screenshot("result.png")
```

### 3. Run it

```bash
droidpilot run hello.dp
```

### 4. Target a specific device

```bash
droidpilot run hello.dp --device emulator-5554
```

---

## DSL Reference

### Basic Commands

```
# Tap a screen coordinate
tap(540, 1200)

# Swipe from one point to another (with optional duration in ms)
swipe(540, 1200, 540, 400)
swipe(540, 1200, 540, 400, 500)

# Type text into the focused field
type("Hello World")

# Wait for N seconds (float supported)
wait(2.0)

# Open an app by package name
open_app("com.instagram.android")

# Take a screenshot and save to a file
screenshot("screen.png")

# Print device info
device_info()
```

### Variables

```
x = 540
y = 1200
tap(x, y)

label = "search query"
type(label)
```

### Conditionals

```
if exists("like_button.png"):
    tap(540, 1600)
else:
    wait(1.0)
```

### Loops

```
repeat 10:
    swipe(540, 1200, 540, 400)
    wait(0.5)
```

### Macros

```
macro scroll_down():
    swipe(540, 1400, 540, 600)
    wait(0.3)

macro like_if_visible(image):
    if exists(image):
        tap_image(image)
        wait(0.5)

# Call the macro
scroll_down()
like_if_visible("heart.png")
```

### Image Matching

```
# Check if an image exists on screen
if exists("play_button.png"):
    tap_image("play_button.png")

# Tap the first match of a template image
tap_image("submit_button.png")
```

---

## Example Scripts

### Instagram Scroll Bot

```
# instagram_scroll.dp

open_app("com.instagram.android")
wait(3.0)

macro scroll_feed():
    swipe(540, 1400, 540, 500, 400)
    wait(1.0)

macro like_post():
    if exists("like_inactive.png"):
        tap_image("like_inactive.png")
        wait(0.5)

repeat 30:
    like_post()
    scroll_feed()
```

### YouTube Auto-Skip Ads

```
# skip_ads.dp

open_app("com.google.android.youtube")
wait(4.0)

macro try_skip():
    if exists("skip_ad.png"):
        tap_image("skip_ad.png")
        wait(1.0)

repeat 20:
    try_skip()
    wait(5.0)
```

### App Stress Test

```
# stress_test.dp

macro relaunch(pkg):
    open_app(pkg)
    wait(2.0)
    screenshot("launch_screen.png")

repeat 50:
    relaunch("com.example.myapp")
    tap(540, 1200)
    wait(1.0)
    swipe(540, 1400, 540, 600)
    wait(1.0)
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         DroidPilot                              │
│                                                                 │
│  ┌───────────┐    ┌──────────────┐    ┌────────────────────┐    │
│  │  DSL      │    │   Parser     │    │  AST Nodes         │    │
│  │  Script   │───▶│  (Lark)      │───▶│  ProgramNode       │    │
│  │  (.dp)    │    │  grammar.lark│    │  CommandNode       │    │
│  └───────────┘    └──────────────┘    │  MacroDefNode      │    │
│                                       │ IfNode / RepeatNode│    │
│                                       └────────┬───────────┘    │
│                                                │                │
│                                                ▼                │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Execution Engine                             │  │
│  │  ┌─────────────────────┐   ┌──────────────────────────┐   │  │
│  │  │  ExecutionContext   │   │  Command Dispatcher      │   │  │
│  │  │  - variables        │   │  - tap / swipe / type    │   │  │
│  │  │  - macro registry   │   │  - wait / screenshot     │   │  │
│  │  │  - plugin registry  │   │  - open_app / exists     │   │  │
│  │  │  - execution state  │   │  - tap_image             │   │  │
│  │  └─────────────────────┘   └──────────────────────────┘   │  │
│  └───────────────────────────────────┬───────────────────────┘  │
│                                      │                          │
│                                      ▼                          │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │                  ADB Backend                            │    │
│  │  ┌──────────────┐   ┌──────────────┐   ┌────────────┐   │    │
│  │  │  ADBClient   │   │  Device      │   │  OpenCV    │   │    │
│  │  │  (subprocess)│   │  (per-serial)│   │  Matcher   │   │    │
│  │  └──────────────┘   └──────────────┘   └────────────┘   │    │
│  └─────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## CLI Reference

```
Usage: droidpilot [OPTIONS] COMMAND [ARGS]...

  DroidPilot — Android automation via ADB.

Options:
  --version   Show the version and exit.
  -h, --help  Show this message and exit.

Commands:
  run          Run a .dp script file
  devices      List connected ADB devices
  screenshot   Capture a screenshot from the device
  shell        Drop into an interactive ADB shell prompt
  validate     Validate a .dp script without running it
  info         Print device info (model, OS version, screen resolution)
```

### `droidpilot run`

```
Usage: droidpilot run [OPTIONS] SCRIPT

  Run a DroidPilot script.

Options:
  -d, --device TEXT    ADB device serial (default: first connected device)
  --dry-run            Parse and validate only; do not execute
  --timeout FLOAT      Maximum execution time in seconds
  -v, --verbose        Enable verbose logging
  --no-color           Disable rich terminal colours
  -h, --help           Show this message and exit.
```

### `droidpilot devices`

```
Usage: droidpilot devices [OPTIONS]

  List all connected ADB devices with their status and properties.

Options:
  --json       Output as JSON
  -h, --help   Show this message and exit.
```

### `droidpilot screenshot`

```
Usage: droidpilot screenshot [OPTIONS] [OUTPUT]

  Take a screenshot and save it locally.

Arguments:
  OUTPUT  Output file path [default: screenshot_<timestamp>.png]

Options:
  -d, --device TEXT   ADB device serial
  -h, --help          Show this message and exit.
```

### `droidpilot validate`

```
Usage: droidpilot validate [OPTIONS] SCRIPT

  Parse and validate a DroidPilot script without running it.

Options:
  --show-ast   Pretty-print the parsed AST
  -h, --help   Show this message and exit.
```

---

## Plugin System

You can extend DroidPilot with custom commands written in Python. Plugins are discovered via Python entry points or registered programmatically.

### Registering a Plugin

```python
# my_plugin.py
from droidpilot.core.context import ExecutionContext

def send_notification(ctx: ExecutionContext, title: str, message: str) -> None:
    """Custom command: send_notification(title, message)"""
    device = ctx.device
    cmd = f'am broadcast -a android.intent.action.SEND --es title "{title}" --es msg "{message}"'
    device.shell(cmd)
```

Register it programmatically:

```python
from droidpilot.core.context import ExecutionContext
from droidpilot.core.engine import ExecutionEngine
from droidpilot.adb.device import ADBDevice

device = ADBDevice("emulator-5554")
ctx = ExecutionContext(device=device)
ctx.register_command("send_notification", send_notification)

engine = ExecutionEngine()
result = engine.execute_file("my_script.dp", ctx)
```

Or via entry points in `pyproject.toml`:

```toml
[project.entry-points."droidpilot.plugins"]
my_plugin = "my_package.my_plugin"
```

---

## Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository on GitHub
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Write tests for your changes in `tests/`
4. Ensure all tests pass: `pytest`
5. Ensure linting passes: `ruff check . && mypy droidpilot/`
6. Submit a pull request with a clear description

### Development Setup

```bash
git clone https://github.com/Gerijacki/droidpilot.git
cd droidpilot
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Git Hooks (pre-push)

The repository ships a pre-push hook at `scripts/pre-push.sh` that mirrors the CI pipeline (ruff → black → mypy → pytest → build check). Install it once after cloning:

```bash
ln -sf "$(pwd)/scripts/pre-push.sh" .git/hooks/pre-push
```

From that point on, every `git push` will run all checks locally. If any step fails the push is blocked and the terminal will show which check failed.

### Running Tests

```bash
pytest
pytest --cov=droidpilot --cov-report=html
```

### Code Style

We use `black` for formatting and `ruff` for linting:

```bash
black droidpilot/ tests/
ruff check droidpilot/ tests/
```

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgements

- [Lark](https://github.com/lark-parser/lark) — the parsing toolkit powering the DSL
- [OpenCV](https://opencv.org/) — image matching engine
- [Rich](https://github.com/Textualize/rich) — beautiful terminal output
- [Click](https://click.palletsprojects.com/) — CLI framework
- [Pydantic](https://docs.pydantic.dev/) — data validation
