"""Rebrand migration tests.

A workspace written by the application's former name must be carried
forward on first launch, without touching derived data and without ever
deleting what the user already had.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from veyrion_workspace.app import paths as paths_mod


@pytest.fixture(autouse=True)
def _reset_guard(monkeypatch):
    """Each test starts with a fresh, un-attempted migration."""
    monkeypatch.setattr(paths_mod, "_migration_attempted", False)
    monkeypatch.delenv("VEYRION_DATA_DIR", raising=False)


@pytest.fixture()
def workspace(tmp_path):
    """A stand-in legacy workspace plus the paths the migration sees."""
    legacy = tmp_path / "legacy" / "OmniReader Pro"
    (legacy / "settings").mkdir(parents=True)
    (legacy / "settings" / "settings.json").write_text(
        '{"appearance": {"theme": "sepia"}}', encoding="utf-8")
    (legacy / "database").mkdir()
    (legacy / "database" / "omnireader.db").write_bytes(b"library-rows")
    (legacy / "database" / "omnireader.pre-migration-1.db").write_bytes(b"older")
    (legacy / "vault").mkdir()
    (legacy / "vault" / "v.bin").write_bytes(b"sealed")
    (legacy / "cache").mkdir()
    (legacy / "cache" / "thumbnails.bin").write_bytes(b"x" * 64)

    target = tmp_path / "current" / "VeyrionWorkspace"
    return legacy, target


def _point_at(monkeypatch, legacy: Path, target: Path) -> None:
    monkeypatch.setattr(paths_mod, "app_data_root", lambda: target)
    monkeypatch.setattr(paths_mod, "legacy_data_root", lambda: legacy)


def test_migrates_library_settings_and_vault(monkeypatch, workspace):
    legacy, target = workspace
    _point_at(monkeypatch, legacy, target)

    result = paths_mod.migrate_legacy_data()

    assert result == target
    assert (target / "settings" / "settings.json").read_text(encoding="utf-8") \
        .startswith('{"appearance"')
    assert (target / "vault" / "v.bin").read_bytes() == b"sealed"


def test_renames_legacy_file_prefix(monkeypatch, workspace):
    legacy, target = workspace
    _point_at(monkeypatch, legacy, target)

    paths_mod.migrate_legacy_data()

    db_dir = target / "database"
    assert (db_dir / "veyrion.db").read_bytes() == b"library-rows"
    assert (db_dir / "veyrion.pre-migration-1.db").read_bytes() == b"older"
    # Nothing must be left behind under the old name.
    assert not list(db_dir.glob("omnireader*"))


def test_derived_cache_is_not_copied(monkeypatch, workspace):
    legacy, target = workspace
    _point_at(monkeypatch, legacy, target)

    paths_mod.migrate_legacy_data()

    assert not (target / "cache").exists()


def test_originals_are_left_untouched(monkeypatch, workspace):
    legacy, target = workspace
    _point_at(monkeypatch, legacy, target)

    paths_mod.migrate_legacy_data()

    # The app never deletes a workspace it did not create this session.
    assert (legacy / "database" / "omnireader.db").read_bytes() == b"library-rows"
    assert (legacy / "settings" / "settings.json").exists()
    assert (legacy / "cache" / "thumbnails.bin").exists()


def test_no_legacy_workspace_is_a_noop(monkeypatch, tmp_path):
    target = tmp_path / "current" / "VeyrionWorkspace"
    monkeypatch.setattr(paths_mod, "app_data_root", lambda: target)
    monkeypatch.setattr(paths_mod, "legacy_data_root", lambda: None)

    assert paths_mod.migrate_legacy_data() is None
    assert not target.exists()


def test_existing_workspace_is_never_overwritten(monkeypatch, workspace):
    legacy, target = workspace
    target.mkdir(parents=True)
    marker = target / "settings"
    marker.mkdir()
    (marker / "settings.json").write_text('{"mine": true}', encoding="utf-8")
    _point_at(monkeypatch, legacy, target)

    assert paths_mod.migrate_legacy_data() is None
    assert (marker / "settings.json").read_text(encoding="utf-8") == '{"mine": true}'


def test_runs_only_once(monkeypatch, workspace):
    legacy, target = workspace
    _point_at(monkeypatch, legacy, target)

    assert paths_mod.migrate_legacy_data() == target
    # A second call (e.g. ensure_all() called twice) must not re-copy.
    assert paths_mod.migrate_legacy_data() is None


def test_rolls_back_a_failed_copy(monkeypatch, workspace):
    legacy, target = workspace
    _point_at(monkeypatch, legacy, target)

    def boom(*_args, **_kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(paths_mod.shutil, "copytree", boom)

    # A half-written workspace must never be presented as valid.
    assert paths_mod.migrate_legacy_data() is None
    assert not target.exists()


def test_explicit_data_dir_disables_migration(monkeypatch, workspace):
    legacy, target = workspace
    _point_at(monkeypatch, legacy, target)
    monkeypatch.setenv("VEYRION_DATA_DIR", str(target))

    assert paths_mod.migrate_legacy_data() is None
    assert not target.exists()


def test_data_root_uses_branded_folder(monkeypatch, tmp_path):
    monkeypatch.delenv("VEYRION_DATA_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setattr(paths_mod.Path, "home", classmethod(lambda cls: tmp_path))

    root = paths_mod.app_data_root()

    assert root.name == "VeyrionWorkspace"
    assert "omni" not in str(root).lower()


def test_data_root_honours_env_override(monkeypatch, tmp_path):
    explicit = tmp_path / "portable"
    monkeypatch.setenv("VEYRION_DATA_DIR", str(explicit))

    assert paths_mod.app_data_root() == explicit.resolve()
