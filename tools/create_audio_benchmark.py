"""Original 8.5s piano fixture rendered from the official CC0 VSCO 2 CE samples.

Optional engine Python needs numpy/scipy/soundfile. Downloads three isolated
notes, not songs. Output is private validation data, excluded from releases.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from nte_music_desk.midi import MidiSong,MidiNote,write_midi


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',required=True,type=Path)
    args=parser.parse_args()
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    from fractions import Fraction
    folder=args.output.resolve();folder.mkdir(parents=True,exist_ok=True)
    samples={};sources=[]
    for key,index in ((49,14),(61,20),(73,26)):
        name=f'Player_dyn2_rr1_{index:03d}.wav'
        url='https://raw.githubusercontent.com/sgossner/VSCO-2-CE/master/'+urllib.parse.quote('Keys/Upright Piano/'+name)
        path=folder/name
        if not path.is_file():
            with urllib.request.urlopen(url,timeout=60) as response:
                data=response.read(12*1024*1024+1)
            if len(data)>12*1024*1024:raise ValueError('Sample exceeds expected size.')
            path.write_bytes(data)
        audio,rate=sf.read(path,dtype='float32',always_2d=True)
        samples[key]=(audio,rate)
        sources.append({'url':url,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'pitch_keycenter':key})
    notes=[MidiNote(0,0,p,88,.5+i*.75,.5+i*.75+.55) for i,p in enumerate((72,76,79,77,74,71,72,67))]
    for i,chord in enumerate(((48,55,60),(53,57,60),(55,59,62),(48,55,60))):
        notes.extend(MidiNote(1,1,p,65,.5+i*2,2+i*2) for p in chord)
    song=MidiSong('Original benchmark: two piano voices',1,480,notes,['melody','chords'],[],8.5,[])
    write_midi(song,folder/'reference.mid')
    rate=44100;mix=np.zeros((int(8.5*rate),2),dtype=np.float32)
    for note in notes:
        key=min(samples,key=lambda p:abs(p-note.pitch));audio,sr=samples[key]
        ratio=Fraction(rate/sr/2**((note.pitch-key)/12)).limit_denominator(2000)
        rendered=resample_poly(audio,ratio.numerator,ratio.denominator)
        if rendered.shape[1]==1:rendered=np.repeat(rendered,2,axis=1)
        start=int(note.start*rate);length=min(int((note.end-note.start)*rate),len(rendered),len(mix)-start)
        value=rendered[:length,:2].copy()
        fade=min(length,int(.05*rate));value[-fade:]*=np.linspace(1,0,fade)[:,None]
        mix[start:start+length]+=value*(note.velocity/127)
    mix*=.75/max(.75,float(np.abs(mix).max()))
    sf.write(folder/'reference.wav',mix,rate,subtype='PCM_16')
    (folder/'fixture.json').write_text(json.dumps({'composition':'Original short test phrase, 20 known notes, leading rest retained',
        'sample_library':'VSCO 2 CE by Sam Gossner / Simon Dalzell; cutting by Elan Hickler',
        'sample_license':'CC0-1.0','license_url':'https://github.com/sgossner/VSCO-2-CE/blob/master/LICENSE',
        'mapping':'https://github.com/sgossner/VSCO-2-CE/blob/SFZ/UprightPiano.sfz','samples':sources,
        'limitation':'A sampled piano benchmark, not a real singing or mixed-song accuracy test.'},indent=2),encoding='utf-8')
    print(folder)


if __name__=='__main__':main()
