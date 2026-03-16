"""
droidpilot.cli — Command-line interface for DroidPilot.

The CLI is implemented with Click and exposes the ``droidpilot`` command
group.  Sub-commands are defined in :mod:`droidpilot.cli.main`.
"""

from droidpilot.cli.main import cli

__all__ = ["cli"]
