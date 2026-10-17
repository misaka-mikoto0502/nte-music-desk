"""Bundled resources are read-only; user state belongs outside the application."""
import os
from pathlib import Path


def asset_dir():
    return Path(__file__).resolve().parent / "assets"


def default_data_dir():
    override = os.environ.get("NTE_MUSIC_DESK_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA")
    if local:
        return Path(local) / "NteMusicDesk"
    return Path.home() / ".local" / "share" / "NteMusicDesk"


def ensure_data_dir(path):
    path = Path(path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path
