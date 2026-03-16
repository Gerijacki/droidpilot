# DroidPilot DSL Reference

The DroidPilot Domain-Specific Language (DSL) is a Python-inspired scripting language for automating Android devices.  Scripts are stored in `.droid` files and executed by the `droidpilot run` command.

---

## Syntax Overview

- **Indentation-based** block structure (like Python) — 4 spaces recommended.
- **Comments** start with `#` and extend to the end of the line.
- **Strings** are double-quoted: `"hello world"`.
- **Numbers** may be integers or floats: `42`, `3.14`.
- **Booleans**: `true` or `false` (lowercase).
- **Case-sensitive** identifiers.

---

## Built-in Commands

### `tap(x, y)`

Tap the screen at pixel coordinates *(x, y)*.

```
tap(540, 1200)
```

| Argument | Type | Description |
|----------|------|-------------|
| `x` | int | Horizontal coordinate (pixels from left) |
| `y` | int | Vertical coordinate (pixels from top) |

---

### `swipe(x1, y1, x2, y2 [, duration_ms])`

Swipe from *(x1, y1)* to *(x2, y2)*.

```
swipe(540, 1500, 540, 400)          # default 300ms
swipe(540, 1500, 540, 400, 600)     # 600ms swipe
```

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `x1, y1` | int | required | Start coordinate |
| `x2, y2` | int | required | End coordinate |
| `duration_ms` | int | `300` | Swipe duration in milliseconds |

---

### `type(text)`

Type a string into the currently focused input field.

```
type("Hello, world!")
type("search query")
```

| Argument | Type | Description |
|----------|------|-------------|
| `text` | string | Text to type |

---

### `wait(seconds)`

Pause execution for *seconds* (float supported).

```
wait(1)
wait(0.5)
wait(2.0)
```

| Argument | Type | Description |
|----------|------|-------------|
| `seconds` | float | Wait duration in seconds |

---

### `screenshot([path])`

Capture the device screen and save it locally.

```
screenshot("before.png")
screenshot()              # defaults to "screenshot.png"
```

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `path` | string | `"screenshot.png"` | Output file path |

---

### `open_app(package)`

Launch an app by its Android package name.

```
open_app("com.instagram.android")
open_app("com.google.android.youtube")
```

| Argument | Type | Description |
|----------|------|-------------|
| `package` | string | Android package name |

---

### `device_info()`

Print and return device information (model, Android version, resolution).

```
device_info()
```

---

### `list_devices()`

Print all connected ADB devices.

```
list_devices()
```

---

### `exists(image_path [, threshold])`

Return `true` if *image_path* is found on the current screen.  Captures a fresh screenshot internally.

```
if exists("like_button.png"):
    tap_image("like_button.png")

if exists("error_dialog.png", 0.9):
    tap(540, 900)
```

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `image_path` | string | required | Template image file path |
| `threshold` | float | `0.8` | Minimum match confidence (0.0–1.0) |

Returns: `true` / `false`

---

### `tap_image(image_path [, threshold])`

Tap the centre of the first match of *image_path* on screen.

```
tap_image("submit_button.png")
tap_image("ok_button.png", 0.85)
```

| Argument | Type | Default | Description |
|----------|------|---------|-------------|
| `image_path` | string | required | Template image file path |
| `threshold` | float | `0.8` | Match confidence threshold |

Returns: `true` if tapped, `false` if not found.

---

### `key_event(keycode)`

Send an Android key event by numeric keycode.

```
key_event(4)    # BACK
key_event(3)    # HOME
key_event(26)   # POWER
```

---

### `back()`

Press the Back button (shorthand for `key_event(4)`).

```
back()
```

---

### `home()`

Press the Home button (shorthand for `key_event(3)`).

```
home()
```

---

### `recent()`

Open the Recent Apps switcher (shorthand for `key_event(187)`).

```
recent()
```

---

### `print(value, ...)`

Print one or more values to the terminal.

```
print("Hello!")
print("x =", x)
```

---

### `stop()`

Immediately halt script execution.

```
if exists("critical_error.png"):
    stop()
```

---

## Variables

Variables are assigned with `=`.  Types are inferred from the right-hand side.

```
x = 540
y = 1200
label = "search"
flag = true
delay = 0.5
```

Variables can be used as command arguments:

```
x = 540
y = 1200
tap(x, y)
type(label)
wait(delay)
```

---

## Arithmetic Expressions

Supported operators: `+`, `-`, `*`, `/`

```
half_x = 1080 / 2
offset = x + 100
total = count * multiplier
```

Expressions can appear in arguments:

```
tap(screen_cx + 50, screen_cy - 100)
wait(base_delay * 2)
```

---

## Conditionals

```
if condition:
    # then branch
    statement
    statement
else:
    # else branch (optional)
    statement
```

### Condition forms

**Comparison:**
```
if x == 5:
    print("five")

if count != 0:
    tap(540, 900)

if attempts < 3:
    swipe(540, 1500, 540, 400)
```

**Command result (boolean return):**
```
if exists("like.png"):
    tap_image("like.png")
```

**Variable:**
```
if flag:
    open_app("com.example.app")
```

### Comparison operators

| Operator | Meaning |
|----------|---------|
| `==` | Equal |
| `!=` | Not equal |
| `<` | Less than |
| `<=` | Less than or equal |
| `>` | Greater than |
| `>=` | Greater than or equal |

---

## Loops

### `repeat N:`

Execute the body exactly *N* times.

```
repeat 10:
    swipe(540, 1500, 540, 400)
    wait(0.5)
```

The loop index is available via the built-in variable `_loop_index` (0-based):

```
repeat 5:
    print(_loop_index)
```

*N* can be a variable or expression:

```
count = 20
repeat count:
    tap(540, 900)
```

---

## Macros

Macros define reusable blocks of commands.

### Definition

```
macro macro_name(param1, param2):
    statement
    statement
```

### No-parameter macro

```
macro scroll_down():
    swipe(540, 1500, 540, 400, 400)
    wait(0.3)
```

### Parameterised macro

```
macro tap_and_wait(x, y):
    tap(x, y)
    wait(0.5)
```

### Calling a macro

```
scroll_down()
tap_and_wait(540, 1200)
```

### Macros with control flow

```
macro like_if_visible(template):
    if exists(template):
        tap_image(template)
        wait(0.4)
    else:
        print("Not found, skipping")
```

### Nesting macros

Macros can call other macros:

```
macro like_and_scroll():
    like_if_visible("like.png")
    scroll_down()
```

---

## Full Example Script

```
# instagram_automation.droid
# Scrolls Instagram feed and likes posts

open_app("com.instagram.android")
wait(3)

macro scroll():
    swipe(540, 1500, 540, 400, 450)
    wait(1.0)

macro like():
    if exists("like_inactive.png"):
        tap_image("like_inactive.png")
        wait(0.3)

repeat 30:
    like()
    scroll()

screenshot("final_feed.png")
home()
```

---

## Script File Extension

DroidPilot scripts conventionally use the `.droid` file extension.

---

## Comments

```
# This is a comment
tap(540, 1200)  # inline comment
```

---

## Reserved Keywords

The following identifiers are reserved and cannot be used as variable or macro names:

`if`, `else`, `repeat`, `macro`, `true`, `false`

---

## Error Messages

When a script fails, DroidPilot reports the error with location information:

```
ParseError (line 5, col 3): Unexpected token 'XX'
ExecutionError [tap] (line 3): Command 'tap' requires a connected device
NameError: Variable 'undefined_var' is not defined
```
