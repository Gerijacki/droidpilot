"""
TemplateMatcher — OpenCV-based template image matching.

Provides utilities for locating a template image within a larger screenshot
using OpenCV's ``matchTemplate`` function with the ``TM_CCOEFF_NORMED``
method (Normalised Cross-Correlation Coefficient).

Classes
-------
MatchResult
    Structured result of a single template match attempt.
TemplateMatcher
    Configurable template matcher with threshold control.

Usage::

    from droidpilot.vision.matcher import TemplateMatcher

    matcher = TemplateMatcher(threshold=0.85)
    found, location, score = matcher.find("screenshot.png", "button.png")
    if found:
        x, y = location
        print(f"Found at ({x}, {y}) with score {score:.3f}")
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger("droidpilot.vision")


# ─── Result dataclass ─────────────────────────────────────────────────────────


@dataclass
class MatchResult:
    """Result of a single template matching operation.

    Attributes
    ----------
    found:
        Whether the template was found above the confidence threshold.
    location:
        (x, y) pixel coordinate of the **centre** of the best match,
        or ``None`` if not found.
    score:
        Match confidence in [0.0, 1.0] for TM_CCOEFF_NORMED.
    template_path:
        Path to the template image file.
    screen_path:
        Path to the screenshot that was searched.
    all_matches:
        All match locations above the threshold (useful for multi-tap).
    """

    found: bool
    location: tuple[int, int] | None
    score: float
    template_path: str
    screen_path: str
    all_matches: list[tuple[int, int]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.all_matches is None:
            self.all_matches = []

    def __bool__(self) -> bool:
        return self.found

    def __repr__(self) -> str:
        status = f"found at {self.location}" if self.found else "not found"
        return f"MatchResult({status}, score={self.score:.3f}, " f"template={self.template_path!r})"


# ─── Matcher ──────────────────────────────────────────────────────────────────


class TemplateMatcher:
    """Locate template images within device screenshots using OpenCV.

    Parameters
    ----------
    threshold:
        Minimum match confidence (0.0–1.0).  Values below this are
        treated as no match.  Default is ``0.8``.
    method:
        OpenCV template matching method constant.  Defaults to
        ``cv2.TM_CCOEFF_NORMED`` (value 5).
    grayscale:
        If ``True`` images are converted to grayscale before matching,
        which is faster and often more reliable.
    """

    _TM_CCOEFF_NORMED = 5  # cv2.TM_CCOEFF_NORMED constant

    def __init__(
        self,
        threshold: float = 0.8,
        method: int | None = None,
        grayscale: bool = True,
    ) -> None:
        if not (0.0 <= threshold <= 1.0):
            raise ValueError(f"threshold must be in [0.0, 1.0], got {threshold}")
        self.threshold = threshold
        self.grayscale = grayscale
        self._method = method if method is not None else self._TM_CCOEFF_NORMED
        self._cv2 = self._import_cv2()
        self._np = self._import_numpy()

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _import_cv2() -> Any:
        """Import OpenCV, raising a helpful error if not installed."""
        try:
            import cv2

            return cv2
        except ImportError as exc:
            raise ImportError(
                "OpenCV is required for image matching. "
                "Install it with: pip install opencv-python"
            ) from exc

    @staticmethod
    def _import_numpy() -> Any:
        """Import NumPy, raising a helpful error if not installed."""
        try:
            import numpy as np

            return np
        except ImportError as exc:
            raise ImportError(
                "NumPy is required for image matching. " "Install it with: pip install numpy"
            ) from exc

    def _load_image(self, path: str, grayscale: bool = False) -> Any:
        """Load an image from *path* with optional grayscale conversion.

        Parameters
        ----------
        path:
            Path to an image file (PNG, JPEG, etc.)
        grayscale:
            Convert to grayscale after loading.

        Raises
        ------
        FileNotFoundError
            If the file does not exist.
        ValueError
            If OpenCV cannot read the file (corrupt or unsupported format).
        """
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"Image file not found: {path!r}")
        flag = self._cv2.IMREAD_GRAYSCALE if grayscale else self._cv2.IMREAD_COLOR
        img = self._cv2.imread(str(file_path), flag)
        if img is None:
            raise ValueError(f"OpenCV could not read image: {path!r}")
        return img

    def _centre_of_match(
        self,
        top_left: tuple[int, int],
        template_shape: tuple[int, ...],
    ) -> tuple[int, int]:
        """Return the centre pixel of a match given the top-left corner."""
        h, w = template_shape[:2]
        cx = top_left[0] + w // 2
        cy = top_left[1] + h // 2
        return (cx, cy)

    # ── Public API ────────────────────────────────────────────────────────────

    def find(
        self,
        screen_path: str,
        template_path: str,
    ) -> tuple[bool, tuple[int, int] | None, float]:
        """Search for *template_path* in *screen_path*.

        Parameters
        ----------
        screen_path:
            Path to the full-device screenshot.
        template_path:
            Path to the template image to search for.

        Returns
        -------
        tuple[bool, tuple[int, int] | None, float]
            ``(found, (cx, cy), score)`` where *found* is True if the
            template was matched above the threshold, *(cx, cy)* is the
            centre of the best match (or ``None``), and *score* is the
            confidence value.
        """
        result = self.find_detailed(screen_path, template_path)
        return result.found, result.location, result.score

    def find_detailed(
        self,
        screen_path: str,
        template_path: str,
    ) -> MatchResult:
        """Like :meth:`find` but returns a full :class:`MatchResult`.

        Parameters
        ----------
        screen_path:
            Path to the device screenshot.
        template_path:
            Path to the template image.

        Returns
        -------
        MatchResult
        """
        screen = self._load_image(screen_path, grayscale=self.grayscale)
        template = self._load_image(template_path, grayscale=self.grayscale)

        t_h, t_w = template.shape[:2]
        s_h, s_w = screen.shape[:2]

        if t_h > s_h or t_w > s_w:
            logger.warning(
                f"Template ({t_w}x{t_h}) is larger than screen ({s_w}x{s_h}); " "no match possible."
            )
            return MatchResult(
                found=False,
                location=None,
                score=0.0,
                template_path=template_path,
                screen_path=screen_path,
            )

        result_map = self._cv2.matchTemplate(screen, template, self._method)
        _, max_val, _, max_loc = self._cv2.minMaxLoc(result_map)

        score = float(max_val)
        found = score >= self.threshold
        location: tuple[int, int] | None = None

        if found:
            location = self._centre_of_match(max_loc, template.shape)
            logger.debug(
                f"[matcher] found {template_path!r} at {location} "
                f"score={score:.3f} threshold={self.threshold}"
            )
        else:
            logger.debug(
                f"[matcher] {template_path!r} not found "
                f"(best score={score:.3f} < threshold={self.threshold})"
            )

        return MatchResult(
            found=found,
            location=location,
            score=score,
            template_path=template_path,
            screen_path=screen_path,
        )

    def find_all(
        self,
        screen_path: str,
        template_path: str,
        max_results: int = 50,
    ) -> list[tuple[int, int]]:
        """Find all locations of *template_path* in *screen_path*.

        Uses non-maximum suppression to avoid returning overlapping matches.

        Parameters
        ----------
        screen_path:
            Path to the device screenshot.
        template_path:
            Path to the template image.
        max_results:
            Maximum number of matches to return.

        Returns
        -------
        list[tuple[int, int]]
            List of centre (x, y) coordinates for each match.
        """
        screen = self._load_image(screen_path, grayscale=self.grayscale)
        template = self._load_image(template_path, grayscale=self.grayscale)

        t_h, t_w = template.shape[:2]
        s_h, s_w = screen.shape[:2]

        if t_h > s_h or t_w > s_w:
            return []

        result_map = self._cv2.matchTemplate(screen, template, self._method)
        locations_y, locations_x = self._np.where(result_map >= self.threshold)

        centres: list[tuple[int, int]] = []
        seen: set[tuple[int, int]] = set()

        for pt_y, pt_x in zip(locations_y, locations_x):
            centre = self._centre_of_match((int(pt_x), int(pt_y)), template.shape)
            # Simple deduplication: skip if within 10px of an existing match.
            duplicate = any(abs(centre[0] - s[0]) < 10 and abs(centre[1] - s[1]) < 10 for s in seen)
            if not duplicate:
                centres.append(centre)
                seen.add(centre)
                if len(centres) >= max_results:
                    break

        logger.debug(f"[matcher] find_all {template_path!r}: {len(centres)} match(es)")
        return centres

    def compare(self, image_path_a: str, image_path_b: str) -> float:
        """Compute a similarity score between two images.

        The images are resized to the same dimensions if necessary.
        Uses normalised cross-correlation on grayscale versions.

        Parameters
        ----------
        image_path_a:
            Path to the first image.
        image_path_b:
            Path to the second image.

        Returns
        -------
        float
            Similarity score in [0.0, 1.0].
        """
        img_a = self._load_image(image_path_a, grayscale=True)
        img_b = self._load_image(image_path_b, grayscale=True)

        # Resize b to match a's dimensions.
        if img_a.shape != img_b.shape:
            h, w = img_a.shape[:2]
            img_b = self._cv2.resize(img_b, (w, h))

        result = self._cv2.matchTemplate(img_a, img_b, self._cv2.TM_CCOEFF_NORMED)
        return float(result[0][0])
