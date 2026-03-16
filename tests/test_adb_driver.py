"""
Tests for droidpilot.adb.client (ADBClient) and droidpilot.adb.device (ADBDevice).

All subprocess calls are mocked so no real ADB binary is needed.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from droidpilot.adb.client import (
    ADBClient,
    ADBError,
    DeviceEntry,
    DeviceNotFoundError,
)
from droidpilot.adb.device import ADBDevice

# ─── ADBClient fixtures / helpers ────────────────────────────────────────────


_DEVICES_OUTPUT = (
    "List of devices attached\n"
    "emulator-5554          device product:sdk_gphone model:sdk_gphone_x86"
    " device:generic_x86 transport_id:1\n"
    "192.168.1.100:5555     device product:walleye model:Pixel_2"
    " device:walleye transport_id:2\n"
)

_DEVICES_EMPTY = "List of devices attached\n"

_DEVICES_UNAUTHORIZED = """List of devices attached
emulator-5554          unauthorized
"""


def _make_completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess:
    """Build a fake CompletedProcess result."""
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.stdout = stdout
    proc.stderr = ""
    proc.returncode = returncode
    return proc


def _make_client() -> tuple[ADBClient, MagicMock]:
    """Return an ADBClient with the subprocess.run call patched."""
    with patch("shutil.which", return_value="/usr/bin/adb"):
        client = ADBClient(adb_path="adb")
    runner = MagicMock(return_value=_make_completed(""))
    client._run = runner  # type: ignore[method-assign]
    return client, runner


# ─── ADBClient construction ───────────────────────────────────────────────────


class TestADBClientConstruction:
    def test_raises_if_adb_not_on_path(self) -> None:
        with patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="adb binary"):
                ADBClient()

    def test_succeeds_when_adb_on_path(self) -> None:
        with patch("shutil.which", return_value="/usr/bin/adb"):
            client = ADBClient()
            assert client is not None


# ─── Device listing ───────────────────────────────────────────────────────────


class TestListDevices:
    def test_parses_two_devices(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_OUTPUT)
        entries = client.list_device_entries()
        assert len(entries) == 2

    def test_first_device_serial(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_OUTPUT)
        entries = client.list_device_entries()
        assert entries[0].serial == "emulator-5554"

    def test_second_device_serial(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_OUTPUT)
        entries = client.list_device_entries()
        assert entries[1].serial == "192.168.1.100:5555"

    def test_model_parsed(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_OUTPUT)
        entries = client.list_device_entries()
        assert entries[0].model == "sdk_gphone_x86"

    def test_empty_device_list(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_EMPTY)
        assert client.list_devices() == []

    def test_unauthorized_device_not_in_list_devices(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_UNAUTHORIZED)
        # list_devices() only returns online devices
        assert client.list_devices() == []

    def test_device_entry_is_online(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_OUTPUT)
        entries = client.list_device_entries()
        assert entries[0].is_online is True

    def test_unauthorized_entry_not_online(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_UNAUTHORIZED)
        entries = client.list_device_entries()
        assert entries[0].is_online is False

    def test_first_device_returns_serial(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_OUTPUT)
        serial = client.first_device()
        assert serial == "emulator-5554"

    def test_first_device_raises_when_empty(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_EMPTY)
        with pytest.raises(DeviceNotFoundError):
            client.first_device()

    def test_get_device_entry_found(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_OUTPUT)
        entry = client.get_device_entry("emulator-5554")
        assert entry.serial == "emulator-5554"

    def test_get_device_entry_not_found_raises(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed(_DEVICES_EMPTY)
        with pytest.raises(DeviceNotFoundError):
            client.get_device_entry("nope-9999")


# ─── Shell / input commands ───────────────────────────────────────────────────


class TestADBClientCommands:
    def test_tap_runs_correct_shell(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed("")
        client.tap(100, 200, serial="emu-5554")
        # Verify that "input tap 100 200" appears somewhere in the call.
        found = any("input tap 100 200" in str(c) for c in runner.call_args_list)
        assert found

    def test_swipe_runs_correct_shell(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed("")
        client.swipe(0, 0, 100, 200, 300, serial="emu-5554")
        found = any("input swipe 0 0 100 200 300" in str(c) for c in runner.call_args_list)
        assert found

    def test_key_event_runs_correct_shell(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed("")
        client.key_event(4, serial="emu-5554")
        found = any("input keyevent 4" in str(c) for c in runner.call_args_list)
        assert found

    def test_shell_returns_stdout(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed("hello world\n")
        result = client.shell("echo hello world")
        assert "hello world" in result

    def test_error_raises_adb_error(self) -> None:
        client, _ = _make_client()

        # Override _run to raise an ADBError.
        def fake_run(*a, **kw):
            raise ADBError("command failed", returncode=1)

        client._run = fake_run  # type: ignore[method-assign]
        with pytest.raises(ADBError):
            client.shell("bad command")

    def test_open_app_uses_monkey(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed("")
        client.open_app("com.example.app", serial="emu-5554")
        found = any(
            "monkey" in str(c) and "com.example.app" in str(c) for c in runner.call_args_list
        )
        assert found

    def test_get_info_returns_dict(self) -> None:
        client, runner = _make_client()
        runner.return_value = _make_completed("some-value\n")
        info = client.get_info(serial="emu-5554")
        assert isinstance(info, dict)
        assert "model" in info
        assert "version" in info
        assert "serial" in info


# ─── ADBError ────────────────────────────────────────────────────────────────


class TestADBError:
    def test_str_representation(self) -> None:
        err = ADBError("something failed", returncode=1, cmd=["adb", "shell", "echo"])
        s = str(err)
        assert "rc=1" in s
        assert "adb shell echo" in s

    def test_device_not_found_error_serial(self) -> None:
        err = DeviceNotFoundError("my-device-123")
        assert err.serial == "my-device-123"
        assert "my-device-123" in str(err)


# ─── DeviceEntry ─────────────────────────────────────────────────────────────


class TestDeviceEntry:
    def test_is_online_device_state(self) -> None:
        entry = DeviceEntry(serial="emu-5554", state="device")
        assert entry.is_online is True

    def test_is_online_offline_state(self) -> None:
        entry = DeviceEntry(serial="emu-5554", state="offline")
        assert entry.is_online is False

    def test_str_representation(self) -> None:
        entry = DeviceEntry(serial="emu-5554", state="device")
        s = str(entry)
        assert "emu-5554" in s
        assert "device" in s


# ─── ADBDevice (high-level interface) ─────────────────────────────────────────


def _make_device_with_mock_client() -> tuple[ADBDevice, MagicMock]:
    """Return an ADBDevice backed by a fully mocked ADBClient."""
    mock_client = MagicMock()
    mock_client.first_device.return_value = "emulator-5554"
    mock_client.get_device_entry.return_value = DeviceEntry(serial="emulator-5554", state="device")

    with patch("droidpilot.adb.device.ADBClient", return_value=mock_client):
        device = ADBDevice(serial="emulator-5554")

    return device, mock_client


class TestADBDevice:
    def test_serial_property(self) -> None:
        device, _ = _make_device_with_mock_client()
        assert device.serial == "emulator-5554"

    def test_tap_delegates_to_client(self) -> None:
        device, client = _make_device_with_mock_client()
        device.tap(100, 200)
        client.tap.assert_called_once_with(100, 200, serial="emulator-5554")

    def test_swipe_delegates_to_client(self) -> None:
        device, client = _make_device_with_mock_client()
        device.swipe(0, 0, 100, 200, duration_ms=500)
        client.swipe.assert_called_once_with(
            0, 0, 100, 200, duration_ms=500, serial="emulator-5554"
        )

    def test_press_back_sends_keycode_4(self) -> None:
        device, client = _make_device_with_mock_client()
        device.press_back()
        client.key_event.assert_called_once_with(4, serial="emulator-5554")

    def test_press_home_sends_keycode_3(self) -> None:
        device, client = _make_device_with_mock_client()
        device.press_home()
        client.key_event.assert_called_once_with(3, serial="emulator-5554")

    def test_open_app_delegates(self) -> None:
        device, client = _make_device_with_mock_client()
        device.open_app("com.example.app")
        client.open_app.assert_called_once_with("com.example.app", serial="emulator-5554")

    def test_screenshot_delegates(self, tmp_path) -> None:
        device, client = _make_device_with_mock_client()
        out = str(tmp_path / "screen.png")
        device.screenshot(out)
        client.screenshot.assert_called_once()

    def test_get_info_delegates(self) -> None:
        device, client = _make_device_with_mock_client()
        client.get_info.return_value = {"model": "Pixel", "version": "13"}
        info = device.get_info()
        assert info["model"] == "Pixel"

    def test_screen_size_parses_correctly(self) -> None:
        device, client = _make_device_with_mock_client()
        client.shell.return_value = "Physical size: 1080x1920"
        w, h = device.screen_size()
        assert w == 1080
        assert h == 1920

    def test_screen_size_fallback_on_bad_output(self) -> None:
        device, client = _make_device_with_mock_client()
        client.shell.return_value = "unexpected output"
        w, h = device.screen_size()
        assert w == 0
        assert h == 0

    def test_battery_level_parses(self) -> None:
        device, client = _make_device_with_mock_client()
        client.shell.return_value = "  level: 85"
        assert device.battery_level() == 85

    def test_battery_level_fallback(self) -> None:
        device, client = _make_device_with_mock_client()
        client.shell.return_value = "no match"
        assert device.battery_level() == -1

    def test_is_screen_on_awake(self) -> None:
        device, client = _make_device_with_mock_client()
        client.shell.return_value = "mWakefulness=Awake"
        assert device.is_screen_on() is True

    def test_is_screen_on_asleep(self) -> None:
        device, client = _make_device_with_mock_client()
        client.shell.return_value = "mWakefulness=Asleep"
        assert device.is_screen_on() is False

    def test_repr(self) -> None:
        device, _ = _make_device_with_mock_client()
        assert "emulator-5554" in repr(device)
