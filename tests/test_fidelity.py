import sys
from pathlib import Path
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nte_music_desk.midi import MidiSong, MidiNote, convert, validate_score
from nte_music_desk.performance import performance_plan
from nte_music_desk.analysis import adaptation_report
from nte_music_desk.instruments import SHIFT


def fixture(notes, names=('melody', 'bass', 'harmony')):
    return MidiSong('voices', 1, 480, sorted(notes, key=lambda n: (n.start, n.pitch)), list(names), [(0, 500000)], max(n.end for n in notes), [])


class FidelityChecks(unittest.TestCase):
    def test_twelve_voice_chord_and_duplicate_accounting(self):
        song = fixture([MidiNote(0, 0, p, 80, 0, .5) for p in range(60, 72)])
        score = convert(song, mode='faithful')
        self.assertEqual(len(score['events']), 12)
        self.assertEqual(adaptation_report(score, performance_plan(score))['performance']['peak_held_keys'], 12)
        self.assertEqual(len(convert(song, mode='chords')['events']), 6)
        song.notes += [MidiNote(1, 1, 60, 70, 0, .5)]
        score = convert(song, mode='faithful')
        s = score['summary']
        self.assertEqual(s['source_notes'], s['notes'] + s['merged'] + s['dropped'] + s['chord_notes_removed'])
        self.assertEqual(s['merged'], 1)
        score['settings']['max_polyphony'] = 11
        with self.assertRaises(ValueError): validate_score(score)

    def test_role_priority_and_original_onsets(self):
        notes = [MidiNote(0, 0, 60, 30, 0, .4), MidiNote(1, 1, 52, 30, 0, .4)]
        notes += [MidiNote(2, 2, p, 120, 0, .4) for p in range(65, 75)]
        score = convert(fixture(notes), mode='balanced', max_polyphony=2, roles={'0': 'melody', '1': 'bass'})
        self.assertEqual({e['source_midi'] for e in score['events']}, {52, 60})
        score = convert(fixture([MidiNote(0, 0, 60, 80, .123456, .5), MidiNote(0, 0, 64, 90, .133456, .6)]), mode='faithful')
        self.assertEqual([e['at'] for e in score['events']], [0, .01])
        self.assertLess(adaptation_report(score, performance_plan(score))['performance']['max_onset_deviation_ms'], .001)

    def test_whole_voice_octave_preserves_intervals(self):
        score = convert(fixture([MidiNote(0, 0, p, 80, i * .4, i * .4 + .3) for i, p in enumerate((48, 55, 60))]), mode='faithful')
        self.assertEqual([e['midi'] for e in score['events']], [60, 67, 72])
        self.assertEqual(score['adaptation']['voice_octaves'], {'0': 12})

    def test_piano_overlap_and_shift_release_guards(self):
        song = fixture([MidiNote(0, 0, 60, 80, 0, .8), MidiNote(0, 0, 64, 80, .1, .8), MidiNote(0, 0, 66, 80, .4, .8)])
        plan = performance_plan(convert(song, mode='faithful', instrument='piano'), 400)
        self.assertGreater(plan.notes[0].duration, .1)
        held = set()
        for _, down, key in plan.key_events:
            if key == SHIFT:
                self.assertFalse(held)
            elif down:
                self.assertNotIn(key.virtual_key, held)
                held.add(key.virtual_key)
            else:
                self.assertIn(key.virtual_key, held)
                held.remove(key.virtual_key)
        self.assertFalse(held)
