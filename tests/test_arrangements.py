from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nte_music_desk.midi import MidiSong, MidiNote, convert
from nte_music_desk.segments import parse_time


class ArrangementChecks(unittest.TestCase):
    def test_segment_clips_sustains_and_preserves_rests_at_both_edges(self):
        song = MidiSong('clip', 0, 480, [MidiNote(0, 0, 60, 80, 0, 4), MidiNote(0, 0, 64, 80, 6, 8)], ['lead'], [], 10, [])
        score = convert(song, start=2, end=9, speed=.5)
        self.assertEqual([(e['at'], e['duration']) for e in score['events']], [(0, 4), (8, 4)])
        self.assertEqual(score['summary']['seconds'], 14)
        score = convert(song, start=5, end=9)
        self.assertEqual(score['events'][0]['at'], 1)
        self.assertEqual(score['summary']['source_origin_seconds'], 5)
        self.assertEqual(score['summary']['seconds'], 4)
        self.assertEqual(song.notes[0].start, 0)
        with self.assertRaises(ValueError):
            convert(song, start=5, end=6)
        for end in (5, 11, float('nan')):
            with self.assertRaises(ValueError):
                convert(song, start=5, end=end)

    def test_segment_time_entry(self):
        self.assertEqual(parse_time('1:20.5'), 80.5)
        self.assertEqual(parse_time('35'), 35)
        for value in ('-1', 'nan', '1:60', 'foo', '1:2:3'):
            with self.assertRaises(ValueError):
                parse_time(value)
