"""Verify a built portable ZIP in a fresh Chinese/space path without game input."""
import argparse
import hashlib
import json
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
    return {str(p.relative_to(folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, default=ROOT / f'releases/v{__version__}/NTE-Music-Desk-v{__version__}-Windows-x64.zip')
    args = parser.parse_args()
    archive = args.archive.resolve()
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    assert archive.with_suffix('.zip.sha256').read_text(encoding='ascii').split()[0] == digest
    target = ROOT / '.build' / ('独立 验证 ' + __version__ + ' ' + uuid.uuid4().hex[:8])
    target.mkdir(parents=True)
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        for item in bundle.infolist():
            resolved = (target / item.filename).resolve()
            assert resolved.is_relative_to(target.resolve())
            assert resolved.suffix.lower() not in ('.safetensors', '.pt', '.onnx')
        bundle.extractall(target)
    app = target / '异环演奏工作台'
    exe = app / '异环演奏工作台.exe'
    env = dict(os.environ)
    for name in ('PYTHONHOME', 'PYTHONPATH', 'TCL_LIBRARY', 'TK_LIBRARY', 'NTE_MUSIC_DESK_DATA_DIR'):
        env.pop(name, None)
    env['PATH'] = str(Path(env.get('SYSTEMROOT', 'C:/Windows')) / 'System32')
    temp = ROOT / '.build/test-temp'
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
        'assets_read_only': True, 'frozen_excerpt_conversion': 'passed', 'exe': str(exe)})
    destination = ROOT / f'.build/release-validation-{__version__}.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
