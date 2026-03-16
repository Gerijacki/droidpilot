"""
droidpilot.vision — OpenCV-based image matching for visual automation.

Public exports
--------------
TemplateMatcher
    Locate template images within device screenshots.
MatchResult
    Structured result returned by TemplateMatcher.find_detailed().
"""

from droidpilot.vision.matcher import MatchResult, TemplateMatcher

__all__ = [
    "TemplateMatcher",
    "MatchResult",
]
