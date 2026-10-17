"""Direct source entry and PyInstaller entry; never searches the working folder."""
from pathlib import Path
import sys

if not getattr(sys, "frozen", False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nte_music_desk.cli import entrypoint

raise SystemExit(entrypoint())
