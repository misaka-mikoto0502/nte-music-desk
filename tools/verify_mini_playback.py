"""Exercise mini-player handoffs through real scheduler processes and fake keys."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import tkinter as tk
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from nte_music_desk import cli
from nte_music_desk.paths import asset_dir
from nte_music_desk.ui import App


def run(work):
    work=work.resolve();work.mkdir(parents=True,exist_ok=False)
    processes,reports,errors,overlaps=[],[],[],[]
    def playback(_,arguments):
        overlaps.append(any(p.poll() is None for p in processes))
        process=subprocess.Popen([sys.executable,str(ROOT/'tools/verify_background_audio.py'),
            '--simulate-player',*arguments],creationflags=0x08000000 if sys.platform=='win32' else 0,
            stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        processes.append(process)
        _,error=process.communicate()
        if process.returncode not in (0,2):errors.append(error.decode(errors='replace'))
        reports.append(Path(arguments[arguments.index('--report')+1]))
        return process.returncode
    root=tk.Tk();root.withdraw()
    app=App(root,SimpleNamespace(ROOT=work/'data',ASSETS=asset_dir(),
        key_schedule=cli.key_schedule,run_playback_and_wait=playback))
    app.show_error=lambda error:errors.append(str(error))
    root.report_callback_exception=lambda kind,error,trace:errors.append(str(error))
    def pump(predicate,timeout=10):
        deadline=time.monotonic()+timeout
        while not predicate() and time.monotonic()<deadline:
            root.update();time.sleep(.01)
        assert predicate(),'Timed out'
    try:
        songs=[]
        for title in ('A','B','C'):
            p=work/(title+'.mid');p.write_bytes((asset_dir()/'scores/twinkle.mid').read_bytes())
            songs.append(p)
        app.open_path(songs[0]);app.countdown.set('0');app.play(None)
        pump(lambda:app.active and app.active.get('phase')=='playing')
        old=app.active
        app.mini.choose_song(songs[1])
        assert app.active is old and app.current_path==songs[0]
        pump(lambda:len(processes)==2 and app.active and app.active.get('phase')=='playing')
        assert app.current_path==songs[1] and processes[0].poll() is not None
        assert json.loads(reports[0].read_text())['held_keys']==0
        app.toggle_pause();pump(lambda:app.active.get('phase')=='paused')
        app.mini.choose_song(songs[2]);pump(lambda:app.active is None)
        assert app.current_path==songs[2] and len(processes)==2
        app.play(None);pump(lambda:app.active and app.active.get('phase')=='playing')
        app.mini.choose_song(songs[0]);app.stop();pump(lambda:app.active is None)
        assert app.current_path==songs[2] and len(processes)==3
        app.seek_fraction(.995);app.play(None);pump(lambda:app.active is None)
        assert len(processes)==4 and app.playback_offset()==0
        assert not errors and not any(overlaps),(errors,overlaps)
        results=[json.loads(p.read_text()) for p in reports]
        assert results[-1]['status']=='completed'
        assert all(r['held_keys']==0 and not r['game_input_sent'] for r in results)
        report=dict(status='passed',playing_switch_autostarts=True,paused_switch_loads_only=True,
            explicit_stop_cancels_switch=True,natural_completion_resets_position=True,
            playback_process_overlap=False,all_keys_released=True,game_input_sent=False,playback_reports=results)
        (work/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False,indent=2))
    finally:
        app.stop()
        for p in processes:
            if p.poll() is None:p.wait(timeout=10)
        app.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work',type=Path,required=True,help='A new folder below .build/validation')
    run(parser.parse_args().work)
