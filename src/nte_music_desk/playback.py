"""Pause the performance clock, releasing physical keys until resume."""
import json
from pathlib import Path
import time


def write_pause_command(path, paused, sequence):
    if type(paused) is not bool or type(sequence) is not int or not 1<=sequence<2**63:
        raise ValueError('暂停控制参数无效。')
    path=Path(path)
    temporary=path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'schema':'nte-player-control-v1','paused':paused,'sequence':sequence}),encoding='utf-8')
    temporary.replace(path)


class PauseControl:
    def __init__(self,path=None,hotkey=None,clock=time.perf_counter):
        self.path=Path(path) if path else None
        self.hotkey,self.clock=hotkey,clock
        self.paused,self.sequence,self.next_read=False,0,0
        self.key_down=bool(hotkey()) if hotkey else False

    def poll(self):
        now=self.clock()
        if self.path and now>=self.next_read:
            self.next_read=now+.025
            try:
                if self.path.stat().st_size<=4096:
                    data=json.loads(self.path.read_text(encoding='utf-8'))
                    if (isinstance(data,dict) and data.get('schema')=='nte-player-control-v1'
                            and type(data.get('paused')) is bool and type(data.get('sequence')) is int
                            and self.sequence<data['sequence']<2**63):
                        self.paused,self.sequence=data['paused'],data['sequence']
            except (OSError,ValueError):pass
        if self.hotkey:
            down=bool(self.hotkey())
            if down and not self.key_down:self.paused=not self.paused
            self.key_down=down
        return self.paused


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


def execute_plan(plan,backend,*,clock=time.perf_counter,sleep=time.sleep,control=None,on_progress=None):
    from .keyboard import PlaybackStopped
    timeline=PerformanceClock(clock)
    wanted={}
    release_at,next_release={},{}
    for index in range(len(plan.key_events)-1,-1,-1):
        at,down,key=plan.key_events[index]
        if down:release_at[index]=next_release.get(key,plan.duration)
        else:next_release[key]=at
    sent,last_report=0,-1

    def publish(force=False):
        nonlocal last_report
        now=clock()
        if on_progress and (force or now-last_report>=.1):
            last_report=now
            on_progress('paused' if timeline.paused_at is not None else 'playing',
                        min(plan.duration,max(0,timeline.elapsed())),getattr(control,'sequence',0))

    def wait_until(at):
        while True:
            backend.check()
            paused=control.poll() if control else False
            if paused and timeline.paused_at is None:
                timeline.pause()
                backend.release_all()
                publish(True)
            elif not paused and timeline.paused_at is not None:
                timeline.resume()
                # Restore the global modifier before any still-sustained notes.
                for key in sorted(wanted,key=lambda k:(k.virtual_key!=0xA0,k.scan_code)):
                    if wanted[key]>timeline.elapsed()+1e-9:backend.down(key)
                publish(True)
            publish()
            if timeline.paused_at is not None:
                sleep(.01)
                continue
            remaining=at-timeline.elapsed()
            if remaining<=1e-9:return
            sleep(min(.01,remaining))

    try:
        for index,(at,is_down,key) in enumerate(plan.key_events):
            wait_until(at)
            if timeline.elapsed()-at>.3:
                raise PlaybackStopped('系统调度延迟超过 300 毫秒，已停止，避免音符挤在一起。')
            if is_down:
                backend.down(key);wanted[key]=release_at[index]
                sent+=key.virtual_key!=0xA0
            else:
                backend.up(key);wanted.pop(key,None)
        wait_until(plan.duration)
        publish(True)
        return sent
    finally:backend.release_all()
