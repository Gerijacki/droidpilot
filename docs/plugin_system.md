# DroidPilot Plugin System

DroidPilot's plugin system lets you register new DSL commands in Python, making them available from any `.droid` script.

---

## Overview

A DroidPilot plugin is any Python module that registers callable handlers for new DSL command names.  Plugins can be:

- **Distributed as packages** and discovered automatically via Python entry points.
- **Loaded programmatically** from a module path or file path.
- **Registered inline** directly on an `ExecutionContext`.

---

## Plugin Contract

A plugin module must expose at least one of:

### Style 1: `COMMANDS` dictionary

```python
# my_plugin.py

from droidpilot.core.context import ExecutionContext

def _send_notification(ctx: ExecutionContext, title: str, msg: str) -> None:
    """Send a notification via am broadcast."""
    cmd = f'am broadcast -a my.NOTIFY --es title "{title}" --es msg "{msg}"'
    ctx.device.shell(cmd)

def _force_rotate(ctx: ExecutionContext, orientation: int) -> None:
    """Set screen orientation (0=auto, 1=portrait, 2=landscape)."""
    ctx.device.shell(f"content insert --uri content://settings/system "
                     f"--bind name:s:accelerometer_rotation --bind value:i:0")
    ctx.device.shell(f"content insert --uri content://settings/system "
                     f"--bind name:s:user_rotation --bind value:i:{orientation}")

COMMANDS = {
    "send_notification": _send_notification,
    "force_rotate":      _force_rotate,
}
```

### Style 2: `register(ctx)` function

```python
# another_plugin.py

from droidpilot.core.context import ExecutionContext

def _clear_app_data(ctx: ExecutionContext, package: str) -> None:
    ctx.device.shell(f"pm clear {package}")

def register(context: ExecutionContext) -> None:
    context.register_command("clear_app_data", _clear_app_data)
```

Both styles can be combined — `PluginLoader` processes `COMMANDS` first, then calls `register()`.

---

## Command Handler Signature

All command handlers must accept `ExecutionContext` as their first argument, followed by zero or more positional arguments:

```python
def my_command(ctx: ExecutionContext, *args: Any) -> Any:
    ...
```

The returned value is passed through as the result of the DSL command (useful for `if exists(...):`-style conditions).

To access the device:

```python
def my_command(ctx: ExecutionContext, pkg: str) -> None:
    device = ctx.device  # ADBDevice | None
    if device is None:
        raise DeviceRequiredError("my_command requires a device")
    device.shell(f"am start {pkg}")
```

To log:

```python
ctx.logger.info("[my_plugin] doing something")
ctx.logger.debug("[my_plugin] verbose details")
```

To print to the terminal:

```python
ctx.console.print("[green]Done![/green]")
```

---

## Loading Plugins

### Method 1: Entry Points (Recommended for Distribution)

Add an entry point to your package's `pyproject.toml`:

```toml
[project.entry-points."droidpilot.plugins"]
my_plugin = "my_package.droidpilot_plugin"
```

DroidPilot will auto-discover it when `PluginLoader.discover_and_load()` is called.

### Method 2: Programmatic loading by module path

```python
from droidpilot.core.context import ExecutionContext
from droidpilot.plugins import PluginLoader

ctx = ExecutionContext(device=device)
loader = PluginLoader(ctx)
manifest = loader.load_module("my_package.droidpilot_plugin")
print(manifest.commands)
```

### Method 3: Load from a Python file path

```python
manifest = loader.load_file("./plugins/instagram_plugin.py")
```

### Method 4: Inline registration (no plugin system needed)

```python
ctx.register_command("my_cmd", my_handler_function)
```

---

## Auto-discovery in CLI

When running `droidpilot run`, pass `--load-plugins` to trigger auto-discovery (or call `loader.discover_and_load()` before `engine.execute()`).

---

## Example Plugin Package

### Directory structure

```
my_droidpilot_plugin/
├── pyproject.toml
├── my_droidpilot_plugin/
│   ├── __init__.py          ← plugin entry point module
│   └── commands.py          ← command implementations
```

### `pyproject.toml`

```toml
[project]
name = "droidpilot-instagram"
version = "0.1.0"
dependencies = ["droidpilot>=0.1"]

[project.entry-points."droidpilot.plugins"]
instagram = "droidpilot_instagram"
```

### `droidpilot_instagram/__init__.py`

```python
"""
DroidPilot Instagram Plugin.

Adds Instagram-specific commands:
  like_post()          — like the currently visible post
  follow_user(handle)  — follow a user by username
"""
from __future__ import annotations
from droidpilot.core.context import ExecutionContext

__version__ = "0.1.0"


def _like_post(ctx: ExecutionContext) -> bool:
    from droidpilot.vision.matcher import TemplateMatcher
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp = f.name
    try:
        ctx.device.screenshot(tmp)
        matcher = TemplateMatcher(threshold=0.82)
        found, loc, _ = matcher.find(tmp, "like_inactive.png")
        if found and loc:
            ctx.device.tap(*loc)
            return True
        return False
    finally:
        os.unlink(tmp)


def _follow_user(ctx: ExecutionContext, handle: str) -> None:
    ctx.logger.info(f"[instagram] searching for @{handle}")
    # … navigate to search, type handle, tap follow …


COMMANDS = {
    "like_post":   _like_post,
    "follow_user": _follow_user,
}
```

### Using the plugin in a script

```
# instagram_bot.droid

open_app("com.instagram.android")
wait(3)

macro do_like():
    like_post()
    wait(0.5)

macro scroll_feed():
    swipe(540, 1500, 540, 400, 400)
    wait(1.2)

repeat 20:
    do_like()
    scroll_feed()
```

---

## Plugin Manifest

After loading, `PluginLoader` returns a `PluginManifest`:

```python
manifest = loader.load_module("my_plugin")
print(manifest.name)          # "my_plugin"
print(manifest.commands)      # {"like_post": <function>, ...}
print(manifest.version)       # "0.1.0" (from __version__)
print(manifest.description)   # first line of module docstring
```

---

## Inspecting Loaded Plugins

```python
for name, manifest in loader.loaded_plugins.items():
    print(f"{name}: {list(manifest.commands.keys())}")
```

---

## Best Practices

1. **Namespace your command names** to avoid conflicts: `instagram_like`, `spotify_skip`.
2. **Handle missing devices gracefully** — check `ctx.device is not None`.
3. **Log at DEBUG level** for routine operations, INFO for significant actions.
4. **Return meaningful values** from commands used in `if` conditions.
5. **Keep commands pure** — avoid storing state in global variables; use `ctx.set_var()` instead.
6. **Document your commands** with a docstring:

   ```python
   def my_cmd(ctx: ExecutionContext, arg: str) -> None:
       """my_cmd(arg) — Short description for --help output."""
       ...
   ```
