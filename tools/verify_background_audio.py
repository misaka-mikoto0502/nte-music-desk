"""Run real offline inference beside the real playback scheduler with a fake keyboard.

Developer-only validation: never creates WindowsKeyboard or sends system input.
Uses the workbench's normal play/pause/seek/stop paths and separate processes.
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))


def simulated_player(arguments):
    from nte_music_desk import cli
    from nte_music_desk.keyboard import PlaybackStopped
    from nte_music_desk.midi import load_score
    from nte_music_desk.performance import performance_plan
    from nte_music_desk.playback import PauseControl, execute_plan
    parser = argparse.ArgumentParser()
    for name in ('play', 'cancel-file', 'report', 'control-file'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hold-ms', type=int, default=300)
    parser.add_argument('--position', type=float, default=0)
    args, _ = parser.parse_known_args(arguments)
    plan = performance_plan(load_score(args.play), args.hold_ms)
    control = PauseControl(args.control_file)
    elapsed, phases, timestamps = 0, set(), []
    class Keyboard:
        def __init__(self): self.held = set()
        def check(self):
            if args.cancel_file.exists(): raise PlaybackStopped('workbench stop')
        def down(self, key):
            self.check(); self.held.add(key); timestamps.append(time.perf_counter())
        def up(self, key): self.held.discard(key)
        def release_all(self): self.held.clear()
    keyboard = Keyboard()
    def progress(phase, position, sequence):
        nonlocal elapsed
        elapsed = position; phases.add(phase)
        cli.write_progress(args.report, phase, elapsed=position, control_sequence=sequence)
    code, status = 0, 'completed'
    try:
        execute_plan(plan, keyboard, control=control, on_progress=progress, start_at=args.position)
    except PlaybackStopped:
        code, status = 2, 'stopped'
    result = {'status':status, 'elapsed':elapsed, 'control_sequence':control.sequence,
              'phases':sorted(phases), 'fake_key_downs':len(timestamps), 'held_keys':len(keyboard.held),
              'game_input_sent':False}
    if code == 2:
        result.update(reason='收到工作台停止指令，已停止。', stop_origin='workbench')
    args.report.write_text(json.dumps(result), encoding='utf-8')
    return code


def run(args):
    import tkinter as tk
    from unittest.mock import patch
    from nte_music_desk import cli
    from nte_music_desk.midi import MidiNote, MidiSong, write_midi
    from nte_music_desk.paths import asset_dir
    from nte_music_desk.ui import App
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    reference = None
    if args.baseline_job:
        reference=json.loads((args.baseline_job.resolve()/'result.json').read_text(encoding='utf-8'))
        assert reference.get('profile')=='song' and reference.get('start')==0 and reference.get('end')==args.end, \
            'Baseline selection differs; use --end to match the baseline before comparing outputs'
    processes, errors, fake_reports = [], [], []
    def playback(_, arguments):
        process = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), '--simulate-player', *arguments],
                                   creationflags=0x08000000 if sys.platform == 'win32' else 0,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        processes.append(process)
        _, error = process.communicate()
        if process.returncode not in (0, 2): errors.append(error.decode(errors='replace'))
        fake_reports.append(Path(arguments[arguments.index('--report') + 1]))
        return process.returncode
    engine = SimpleNamespace(ROOT=work/'data', ASSETS=asset_dir(), key_schedule=cli.key_schedule,
                             run_playback_and_wait=playback, render_preview=cli.render_preview,
                             render_song_preview=cli.render_song_preview, limit_score=cli.limit_score)
    root = tk.Tk(); root.withdraw()
    app = App(root, engine)
    events = [MidiNote(0, 0, pitch+i%3, 90, i*.25, i*.25+.09) for i in range(1600) for pitch in (60, 64, 67)]
    score = work/'scheduler-fixture.mid'
    write_midi(MidiSong('调度测试',1,480,events,['合成和弦'],[(0,500000)],400,[]), score)
    app.open_path(score)
    app.countdown.set('0')
    app.open_offline_audio(args.source.resolve())
    dialog = app.offline_dialog; dialog.window.withdraw(); dialog.select_profile('song')
    def pump(predicate, timeout):
        deadline = time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:
            root.update(); time.sleep(.01)
        assert predicate(), 'Timed out; ' + dialog.state.get()
    report = {'game_input_sent':False, 'real_keyboard_created':False}
    try:
        # Cancel a real inference tree while a separate playback process runs.
        dialog.end.set('0:30'); dialog.begin(); app.play(None)
        pump(lambda: bool(processes) and dialog.stage in ('vocal', 'recognize'), 60)
        playing = app.active; player = processes[-1]
        dialog.cancel(); pump(lambda: dialog.job is None, 15)
        assert app.active is playing and player.poll() is None
        report['cancel_kept_playback_running'] = True
        app.stop(); pump(lambda: app.active is None, 10)
        assert json.loads(fake_reports[-1].read_text())['held_keys'] == 0

        # Preview generation is real, but mute device output for this test.
        dialog.end.set('' if args.end is None else str(args.end)); dialog.begin()
        with patch('winsound.PlaySound') as sound:
            app.preview(); pump(lambda: app.preview_started is not None, 20)
            assert dialog.job is not None and app.preview_token
            report['preview_prepared_while_transcribing'] = True
            app.stop_preview()
        app.remember_position(0, True); app.play(None)
        pump(lambda: app.active and app.active.get('phase') == 'playing', 10)
        app.toggle_pause(); pump(lambda: app.active.get('phase') == 'paused', 5)
        app.seek_fraction(.2)
        pump(lambda: app.active.get('elapsed', 0) >= 79, 5)
        app.toggle_pause(); pump(lambda: app.active.get('phase') == 'playing', 5)
        report['pause_seek_resume_while_transcribing'] = True
        playing, original_song = app.active, app.current_path
        cancel_count = len(fake_reports)
        started = time.monotonic()
        pump(lambda: dialog.job is None, 480)
        assert dialog.result and app.active is playing and app.current_path == original_song
        result = dialog.result
        report.update(status='passed', result=result, concurrent_wait_seconds=round(time.monotonic()-started,3),
                      completion_kept_current_playback=True)
        if args.baseline_job:
            baseline = args.baseline_job.resolve(); job = Path(result['midi']).parent
            reference = json.loads((baseline/'result.json').read_text(encoding='utf-8'))
            assert reference['source_sha256'] == result['source_sha256']
            same = {name:(job/name).read_bytes()==(baseline/name).read_bytes()
                    for name in ('raw-notes.json','native-notes.json','vocal-notes.json')}
            same['midi'] = Path(result['midi']).read_bytes()==(baseline/Path(reference['midi']).name).read_bytes()
            report['baseline_byte_identical'] = same
            assert all(same.values()), same
        app.stop(); pump(lambda: app.active is None and len(fake_reports)>cancel_count, 10)
        reports = [json.loads(p.read_text()) for p in fake_reports]
        assert not errors, errors
        assert all(r['held_keys']==0 and not r['game_input_sent'] for r in reports)
        report['playback_processes'] = reports
        report['stop_released_all_fake_keys'] = True
        (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        app.stop()
        for process in processes:
            if process.poll() is None: process.wait(timeout=10)
        app.close()


if __name__ == '__main__':
    if '--simulate-player' in sys.argv:
        raise SystemExit(simulated_player(sys.argv[2:]))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--baseline-job', type=Path)
    parser.add_argument('--end',type=float,help='Optional end in seconds; match the baseline selection')
    args=parser.parse_args()
    if args.end is not None and not 0<args.end<=3600:parser.error('--end must be within 0–3600 seconds')
    run(args)
