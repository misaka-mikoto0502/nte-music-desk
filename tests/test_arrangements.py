from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nte_music_desk.midi import MidiSong, MidiNote, convert
from nte_music_desk.segments import parse_time
from nte_music_desk.analysis import recommend_transpositions


class ArrangementChecks(unittest.TestCase):
    def test_transpose_candidates_prefer_full_range_and_do_not_mutate_source(self):
        song = MidiSong('low lead', 0, 480, [MidiNote(0, 0, pitch, 80, i, i + .5) for i, pitch in enumerate((40, 44, 47))], ['lead'], [], 3, [])
        from nte_music_desk.cli import key_schedule
        result = recommend_transpositions(song, tracks=[0], planner=key_schedule)
        self.assertEqual(len(result), 3)
        self.assertEqual(result[0]['transpose'], 12)
        self.assertEqual(result[0]['folded'], 0)
        self.assertEqual([n.pitch for n in song.notes], [40, 44, 47])
        self.assertEqual(result, recommend_transpositions(song, tracks=[0], planner=key_schedule))
        with self.assertRaises(ValueError):
            recommend_transpositions(song, tracks=[0], start=9)

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
