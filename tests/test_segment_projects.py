"""Segment boundaries, persistence and real community HTTP round trips."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from nte_music_desk.arrangement import apply_region, compile_arrangement, validate_segments
from nte_music_desk.community import CommunityDemo, project_document, project_song, request_json, validate_project
from nte_music_desk.midi import MidiNote, MidiSong, convert
from nte_music_desk.performance import performance_plan
from nte_music_desk.presets import DEFAULTS, PresetStore


class SegmentProjectChecks(unittest.TestCase):
    def setUp(self):
        self.song = MidiSong('自己的示例', 1, 480,
                            [MidiNote(0, 0, 60, 80, 0, 3), MidiNote(0, 0, 64, 90, 1, 2),
                             MidiNote(0, 0, 67, 80, 3, 3.8), MidiNote(0, 0, 72, 90, 3, 3.8),
                             MidiNote(1, 1, 48, 70, 0, 1), MidiNote(1, 1, 50, 70, 3, 4)],
                            ['旋律', '低音'], [(0, 500000)], 5, [])
        self.settings = {**deepcopy(DEFAULTS), 'mode': 'faithful', 'tracks': [0, 1]}
        self.edit = dict(start=2, end=4, name='副歌', mode='melody', transpose=0, tracks=[0])

    def test_crossing_note_is_owned_once_and_unaffected_notes_keep_octaves(self):
        before = deepcopy(self.song.notes)
        self.settings['segments'] = [self.edit]
        score = compile_arrangement(self.song, self.settings, 'guitar')
        self.assertEqual(sum(e['source_at'] == 0 and e['source_midi'] == 60 for e in score['events']), 1)
        crossing = next(e for e in score['events'] if e['source_midi'] == 60)
        self.assertEqual(crossing['duration'], 3)
        self.assertEqual(sum(e['source_at'] == 3 for e in score['events']), 1)
        baseline = convert(self.song, tracks=[0, 1], mode='faithful', start=0, end=5)
        self.assertEqual([e for e in score['events'] if e['source_at'] < 2],
                         [e for e in baseline['events'] if e['source_at'] < 2])
        self.assertEqual(before, self.song.notes)
        for instrument in ('guitar', 'piano'):
            plan = performance_plan(compile_arrangement(self.song, self.settings, instrument))
            held = set()
            for _, down, key in plan.key_events:
                if down:
                    self.assertNotIn(key, held)
                    held.add(key)
                else:
                    self.assertIn(key, held)
                    held.remove(key)
            self.assertFalse(held)

    def test_overwrite_retains_outer_ranges_and_invalid_ranges_are_rejected(self):
        initial = [{**self.edit, 'start': 0, 'end': 5}]
        replacement = {**self.edit, 'start': 1, 'end': 2, 'transpose': 12}
        result = apply_region(initial, replacement)
        self.assertEqual([(s['start'], s['end'], s['transpose']) for s in result], [(0, 1, 0), (1, 2, 12), (2, 5, 0)])
        for value in ([self.edit, self.edit], [{**self.edit, 'end': float('nan')}], [{**self.edit, 'tracks': []}]):
            with self.assertRaises(ValueError):
                validate_segments(value)
        with self.assertRaises(ValueError):
            validate_segments([self.edit], duration=3)

    def test_edit_at_song_start_does_not_replace_global_settings_in_report(self):
        self.settings['segments'] = [{**self.edit, 'start': 0, 'transpose': 12}]
        score = compile_arrangement(self.song, self.settings, 'guitar')
        self.assertEqual(score['settings']['transpose'], 0)
        self.assertEqual(score['settings']['tracks'], [0, 1])
        self.assertEqual(score['settings']['segments'][0]['transpose'], 12)

    def test_saved_segments_restore_and_legacy_settings_remain_usable(self):
        with tempfile.TemporaryDirectory() as directory:
            store = PresetStore(directory)
            self.settings['segments'] = [self.edit]
            store.save('a' * 64, 'piano', self.settings)
            restored = store.load('a' * 64, 'piano', [0, 1])
            self.assertEqual(restored['segments'], [self.edit])
            legacy = deepcopy(self.settings)
            legacy.pop('segments')
            store.save('b' * 64, 'guitar', legacy)
            self.assertEqual(store.load('b' * 64, 'guitar', [0, 1])['segments'], [])

    def test_http_publication_survives_restart_and_import_reproduces_plan(self):
        self.settings['segments'] = [self.edit]
        document = project_document(self.song, self.settings, 'piano', title='小样', author='测试作者')
        with tempfile.TemporaryDirectory() as directory:
            service = CommunityDemo(directory)
            try:
                published = request_json(service.endpoint, project=document)
                listing = request_json(service.endpoint)
                self.assertEqual(len(listing['projects']), 1)
                downloaded = request_json(service.endpoint, '/projects/' + published['id'])['project']
                imported = project_song(downloaded['source'])
                expected = performance_plan(compile_arrangement(self.song, self.settings, 'piano'))
                actual = performance_plan(compile_arrangement(imported, downloaded['settings'], downloaded['instrument']))
                self.assertEqual(actual.key_events, expected.key_events)
                self.assertEqual(request_json(service.endpoint, project=document)['id'], published['id'])
            finally:
                service.close()
            service = CommunityDemo(directory)
            try:
                self.assertEqual(request_json(service.endpoint)['projects'][0]['author'], '测试作者')
            finally:
                service.close()

    def test_untrusted_projects_reject_invalid_tracks_and_nonfinite_notes(self):
        document = project_document(self.song, self.settings, 'guitar', title='小样', author='作者')
        for change in ('pitch', 'time', 'track', 'segments'):
            item = deepcopy(document)
            if change == 'pitch': item['source']['notes'][0]['pitch'] = 999
            if change == 'time': item['source']['notes'][0]['start'] = float('inf')
            if change == 'track': item['settings']['tracks'] = [9]
            if change == 'segments': item['settings']['segments'] = [{**self.edit, 'end': 10}]
            with self.assertRaises(ValueError):
                validate_project(item)
