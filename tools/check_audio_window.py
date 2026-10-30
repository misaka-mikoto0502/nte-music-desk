"""Run the shared production pipeline, save/download and layout checks in WebView2.

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
    parser.add_argument('--without-wasm',action='store_true',help='Test genuine missing-WASM CPU fallback')
    parser.add_argument('--profile',choices=['polyphonic','detail','melody'],default='polyphonic')
    parser.add_argument('--align',action='store_true')
    parser.add_argument('--cancel',action='store_true',help='Cancel after the first real inference window')
    args=parser.parse_args();folder=args.output.resolve();folder.mkdir(parents=True,exist_ok=True)
    session=LightAudioSession(folder,lambda _:None,assets=args.assets/'light_audio')
    session.select_desktop_audio(args.audio)
    if args.without_wasm:
        for name in list(session.files):
            if name.endswith('.wasm'):session.files.pop(name)
    report=folder/'host.json';report.unlink(missing_ok=True)
    before=set(folder.rglob('*.mid'))
    process=subprocess.Popen([str(verify_host(args.assets/'audio_window')),session.url,str(folder/'profile'),str(report),
        '--diagnostic-cancel' if args.cancel else '--diagnostic',args.profile,'24' if args.align else '0'],stdin=subprocess.PIPE)
    try:
        process.wait(timeout=60)
        result=json.loads(report.read_text(encoding='utf-8-sig'))
        if args.cancel:
            assert result['state']=='cancelled' and not session.busy,result
            assert set(folder.rglob('*.mid'))==before
            print(json.dumps({'native_shared_pipeline':'cancelled_without_output','game_input_sent':False}));return
        if result['state']!='diagnostic':raise RuntimeError(result)
        data=json.loads(result['data'])
        if 'result' not in data:raise RuntimeError(data)
        notes=data['result']['notes']
        if args.expected_notes is not None and notes!=args.expected_notes:raise AssertionError((notes,args.expected_notes))
        from nte_music_desk.midi import read_midi
        assert len(read_midi(Path(result['download'])).notes)==notes
        assert session.result.read_bytes()==Path(result['download']).read_bytes()
        provenance=json.loads((session.result.parent/'provenance.json').read_text(encoding='utf-8'))
        assert provenance['source']['profile']==args.profile
        assert provenance['processing']['alignment']['window_ms']==(24 if args.align else 0)
        assert (session.result.parent/'model_selected.mid').is_file() and (session.result.parent/'model_raw.mid').is_file()
        for layout in result['layout']:
            assert layout['scrollWidth']<=layout['width'] and layout['scrollHeight']<=layout['height'],layout
            assert layout['panelBottom']<=layout['footerTop'] and layout['downloadVisible'],layout
            assert not layout['settingsOverflow'] and not layout['resultOverflow'],layout
        if args.without_wasm:assert any(p.get('phase')=='fallback' for p in data['phases'])
        print(json.dumps({'native_shared_pipeline':'passed','notes':notes,'saved_midi_and_download':'identical',
            'layout_cases':len(result['layout']),'fallback':args.without_wasm,'game_input_sent':False}))
    finally:
        if process.poll() is None:process.terminate()
        process.stdin.close();session.close()
if __name__=='__main__':main()
