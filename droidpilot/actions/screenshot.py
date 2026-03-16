"""
droidpilot.actions.screenshot — Screenshot capture and analysis utilities.

Provides functions for capturing device screenshots and optionally
performing basic analysis (image dimensions, file size, etc.).

Functions
---------
capture_screenshot(device, output_path)
    Capture and save a screenshot to a local path.
capture_to_bytes(device)
    Capture a screenshot and return it as raw bytes.
capture_timestamped(device, directory, prefix)
    Capture a screenshot with an auto-generated timestamped filename.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from droidpilot.adb.device import ADBDevice

logger = logging.getLogger("droidpilot.actions.screenshot")


def capture_screenshot(
    device: "ADBDevice",
    output_path: str = "screenshot.png",
) -> str:
    """Capture the device screen and save it to *output_path*.

    Parameters
    ----------
    device:
        The target :class:`~droidpilot.adb.device.ADBDevice`.
    output_path:
        Destination file path on the local machine.  The parent
        directory must exist.

    Returns
    -------
    str
        The resolved absolute path of the saved screenshot.

    Raises
    ------
    OSError
        If the output directory does not exist.
    droidpilot.adb.client.ADBError
        If the ADB screencap command fails.
    """
    out = Path(output_path)
    if not out.parent.exists():
        raise OSError(f"Output directory does not exist: {out.parent}")

    logger.info(f"[screenshot] capturing → {output_path!r}")
    saved = device.screenshot(str(out))
    logger.info(f"[screenshot] saved: {saved!r}")
    return saved


def capture_to_bytes(device: "ADBDevice") -> bytes:
    """Capture a screenshot and return it as raw PNG bytes.

    Uses a temporary file internally; the file is deleted after reading.

    Parameters
    ----------
    device:
        The target device.

    Returns
    -------
    bytes
        Raw PNG image data.
    """
    import tempfile

    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        device.screenshot(tmp_path)
        data = Path(tmp_path).read_bytes()
    finally:
        try:
            Path(tmp_path).unlink()
        except OSError:
            pass

    logger.debug(f"[screenshot] captured {len(data)} bytes")
    return data


def capture_timestamped(
    device: "ADBDevice",
    directory: str = ".",
    prefix: str = "screenshot",
) -> str:
    """Capture a screenshot with an auto-generated timestamped filename.

    The filename format is: ``<prefix>_YYYYMMDD_HHMMSS.png``.

    Parameters
    ----------
    device:
        The target device.
    directory:
        Directory where the screenshot will be saved.
    prefix:
        Filename prefix (default ``"screenshot"``).

    Returns
    -------
    str
        The path to the saved screenshot file.
    """
    from datetime import datetime

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{prefix}_{ts}.png"
    out_path = str(Path(directory) / filename)

    return capture_screenshot(device, out_path)


def get_image_dimensions(image_path: str) -> tuple[int, int]:
    """Return the (width, height) of a PNG image.

    Parameters
    ----------
    image_path:
        Path to a PNG file.

    Returns
    -------
    tuple[int, int]
        (width, height) in pixels.

    Raises
    ------
    ImportError
        If OpenCV is not installed.
    FileNotFoundError
        If the image does not exist.
    """
    try:
        import cv2
    except ImportError as exc:
        raise ImportError(
            "OpenCV is required for get_image_dimensions. "
            "Install it with: pip install opencv-python"
        ) from exc

    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {image_path!r}")

    img = cv2.imread(str(path))
    if img is None:
        raise ValueError(f"Cannot read image: {image_path!r}")

    h, w = img.shape[:2]
    return w, h
