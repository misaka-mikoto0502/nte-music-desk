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


class PlaybackChecks(unittest.TestCase):
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
