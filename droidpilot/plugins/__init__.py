"""
droidpilot.plugins — Plugin discovery and loading system.

DroidPilot's plugin system allows third-party Python packages to register
new DSL commands.  Plugins are discovered via Python packaging entry points
under the group ``"droidpilot.plugins"``, or can be loaded explicitly by
file path or Python module name.

Public exports
--------------
PluginLoader
    Discovers and loads DroidPilot plugins.
PluginManifest
    Metadata returned by a loaded plugin.
PluginError
    Raised when a plugin cannot be loaded or is invalid.
"""

from droidpilot.plugins.plugin_loader import PluginError, PluginLoader, PluginManifest

__all__ = [
    "PluginLoader",
    "PluginManifest",
    "PluginError",
]
