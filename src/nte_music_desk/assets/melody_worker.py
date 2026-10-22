"""GAME 1.0.3 ONNX inference, following OpenVPI's documented module workflow.

Reference: https://github.com/openvpi/GAME/blob/main/ONNX.md
The exported encoder includes its audio frontend. No training or lyric input is
needed. Run with optional audio-engine Python (numpy, scipy, soundfile, ORT).
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import sys
from audio_runtime import prefer_system_runtime

prefer_system_runtime()


def infer(config):
    import numpy as np
    import onnxruntime as ort
    import soundfile as sf
    from scipy.signal import resample_poly
    model=Path(config['model'])
    settings=json.loads((model/'config.json').read_text(encoding='utf-8'))
    audio,rate=sf.read(config['source'],dtype='float32',always_2d=True)
    audio=audio.mean(axis=1)
    if not len(audio) or not np.isfinite(audio).all():raise ValueError('人声采样为空或包含非有限值。')
    sr=int(settings['samplerate'])
    if rate!=sr:
        gcd=math.gcd(rate,sr)
        audio=resample_poly(audio,sr//gcd,rate//gcd).astype(np.float32)
    seconds=len(audio)/sr
    opts=ort.SessionOptions()
    opts.intra_op_num_threads=max(1,min(4,(os.cpu_count() or 2)//2))
    opts.inter_op_num_threads=1
    sessions={name:ort.InferenceSession(str(model/(name+'.onnx')),sess_options=opts,providers=['CPUExecutionProvider'])
              for name in ('encoder','segmenter','estimator','dur2bd','bd2dur')}
    def run(name,**values):
        session=sessions[name]
        names={i.name for i in session.get_inputs()}
        missing=names-set(values)
        if missing:raise ValueError(f'GAME {name} 输入不匹配：{sorted(missing)}')
        return dict(zip([o.name for o in session.get_outputs()],session.run(None,{k:v for k,v in values.items() if k in names})))
    language=np.array([settings.get('languages',{}).get(config.get('language','zh'),0)],dtype=np.int64)
    notes=[]
    # Bound transformer memory. One-second context on both sides reduces cuts;
    # crop back to each 20-second core without resetting the shared song timeline.
    for core_sample in range(0,len(audio),20*sr):
        end_sample=min(len(audio),core_sample+20*sr)
        left=max(0,core_sample-sr)
        right=min(len(audio),end_sample+sr)
        waveform=np.ascontiguousarray(audio[left:right][None,:],dtype=np.float32)
        duration=np.array([(right-left)/sr],dtype=np.float32)
        enc=run('encoder',waveform=waveform,duration=duration)
        known=run('dur2bd',durations=duration[:,None],maskN=np.ones((1,1),dtype=bool),maskT=enc['maskT'])
        boundaries=known.get('boundaries',known.get('known_boundaries'))
        if boundaries is None:raise ValueError('GAME 缺少初始边界输出。')
        for step in range(8 if settings.get('loop') else 1):
            seg=run('segmenter',x_seg=enc['x_seg'],maskT=enc['maskT'],known_boundaries=known.get('boundaries',boundaries),
                    prev_boundaries=boundaries,language=language,threshold=np.array(.2,dtype=np.float32),
                    radius=np.array(2,dtype=np.int64),t=np.array([step/8],dtype=np.float32))
            boundaries=seg['boundaries']
        durations=run('bd2dur',boundaries=boundaries,maskT=enc['maskT'],duration=duration)
        estimated=run('estimator',x_est=enc['x_est'],boundaries=boundaries,maskT=enc['maskT'],maskN=durations['maskN'],threshold=np.array(.2,dtype=np.float32))
        cursor=left/sr
        for length,valid,present,pitch in zip(durations['durations'][0],durations['maskN'][0],estimated['presence'][0],estimated['scores'][0]):
            if not valid:continue
            finish=cursor+float(length)
            start=max(cursor,core_sample/sr)
            stop=min(finish,end_sample/sr,seconds)
            if present and math.isfinite(float(pitch)) and 0<=pitch<=127 and stop-start>=.04:
                item={'start':round(start,6),'end':round(stop,6),'pitch':int(np.rint(pitch))}
                # Only coalesce a note split exactly at the processing boundary.
                if notes and core_sample>0 and abs(start-core_sample/sr)<.015 and abs(notes[-1]['end']-start)<.015 and notes[-1]['pitch']==item['pitch']:
                    notes[-1]['end']=item['end']
                else:notes.append(item)
            cursor=finish
        print(f'旋律 Beta：{end_sample/sr:.1f} / {seconds:.1f} 秒',flush=True)
    return {'seconds':seconds,'notes':notes,'engine':'GAME','version':'1.0.3','model':'small-onnx',
            'provider':'CPUExecutionProvider','steps':8,'language':config.get('language','zh'),
            'note':'Predicted singing notes; beta; no manual pitch correction or rhythm quantization.'}


if __name__=='__main__':
    config=json.loads(Path(sys.argv[1]).read_text(encoding='utf-8'))
    result=infer(config)
    Path(config['response']).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
