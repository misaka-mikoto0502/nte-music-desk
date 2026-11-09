"""Check that a preview's EXE, archives, assets and current source agree.

Run with the same Python version used to build, with PyInstaller installed.
This reads bytecode; it never launches the application or sends game input.
"""
import argparse
import hashlib
import json
import marshal
from pathlib import Path
import sys
from types import CodeType
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.package_source import collect_files


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def normalize_code(code):
    # PyInstaller rewrites source filenames to relative paths. All executable
    # code, constants (including nested functions), names and line data remain.
    if isinstance(code,CodeType):
        return code.replace(co_filename='',co_consts=tuple(normalize_code(c) for c in code.co_consts))
    return code


def verify(folder):
    from PyInstaller.archive.readers import CArchiveReader
    folder=folder.resolve()
    app=folder/'异环演奏工作台'
    exe=app/'异环演奏工作台.exe'
    windows=list(folder.glob('*-Windows-x64.zip'));sources=list(folder.glob('*-Source.zip'))
    assert len(windows)==len(sources)==1,'Keep one Windows ZIP and one Source ZIP in the preview folder'
    windows,source=windows[0],sources[0]
    for archive in (windows,source):
        assert digest(archive)==archive.with_suffix('.zip.sha256').read_text().split()[0],archive.name
    with zipfile.ZipFile(source) as bundle:
        expected={'nte-music-desk/'+p.relative_to(ROOT).as_posix():p for p in collect_files()}
        actual=set(bundle.namelist())
        assert len(actual)==len(bundle.namelist()),'Source ZIP contains duplicate paths'
        assert set(expected)==actual,dict(missing=sorted(set(expected)-actual),extra=sorted(actual-set(expected)))
        changed=[name for name,p in expected.items() if p.read_bytes()!=bundle.read(name)]
        assert not changed,dict(source_changed=changed)
    with zipfile.ZipFile(windows) as bundle:
        expected_paths=set()
        for entry in bundle.infolist():
            if entry.is_dir():continue
            path=(folder/entry.filename).resolve()
            assert path.is_relative_to(app.resolve()),entry.filename
            assert path not in expected_paths,'Windows ZIP contains duplicate paths'
            expected_paths.add(path)
            with bundle.open(entry) as stream:reference=hashlib.file_digest(stream,'sha256').hexdigest()
            assert digest(path)==reference,entry.filename
        assert expected_paths=={p.resolve() for p in app.rglob('*') if p.is_file()},'Expanded app differs from Windows ZIP'
    source_assets=ROOT/'src/nte_music_desk/assets'
    source_files={p.relative_to(source_assets).as_posix():p for p in source_assets.rglob('*') if p.is_file()
                  and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    frozen_assets=app/'_internal/nte_music_desk/assets'
    assert set(source_files)=={p.relative_to(frozen_assets).as_posix() for p in frozen_assets.rglob('*') if p.is_file()}
    for name,p in source_files.items():assert digest(p)==digest(frozen_assets/name),name
    archive=CArchiveReader(str(exe))
    pyz=archive.open_embedded_archive(next(name for name,item in archive.toc.items() if item[-1]=='z'))
    checked=[]
    # __main__ is Python's -m entry; audio_quality is a development-only scorer.
    # The executable uses _bootstrap, which is checked separately below.
    for path in (ROOT/'src/nte_music_desk').glob('*.py'):
        if path.stem in ('__main__','audio_quality'):continue
        name='nte_music_desk'+('' if path.stem=='__init__' else '.'+path.stem)
        actual=marshal.loads(archive.extract('_bootstrap')) if path.stem=='_bootstrap' else pyz.extract(name)
        expected=compile(path.read_bytes(),'','exec',dont_inherit=True,optimize=0)
        assert normalize_code(actual)==normalize_code(expected),'EXE contains stale Python code: '+name
        checked.append(name)
    return dict(status='passed',exe=str(exe),source_files=len(collect_files()),
        compiled_modules=len(checked),asset_files=len(source_files),windows_files=len(expected_paths),
        source_archive_matches_workspace=True,exe_code_matches_workspace=True,
        expanded_application_matches_zip=True,assets_match_workspace=True,
        windows_sha256=digest(windows),source_sha256=digest(source),exe_sha256=digest(exe),game_input_sent=False)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,default=ROOT/'.build/current')
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    report=verify(args.folder)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
