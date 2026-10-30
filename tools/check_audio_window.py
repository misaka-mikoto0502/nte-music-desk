"""Run the production Worker in the native WebView2 host on a local short fixture.

No keyboard/mouse/game input, model downloads or external browser are used.
Requires the system WebView2 Runtime; a temporary diagnostic window is shown.
"""
from pathlib import Path
import argparse,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from nte_music_desk.light_audio import LightAudioSession
from nte_music_desk.audio_window import verify_host

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio',type=Path,required=True)
    parser.add_argument('--assets',type=Path,default=ROOT/'src/nte_music_desk/assets')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--expected-notes',type=int)
    args=parser.parse_args();folder=args.output.resolve();folder.mkdir(parents=True,exist_ok=True)
    session=LightAudioSession(folder,lambda _:None,assets=args.assets/'light_audio')
    session.select_desktop_audio(args.audio)
    report=folder/'host.json';report.unlink(missing_ok=True)
    process=subprocess.Popen([str(verify_host(args.assets/'audio_window')),session.url,str(folder/'profile'),str(report),'--diagnostic'],stdin=subprocess.PIPE)
    try:
        process.wait(timeout=60)
        result=json.loads(report.read_text(encoding='utf-8-sig'))
        if result['state']!='diagnostic':raise RuntimeError(result)
        data=json.loads(result['data'])
        if 'result' not in data:raise RuntimeError(data)
        notes=len(data['result']['notes'])
        if args.expected_notes is not None and notes!=args.expected_notes:raise AssertionError((notes,args.expected_notes))
        print(json.dumps({'native_webview_worker':'passed','notes':notes,'game_input_sent':False}))
    finally:
        if process.poll() is None:process.terminate()
        process.stdin.close();session.close()
if __name__=='__main__':main()
