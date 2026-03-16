"""
droidpilot.actions.app — App lifecycle management actions.

Provides functions for launching, stopping, installing, and querying
Android applications via ADB.

Functions
---------
open_app(device, package)
    Launch an app by package name.
force_stop_app(device, package)
    Force-stop a running app.
restart_app(device, package, delay)
    Force-stop and re-launch an app.
install_apk(device, apk_path)
    Install an APK onto the device.
uninstall_app(device, package)
    Uninstall an app from the device.
is_installed(device, package)
    Check whether an app is installed.
is_running(device, package)
    Check whether an app process is currently running.
get_version(device, package)
    Return the versionName of an installed package.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from droidpilot.adb.device import ADBDevice

logger = logging.getLogger("droidpilot.actions.app")


def open_app(device: "ADBDevice", package: str) -> None:
    """Launch *package* using an implicit MAIN intent.

    Uses ``monkey -p <package> -c android.intent.category.LAUNCHER 1``
    to trigger the launcher intent without requiring a specific activity
    name.

    Parameters
    ----------
    device:
        The target device.
    package:
        Android package name (e.g. ``"com.instagram.android"``).

    Raises
    ------
    ValueError
        If *package* is empty.
    """
    if not package:
        raise ValueError("package must not be empty")

    logger.info(f"[open_app] launching {package!r}")
    device.open_app(package)


def force_stop_app(device: "ADBDevice", package: str) -> None:
    """Force-stop *package*.

    Equivalent to ``adb shell am force-stop <package>``.

    Parameters
    ----------
    device:
        The target device.
    package:
        Android package name.
    """
    if not package:
        raise ValueError("package must not be empty")

    logger.info(f"[force_stop_app] stopping {package!r}")
    device.force_stop(package)


def restart_app(
    device: "ADBDevice",
    package: str,
    delay: float = 1.0,
) -> None:
    """Force-stop *package*, wait *delay* seconds, then relaunch it.

    Parameters
    ----------
    device:
        The target device.
    package:
        Android package name.
    delay:
        Seconds to wait between stopping and relaunching.
    """
    logger.info(f"[restart_app] restarting {package!r} (delay={delay}s)")
    force_stop_app(device, package)
    time.sleep(delay)
    open_app(device, package)


def install_apk(device: "ADBDevice", apk_path: str) -> None:
    """Install an APK file onto the device.

    Calls ``adb install -r <apk_path>``.  The ``-r`` flag allows
    reinstallation of existing packages.

    Parameters
    ----------
    device:
        The target device.
    apk_path:
        Local path to the APK file.

    Raises
    ------
    FileNotFoundError
        If the APK file does not exist.
    """
    from pathlib import Path

    path = Path(apk_path)
    if not path.exists():
        raise FileNotFoundError(f"APK file not found: {apk_path!r}")

    logger.info(f"[install_apk] installing {apk_path!r}")
    device.install(str(path))
    logger.info(f"[install_apk] installation complete")


def uninstall_app(device: "ADBDevice", package: str) -> None:
    """Uninstall *package* from the device.

    Parameters
    ----------
    device:
        The target device.
    package:
        Android package name.
    """
    logger.info(f"[uninstall_app] uninstalling {package!r}")
    device.uninstall(package)


def is_installed(device: "ADBDevice", package: str) -> bool:
    """Return ``True`` if *package* is installed on the device.

    Parameters
    ----------
    device:
        The target device.
    package:
        Android package name.

    Returns
    -------
    bool
    """
    result = device.is_installed(package)
    logger.debug(f"[is_installed] {package!r} → {result}")
    return result


def is_running(device: "ADBDevice", package: str) -> bool:
    """Return ``True`` if *package*'s process is currently running.

    Uses ``dumpsys activity`` to check for the process.

    Parameters
    ----------
    device:
        The target device.
    package:
        Android package name.

    Returns
    -------
    bool
    """
    output = device.shell(f"pidof {package}")
    running = bool(output.strip())
    logger.debug(f"[is_running] {package!r} → {running}")
    return running


def get_version(device: "ADBDevice", package: str) -> str:
    """Return the ``versionName`` of the installed *package*.

    Parameters
    ----------
    device:
        The target device.
    package:
        Android package name.

    Returns
    -------
    str
        The versionName string, or an empty string if not found.
    """
    output = device.shell(f"dumpsys package {package} | grep versionName")
    for line in output.splitlines():
        line = line.strip()
        if "versionName=" in line:
            return line.split("versionName=", 1)[-1].split()[0]
    return ""
