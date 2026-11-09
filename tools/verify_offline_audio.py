"""Exercise the frozen offline worker with an explicitly supplied local sample.

Run twice (piano/song) after verify_release.py. No keyboard input, UAC, cloud
upload, Python environment or external decoder is used by the tested EXE.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time
import uuid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--profile', choices=['piano', 'song'], required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--end', type=float)
    parser.add_argument('--baseline-job', type=Path, help='Require byte-identical notes and MIDI against an earlier successful job')
    parser.add_argument('--max-seconds', type=float, help='Fail if the complete frozen job exceeds this wall-clock budget')
    args = parser.parse_args()
    job = args.work.resolve() / (args.profile + '-' + uuid.uuid4().hex[:8]); job.mkdir(parents=True)
    request = job / 'request.json'
    request.write_text(json.dumps({'source':str(args.source.resolve()),'profile':args.profile,'start':0,'end':args.end}),encoding='utf-8')
    env = {k:v for k,v in os.environ.items() if k not in ('PYTHONHOME','PYTHONPATH','TCL_LIBRARY','TK_LIBRARY','NTE_MUSIC_DESK_DATA_DIR')}
    env.update(PATH=str(Path(env.get('SystemRoot','C:/Windows'))/'System32'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               HTTP_PROXY='http://127.0.0.1:9', HTTPS_PROXY='http://127.0.0.1:9')
    begin = time.monotonic()
    with (job/'process.log').open('w',encoding='utf-8') as log:
        result = subprocess.run([str(args.exe.resolve()),'--data-dir',str(job/'个人 数据'),'--offline-audio-worker',str(request)],
            cwd=job,env=env,stdout=log,stderr=log,timeout=600)
    report = json.loads((job/'result.json').read_text(encoding='utf-8'))
    assert result.returncode == 0 and report['status']=='ok',report
    assert report['notes']>0 and Path(report['midi']).is_file()
    assert report['network'] is False and report['runtime']=='CPU'
    assert (job/'audio-preview.wav').stat().st_size>1000 and (job/'score-preview.wav').stat().st_size>1000
    report.update(elapsed=round(time.monotonic()-begin,3), executable=str(args.exe.resolve()), external_python=False,
                  external_decoder=False, path='System32 only', online_model_access='disabled',game_input_sent=False)
    if args.baseline_job:
        baseline = args.baseline_job.resolve()
        reference = json.loads((baseline/'result.json').read_text(encoding='utf-8'))
        for name in ('status', 'profile', 'source_sha256', 'start', 'end', 'seed'):
            assert report.get(name) == reference.get(name), 'Baseline input/settings differ: ' + name
        identical = {}
        for name in ('raw-notes.json', 'vocal-notes.json', 'native-notes.json'):
            if (baseline/name).is_file():
                identical[name] = (job/name).read_bytes() == (baseline/name).read_bytes()
        identical['midi'] = Path(report['midi']).read_bytes() == (baseline/Path(reference['midi']).name).read_bytes()
        report['baseline_byte_identical'] = identical
    if args.max_seconds is not None:
        report['budget_seconds'] = args.max_seconds
        report['within_budget'] = report['elapsed'] <= args.max_seconds
    (job/'verification.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if args.baseline_job:
        assert all(report['baseline_byte_identical'].values()), 'Optimized output differs from the accepted baseline; review verification.json'
    if args.max_seconds is not None:
        assert report['within_budget'], 'Complete job exceeds latency budget; review verification.json'


if __name__=='__main__':main()
