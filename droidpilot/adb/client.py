"""
ADBClient — Low-level wrapper around the ``adb`` command-line tool.

This module provides a thin Python interface to the Android Debug Bridge
(ADB) binary.  All communication with ADB happens via ``subprocess``;
no third-party ADB Python library is required.

Classes
-------
ADBClient
    Manages discovery and connection to ADB devices.
DeviceNotFoundError
    Raised when the requested device cannot be found.
ADBError
    Raised when an ADB command returns a non-zero exit code.
"""

from __future__ import annotations

import subprocess
import shutil
import time
from dataclasses import dataclass, field
from typing import Optional


# ─── Exceptions ───────────────────────────────────────────────────────────────


class ADBError(Exception):
    """Raised when an ADB subprocess command fails.

    Attributes
    ----------
    returncode:
        The exit code returned by the adb process.
    stderr:
        Standard error output from the adb process.
    cmd:
        The command list that was executed.
    """

    def __init__(
        self,
        message: str,
        returncode: int = -1,
        stderr: str = "",
        cmd: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr
        self.cmd = cmd or []

    def __str__(self) -> str:
        cmd_str = " ".join(self.cmd) if self.cmd else "unknown"
        return f"ADBError (rc={self.returncode}): {self.args[0]!r}  cmd={cmd_str!r}"


class DeviceNotFoundError(ADBError):
    """Raised when the requested device serial is not in ``adb devices``."""

    def __init__(self, serial: str) -> None:
        super().__init__(f"Device {serial!r} not found or not authorised")
        self.serial = serial


# ─── Device info dataclass ────────────────────────────────────────────────────


@dataclass
class DeviceEntry:
    """A single entry from ``adb devices``."""

    serial: str
    state: str  # "device", "offline", "unauthorized", ...
    transport_id: str = ""
    product: str = ""
    model: str = ""
    device: str = ""

    @property
    def is_online(self) -> bool:
        """Return ``True`` if the device is in the ``device`` state."""
        return self.state == "device"

    def __str__(self) -> str:
        return f"{self.serial} ({self.state})"


# ─── Client ───────────────────────────────────────────────────────────────────


class ADBClient:
    """Interface to the ``adb`` command-line tool.

    Parameters
    ----------
    adb_path:
        Path to the adb binary.  Defaults to ``"adb"`` (expects it on PATH).
    timeout:
        Default timeout in seconds for ADB subprocess calls.
    """

    def __init__(
        self,
        adb_path: str = "adb",
        timeout: float = 30.0,
    ) -> None:
        self._adb_path = adb_path
        self._timeout = timeout
        self._check_adb()

    # ── Internal helpers ─────────────────────────────────────────────────────

    def _check_adb(self) -> None:
        """Verify that the adb binary is accessible."""
        if shutil.which(self._adb_path) is None:
            raise FileNotFoundError(
                f"adb binary not found at {self._adb_path!r}. "
                "Install Android platform-tools and ensure adb is on your PATH."
            )

    def _run(
        self,
        args: list[str],
        timeout: float | None = None,
        check: bool = True,
        input_data: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Execute an adb command and return the CompletedProcess result.

        Parameters
        ----------
        args:
            Arguments appended after the ``adb`` binary name.
        timeout:
            Override the default timeout.
        check:
            If ``True`` (default) raise :class:`ADBError` on non-zero exit.
        input_data:
            Optional stdin text to pipe into the process.

        Returns
        -------
        subprocess.CompletedProcess
        """
        cmd = [self._adb_path, *args]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self._timeout,
                input=input_data,
            )
        except subprocess.TimeoutExpired as exc:
            raise ADBError(
                f"adb command timed out after {timeout or self._timeout}s",
                cmd=cmd,
            ) from exc
        except OSError as exc:
            raise ADBError(f"Failed to run adb: {exc}", cmd=cmd) from exc

        if check and result.returncode != 0:
            raise ADBError(
                message=result.stderr.strip() or f"adb exited with code {result.returncode}",
                returncode=result.returncode,
                stderr=result.stderr,
                cmd=cmd,
            )
        return result

    def _serial_args(self, serial: str | None) -> list[str]:
        """Return ``["-s", serial]`` if *serial* is set, else ``[]``."""
        return ["-s", serial] if serial else []

    # ── Device discovery ─────────────────────────────────────────────────────

    def list_devices(self) -> list[str]:
        """Return a list of serial numbers of all connected devices.

        Only returns devices in the ``device`` state (i.e. authorised and
        online); offline or unauthorized devices are excluded.

        Returns
        -------
        list[str]
        """
        return [e.serial for e in self.list_device_entries() if e.is_online]

    def list_device_entries(self) -> list[DeviceEntry]:
        """Return :class:`DeviceEntry` objects for all connected devices.

        Parses the output of ``adb devices -l`` which looks like::

            List of devices attached
            emulator-5554          device product:sdk_gphone model:sdk_gphone ...
            192.168.1.10:5555      device product:...

        Returns
        -------
        list[DeviceEntry]
        """
        result = self._run(["devices", "-l"])
        entries: list[DeviceEntry] = []
        lines = result.stdout.strip().splitlines()
        # Skip the header line "List of devices attached"
        for line in lines[1:]:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial = parts[0]
            state = parts[1]
            extra: dict[str, str] = {}
            for kv in parts[2:]:
                if ":" in kv:
                    k, _, v = kv.partition(":")
                    extra[k] = v
            entry = DeviceEntry(
                serial=serial,
                state=state,
                transport_id=extra.get("transport_id", ""),
                product=extra.get("product", ""),
                model=extra.get("model", ""),
                device=extra.get("device", ""),
            )
            entries.append(entry)
        return entries

    def get_device_entry(self, serial: str) -> DeviceEntry:
        """Return the :class:`DeviceEntry` for a specific *serial*.

        Raises
        ------
        DeviceNotFoundError
            If the device is not found in the device list.
        """
        for entry in self.list_device_entries():
            if entry.serial == serial:
                return entry
        raise DeviceNotFoundError(serial)

    def first_device(self) -> str:
        """Return the serial of the first connected device.

        Raises
        ------
        DeviceNotFoundError
            If no devices are connected.
        """
        devices = self.list_devices()
        if not devices:
            raise DeviceNotFoundError("<no device>")
        return devices[0]

    # ── Raw command execution ─────────────────────────────────────────────────

    def shell(
        self,
        command: str,
        serial: str | None = None,
        timeout: float | None = None,
    ) -> str:
        """Execute a shell command on the device and return stdout.

        Parameters
        ----------
        command:
            Shell command string.
        serial:
            Target device serial.  Uses the default device if ``None``.
        timeout:
            Override the default timeout.

        Returns
        -------
        str
            The command's stdout output, stripped of trailing whitespace.
        """
        result = self._run(
            [*self._serial_args(serial), "shell", command],
            timeout=timeout,
        )
        return result.stdout.rstrip()

    def push(
        self,
        local_path: str,
        remote_path: str,
        serial: str | None = None,
    ) -> None:
        """Push a local file to the device.

        Parameters
        ----------
        local_path:
            Path to the local file.
        remote_path:
            Destination path on the device.
        serial:
            Target device serial.
        """
        self._run([*self._serial_args(serial), "push", local_path, remote_path])

    def pull(
        self,
        remote_path: str,
        local_path: str,
        serial: str | None = None,
    ) -> None:
        """Pull a file from the device to the local machine.

        Parameters
        ----------
        remote_path:
            Source path on the device.
        local_path:
            Destination path on the local machine.
        serial:
            Target device serial.
        """
        self._run([*self._serial_args(serial), "pull", remote_path, local_path])

    def connect(self, host: str, port: int = 5555) -> str:
        """Connect to a device over TCP/IP.

        Parameters
        ----------
        host:
            IP address or hostname of the device.
        port:
            ADB port (default 5555).

        Returns
        -------
        str
            The serial ``"<host>:<port>"`` of the connected device.
        """
        address = f"{host}:{port}"
        result = self._run(["connect", address])
        output = result.stdout.strip()
        if "connected" not in output.lower():
            raise ADBError(f"Failed to connect to {address}: {output}")
        return address

    def disconnect(self, serial: str | None = None) -> None:
        """Disconnect a TCP device.

        Parameters
        ----------
        serial:
            Device serial to disconnect.  Disconnects all TCP devices if ``None``.
        """
        args = ["disconnect"]
        if serial:
            args.append(serial)
        self._run(args)

    def start_server(self) -> None:
        """Start the ADB server if it is not already running."""
        self._run(["start-server"])

    def kill_server(self) -> None:
        """Kill the ADB server."""
        self._run(["kill-server"])

    def wait_for_device(self, serial: str | None = None, timeout: float = 30.0) -> None:
        """Block until a device comes online.

        Parameters
        ----------
        serial:
            Device serial to wait for.  Waits for any device if ``None``.
        timeout:
            Maximum seconds to wait.

        Raises
        ------
        ADBError
            If the device does not come online within *timeout*.
        """
        self._run(
            [*self._serial_args(serial), "wait-for-device"],
            timeout=timeout,
        )

    def version(self) -> str:
        """Return the ADB version string."""
        result = self._run(["version"])
        return result.stdout.strip()

    # ── Input events ──────────────────────────────────────────────────────────

    def tap(self, x: int, y: int, serial: str | None = None) -> None:
        """Send a tap event at (x, y)."""
        self.shell(f"input tap {x} {y}", serial=serial)

    def swipe(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration_ms: int = 300,
        serial: str | None = None,
    ) -> None:
        """Send a swipe gesture."""
        self.shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}", serial=serial)

    def type_text(self, text: str, serial: str | None = None) -> None:
        """Type text into the focused input field.

        Spaces are handled by sending individual key events; the rest is
        URL-encoded and sent via ``input text``.
        """
        import urllib.parse
        encoded = urllib.parse.quote(text, safe="")
        self.shell(f"input text '{encoded}'", serial=serial)

    def key_event(self, keycode: int, serial: str | None = None) -> None:
        """Send an Android key event."""
        self.shell(f"input keyevent {keycode}", serial=serial)

    # ── Screen capture ────────────────────────────────────────────────────────

    def screenshot(self, local_path: str, serial: str | None = None) -> None:
        """Capture the device screen and save it to *local_path*.

        Strategy:
        1. Capture to /sdcard/droidpilot_tmp_screen.png on device.
        2. Pull the file to the local machine.
        3. Remove the temp file from the device.

        Parameters
        ----------
        local_path:
            Destination path on the local machine.
        serial:
            Target device serial.
        """
        remote = "/sdcard/droidpilot_tmp_screen.png"
        self.shell(f"screencap -p {remote}", serial=serial)
        self.pull(remote, local_path, serial=serial)
        self.shell(f"rm -f {remote}", serial=serial)

    # ── App management ────────────────────────────────────────────────────────

    def open_app(self, package: str, serial: str | None = None) -> None:
        """Launch an app by its package name using a MAIN intent."""
        cmd = (
            f"monkey -p {package} -c android.intent.category.LAUNCHER 1"
        )
        self.shell(cmd, serial=serial)

    def force_stop(self, package: str, serial: str | None = None) -> None:
        """Force-stop an app."""
        self.shell(f"am force-stop {package}", serial=serial)

    def install(self, apk_path: str, serial: str | None = None) -> None:
        """Install an APK onto the device."""
        self._run([*self._serial_args(serial), "install", "-r", apk_path])

    def uninstall(self, package: str, serial: str | None = None) -> None:
        """Uninstall an app by package name."""
        self._run([*self._serial_args(serial), "uninstall", package])

    def list_packages(
        self, filter_str: str = "", serial: str | None = None
    ) -> list[str]:
        """Return a list of installed package names.

        Parameters
        ----------
        filter_str:
            Optional substring filter.
        serial:
            Target device serial.
        """
        cmd = "pm list packages"
        if filter_str:
            cmd += f" | grep {filter_str}"
        output = self.shell(cmd, serial=serial)
        packages = []
        for line in output.splitlines():
            line = line.strip()
            if line.startswith("package:"):
                packages.append(line[len("package:"):])
        return packages

    # ── Device information ────────────────────────────────────────────────────

    def get_prop(self, prop: str, serial: str | None = None) -> str:
        """Return a system property value via ``getprop``."""
        return self.shell(f"getprop {prop}", serial=serial)

    def get_info(self, serial: str | None = None) -> dict[str, str]:
        """Return a dict of device information.

        Keys: ``model``, ``manufacturer``, ``version``, ``sdk``,
              ``resolution``, ``serial``.
        """
        model = self.get_prop("ro.product.model", serial=serial)
        manufacturer = self.get_prop("ro.product.manufacturer", serial=serial)
        version = self.get_prop("ro.build.version.release", serial=serial)
        sdk = self.get_prop("ro.build.version.sdk", serial=serial)
        resolution_raw = self.shell("wm size", serial=serial)
        resolution = resolution_raw.replace("Physical size: ", "").strip()
        return {
            "model": model,
            "manufacturer": manufacturer,
            "version": version,
            "sdk": sdk,
            "resolution": resolution,
            "serial": serial or "default",
        }
