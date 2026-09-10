"""Plugin host with an explicit permission model.

Plugins are untrusted code. Design:

* Every plugin ships a ``plugin.json`` manifest declaring an id, name,
  version, entry point, and the exact permissions it needs.
* The host validates the manifest (id pattern, entry within the plugin
  folder, no absolute paths) before importing anything.
* The plugin entry is imported only after the user approves its
  permissions on first load; approval is remembered in the settings.
* A thin facade (``PluginAPI``) is passed to the plugin instead of the
  application internals, so the plugin can only touch what the facade
  exposes, and each facade method re-checks the granted permissions.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from omnireader_pro.app import paths
from omnireader_pro.utils.pathutils import PathSafetyError, ensure_within, validate_path

logger = logging.getLogger("omnireader.plugins")

PERMISSIONS = {
    "filesystem.read": "Read files (any path)",
    "filesystem.write": "Write files (any path)",
    "network": "Make network requests",
    "clipboard": "Read or write the clipboard",
    "document.read": "Read document text via the facade",
    "document.write": "Modify documents via the facade",
}

VALID_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")


class PluginError(Exception):
    pass


@dataclass
class PluginManifest:
    id: str = ""
    name: str = ""
    version: str = "0.1.0"
    entry: str = "main.py"
    permissions: list = field(default_factory=list)
    description: str = ""
    author: str = ""
    trusted: bool = False

    @classmethod
    def load(cls, plugin_dir: Path) -> "PluginManifest":
        manifest_path = plugin_dir / "plugin.json"
        if not manifest_path.exists():
            raise PluginError("plugin.json is missing")
        try:
            raw = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            raise PluginError(f"plugin.json is invalid: {e}")
        if not isinstance(raw, dict):
            raise PluginError("plugin.json must contain an object")
        pid = str(raw.get("id", ""))
        if not VALID_ID.match(pid):
            raise PluginError(f"invalid plugin id: {pid!r}")
        entry = str(raw.get("entry", "main.py"))
        try:
            entry_path = ensure_within(entry, plugin_dir)
        except PathSafetyError as e:
            raise PluginError(f"entry escapes plugin folder: {e}")
        if not entry_path.exists():
            raise PluginError(f"entry file not found: {entry}")
        perms = raw.get("permissions", [])
        if not isinstance(perms, list):
            raise PluginError("permissions must be a list")
        unknown = set(perms) - set(PERMISSIONS)
        if unknown:
            raise PluginError(f"undeclared permissions: {sorted(unknown)}")
        if "network" in perms and not raw.get("trusted"):
            raise PluginError(
                "network permission requires \"trusted\": true in the "
                "manifest — network plugins are reviewed manually")
        return cls(
            id=pid,
            name=str(raw.get("name", pid)),
            version=str(raw.get("version", "0.1.0")),
            entry=entry,
            permissions=perms,
            description=str(raw.get("description", "")),
            author=str(raw.get("author", "")),
            trusted=bool(raw.get("trusted", False)),
        )


class PluginFacade:
    """The only object a plugin receives — every method enforces grants."""

    def __init__(self, manifest: PluginManifest, app_api: dict) -> None:
        self._manifest = manifest
        self._api = app_api

    def _require(self, perm: str) -> None:
        if perm not in self._manifest.permissions:
            raise PermissionError(
                f"plugin '{self._manifest.id}' lacks permission: {perm}")

    # -- capabilities ------------------------------------------------------
    def get_setting(self, key: str, default: Any = None) -> Any:
        settings = self._api.get("settings")
        if settings is None:
            return default
        return settings.get("plugins", f"{self._manifest.id}.{key}", default)

    def set_setting(self, key: str, value: Any) -> None:
        settings = self._api.get("settings")
        if settings is not None:
            settings.set("plugins", f"{self._manifest.id}.{key}", value)

    def open_document(self, path: str):
        self._require("document.read")
        opener = self._api.get("open_document")
        return opener(path) if opener else None

    def log(self, message: str) -> None:
        logger.info("[plugin:%s] %s", self._manifest.id, message)

    def add_command(self, title: str, callback: Callable) -> None:
        self._require("document.read")
        registry = self._api.get("add_command")
        if registry:
            registry(self._manifest.id, title, callback)

    def notify(self, message: str, kind: str = "info") -> None:
        toaster = self._api.get("toast")
        if toaster:
            toaster(message, kind)


class PluginHost:
    """Discovers, validates, loads, and manages plugins."""

    def __init__(self, settings, app_api: dict | None = None) -> None:
        self._settings = settings
        self._api = app_api or {}
        self._plugins_dir = paths.plugins_dir()
        self._plugins_dir.mkdir(parents=True, exist_ok=True)
        self._loaded: dict[str, Any] = {}

    # -- discovery ------------------------------------------------------------
    def discover(self) -> list[dict]:
        """Return plugin descriptors without loading any code."""
        out = []
        for entry in sorted(self._plugins_dir.iterdir()):
            if not entry.is_dir():
                continue
            try:
                manifest = PluginManifest.load(entry)
                approved = self._approved(manifest.id)
                out.append({
                    "id": manifest.id, "name": manifest.name,
                    "version": manifest.version,
                    "description": manifest.description,
                    "author": manifest.author,
                    "permissions": manifest.permissions,
                    "approved": approved,
                    "loaded": manifest.id in self._loaded,
                    "path": entry,
                })
            except PluginError as e:
                out.append({"id": entry.name, "name": entry.name,
                            "version": "", "description": f"INVALID: {e}",
                            "author": "", "permissions": [],
                            "approved": False, "loaded": False, "path": entry,
                            "error": str(e)})
        return out

    def _approved(self, plugin_id: str) -> bool:
        approved = self._settings.get("plugins", "approved", [])
        return plugin_id in approved

    # -- loading ---------------------------------------------------------------
    def load_plugin(self, plugin_id: str, force_approve: bool = False) -> Any:
        """Load a plugin after its permissions are approved."""
        entry_dir = self._plugins_dir / plugin_id
        manifest = PluginManifest.load(entry_dir)
        if not force_approve and not self._approved(plugin_id):
            raise PluginError(
                f"plugin '{manifest.name}' is not approved — the user must "
                f"approve its permissions first")
        module_name = f"or_plugin_{manifest.id.replace('.', '_')}"
        spec = importlib.util.spec_from_file_location(
            module_name, str(entry_dir / manifest.entry))
        if spec is None or spec.loader is None:
            raise PluginError(f"cannot load entry for '{manifest.id}'")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception as e:
            logger.exception("plugin %s crashed during import", manifest.id)
            raise PluginError(f"plugin '{manifest.name}' crashed on load: {e}")
        facade = PluginFacade(manifest, self._api)
        activate = getattr(module, "activate", None)
        if not callable(activate):
            raise PluginError(
                f"plugin '{manifest.name}' has no callable activate(facade)")
        try:
            activate(facade)
        except PermissionError as e:
            # A permission denial is a security event, not a crash: it must
            # propagate as itself so callers can handle it distinctly.
            logger.warning("plugin %s denied permission: %s", manifest.id, e)
            raise
        except Exception as e:
            logger.exception("plugin %s failed to activate", manifest.id)
            raise PluginError(f"plugin '{manifest.name}' failed to activate: {e}")
        self._loaded[manifest.id] = module
        return module

    def approve(self, plugin_id: str) -> None:
        approved = list(self._settings.get("plugins", "approved", []))
        if plugin_id not in approved:
            approved.append(plugin_id)
            self._settings.set("plugins", "approved", approved)

    def revoke(self, plugin_id: str) -> None:
        approved = [p for p in self._settings.get("plugins", "approved", [])
                    if p != plugin_id]
        self._settings.set("plugins", "approved", approved)
        self._loaded.pop(plugin_id, None)

    def load_all_approved(self) -> list[dict]:
        results = []
        for entry in sorted(self._plugins_dir.iterdir()):
            if not entry.is_dir():
                continue
            try:
                manifest = PluginManifest.load(entry)
                if self._approved(manifest.id):
                    try:
                        self.load_plugin(manifest.id)
                        results.append({"id": manifest.id, "ok": True})
                    except PluginError as e:
                        logger.warning("plugin %s disabled: %s",
                                       manifest.id, e)
                        results.append({"id": manifest.id, "ok": False,
                                        "error": str(e)})
            except PluginError as e:
                logger.info("skipping invalid plugin %s: %s", entry.name, e)
        return results

    def installed_plugin_path(self) -> Path:
        return self._plugins_dir