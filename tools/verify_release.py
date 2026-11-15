"""Verify a built portable ZIP in a fresh Chinese/space path without game input."""
import argparse
import hashlib
import json
import shutil
import os
from pathlib import Path
import subprocess
import sys
import uuid
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from nte_music_desk import __version__


def hashes(folder):
    return {str(p.relative_to(folder)): file_hash(p) for p in folder.rglob('*') if p.is_file()}


def file_hash(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT / f'releases/v{__version__}/NTE-Music-Desk-v{__version__}-Windows-x64.zip')
    parser.add_argument('--report', type=Path, help='Write evidence to a separate path for development builds')
    parser.add_argument('--work', type=Path, default=ROOT / '.build/validation', help='Independent extraction workspace')
    parser.add_argument('--keep-extracted', action='store_true', help='Keep the second application copy for additional debugging')
    args = parser.parse_args()
    archive = args.archive.resolve()
    digest = file_hash(archive)
    assert archive.with_suffix('.zip.sha256').read_text(encoding='ascii').split()[0] == digest
    target = args.work.resolve() / ('独立 验证 ' + __version__ + ' ' + uuid.uuid4().hex[:8])
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        for item in bundle.infolist():
            resolved = (target / item.filename).resolve()
            assert resolved.is_relative_to(target.resolve())
            if resolved.suffix.lower() in ('.safetensors', '.pt', '.onnx', '.ckpt', '.pth', '.gguf'):
                relative = Path(item.filename).as_posix()
                assert '/assets/offline_audio/models/' in relative
            assert not {'__pycache__', 'catalogs', 'audio-models', 'transcriptions', 'downloaded_midis', 'audio-engine',
                        'light_audio', 'audio_window', 'audio_worker.py', 'melody_worker.py', 'separation_runtime.py',
                        'audio_runtime.py'} & set(Path(item.filename).parts), item.filename
        bundle.extractall(target)
    app = target / '异环演奏工作台'
    exe = app / '异环演奏工作台.exe'
    source_assets = ROOT / 'src/nte_music_desk/assets'
    expected_assets = {str(p.relative_to(source_assets)): file_hash(p)
                       for p in source_assets.rglob('*') if p.is_file()
                       and '__pycache__' not in p.parts and p.suffix not in ('.pyc', '.pyo')}
    assert hashes(app / '_internal/nte_music_desk/assets') == expected_assets, 'Frozen assets differ from current source'
    assert archive.stat().st_size < 1_000_000_000, 'Complete portable archive exceeds 1 GB'
    assert sum(p.stat().st_size for p in app.rglob('*') if p.is_file()) < 1_000_000_000, 'Extracted application exceeds 1 GB'
    env = dict(os.environ)
    for name in ('PYTHONHOME', 'PYTHONPATH', 'TCL_LIBRARY', 'TK_LIBRARY', 'NTE_MUSIC_DESK_DATA_DIR'):
        env.pop(name, None)
    env['PATH'] = str(Path(env.get('SYSTEMROOT', 'C:/Windows')) / 'System32')
    temp = args.work.resolve() / 'test-temp'
    temp.mkdir(exist_ok=True)
    env['TEMP'] = env['TMP'] = str(temp)
    report_path = target / 'frozen-report.json'
    before = hashes(app)
    result = subprocess.run([str(exe), '--data-dir', str(target / '用户 数据'), '--self-test', str(report_path)],
        env=env, cwd=str(target), timeout=60, capture_output=True)
    assert result.returncode == 0, result.stderr
    report = json.loads(report_path.read_text(encoding='utf-8'))
    assert report['version'] == __version__ and report['frozen'] and report['status'] == 'passed'
    assert report['game_input_sent'] is False
    exported = target / '片段 曲谱.json'
    result = subprocess.run([str(exe), '--data-dir', str(target / '用户 数据'), '--convert',
        str(app / '_internal/nte_music_desk/assets/scores/twinkle.musicxml'), '--start', '1', '--end', '3',
        '--mode', 'faithful', '--max-polyphony', '12', '--output', str(exported)],
        env=env, cwd=str(target), timeout=30, capture_output=True)
    assert result.returncode == 0, result.stderr
    score = json.loads(exported.read_text(encoding='utf-8'))
    assert score['summary']['seconds'] == 2 and score['settings']['end'] == 3
    assert score['mode'] == 'faithful' and score['settings']['max_polyphony'] == 12
    assert before == hashes(app), 'Application resources were modified'
    report.update({'zip_sha256': digest, 'zip_bytes': archive.stat().st_size, 'zip_crc': 'passed',
        'assets_read_only': True, 'assets_match_source': True, 'frozen_excerpt_conversion': 'passed', 'exe': str(exe)})
    if not args.keep_extracted:
        assert app.resolve().is_relative_to(args.work.resolve())
        shutil.rmtree(app)
    report['extracted_application_retained'] = args.keep_extracted
    destination = args.report.resolve() if args.report else args.work.resolve() / f'release-validation-{__version__}.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
