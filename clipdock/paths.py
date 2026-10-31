"""Writable application data, independent of the installed source files."""
import os
import sys
from pathlib import Path


def data_directory():
    override = os.environ.get("CLIPDOCK_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        return (Path(base) if base else Path.home() / "AppData" / "Local") / "ClipDock"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ClipDock"
    base = os.environ.get("XDG_DATA_HOME")
    return (Path(base) if base else Path.home() / ".local" / "share") / "clipdock"
