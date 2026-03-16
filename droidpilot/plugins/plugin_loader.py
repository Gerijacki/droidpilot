"""
DroidPilot Plugin Loader.

Discovers, validates, and loads plugins that extend the DroidPilot DSL
with custom commands.

Plugin Contract
---------------
A plugin is a Python module or package that exposes either:

1. A ``register(context: ExecutionContext) -> None`` function that registers
   commands directly via ``context.register_command(...)``.

   Example::

       # my_plugin/__init__.py
       from droidpilot.core.context import ExecutionContext

       def register(context: ExecutionContext) -> None:
           context.register_command("my_cmd", _my_cmd_impl)

       def _my_cmd_impl(ctx: ExecutionContext, arg: str) -> None:
           ctx.device.shell(f"echo {arg}")

2. A ``COMMANDS`` dict mapping command names to callables::

       # another_plugin.py
       COMMANDS = {
           "greet": lambda ctx, name: ctx.console.print(f"Hello {name}!"),
       }

Discovery
---------
Plugins can be discovered in three ways:

a) Python entry points under the group ``"droidpilot.plugins"``.
b) By explicit Python import path via :meth:`PluginLoader.load_module`.
c) By file system path via :meth:`PluginLoader.load_file`.
"""

from __future__ import annotations

import importlib
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from droidpilot.core.context import ExecutionContext

logger = logging.getLogger("droidpilot.plugins")


# ─── Exceptions ───────────────────────────────────────────────────────────────


class PluginError(Exception):
    """Raised when a plugin cannot be loaded or fails validation."""


# ─── Plugin manifest ──────────────────────────────────────────────────────────


@dataclass
class PluginManifest:
    """Metadata about a successfully loaded plugin.

    Attributes
    ----------
    name:
        The plugin's name (entry-point name or module name).
    module_path:
        The Python dotted module path or file path that was loaded.
    commands:
        Mapping of command names registered by this plugin.
    version:
        Plugin version string (from ``__version__`` attribute if present).
    description:
        Short description (from ``__doc__`` if present).
    """

    name: str
    module_path: str
    commands: dict[str, Callable[..., Any]] = field(default_factory=dict)
    version: str = "unknown"
    description: str = ""

    def __repr__(self) -> str:
        cmds = ", ".join(self.commands.keys())
        return (
            f"PluginManifest(name={self.name!r}, "
            f"commands=[{cmds}], "
            f"version={self.version!r})"
        )


# ─── Loader ───────────────────────────────────────────────────────────────────


class PluginLoader:
    """Discovers and loads DroidPilot plugins.

    Parameters
    ----------
    context:
        The :class:`~droidpilot.core.context.ExecutionContext` into which
        discovered commands will be registered.
    """

    #: The entry-point group name used for automatic discovery.
    ENTRY_POINT_GROUP = "droidpilot.plugins"

    def __init__(self, context: "ExecutionContext") -> None:
        self._context = context
        self._loaded: dict[str, PluginManifest] = {}

    # ── Public API ────────────────────────────────────────────────────────────

    def discover_and_load(self) -> list[PluginManifest]:
        """Discover all installed plugins via entry points and load them.

        Uses :mod:`importlib.metadata` to enumerate packages that declare
        entry points in the ``"droidpilot.plugins"`` group.

        Returns
        -------
        list[PluginManifest]
            Manifests of all successfully loaded plugins.
        """
        manifests: list[PluginManifest] = []

        try:
            from importlib.metadata import entry_points

            eps = entry_points(group=self.ENTRY_POINT_GROUP)
        except Exception as exc:
            logger.warning(f"[plugins] entry-point discovery failed: {exc}")
            return manifests

        for ep in eps:
            try:
                manifest = self._load_entry_point(ep)
                manifests.append(manifest)
                logger.info(
                    f"[plugins] loaded {manifest.name!r} — "
                    f"{len(manifest.commands)} command(s)"
                )
            except PluginError as exc:
                logger.error(f"[plugins] failed to load {ep.name!r}: {exc}")

        return manifests

    def load_module(self, module_path: str, name: str | None = None) -> PluginManifest:
        """Load a plugin from a Python dotted module path.

        Parameters
        ----------
        module_path:
            Dotted import path, e.g. ``"my_package.droidpilot_plugin"``.
        name:
            Optional override for the plugin name.  Defaults to the last
            component of *module_path*.

        Returns
        -------
        PluginManifest

        Raises
        ------
        PluginError
            If the module cannot be imported or has no recognisable plugin API.
        """
        plugin_name = name or module_path.rsplit(".", 1)[-1]

        if plugin_name in self._loaded:
            logger.debug(f"[plugins] {plugin_name!r} already loaded — skipping")
            return self._loaded[plugin_name]

        try:
            module = importlib.import_module(module_path)
        except ImportError as exc:
            raise PluginError(
                f"Cannot import plugin module {module_path!r}: {exc}"
            ) from exc

        return self._activate(module, plugin_name, module_path)

    def load_file(self, file_path: str, name: str | None = None) -> PluginManifest:
        """Load a plugin from a Python source file.

        The file is imported as a standalone module using
        :func:`importlib.util.spec_from_file_location`.

        Parameters
        ----------
        file_path:
            Path to a ``.py`` plugin source file.
        name:
            Optional plugin name.  Defaults to the file stem.

        Returns
        -------
        PluginManifest

        Raises
        ------
        PluginError
            If the file cannot be loaded or has no recognisable plugin API.
        FileNotFoundError
            If the file does not exist.
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Plugin file not found: {file_path!r}")

        plugin_name = name or path.stem

        if plugin_name in self._loaded:
            logger.debug(f"[plugins] {plugin_name!r} already loaded — skipping")
            return self._loaded[plugin_name]

        spec = importlib.util.spec_from_file_location(plugin_name, str(path))
        if spec is None or spec.loader is None:
            raise PluginError(
                f"Cannot create module spec for plugin file {file_path!r}"
            )

        module = importlib.util.module_from_spec(spec)
        sys.modules[plugin_name] = module

        try:
            spec.loader.exec_module(module)  # type: ignore[union-attr]
        except Exception as exc:
            del sys.modules[plugin_name]
            raise PluginError(
                f"Error executing plugin file {file_path!r}: {exc}"
            ) from exc

        return self._activate(module, plugin_name, str(path))

    @property
    def loaded_plugins(self) -> dict[str, PluginManifest]:
        """Read-only mapping of loaded plugin name → manifest."""
        return dict(self._loaded)

    def unload(self, name: str) -> bool:
        """Unload a plugin by name.

        Commands registered by this plugin are NOT unregistered from the
        context (that would require context support for deregistration).
        This method only removes the plugin from the internal registry.

        Parameters
        ----------
        name:
            Plugin name to unload.

        Returns
        -------
        bool
            ``True`` if the plugin was found and removed, ``False`` if not found.
        """
        if name in self._loaded:
            del self._loaded[name]
            logger.info(f"[plugins] unloaded {name!r}")
            return True
        return False

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _load_entry_point(self, ep: Any) -> PluginManifest:
        """Load a single entry-point into the context.

        Parameters
        ----------
        ep:
            An :class:`importlib.metadata.EntryPoint` instance.

        Returns
        -------
        PluginManifest

        Raises
        ------
        PluginError
        """
        try:
            obj = ep.load()
        except Exception as exc:
            raise PluginError(f"Failed to load entry point: {exc}") from exc

        # Entry point can point to a module or a callable.
        if callable(obj):
            # It's a register-function style plugin.
            module_name = getattr(obj, "__module__", ep.name)
            module = sys.modules.get(module_name)
            if module is None:
                # Create a synthetic module.
                import types
                module = types.ModuleType(module_name)
                module.register = obj  # type: ignore[attr-defined]
        else:
            module = obj

        return self._activate(module, ep.name, ep.value)

    def _activate(
        self,
        module: Any,
        name: str,
        module_path: str,
    ) -> PluginManifest:
        """Extract commands from *module* and register them into the context.

        Supports two plugin styles:

        1. ``module.register(ctx)`` — called with the execution context.
        2. ``module.COMMANDS`` — dict of ``name → callable``.

        Parameters
        ----------
        module:
            The loaded Python module object.
        name:
            Plugin name.
        module_path:
            The dotted path or file path used for display.

        Returns
        -------
        PluginManifest

        Raises
        ------
        PluginError
            If the module exposes neither ``register`` nor ``COMMANDS``.
        """
        manifest = PluginManifest(
            name=name,
            module_path=module_path,
            version=getattr(module, "__version__", "unknown"),
            description=(module.__doc__ or "").strip().split("\n")[0],
        )

        # Style 1: COMMANDS dict
        commands_dict: dict[str, Callable[..., Any]] | None = getattr(
            module, "COMMANDS", None
        )
        if commands_dict and isinstance(commands_dict, dict):
            for cmd_name, fn in commands_dict.items():
                if not callable(fn):
                    logger.warning(
                        f"[plugins] {name!r}: COMMANDS[{cmd_name!r}] is not callable"
                    )
                    continue
                self._context.register_command(cmd_name, fn)
                manifest.commands[cmd_name] = fn
                logger.debug(f"[plugins] {name!r}: registered command {cmd_name!r}")

        # Style 2: register(ctx) function
        register_fn = getattr(module, "register", None)
        if callable(register_fn):
            # Capture commands registered by the function.
            before = set(self._context.commands.keys())
            try:
                register_fn(self._context)
            except Exception as exc:
                raise PluginError(
                    f"Plugin {name!r} register() raised an exception: {exc}"
                ) from exc
            after = set(self._context.commands.keys())
            new_cmds = after - before
            for cmd_name in new_cmds:
                fn = self._context.commands[cmd_name]
                manifest.commands[cmd_name] = fn
                logger.debug(
                    f"[plugins] {name!r}: registered command {cmd_name!r} via register()"
                )

        if not manifest.commands and commands_dict is None and register_fn is None:
            raise PluginError(
                f"Plugin {name!r} exposes neither a 'COMMANDS' dict "
                f"nor a 'register(ctx)' function."
            )

        self._loaded[name] = manifest
        return manifest
