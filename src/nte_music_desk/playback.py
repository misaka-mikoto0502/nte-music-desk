"""Pause the performance clock, releasing physical keys until resume."""
import json
import math
from bisect import bisect_left
from pathlib import Path
import time


def write_pause_command(path, paused, sequence, *, seek_to=None, seek_sequence=None):
    if type(paused) is not bool or type(sequence) is not int or not 1<=sequence<2**63:
        raise ValueError('暂停控制参数无效。')
    command={'schema':'nte-player-control-v1','paused':paused,'sequence':sequence}
    if seek_to is not None:
        seek_sequence=sequence if seek_sequence is None else seek_sequence
        if (type(seek_to) not in (int,float) or not math.isfinite(seek_to) or seek_to<0
                or type(seek_sequence) is not int or not 1<=seek_sequence<=sequence):
            raise ValueError('定位控制参数无效。')
        command.update(seek_to=seek_to,seek_sequence=seek_sequence)
    path=Path(path)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps(command),encoding='utf-8')
    temporary.replace(path)


class PauseControl:
    def __init__(self,path=None,hotkey=None,clock=time.perf_counter):
        self.path=Path(path) if path else None
        self.hotkey,self.clock=hotkey,clock
        self.paused,self.sequence,self.next_read=False,0,0
        self.seek_sequence,self.pending_seek=0,None
        self.key_down=bool(hotkey()) if hotkey else False

    def poll(self):
        now=self.clock()
        if self.path and now>=self.next_read:
            self.next_read=now+.025
            try:
                if self.path.stat().st_size<=4096:
                    data=json.loads(self.path.read_text(encoding='utf-8'))
                    valid_seek=('seek_to' not in data or (type(data.get('seek_to')) in (int,float)
                        and math.isfinite(data['seek_to']) and data['seek_to']>=0
                        and type(data.get('seek_sequence')) is int and type(data.get('sequence')) is int
                        and 1<=data['seek_sequence']<=data['sequence'])) if isinstance(data,dict) else False
                    if (isinstance(data,dict) and valid_seek and data.get('schema')=='nte-player-control-v1'
                            and type(data.get('paused')) is bool and type(data.get('sequence')) is int
                            and self.sequence<data['sequence']<2**63):
                        self.paused,self.sequence=data['paused'],data['sequence']
                        if 'seek_to' in data and data['seek_sequence']>self.seek_sequence:
                            self.pending_seek=data['seek_to'];self.seek_sequence=data['seek_sequence']
            except (OSError,ValueError):pass
        if self.hotkey:
            down=bool(self.hotkey())
            if down and not self.key_down:self.paused=not self.paused
            self.key_down=down
        return self.paused

    def take_seek(self):
        position,self.pending_seek=self.pending_seek,None
        return position


class PerformanceClock:
    def __init__(self,clock):
        self.clock,self.started=clock,clock()
        self.paused_at,self.pause_seconds=None,0

    def elapsed(self):
        return (self.clock() if self.paused_at is None else self.paused_at)-self.started-self.pause_seconds

    def pause(self):
        if self.paused_at is None:self.paused_at=self.clock()

    def resume(self):
        if self.paused_at is not None:
            self.pause_seconds+=self.clock()-self.paused_at
            self.paused_at=None

    def seek(self,position):
        now=self.clock()
        self.started,self.pause_seconds=now-position,0
        if self.paused_at is not None:self.paused_at=now


def execute_plan(plan,backend,*,clock=time.perf_counter,sleep=time.sleep,control=None,on_progress=None,start_at=0):
    from .keyboard import PlaybackStopped
    if type(start_at) not in (int,float) or not math.isfinite(start_at) or not 0<=start_at<=plan.duration:
        raise ValueError('演奏位置超出曲谱范围。')
    timeline=PerformanceClock(clock);timeline.seek(start_at)
    wanted={}
    release_at,next_release={},{}
    for index in range(len(plan.key_events)-1,-1,-1):
        at,down,key=plan.key_events[index]
        if down:release_at[index]=next_release.get(key,plan.duration)
        else:next_release[key]=at
    times=[event[0] for event in plan.key_events]
    checkpoints,state={},{}
    for i,(at,down,key) in enumerate(plan.key_events):
        if i%512==0:checkpoints[i]=dict(state)
        if down:state[key]=release_at[i]
        else:state.pop(key,None)
    checkpoints[len(plan.key_events)]=dict(state)

    def locate(position):
        index=bisect_left(times,position)
        checkpoint=index if index in checkpoints else index//512*512
        state=dict(checkpoints[checkpoint])
        for i in range(checkpoint,index):
            _,down,key=plan.key_events[i]
            if down:state[key]=release_at[i]
            else:state.pop(key,None)
        return index,{key:end for key,end in state.items() if end>position+1e-9}

    index,wanted=locate(start_at)
    restore_pending=True
    sent,last_report=0,-1

    def publish(force=False):
        nonlocal last_report
        now=clock()
        if on_progress and (force or now-last_report>=.1):
            last_report=now
            on_progress('paused' if timeline.paused_at is not None else 'playing',
                        min(plan.duration,max(0,timeline.elapsed())),getattr(control,'sequence',0))

    try:
        while True:
            backend.check()
            paused=control.poll() if control else False
            changed=False
            if paused and timeline.paused_at is None:
                timeline.pause()
                backend.release_all()
                changed=True
            elif not paused and timeline.paused_at is not None:
                timeline.resume()
                restore_pending=True;changed=True
            target=control.take_seek() if control and hasattr(control,'take_seek') else None
            if target is not None:
                backend.release_all()
                target=min(plan.duration,max(0,target))
                timeline.seek(target);index,wanted=locate(target)
                restore_pending=True;changed=True
            if timeline.paused_at is None and restore_pending:
                # Restore the global modifier before any still-sustained notes.
                for key in sorted(wanted,key=lambda k:(k.virtual_key!=0xA0,k.scan_code)):
                    if wanted[key]>timeline.elapsed()+1e-9:backend.down(key)
                restore_pending=False
            publish(changed)
            if timeline.paused_at is not None:
                sleep(.01)
                continue
            at=plan.key_events[index][0] if index<len(plan.key_events) else plan.duration
            remaining=at-timeline.elapsed()
            if remaining>1e-9:
                sleep(min(.01,remaining));continue
            if index>=len(plan.key_events):break
            if timeline.elapsed()-at>.3:
                raise PlaybackStopped('系统调度延迟超过 300 毫秒，已停止，避免音符挤在一起。')
            _,is_down,key=plan.key_events[index]
            if is_down:
                backend.down(key);wanted[key]=release_at[index]
                sent+=key.virtual_key!=0xA0
            else:
                if key in wanted:backend.up(key)
                wanted.pop(key,None)
            index+=1
        publish(True)
        return sent
    finally:
        backend.release_all()
        publish(True)
