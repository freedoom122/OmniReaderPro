"""Veyrion Workspace — universal document workspace.

READ. EDIT. ORGANIZE. CREATE.

Brand constants live here so every surface (window title, installers,
About dialog, data directories) reads from one place.
"""

__version__ = "1.1.0"

# -- Identity ------------------------------------------------------------
APP_NAME = "Veyrion Workspace"
APP_SLUG = "VeyrionWorkspace"          # file-system / executable safe form
APP_TAGLINE = "READ. EDIT. ORGANIZE. CREATE."
ORG_NAME = "Veyrion Studios"
ORG_DOMAIN = "veyrionstudios.com"

# Folder created under the OS application-data root.
DATA_DIR_NAME = "VeyrionWorkspace"

# -- Release channel -----------------------------------------------------
GITHUB_OWNER = "freedoom122"
GITHUB_REPO = "VeyrionWorkspace"

# -- Legacy (pre-rebrand) identity --------------------------------------
# Workspaces written by the application's former name are migrated forward
# once on first launch so no user loses a library, settings, or a vault.
# See ``app.paths.migrate_legacy_data``.
LEGACY_DATA_DIR_NAMES = ("OmniReader Pro", "OmniReaderPro")
LEGACY_FILE_PREFIX = "omnireader"      # omnireader.db / omnireader.log / ...
CURRENT_FILE_PREFIX = "veyrion"

__all__ = [
    "__version__", "APP_NAME", "APP_SLUG", "APP_TAGLINE", "ORG_NAME",
    "ORG_DOMAIN", "DATA_DIR_NAME", "GITHUB_OWNER", "GITHUB_REPO",
    "LEGACY_DATA_DIR_NAMES", "LEGACY_FILE_PREFIX", "CURRENT_FILE_PREFIX",
]
