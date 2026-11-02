"""Compare an untouched model MIDI with a known, authorized reference MIDI."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from nte_music_desk.audio_quality import compare_notes
from nte_music_desk.midi import read_midi


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reference',type=Path)
    parser.add_argument('prediction',type=Path)
    parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--tolerance',type=float,default=.1)
    args=parser.parse_args()
    if args.output.resolve() in (args.reference.resolve(),args.prediction.resolve()):
        parser.error('报告不能覆盖输入 MIDI。')
    report=compare_notes(read_midi(args.reference),read_midi(args.prediction),args.tolerance)
    report['files']={name:{'name':path.name,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
                     for name,path in (('reference',args.reference),('prediction',args.prediction))}
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
