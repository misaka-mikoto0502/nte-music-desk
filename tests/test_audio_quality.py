import unittest
from nte_music_desk.audio_quality import compare_notes
from nte_music_desk.midi import MidiNote,MidiSong


def song(notes):return MidiSong('test',1,480,notes,['test'],[],4,[])


class AudioQualityChecks(unittest.TestCase):
    def test_duplicate_wrong_pitch_and_missed_notes_are_not_counted_as_correct(self):
        truth=song([MidiNote(0,0,60,80,0,1),MidiNote(0,0,62,80,2,3),MidiNote(0,9,36,80,1,1.1)])
        predicted=song([MidiNote(0,0,60,80,.05,.9),MidiNote(0,0,60,80,.06,.9),MidiNote(0,0,63,80,2,3)])
        result=compare_notes(truth,predicted)
        self.assertEqual((result['matched_notes'],result['missed_notes'],result['extra_notes']),(1,1,2))
        self.assertAlmostEqual(result['onset_pitch_f1'],.4)
        self.assertAlmostEqual(result['median_absolute_onset_error_seconds'],.05)

    def test_repeated_pitch_matches_are_one_to_one_and_bounded_by_onset(self):
        truth=song([MidiNote(0,0,60,80,1,1.5),MidiNote(0,0,60,80,1.15,1.5)])
        predicted=song([MidiNote(0,0,60,80,.9,1.2),MidiNote(0,0,60,80,1.07,1.4)])
        self.assertEqual(compare_notes(truth,predicted)['matched_notes'],2)
        self.assertEqual(compare_notes(truth,song([]))['onset_pitch_f1'],0)
        for tolerance in (float('nan'),0,-1,True):
            with self.assertRaises(ValueError):compare_notes(truth,predicted,tolerance)
