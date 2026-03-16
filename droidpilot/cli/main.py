"""
DroidPilot CLI — command-line entry point.

Provides the ``droidpilot`` command with sub-commands:

    droidpilot run <script>        Run a .dp script
    droidpilot devices             List connected ADB devices
    droidpilot screenshot [output] Take a screenshot
    droidpilot validate <script>   Validate a script without running it
    droidpilot info                Print device information
    droidpilot shell               Drop into an interactive ADB shell

All sub-commands share the ``--device`` / ``-d`` option for targeting a
specific ADB device serial.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from droidpilot.adb.device import ADBDevice

import json
import sys
import time
from datetime import datetime

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from droidpilot import __version__

# Lazy imports for heavy modules — only pulled in when the relevant command runs.

_console = Console()
_err_console = Console(stderr=True)


# ─── Shared helpers ───────────────────────────────────────────────────────────


def _get_device(serial: str | None) -> "ADBDevice":
    """Resolve the target device; raise a friendly error if unavailable."""
    from droidpilot.adb.client import ADBClient, ADBError, DeviceNotFoundError
    from droidpilot.adb.device import ADBDevice

    client = ADBClient()
    try:
        resolved_serial = serial or client.first_device()
    except (ADBError, FileNotFoundError) as exc:
        _err_console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    try:
        device = ADBDevice(serial=resolved_serial)
    except DeviceNotFoundError as exc:
        _err_console.print(f"[red]Device not found:[/red] {exc}")
        sys.exit(1)
    return device


def _abort(message: str, code: int = 1) -> None:
    """Print an error message and exit."""
    _err_console.print(f"[bold red]Error:[/bold red] {message}")
    sys.exit(code)


# ─── Root CLI group ───────────────────────────────────────────────────────────


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, prog_name="droidpilot")
def cli() -> None:
    """DroidPilot — Android automation via ADB.

    Write scripts in the DroidPilot DSL and run them on connected Android
    devices without installing anything on the device itself.

    Examples:

    \b
      droidpilot run my_script.dp
      droidpilot run my_script.dp --device emulator-5554
      droidpilot devices
      droidpilot screenshot screen.png
      droidpilot validate my_script.dp --show-ast
    """


# ─── run ──────────────────────────────────────────────────────────────────────


@cli.command("run")
@click.argument("script", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "-d",
    "--device",
    default=None,
    metavar="SERIAL",
    help="ADB device serial (default: first connected device).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Parse and validate only; do not execute commands.",
)
@click.option(
    "--timeout",
    type=float,
    default=None,
    metavar="SECONDS",
    help="Maximum script execution time in seconds.",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose (DEBUG) logging.",
)
@click.option(
    "--no-color",
    is_flag=True,
    default=False,
    help="Disable Rich terminal colours.",
)
@click.option(
    "--stop-on-error/--continue-on-error",
    default=True,
    help="Stop on first error (default) or collect all errors.",
)
def cmd_run(
    script: str,
    device: str | None,
    dry_run: bool,
    timeout: float | None,
    verbose: bool,
    no_color: bool,
    stop_on_error: bool,
) -> None:
    """Run a DroidPilot script.

    SCRIPT is the path to a .dp automation script file.
    """
    from droidpilot.core.context import ExecutionContext
    from droidpilot.core.engine import ExecutionEngine
    from droidpilot.core.parser import DroidPilotParser, ParseError

    console = Console(no_color=no_color)
    err_console = Console(stderr=True, no_color=no_color)

    # ── Parse ────────────────────────────────────────────────────────────────
    parser = DroidPilotParser()
    try:
        program = parser.parse_file(script)
    except ParseError as exc:
        err_console.print(f"[bold red]Parse error:[/bold red] {exc}")
        sys.exit(1)
    except FileNotFoundError as exc:
        err_console.print(f"[bold red]File not found:[/bold red] {exc}")
        sys.exit(1)

    console.print(
        f"[bold green]Parsed[/bold green] {script!r} — "
        f"{len(program.statements)} top-level statement(s)"
    )

    if dry_run:
        console.print("[yellow]Dry-run mode: execution skipped.[/yellow]")
        sys.exit(0)

    # ── Connect device ───────────────────────────────────────────────────────
    dev = _get_device(device)
    console.print(f"[bold cyan]Device:[/bold cyan] {dev.serial}")

    # ── Execute ──────────────────────────────────────────────────────────────
    ctx = ExecutionContext(device=dev, verbose=verbose, console=console)
    engine = ExecutionEngine(stop_on_error=stop_on_error)

    start = time.monotonic()

    if timeout is not None:
        import threading

        def _stopper() -> None:
            time.sleep(timeout)
            if ctx.is_running:
                console.print(f"\n[yellow]Timeout after {timeout}s — stopping execution.[/yellow]")
                ctx.stop()

        t = threading.Thread(target=_stopper, daemon=True)
        t.start()

    result = engine.execute(program, ctx)

    elapsed = time.monotonic() - start

    # ── Report ───────────────────────────────────────────────────────────────
    if result.success:
        console.print(
            Panel(
                f"[bold green]Script completed successfully[/bold green]\n"
                f"Commands run: {result.stats.commands_executed}\n"
                f"Elapsed:      {elapsed:.3f}s",
                title="[green]DroidPilot — OK[/green]",
                border_style="green",
            )
        )
        sys.exit(0)
    else:
        err_lines = "\n".join(f"  • {e}" for e in result.errors)
        err_console.print(
            Panel(
                f"[bold red]Script failed[/bold red] with {len(result.errors)} error(s):\n"
                f"{err_lines}\n\n"
                f"Commands run: {result.stats.commands_executed}\n"
                f"Elapsed:      {elapsed:.3f}s",
                title="[red]DroidPilot — FAILED[/red]",
                border_style="red",
            )
        )
        sys.exit(1)


# ─── devices ──────────────────────────────────────────────────────────────────


@cli.command("devices")
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output device list as JSON.",
)
def cmd_devices(as_json: bool) -> None:
    """List all connected ADB devices."""
    from droidpilot.adb.client import ADBClient, ADBError

    try:
        client = ADBClient()
        entries = client.list_device_entries()
    except FileNotFoundError as exc:
        _abort(str(exc))
    except ADBError as exc:
        _abort(str(exc))

    if as_json:
        data = [
            {
                "serial": e.serial,
                "state": e.state,
                "model": e.model,
                "product": e.product,
                "transport_id": e.transport_id,
            }
            for e in entries
        ]
        click.echo(json.dumps(data, indent=2))
        return

    if not entries:
        _console.print("[yellow]No devices connected.[/yellow]")
        _console.print("Connect a device via USB or run: [dim]adb connect <host>:<port>[/dim]")
        return

    table = Table(title="Connected ADB Devices", show_header=True, header_style="bold cyan")
    table.add_column("Serial", style="green")
    table.add_column("State", style="white")
    table.add_column("Model", style="dim")
    table.add_column("Product", style="dim")

    for entry in entries:
        state_style = "green" if entry.is_online else "red"
        table.add_row(
            entry.serial,
            Text(entry.state, style=state_style),
            entry.model or "—",
            entry.product or "—",
        )

    _console.print(table)
    _console.print(f"Total: {len(entries)} device(s)")


# ─── screenshot ───────────────────────────────────────────────────────────────


@cli.command("screenshot")
@click.argument("output", required=False, default=None)
@click.option(
    "-d",
    "--device",
    default=None,
    metavar="SERIAL",
    help="ADB device serial.",
)
def cmd_screenshot(output: str | None, device: str | None) -> None:
    """Capture a screenshot from the device.

    OUTPUT is the destination file path (default: screenshot_<timestamp>.png).
    """
    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"screenshot_{ts}.png"

    dev = _get_device(device)
    _console.print(f"[bold cyan]Device:[/bold cyan] {dev.serial}")
    _console.print(f"Capturing screenshot → [green]{output}[/green] ...")

    try:
        saved = dev.screenshot(output)
    except Exception as exc:
        _abort(f"Screenshot failed: {exc}")

    _console.print(f"[bold green]Saved:[/bold green] {saved}")


# ─── validate ─────────────────────────────────────────────────────────────────


@cli.command("validate")
@click.argument("script", type=click.Path(exists=True, dir_okay=False))
@click.option(
    "--show-ast",
    is_flag=True,
    default=False,
    help="Pretty-print the parsed AST.",
)
def cmd_validate(script: str, show_ast: bool) -> None:
    """Parse and validate a DroidPilot script without running it."""
    from droidpilot.core.parser import DroidPilotParser, ParseError

    parser = DroidPilotParser()
    try:
        program = parser.parse_file(script)
    except ParseError as exc:
        _err_console.print(f"[bold red]Parse error:[/bold red] {exc}")
        sys.exit(1)
    except FileNotFoundError as exc:
        _err_console.print(f"[bold red]File not found:[/bold red] {exc}")
        sys.exit(1)

    _console.print(
        f"[bold green]✓ Valid[/bold green] — {script!r} parsed successfully "
        f"({len(program.statements)} top-level statement(s))"
    )

    if show_ast:
        _console.print()
        _console.print("[bold cyan]AST:[/bold cyan]")
        _console.print(program.pretty())


# ─── info ─────────────────────────────────────────────────────────────────────


@cli.command("info")
@click.option(
    "-d",
    "--device",
    default=None,
    metavar="SERIAL",
    help="ADB device serial.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    default=False,
    help="Output as JSON.",
)
def cmd_info(device: str | None, as_json: bool) -> None:
    """Print device information (model, OS version, resolution, etc.)."""
    dev = _get_device(device)

    try:
        info = dev.get_info()
    except Exception as exc:
        _abort(f"Failed to get device info: {exc}")

    if as_json:
        click.echo(json.dumps(info, indent=2))
        return

    table = Table(
        title=f"Device Info — {dev.serial}",
        show_header=False,
        box=None,
    )
    table.add_column("Property", style="bold cyan", no_wrap=True)
    table.add_column("Value", style="white")

    for key, value in info.items():
        table.add_row(key.capitalize(), value or "—")

    _console.print(table)


# ─── shell ────────────────────────────────────────────────────────────────────


@cli.command("shell")
@click.option(
    "-d",
    "--device",
    default=None,
    metavar="SERIAL",
    help="ADB device serial.",
)
@click.argument("command", nargs=-1)
def cmd_shell(device: str | None, command: tuple[str, ...]) -> None:
    """Run a single ADB shell command, or drop into interactive mode.

    If COMMAND is supplied, it is run directly.  Without COMMAND, an
    interactive read-eval-print loop is started.

    \b
    Examples:
      droidpilot shell getprop ro.product.model
      droidpilot shell
    """
    dev = _get_device(device)

    if command:
        cmd_str = " ".join(command)
        try:
            output = dev.shell(cmd_str)
        except Exception as exc:
            _abort(f"Shell command failed: {exc}")
        click.echo(output)
        return

    # Interactive mode.
    _console.print(f"[bold cyan]DroidPilot Shell[/bold cyan] — device [green]{dev.serial}[/green]")
    _console.print("Type [dim]exit[/dim] or press Ctrl-D to quit.\n")

    while True:
        try:
            line = click.prompt("adb> ", prompt_suffix="", default="", show_default=False)
        except (EOFError, KeyboardInterrupt):
            _console.print("\n[dim]Bye.[/dim]")
            break

        line = line.strip()
        if not line:
            continue
        if line.lower() in ("exit", "quit", "q"):
            _console.print("[dim]Bye.[/dim]")
            break

        try:
            output = dev.shell(line)
            if output:
                click.echo(output)
        except Exception as exc:
            _err_console.print(f"[red]Error:[/red] {exc}")


# ─── record ───────────────────────────────────────────────────────────────────


@cli.command("record")
@click.option(
    "-d",
    "--device",
    default=None,
    metavar="SERIAL",
    help="ADB device serial.",
)
@click.option(
    "-o",
    "--output",
    default=None,
    metavar="FILE",
    help="Output script file path (default: recorded_<timestamp>.dp).",
)
@click.option(
    "--duration",
    type=float,
    default=None,
    metavar="SECONDS",
    help="Automatically stop recording after SECONDS seconds.",
)
def cmd_record(device: str | None, output: str | None, duration: float | None) -> None:
    """Record device interactions and save them as a DroidPilot script.

    Starts the event recorder and captures all taps, swipes, and gestures.
    Press Ctrl+C (or use --duration) to stop recording.

    \b
    Examples:
      droidpilot record -o my_recording.dp
      droidpilot record --duration 30 -o short_demo.dp
    """
    from droidpilot.recorder.event_recorder import EventRecorder

    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"recorded_{ts}.dp"

    dev = _get_device(device)
    _console.print(f"[bold cyan]Device:[/bold cyan] {dev.serial}")
    _console.print(f"[bold green]Recording[/bold green] interactions → [green]{output}[/green]")

    if duration:
        _console.print(f"Will auto-stop after [yellow]{duration:.1f}s[/yellow].")
    else:
        _console.print("Press [bold]Ctrl+C[/bold] to stop recording.\n")

    recorder = EventRecorder(dev)
    try:
        recorder.start()
        if duration:
            time.sleep(duration)
        else:
            while True:
                time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        recorder.stop()

    events = recorder.events
    _console.print(f"\n[bold green]Captured[/bold green] {len(events)} interaction(s).")

    if not events:
        _console.print("[yellow]No events recorded.  Nothing saved.[/yellow]")
        return

    recorder.save_dsl(output)
    _console.print(f"[bold green]Saved:[/bold green] {output}")

    _console.print("\nGenerated script preview:")
    _console.print(f"[dim]{recorder.to_dsl()[:500]}[/dim]")


# ─── doctor ───────────────────────────────────────────────────────────────────


@cli.command("doctor")
@click.option(
    "-d",
    "--device",
    default=None,
    metavar="SERIAL",
    help="ADB device serial to check (optional).",
)
def cmd_doctor(device: str | None) -> None:
    """Run a system health check for DroidPilot.

    Verifies that all required dependencies are installed and that
    ADB is reachable.  Optionally checks device connectivity.

    \b
    Checks performed:
      • Python version (3.11+)
      • adb binary on PATH
      • lark library installed
      • click library installed
      • rich library installed
      • opencv-python installed
      • numpy installed
      • pydantic installed
      • ADB server running
      • Device connectivity (if --device is given)
    """
    import importlib
    import shutil

    _console.print("\n[bold cyan]DroidPilot Doctor[/bold cyan] — system health check\n")

    checks: list[tuple[str, bool, str]] = []  # (label, ok, detail)

    # ── Python version ───────────────────────────────────────────────────────
    import sys as _sys

    py_ok = _sys.version_info >= (3, 11)
    checks.append(
        (
            "Python ≥ 3.11",
            py_ok,
            f"{_sys.version_info.major}.{_sys.version_info.minor}.{_sys.version_info.micro}",
        )
    )

    # ── adb binary ───────────────────────────────────────────────────────────
    adb_path = shutil.which("adb")
    checks.append(
        (
            "adb binary on PATH",
            adb_path is not None,
            adb_path or "not found — install android-platform-tools",
        )
    )

    # ── Python packages ──────────────────────────────────────────────────────
    packages = [
        ("lark", "lark"),
        ("click", "click"),
        ("rich", "rich"),
        ("opencv-python", "cv2"),
        ("numpy", "numpy"),
        ("pydantic", "pydantic"),
    ]
    for pkg_name, import_name in packages:
        try:
            mod = importlib.import_module(import_name)
            ver = getattr(mod, "__version__", "installed")
            checks.append((f"pkg: {pkg_name}", True, ver))
        except ImportError:
            checks.append(
                (
                    f"pkg: {pkg_name}",
                    False,
                    f"not installed — run: pip install {pkg_name}",
                )
            )

    # ── ADB server ───────────────────────────────────────────────────────────
    if adb_path:
        try:
            import subprocess as _sp

            result = _sp.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            adb_server_ok = result.returncode == 0
            checks.append(
                (
                    "adb server",
                    adb_server_ok,
                    "running" if adb_server_ok else result.stderr.strip(),
                )
            )

            # Count connected devices
            lines = [ln for ln in result.stdout.splitlines()[1:] if ln.strip() and "device" in ln]
            checks.append(
                (
                    "connected devices",
                    len(lines) > 0,
                    f"{len(lines)} device(s) detected",
                )
            )
        except Exception as exc:
            checks.append(("adb server", False, str(exc)))

    # ── Device connectivity ───────────────────────────────────────────────────
    if device and adb_path:
        try:
            from droidpilot.adb.client import ADBClient

            client = ADBClient()
            entry = client.get_device_entry(device)
            checks.append(
                (
                    f"device {device!r}",
                    entry.is_online,
                    f"state={entry.state} model={entry.model or 'unknown'}",
                )
            )
        except Exception as exc:
            checks.append((f"device {device!r}", False, str(exc)))

    # ── Report ───────────────────────────────────────────────────────────────
    table = Table(
        title="DroidPilot Doctor",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Check", style="white", no_wrap=True)
    table.add_column("Status", justify="center", no_wrap=True)
    table.add_column("Details", style="dim")

    all_ok = True
    for label, ok, detail in checks:
        status = "[bold green]✓ OK[/bold green]" if ok else "[bold red]✗ FAIL[/bold red]"
        table.add_row(label, status, detail)
        if not ok:
            all_ok = False

    _console.print(table)
    _console.print()

    if all_ok:
        _console.print("[bold green]All checks passed — DroidPilot is ready.[/bold green]")
        sys.exit(0)
    else:
        _err_console.print(
            "[bold red]Some checks failed.  Please resolve the issues above.[/bold red]"
        )
        sys.exit(1)


# ─── Entry point guard ────────────────────────────────────────────────────────


if __name__ == "__main__":
    cli()
