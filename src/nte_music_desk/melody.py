"""Opt-in singing melody extraction, using the official GAME ONNX release.

Model weights are a separate download under CC BY-NC-SA 4.0. No weights are
included in the desktop bundle; every task retains the untouched note timings.
"""
from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import math
from pathlib import Path
import urllib.request
import uuid
import zipfile

from .midi import MidiNote, MidiSong, read_midi, write_midi
from .paths import asset_dir
from .transcription import TranscriptionCancelled

GAME_VERSION = '1.0.3'
GAME_URL = 'https://github.com/openvpi/GAME/releases/download/v1.0.3/GAME-1.0.3-small-onnx.zip'
GAME_SHA256 = '00ba0c64115b6b874d9ea4afd3e6cf822abda2a04e52569233b0a044fd40e4e8'
GAME_FILES = {'config.json','encoder.onnx','segmenter.onnx','estimator.onnx','dur2bd.onnx','bd2dur.onnx'}


def game_model_directory(directory):
    return Path(directory)/'audio-models'/'game-1.0.3-small'


def unpack_model(archive, target):
    """Only six fixed files, bounded sizes, no extractall or archive paths."""
    target = Path(target)
    if hashlib.sha256(Path(archive).read_bytes()).hexdigest() != GAME_SHA256:
        raise ValueError('旋律 Beta 模型校验失败，请重新下载官方模型。')
    with zipfile.ZipFile(archive) as z:
        files = [i for i in z.infolist() if not i.is_dir()]
        if len(files)!=6 or {i.filename for i in files} != {'GAME-1.0.3-small-onnx/'+name for name in GAME_FILES} or sum(i.file_size for i in files)>80*1024*1024 or any(i.flag_bits&1 for i in files):
            raise ValueError('旋律模型压缩包结构不匹配。')
        target.mkdir(parents=True,exist_ok=True)
        hashes = {}
        for entry in files:
            data=z.read(entry)
            name=entry.filename.rsplit('/',1)[1]
            (target/name).write_bytes(data)
            hashes[name]=hashlib.sha256(data).hexdigest()
    (target/'verified.json').write_text(json.dumps({'version':GAME_VERSION,'archive_sha256':GAME_SHA256,'files':hashes,
        'source':GAME_URL,'license':'CC BY-NC-SA 4.0','license_url':'https://github.com/openvpi/GAME/releases/tag/v1.0.0'},indent=2),encoding='utf-8')


def model_ready(directory):
    target=game_model_directory(directory)
    try:
        marker=json.loads((target/'verified.json').read_text(encoding='utf-8'))
        return marker['archive_sha256']==GAME_SHA256 and set(marker['files'])==GAME_FILES and all(
            (target/name).is_file() and hashlib.sha256((target/name).read_bytes()).hexdigest()==marker['files'][name] for name in GAME_FILES)
    except (OSError,ValueError,KeyError,TypeError):
        return False


def prepare_model(job, directory, notify=None, *, accepted_terms=False):
    if accepted_terms is not True:
        raise ValueError('首次下载或使用 GAME 权重前，请阅读并确认 CC BY-NC-SA 4.0 模型条款；模型许可不替代音乐授权。')
    if model_ready(directory): return game_model_directory(directory)
    target=game_model_directory(directory)
    target.parent.mkdir(parents=True,exist_ok=True)
    staging=target.parent/('game-download-'+uuid.uuid4().hex+'.zip')
    try:
        if notify:notify('正在下载旋律 Beta 小模型（约 46 MB，仅首次需要）…')
        with urllib.request.urlopen(urllib.request.Request(GAME_URL,headers={'User-Agent':'NTE-Music-Desk'}),timeout=30) as response, staging.open('wb') as stream:
            total=0
            while block:=response.read(256*1024):
                if job.cancelled.is_set():raise TranscriptionCancelled('旋律模型下载已取消。')
                total+=len(block)
                if total>50*1024*1024:raise ValueError('模型下载大小超出预期。')
                stream.write(block)
        if job.cancelled.is_set():raise TranscriptionCancelled('旋律模型下载已取消。')
        unpack_model(staging,target)
        return target
    finally:
        staging.unlink(missing_ok=True)


def events_to_song(data,title):
    if not isinstance(data,dict) or type(data.get('seconds')) not in (float,int) or not math.isfinite(data['seconds']) or not 0<data['seconds']<=1800:
        raise ValueError('旋律 Beta 返回的音频时长无效。')
    events=data.get('notes')
    if not isinstance(events,list) or not 0<len(events)<=100000:
        raise ValueError('旋律 Beta 没有识别到可用的歌声，请换用独唱更清晰的片段。')
    notes=[]
    for event in events:
        if not isinstance(event,dict):raise ValueError('旋律 Beta 返回的音符无效。')
        p,a,b=event.get('pitch'),event.get('start'),event.get('end')
        if type(p) is not int or not 0<=p<=127 or any(type(t) not in (float,int) or not math.isfinite(t) for t in (a,b)) or not 0<=a<min(b,data['seconds'])<=b<=data['seconds']+.03:
            raise ValueError('旋律 Beta 返回的音高或时间无效。')
        notes.append(MidiNote(0,0,p,88,a,min(b,data['seconds']),0))
    notes.sort(key=lambda n:(n.start,n.pitch))
    # The singing model is monophonic. Large overlapping notes indicate a
    # broken worker response, not permission to invent polyphonic vocals.
    if any(a.end>b.start+.03 for a,b in zip(notes,notes[1:])):
        raise ValueError('旋律 Beta 的单旋律时间重叠异常，未合入伴奏。')
    return MidiSong(title,1,480,notes,['主旋律 · Beta'],[(0,500000)],data['seconds'],[])


def combine_with_accompaniment(accompaniment,melody,title):
    """Seconds are shared. Never trim leading rests or independently retime."""
    offset=len(accompaniment.track_names)
    # Avoid assigning more than 15 GM patches to the single MIDI port. Converting
    # every voice to a piano is deliberate here; instrument names remain in tracks.
    from .parts import instrument_name
    names=list(accompaniment.track_names)+list(melody.track_names)
    notes=[]
    for n in accompaniment.notes:
        if n.channel==9:continue
        notes.append(replace(n,program=0))
        names[n.track]=f'伴奏 · {instrument_name(n.program,n.channel)} · {accompaniment.track_names[n.track]}'
    notes.extend(replace(n,track=n.track+offset,program=0) for n in melody.notes)
    return MidiSong(title,1,480,sorted(notes,key=lambda n:(n.start,n.track,n.pitch)),names,[(0,500000)],max(accompaniment.seconds,melody.seconds),
                    ['主旋律为 Beta 识别结果；伴奏与旋律均转换为钢琴音色，原始伴奏 MIDI 另存保留。'])


def extract_beta(job,executable,audio,directory,models_directory,notify=None,language='auto',*,accepted_terms=False):
    model=prepare_model(job,models_directory,notify,accepted_terms=accepted_terms)
    target=Path(directory)
    request,response=target/'melody-request.json',target/'melody-response.json'
    request.write_text(json.dumps({'source':str(audio),'model':str(model),'response':str(response),'language':language},ensure_ascii=False),encoding='utf-8')
    job.run([str(executable),str(asset_dir()/'melody_worker.py'),str(request)],target/'engine.log',notify,
            failure='旋律 Beta 识别失败，已完成的伴奏仍可使用。')
    if not response.is_file() or response.stat().st_size>16*1024*1024:
        raise ValueError('旋律 Beta 未返回有效结果。')
    data=json.loads(response.read_text(encoding='utf-8'))
    song=events_to_song(data,'主旋律 · Beta')
    path=target/'melody-beta.mid'
    write_midi(song,path)
    return path,data
