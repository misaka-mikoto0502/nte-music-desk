import ctypes
from pathlib import Path
import struct
import sys
import unittest
import tempfile
import wave
import copy
from unittest.mock import patch
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nte_music_desk import midi, cli
from nte_music_desk.instruments import SHIFT
from nte_music_desk.keyboard import PlaybackStopped, WindowsKeyboard, elevation_command
from nte_music_desk.performance import performance_plan


def song(pitches=(60,63,67)):
    return midi.MidiSong("fixture",0,480,[midi.MidiNote(0,0,p,80,0,.5) for p in pitches],
                         ["lead"],[(0,500000)],.5,[])


class Clock:
    now = 0
    def read(self): return self.now
    def sleep(self,value): self.now += value


class Keyboard:
    def __init__(self,clock,stop_at=None): self.clock,self.stop_at,self.held,self.notes=clock,stop_at,set(),[]
    def check(self):
        if self.stop_at is not None and self.clock.now>=self.stop_at: raise PlaybackStopped("cancel")
    def down(self,key):
        self.check()
        if key==SHIFT: assert not self.held
        else: self.notes.append((key.virtual_key,SHIFT in self.held))
        self.held.add(key)
    def up(self,key): self.held.discard(key)
    def release_all(self): self.held.clear()


class MidiChecks(unittest.TestCase):
    def test_preview_and_execution_share_mixed_chord_and_repeated_key_timing(self):
        for instrument in ('piano', 'guitar'):
            for mode in ('melody', 'chords'):
                original = midi.convert(song(), instrument=instrument, mode=mode)
                before = copy.deepcopy(original)
                performance_plan(original)
                self.assertEqual(original, before)
        score = midi.convert(song((60, 61, 67)), mode='chords', instrument='piano')
        plan = performance_plan(score, 200)
        self.assertEqual(plan.mixed_groups, 1)
        self.assertEqual([round(n.at, 3) for n in plan.notes], [.02, .02, .075])
        self.assertEqual(list(plan.key_events), cli.key_schedule(score, 200))
        with patch.object(cli, 'render_audio') as render:
            cli.render_preview(score, 'unused.wav', hold_ms=200)
            self.assertEqual(render.call_args.args[0], [{'at': n.at, 'duration': n.duration, 'midi': n.midi} for n in plan.notes])
        clock = Clock(); keyboard = Keyboard(clock)
        cli.play_timed(score, keyboard, 200, clock=clock.read, sleep=clock.sleep)
        self.assertAlmostEqual(clock.now, plan.duration)
        self.assertEqual(len(keyboard.notes), len(plan.notes))
        self.assertFalse(keyboard.held)
        repeated = song((60,))
        repeated.notes.append(midi.MidiNote(0, 0, 60, 80, .1, .4))
        plan = performance_plan(midi.convert(repeated, mode='chords', instrument='guitar'))
        self.assertLess(plan.notes[0].at + plan.notes[0].duration, plan.notes[1].at)

    def test_track_audition_preserves_source_polyphony_and_range(self):
        fixture = song((24, 36, 48, 60, 72, 84, 96, 108))
        fixture.notes.append(midi.MidiNote(1, 0, 65, 80, 0, .5))
        fixture.track_names.append('other')
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / 'preview.wav'
            with patch.object(cli, 'render_audio', return_value=.5) as render:
                self.assertEqual(cli.render_song_preview(fixture, path, tracks=[0]), .5)
                events = render.call_args.args[0]
                self.assertEqual([e['midi'] for e in events], [24, 36, 48, 60, 72, 84, 96, 108])
            cli.render_song_preview(fixture, path, tracks=[1])
            with wave.open(str(path)) as audio:
                self.assertEqual(audio.getframerate(), 22050)
                self.assertGreater(audio.getnframes(), 1000)
            with self.assertRaises(ValueError):
                cli.render_song_preview(fixture, path, tracks=[9])

    def test_tempo_integration_and_running_status(self):
        track=(b'\x00\xff\x51\x03\x07\xa1\x20'+b'\x00\x90\x3c\x50'+
               b'\x83\x60\xff\x51\x03\x0f\x42\x40'+b'\x83\x60\x90\x3c\x00'+b'\x00\xff\x2f\x00')
        data=b'MThd'+struct.pack('>IHHH',6,0,1,480)+b'MTrk'+struct.pack('>I',len(track))+track
        result=midi.parse_midi(data)
        self.assertAlmostEqual(result.notes[0].end,1.5)
        for invalid in (b'not MIDI',data[:-3]):
            with self.assertRaises(ValueError): midi.parse_midi(invalid)

    def test_profile_ranges_and_old_scores(self):
        original=song((33,96))
        for instrument,low,high in (("guitar",52,87),("piano",48,83)):
            converted=midi.convert(original,instrument=instrument,mode="chords")
            self.assertTrue(all(low<=n["midi"]<=high for n in converted["events"]))
            self.assertTrue(all(n["midi"]%12==n["source_midi"]%12 for n in converted["events"]))
        old=midi.convert(song());old.pop("instrument")
        self.assertIs(midi.validate_score(old),old)

    def test_mixed_chords_and_cancel_cleanup(self):
        score=midi.convert(song(),mode="chords",instrument="piano")
        clock=Clock(); keyboard=Keyboard(clock)
        self.assertEqual(cli.play_timed(score,keyboard,clock=clock.read,sleep=clock.sleep),3)
        self.assertCountEqual(keyboard.notes,[(0x41,False),(0x53,True),(0x47,False)])
        self.assertFalse(keyboard.held)
        for stop in (.03,.067,.08):
            clock=Clock();keyboard=Keyboard(clock,stop_at=stop)
            with self.assertRaises(PlaybackStopped): cli.play_timed(score,keyboard,clock=clock.read,sleep=clock.sleep)
            self.assertFalse(keyboard.held)
        # Exercise the real cleanup/focus guard against a fake Win32 surface.
        # Do not construct WindowsKeyboard or call a native input function.
        native=WindowsKeyboard.__new__(WindowsKeyboard)
        key=next(k for _,_,k in cli.key_schedule(score) if k!=SHIFT)
        sent=[]
        native.held,native.allow_shift,native.hwnd,native.pid={key,SHIFT},True,101,55
        native.cancelled=lambda:False
        native.window_pid=lambda hwnd:55
        native.user32=SimpleNamespace(IsWindow=lambda hwnd:True,GetForegroundWindow=lambda:101,
            GetAsyncKeyState=lambda vk:0x8000 if vk==0x10 else 0,
            keybd_event=lambda vk,scan,flags,extra:sent.append((vk,flags)))
        native.check()  # Our own Shift is allowed while the target has focus.
        native.user32.GetForegroundWindow=lambda:202
        with self.assertRaises(PlaybackStopped):native.check()
        native.release_all()
        self.assertEqual(sent,[(key.virtual_key,2),(SHIFT.virtual_key,2)])
        self.assertFalse(native.held)

    def test_shared_letter_has_release_and_frozen_relaunch(self):
        score=midi.convert(song((60,61)),mode="chords",instrument="piano")
        schedule=cli.key_schedule(score)
        letter=[(at,down) for at,down,key in schedule if key.virtual_key==0x41]
        self.assertEqual([down for _,down in letter],[1,0,1,0])
        with patch.object(sys,"frozen",True,create=True):
            exe,args,cwd=elevation_command(["--play","曲谱 with spaces.json"])
            self.assertEqual(exe,sys.executable)
            self.assertNotIn("-I",args)
            self.assertEqual(args.count("--elevated-child"),1)
        exe,args,cwd=elevation_command([])
        self.assertTrue(Path(args[4]).is_file())
        self.assertIn("-I",args)


if __name__=="__main__": unittest.main()
