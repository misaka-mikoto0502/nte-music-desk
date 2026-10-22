"""Six original calibration phrases using the three CC0 benchmark piano samples.

Run create_audio_benchmark.py first. This developer tool needs numpy/scipy/
soundfile; those libraries and benchmark audio are not desktop dependencies.
"""
import argparse
from fractions import Fraction
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from nte_music_desk.midi import MidiNote,MidiSong,write_midi


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    import numpy as np
    import soundfile as sf
    from scipy.signal import resample_poly
    samples={key:sf.read(args.samples/f'Player_dyn2_rr1_{index:03d}.wav',dtype='float32',always_2d=True)
             for key,index in ((49,14),(61,20),(73,26))}
    cases={}
    cases['scale']=[(p,.5+i*.45,.5+i*.45+.34,85) for i,p in enumerate([60,62,64,65,67,69,71,72,74,72,71,69,67,65,64,62])]
    cases['arpeggio']=[(p,.4+i*.3,.4+i*.3+.22,80) for i,p in enumerate([48,55,60,64,67,72,67,64,50,57,62,65,69,74,69,65])]
    cases['repeated']=[(p,.5+i*.3,.5+i*.3+.19,88) for i,p in enumerate([60,60,60,62,62,64,64,64,67,67,67,64,64,62,60,60])]
    cases['triads']=[(p,.5+i*1.5,.5+i*1.5+1.1,85) for i,chord in enumerate([(48,60,64,67),(53,60,65,69),(55,59,62,67),(48,60,64,67)]) for p in chord]
    cases['legato']=[(p,.5+i*.65,.5+i*.65+.82,75) for i,p in enumerate([60,64,67,72,71,69,65,62])]
    cases['dynamics']=[(p,.5+i*.6,.5+i*.6+.43,v) for i,(p,v) in enumerate(zip([60,62,64,67,72,71,69,67,65,64,62,60],[45,55,65,80,100,110,100,85,70,60,50,45]))]
    folder=args.output.resolve();folder.mkdir(parents=True,exist_ok=True)
    for name,events in cases.items():
        notes=[MidiNote(0,0,p,v,a,b) for p,a,b,v in events]
        seconds=max(n.end for n in notes)+.5
        write_midi(MidiSong(name,1,480,notes,['piano'],[],seconds,[]),folder/(name+'.mid'))
        rate=22050;mix=np.zeros((int(seconds*rate),2),dtype=np.float32)
        for note in notes:
            key=min(samples,key=lambda k:abs(k-note.pitch));audio,sr=samples[key]
            ratio=Fraction(rate/sr/2**((note.pitch-key)/12)).limit_denominator(2000)
            rendered=resample_poly(audio,ratio.numerator,ratio.denominator)
            if rendered.shape[1]==1:rendered=np.repeat(rendered,2,axis=1)
            start=int(note.start*rate);length=min(int((note.end-note.start)*rate),len(rendered),len(mix)-start)
            value=rendered[:length,:2].copy();fade=min(length,int(.025*rate))
            value[-fade:]*=np.linspace(1,0,fade)[:,None]
            mix[start:start+length]+=value*(note.velocity/127)
        mix*=.75/max(.75,float(abs(mix).max()))
        sf.write(folder/(name+'.wav'),mix,rate,subtype='PCM_16')
        mix.mean(axis=1).astype('<f4').tofile(folder/(name+'.f32'))
    fixture=json.loads((args.samples/'fixture.json').read_text(encoding='utf-8'))
    (folder/'manifest.json').write_text(json.dumps({'case_names':list(cases),'sample_provenance':fixture,
        'limitation':'Synthetic calibration phrases from one sample library; not a held-out real-song accuracy benchmark.'},indent=2),encoding='utf-8')
    print(folder)


if __name__=='__main__':main()
