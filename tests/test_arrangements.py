from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nte_music_desk.midi import MidiSong, MidiNote, convert
from nte_music_desk.segments import parse_time
from nte_music_desk.analysis import recommend_transpositions, adaptation_report


class ArrangementChecks(unittest.TestCase):
    def test_recommendation_finds_a_non_octave_shift_beyond_twelve_semitones(self):
        song = MidiSong('wide low range', 0, 480,
            [MidiNote(0, 0, 35, 80, 0, .5), MidiNote(0, 0, 70, 80, 1, 1.5)], ['lead'], [], 2, [])
        result = recommend_transpositions(song, mode='faithful', range_policy='strict')
        self.assertEqual([candidate['transpose'] for candidate in result], [17])
        self.assertEqual(result[0]['folded'], 0)

    def test_equally_good_recommendations_keep_the_current_transposition(self):
        song = MidiSong('middle', 0, 480, [MidiNote(0, 0, 60, 80, 0, 1)], ['lead'], [], 2, [])
        self.assertEqual(recommend_transpositions(song, transpose=5)[0]['transpose'], 5)
        with self.assertRaisesRegex(ValueError, '已取消'):
            recommend_transpositions(song, cancel=lambda: True)

    def test_piano_recommendation_prefers_less_actual_timing_adjustment(self):
        song = MidiSong('close shift change', 0, 480,
            [MidiNote(0, 0, 60, 80, 0, 1), MidiNote(0, 0, 61, 80, .02, 1.02)], ['lead'], [], 2, [])
        candidates = recommend_transpositions(song, mode='faithful', instrument='piano', limit=73)
        original = next(candidate for candidate in candidates if candidate['transpose'] == 0)
        self.assertGreater(original['max_timing_adjustment_ms'], 0)
        self.assertEqual(candidates[0]['transpose'], -1)
        self.assertEqual(candidates[0]['max_timing_adjustment_ms'], 0)
        self.assertLess(candidates[0]['cost'], original['cost'])

    def test_report_distinguishes_absolute_source_positions_from_duration(self):
        from nte_music_desk.performance import performance_plan
        from nte_music_desk.ui import position_label
        song = MidiSong('late notes', 0, 480, [MidiNote(0, 0, 30, 80, 180, 181)], ['lead'], [], 200, [])
        score = convert(song)
        report = adaptation_report(score, performance_plan(score))
        self.assertEqual(report['timeline']['source_seconds'], 200)
        self.assertEqual(report['timeline']['source_origin_seconds'], 180)
        self.assertEqual(report['timeline']['performance_seconds'], 1)
        self.assertEqual(report['changes'][0]['source_at'], 180)
        self.assertEqual(position_label(180), '03:00.000')
        self.assertEqual(position_label(59.9998), '01:00.000')

    def test_report_accounts_for_removed_and_merged_notes_with_source_positions(self):
        song = MidiSong('dense', 0, 480, [MidiNote(0, 0, p, 80, 2, 3) for p in (24, 36, 48, 60, 72, 84, 96)], ['lead'], [], 4, [])
        score = convert(song, tracks=[0], mode='chords')
        report = adaptation_report(score)
        summary = report['summary']
        self.assertEqual(summary['source_notes'], summary['notes'] + summary['chord_notes_removed'] + summary['dropped'] + summary['merged'])
        self.assertEqual(summary['folded'], 3)
        self.assertEqual({c['action'] for c in report['changes']}, {'simplified', 'folded', 'merged'})
        self.assertTrue(all(c['source_at'] == 2 for c in report['changes']))
        song.notes = [MidiNote(0, 0, 60, 80, 2, 3)] * 3000
        report = adaptation_report(convert(song))
        self.assertTrue(report['truncated'])
        self.assertEqual(len(report['changes']), 2000)
        self.assertEqual(report['total_changes'], 2999)

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
