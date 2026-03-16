"""
Tests for droidpilot.actions (tap, swipe, text, app, screenshot).

All device calls are mocked so no physical ADB device is required.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from droidpilot.actions.app import (
    force_stop_app,
    get_version,
    install_apk,
    is_installed,
    is_running,
    open_app,
    restart_app,
    uninstall_app,
)
from droidpilot.actions.screenshot import (
    capture_screenshot,
    capture_timestamped,
    capture_to_bytes,
)
from droidpilot.actions.swipe import (
    fling_down,
    fling_up,
    horizontal_swipe_left,
    horizontal_swipe_right,
    scroll_down,
    scroll_up,
    swipe,
)
from droidpilot.actions.tap import (
    double_tap,
    long_press,
    tap,
    tap_sequence,
)
from droidpilot.actions.text import (
    clear_field,
    press_backspace,
    press_enter,
    press_tab,
    type_line,
    type_text,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────


def _mock_device() -> MagicMock:
    """Return a MagicMock that behaves like an ADBDevice."""
    dev = MagicMock()
    dev.screen_size.return_value = (1080, 1920)
    dev.serial = "emulator-5554"
    return dev


# ─── tap ──────────────────────────────────────────────────────────────────────


class TestTap:
    def test_calls_device_tap(self) -> None:
        dev = _mock_device()
        tap(dev, 100, 200)
        dev.tap.assert_called_once_with(100, 200)

    def test_negative_x_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError, match="non-negative"):
            tap(dev, -1, 200)

    def test_negative_y_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError, match="non-negative"):
            tap(dev, 100, -5)

    def test_pre_post_delay(self) -> None:
        import time

        dev = _mock_device()
        start = time.monotonic()
        tap(dev, 100, 200, pre_delay=0.05, post_delay=0.05)
        elapsed = time.monotonic() - start
        assert elapsed >= 0.09  # allow small timing tolerance

    def test_zero_coordinates(self) -> None:
        dev = _mock_device()
        tap(dev, 0, 0)
        dev.tap.assert_called_once_with(0, 0)


class TestLongPress:
    def test_calls_device_long_press(self) -> None:
        dev = _mock_device()
        long_press(dev, 540, 960, duration_ms=800)
        dev.long_press.assert_called_once_with(540, 960, duration_ms=800)

    def test_negative_coords_raise(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError):
            long_press(dev, -1, 0)

    def test_zero_duration_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError):
            long_press(dev, 100, 200, duration_ms=0)

    def test_negative_duration_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError):
            long_press(dev, 100, 200, duration_ms=-100)


class TestDoubleTap:
    def test_calls_tap_twice(self) -> None:
        dev = _mock_device()
        double_tap(dev, 300, 400)
        assert dev.tap.call_count == 2
        dev.tap.assert_any_call(300, 400)

    def test_negative_coords_raise(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError):
            double_tap(dev, -1, 400)


class TestTapSequence:
    def test_taps_all_coordinates(self) -> None:
        dev = _mock_device()
        coords = [(100, 200), (300, 400), (500, 600)]
        tap_sequence(dev, coords, interval=0.0)
        assert dev.tap.call_count == 3
        dev.tap.assert_any_call(100, 200)
        dev.tap.assert_any_call(300, 400)
        dev.tap.assert_any_call(500, 600)

    def test_empty_sequence(self) -> None:
        dev = _mock_device()
        tap_sequence(dev, [], interval=0.0)
        dev.tap.assert_not_called()


# ─── swipe ────────────────────────────────────────────────────────────────────


class TestSwipe:
    def test_calls_device_swipe(self) -> None:
        dev = _mock_device()
        swipe(dev, 100, 200, 300, 400, 500)
        dev.swipe.assert_called_once_with(100, 200, 300, 400, duration_ms=500)

    def test_negative_x1_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError):
            swipe(dev, -1, 0, 100, 200)

    def test_negative_duration_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError):
            swipe(dev, 0, 0, 100, 200, -1)

    def test_zero_duration_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError):
            swipe(dev, 0, 0, 100, 200, 0)


class TestScrollActions:
    def test_scroll_down_calls_swipe(self) -> None:
        dev = _mock_device()
        scroll_down(dev, steps=3)
        assert dev.swipe.call_count == 3

    def test_scroll_up_calls_swipe(self) -> None:
        dev = _mock_device()
        scroll_up(dev, steps=2)
        assert dev.swipe.call_count == 2

    def test_fling_down_calls_swipe(self) -> None:
        dev = _mock_device()
        fling_down(dev)
        dev.swipe.assert_called_once()

    def test_fling_up_calls_swipe(self) -> None:
        dev = _mock_device()
        fling_up(dev)
        dev.swipe.assert_called_once()

    def test_horizontal_swipe_left(self) -> None:
        dev = _mock_device()
        horizontal_swipe_left(dev)
        dev.swipe.assert_called_once()

    def test_horizontal_swipe_right(self) -> None:
        dev = _mock_device()
        horizontal_swipe_right(dev)
        dev.swipe.assert_called_once()

    def test_scroll_down_fallback_on_screen_size_error(self) -> None:
        dev = _mock_device()
        dev.screen_size.side_effect = Exception("no device")
        scroll_down(dev, steps=1)  # Should not raise; falls back to defaults.
        assert dev.swipe.call_count == 1


# ─── text ─────────────────────────────────────────────────────────────────────


class TestTypeText:
    def test_calls_device_type_text(self) -> None:
        dev = _mock_device()
        type_text(dev, "hello")
        dev.type_text.assert_called_once_with("hello")

    def test_empty_string_skipped(self) -> None:
        dev = _mock_device()
        type_text(dev, "")
        dev.type_text.assert_not_called()


class TestTypeLine:
    def test_types_text_then_enter(self) -> None:
        dev = _mock_device()
        type_line(dev, "search query")
        dev.type_text.assert_called_once_with("search query")
        dev.key_event.assert_called_once_with(66)  # ENTER keycode


class TestPressMethods:
    def test_press_enter(self) -> None:
        dev = _mock_device()
        press_enter(dev)
        dev.key_event.assert_called_once_with(66)

    def test_press_backspace_once(self) -> None:
        dev = _mock_device()
        press_backspace(dev, count=1)
        dev.key_event.assert_called_once_with(67)

    def test_press_backspace_multiple(self) -> None:
        dev = _mock_device()
        press_backspace(dev, count=5)
        assert dev.key_event.call_count == 5

    def test_press_backspace_zero_does_nothing(self) -> None:
        dev = _mock_device()
        press_backspace(dev, count=0)
        dev.key_event.assert_not_called()

    def test_press_tab(self) -> None:
        dev = _mock_device()
        press_tab(dev)
        dev.key_event.assert_called_once_with(61)


class TestClearField:
    def test_clear_calls_shell(self) -> None:
        dev = _mock_device()
        clear_field(dev)
        assert dev.shell.call_count >= 1


# ─── app ──────────────────────────────────────────────────────────────────────


class TestAppActions:
    def test_open_app_calls_device(self) -> None:
        dev = _mock_device()
        open_app(dev, "com.example.app")
        dev.open_app.assert_called_once_with("com.example.app")

    def test_open_app_empty_package_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError):
            open_app(dev, "")

    def test_force_stop_calls_device(self) -> None:
        dev = _mock_device()
        force_stop_app(dev, "com.example.app")
        dev.force_stop.assert_called_once_with("com.example.app")

    def test_force_stop_empty_package_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(ValueError):
            force_stop_app(dev, "")

    def test_restart_app_stops_then_opens(self) -> None:
        dev = _mock_device()
        restart_app(dev, "com.example.app", delay=0.0)
        dev.force_stop.assert_called_once_with("com.example.app")
        dev.open_app.assert_called_once_with("com.example.app")

    def test_install_apk_file_not_found(self) -> None:
        dev = _mock_device()
        with pytest.raises(FileNotFoundError):
            install_apk(dev, "/nonexistent/file.apk")

    def test_install_apk_calls_device(self, tmp_path) -> None:
        apk = tmp_path / "test.apk"
        apk.write_bytes(b"PK fake apk")
        dev = _mock_device()
        install_apk(dev, str(apk))
        dev.install.assert_called_once()

    def test_uninstall_calls_device(self) -> None:
        dev = _mock_device()
        uninstall_app(dev, "com.example.app")
        dev.uninstall.assert_called_once_with("com.example.app")

    def test_is_installed_true(self) -> None:
        dev = _mock_device()
        dev.is_installed.return_value = True
        assert is_installed(dev, "com.example.app") is True

    def test_is_installed_false(self) -> None:
        dev = _mock_device()
        dev.is_installed.return_value = False
        assert is_installed(dev, "com.example.app") is False

    def test_is_running_true(self) -> None:
        dev = _mock_device()
        dev.shell.return_value = "12345"
        assert is_running(dev, "com.example.app") is True

    def test_is_running_false(self) -> None:
        dev = _mock_device()
        dev.shell.return_value = ""
        assert is_running(dev, "com.example.app") is False

    def test_get_version_found(self) -> None:
        dev = _mock_device()
        dev.shell.return_value = "  versionName=1.2.3\n"
        version = get_version(dev, "com.example.app")
        assert version == "1.2.3"

    def test_get_version_not_found(self) -> None:
        dev = _mock_device()
        dev.shell.return_value = ""
        assert get_version(dev, "com.example.app") == ""


# ─── screenshot ───────────────────────────────────────────────────────────────


class TestScreenshotActions:
    def test_capture_screenshot_calls_device(self, tmp_path) -> None:
        dev = _mock_device()
        dev.screenshot.return_value = str(tmp_path / "out.png")
        result = capture_screenshot(dev, str(tmp_path / "out.png"))
        dev.screenshot.assert_called_once()
        assert result

    def test_capture_screenshot_missing_dir_raises(self) -> None:
        dev = _mock_device()
        with pytest.raises(OSError):
            capture_screenshot(dev, "/nonexistent/dir/out.png")

    def test_capture_to_bytes_returns_bytes(self, tmp_path) -> None:
        fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
        dev = _mock_device()

        def fake_screenshot(path: str) -> None:
            Path(path).write_bytes(fake_png)

        dev.screenshot.side_effect = fake_screenshot
        data = capture_to_bytes(dev)
        assert isinstance(data, bytes)
        assert data == fake_png

    def test_capture_timestamped_creates_file(self, tmp_path) -> None:
        dev = _mock_device()
        dev.screenshot.return_value = str(tmp_path / "snap.png")
        # capture_screenshot will call dev.screenshot — mock it to work.
        result = capture_timestamped(dev, directory=str(tmp_path))
        dev.screenshot.assert_called_once()
        assert "screenshot_" in result or str(tmp_path) in result
