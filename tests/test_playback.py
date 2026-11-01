import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from nte_music_desk.playback import PauseControl, write_pause_command, execute_plan
from nte_music_desk.performance import PerformancePlan
from nte_music_desk.keyboard import KEYS, PlaybackStopped
from nte_music_desk.instruments import SHIFT


class Clock:
    def __init__(self):self.now=0
    def read(self):return self.now
    def sleep(self,t):self.now+=t


class Keyboard:
    def __init__(self,clock,stop=None):self.clock,self.stop,self.held,self.events=clock,stop,set(),[]
    def check(self):
        if self.stop is not None and self.clock.now>=self.stop:raise PlaybackStopped('focus or cancel')
    def down(self,key):
        self.check()
        if key==SHIFT:assert not self.held
        self.held.add(key);self.events.append((self.clock.now,True,key))
    def up(self,key):
        if key in self.held:self.held.remove(key);self.events.append((self.clock.now,False,key))
    def release_all(self):
        for key in sorted(self.held,key=lambda k:k==SHIFT):self.up(key)


class TimedPause:
    sequence=1
    def __init__(self,clock,end=.6,start=.1):self.clock,self.end,self.start=clock,end,start
    def poll(self):return self.start<=self.clock.now<self.end


class TimedSeek:
    sequence=0
    def __init__(self,clock,at,target,pause=None):
        self.clock,self.at,self.target,self.pause=clock,at,target,pause
        self.issued,self.pending=False,None
    def poll(self):
        if not self.issued and self.clock.now>=self.at:
            self.pending=self.target;self.issued=True;self.sequence=1
        return self.pause is not None and self.pause[0]<=self.clock.now<self.pause[1]
    def take_seek(self):
        value,self.pending=self.pending,None;return value


class PlaybackChecks(unittest.TestCase):
    def test_start_in_middle_restores_shift_and_sustain_without_old_attacks(self):
        a,b=KEYS['E3'],KEYS['F3']
        plan=PerformancePlan(((0,True,SHIFT),(.02,True,a),(.3,False,a),(.31,False,SHIFT),(.6,True,b),(.8,False,b)),(),1,0)
        clock=Clock();keyboard=Keyboard(clock)
        execute_plan(plan,keyboard,clock=clock.read,sleep=clock.sleep,start_at=.2)
        self.assertEqual([k for _,down,k in keyboard.events if down],[SHIFT,a,b])
        self.assertAlmostEqual(clock.now,.815,delta=.001);self.assertFalse(keyboard.held)
        downs=[at for at,down,_ in keyboard.events if down]
        self.assertGreaterEqual(downs[1]-downs[0],.015-1e-9)

    def test_forward_and_backward_seek_reconstruct_the_new_key_state(self):
        a,b=KEYS['E3'],KEYS['F3']
        plan=PerformancePlan(((0,True,a),(.4,False,a),(.6,True,b),(.8,False,b)),(),1,0)
        for at,target,expected in [(.1,.6,[a,b]),(.65,.1,[a,b,a,b])]:
            clock=Clock();keyboard=Keyboard(clock);control=TimedSeek(clock,at,target);states=[]
            execute_plan(plan,keyboard,clock=clock.read,sleep=clock.sleep,control=control,on_progress=lambda *s:states.append(s))
            self.assertEqual([k for _,down,k in keyboard.events if down],expected)
            self.assertTrue(any(abs(elapsed-target)<.011 and seq==1 for _,elapsed,seq in states))
            self.assertFalse(keyboard.held)

    def test_seek_while_paused_stays_silent_until_resume(self):
        a,b=KEYS['E3'],KEYS['F3']
        plan=PerformancePlan(((0,True,a),(.4,False,a),(.6,True,b),(.8,False,b)),(),1,0)
        clock=Clock();keyboard=Keyboard(clock);control=TimedSeek(clock,.2,.6,pause=(.1,.5))
        execute_plan(plan,keyboard,clock=clock.read,sleep=clock.sleep,control=control)
        self.assertFalse(any(down and .1<at<.5 for at,down,_ in keyboard.events))
        self.assertAlmostEqual(next(at for at,down,k in keyboard.events if down and k==b),.5,delta=.011)
        self.assertFalse(keyboard.held)

    def test_seek_id_survives_fast_pause_commands_without_repeating_the_jump(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'control.json';clock=Clock();control=PauseControl(path,clock=clock.read)
            write_pause_command(path,False,1,seek_to=.6,seek_sequence=1)
            control.poll();self.assertEqual(control.take_seek(),.6)
            write_pause_command(path,True,2,seek_to=.6,seek_sequence=1);clock.now+=.1
            self.assertTrue(control.poll());self.assertIsNone(control.take_seek())
            write_pause_command(path,True,3,seek_to=.2,seek_sequence=3);clock.now+=.1
            control.poll();self.assertEqual(control.take_seek(),.2)
            with self.assertRaises(ValueError):write_pause_command(path,False,4,seek_to=float('nan'))

    def test_pause_freezes_timeline_releases_and_restores_sustain_without_skipping(self):
        a,b=KEYS['E3'],KEYS['F3']
        plan=PerformancePlan(((0,True,a),(.4,False,a),(.6,True,b),(.8,False,b)),(),1,0)
        clock=Clock();keyboard=Keyboard(clock);states=[]
        sent=execute_plan(plan,keyboard,clock=clock.read,sleep=clock.sleep,control=TimedPause(clock),on_progress=lambda *state:states.append(state))
        self.assertEqual(sent,2)
        self.assertAlmostEqual(clock.now,1.5,delta=.02)
        downs=[(at,key) for at,down,key in keyboard.events if down]
        self.assertEqual([key for _,key in downs],[a,a,b])
        self.assertAlmostEqual(downs[1][0],.6,delta=.02)
        self.assertAlmostEqual(downs[2][0],1.1,delta=.02)
        paused=[at for phase,at,_ in states if phase=='paused']
        self.assertTrue(paused);self.assertAlmostEqual(max(paused),min(paused))
        self.assertFalse(keyboard.held)

    def test_pause_restores_shift_before_notes_and_stop_while_paused_releases(self):
        a=KEYS['F3']
        plan=PerformancePlan(((0,True,SHIFT),(.02,True,a),(.3,False,a),(.31,False,SHIFT)),(),.5,0)
        clock=Clock();keyboard=Keyboard(clock)
        execute_plan(plan,keyboard,clock=clock.read,sleep=clock.sleep,control=TimedPause(clock,end=.5))
        restored=[key for at,down,key in keyboard.events if down and at>=.49]
        self.assertEqual(restored,[SHIFT,a]);self.assertFalse(keyboard.held)
        clock=Clock();keyboard=Keyboard(clock,stop=.4)
        with self.assertRaises(PlaybackStopped):execute_plan(plan,keyboard,clock=clock.read,sleep=clock.sleep,control=TimedPause(clock,end=10))
        self.assertFalse(keyboard.held)
        self.assertEqual(len([1 for _,down,_ in keyboard.events if down]),2)

    def test_control_sequences_invalid_input_and_f7_edges(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'control.json';clock=Clock();key=[True]
            control=PauseControl(path,lambda:key[0],clock.read)
            self.assertFalse(control.poll())
            key[0]=False;control.poll();key[0]=True
            self.assertTrue(control.poll());self.assertTrue(control.poll())
            write_pause_command(path,False,1);clock.now+=.1
            self.assertFalse(control.poll());self.assertEqual(control.sequence,1)
            path.write_text('{bad');clock.now+=.1
            self.assertFalse(control.poll())
            write_pause_command(path,True,2);clock.now+=.1
            self.assertTrue(control.poll())
            write_pause_command(path,False,1);clock.now+=.1
            self.assertTrue(control.poll())
            with self.assertRaises(ValueError):write_pause_command(path,1,3)

    def test_resume_at_release_boundary_does_not_retrigger_finished_note(self):
        a=KEYS['E3']
        plan=PerformancePlan(((0,True,a),(.4,False,a)),(),.6,0)
        clock=Clock();keyboard=Keyboard(clock);states=[]
        execute_plan(plan,keyboard,clock=clock.read,sleep=clock.sleep,control=TimedPause(clock,end=.8,start=.4),
                     on_progress=lambda *state:states.append(state))
        self.assertTrue(any(phase=='paused' for phase,_,_ in states))
        self.assertEqual(len([1 for _,down,_ in keyboard.events if down]),1)
        self.assertFalse(keyboard.held)
