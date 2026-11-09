"""Create a GitHub-ready source ZIP from an explicit directory allowlist."""
import hashlib
import argparse
from pathlib import Path
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"src"))
from nte_music_desk import __version__
from tools.check_release import check_release


TOP_FILES=("README.md","LICENSE","THIRD_PARTY_NOTICES.md","CHANGELOG.md","AGENTS.md","pyproject.toml","requirements-build.txt",".gitignore",".gitattributes")
HOST_BINARIES={"src/nte_music_desk/assets/audio_window/"+name for name in (
    "NteAudioWindow.exe","Microsoft.Web.WebView2.Core.dll","Microsoft.Web.WebView2.WinForms.dll","WebView2Loader.dll")}
PRIVATE_DIRS={"__pycache__","node_modules",".venv","venv",".build","build","dist","runs","arrangements",
              "light-transcriptions","transcriptions","offline-transcriptions","audio-models","downloaded_midis","catalog_cache",
              ".eggs",".tox",".nox",".pytest_cache",".mypy_cache",".ruff_cache",".hypothesis","htmlcov",".idea",".vs"}

def collect_files(root=ROOT):
    files=[root/name for name in TOP_FILES]
    for directory in ("src","tests","tools","docs",".github"):
        for path in (root/directory).rglob("*"):
            relative=path.relative_to(root)
            if relative.as_posix().startswith('src/nte_music_desk/assets/offline_audio/'):continue
            if (not path.is_file() or path.is_symlink() or any(part in PRIVATE_DIRS or part.endswith('.egg-info') for part in relative.parts)
                or path.suffix in ('.pyc','.pyo','.log','.lnk','.spec','.tmp','.bak')
                or path.name in ('midi_ui_settings.json','audio-engine.json','.env','.coverage','coverage.xml','.DS_Store','Thumbs.db','desktop.ini')
                or path.name.startswith(('.env.','.coverage.')) or path.name.endswith('~')):continue
            if path.suffix.lower() in ('.exe','.dll','.cmd','.bat') and relative.as_posix() not in HOST_BINARIES:
                raise ValueError(f'Unexpected executable in source tree: {relative}')
            files.append(path)
    files.append(root/"releases/README.md")
    return sorted(files)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/"releases"/f"v{__version__}"/f"NTE-Music-Desk-v{__version__}-Source.zip")
    parser.add_argument('--overwrite',action='store_true')
    args=parser.parse_args();output=args.output.resolve()
    if output.exists() and not args.overwrite:raise FileExistsError('Source archive already exists; choose a new --output or explicitly use --overwrite')
    check_release(ROOT)
    files=collect_files()
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"w",zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for path in files:
            archive.write(path,"nte-music-desk/"+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert 'nte-music-desk/.gitattributes' in archive.namelist()
        for name in archive.namelist():
            relative=Path(name).relative_to('nte-music-desk')
            assert not PRIVATE_DIRS.intersection(relative.parts)
            if relative.suffix.lower() in ('.exe','.dll','.cmd','.bat'):assert relative.as_posix() in HOST_BINARIES
    digest=hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n",encoding="ascii")
    print(f"Source package: {len(files)} files, {output.stat().st_size:,} bytes")


if __name__=="__main__":main()
