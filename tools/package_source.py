"""Create a GitHub-ready source ZIP from an explicit directory allowlist."""
import hashlib
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"src"))
from nte_music_desk import __version__


def main():
    files=[ROOT/name for name in ("README.md","LICENSE","THIRD_PARTY_NOTICES.md","CHANGELOG.md","pyproject.toml","requirements-build.txt",".gitignore")]
    for directory in ("src","tests","tools","docs",".github"):
        for path in (ROOT/directory).rglob("*"):
            if path.is_file() and not any(part == "__pycache__" or part.endswith(".egg-info") for part in path.parts) and path.suffix not in (".pyc",".pyo",".log"):
                files.append(path)
    files.append(ROOT/"releases/README.md")
    output=ROOT/"releases"/f"NTE-Music-Desk-v{__version__}-Source.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in sorted(files):
            archive.write(path,"nte-music-desk/"+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert all(not any(part in name for part in ("__pycache__","midi_ui_settings.json","downloaded_midis/","runs/",".exe",".cmd")) for name in archive.namelist())
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n",encoding="ascii")
    print(f"Source package: {len(files)} files, {output.stat().st_size:,} bytes")


if __name__=="__main__":main()
