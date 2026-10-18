import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nte_music_desk.midi import parse_midi
from nte_music_desk.presets import PresetStore, DEFAULTS


class PartChecks(unittest.TestCase):
    def test_type_zero_and_mid_note_program_change_split_without_losing_notes(self):
        track = (b'\x00\xc0\x28\x00\xc1\x20\x00\x90\x3c\x50\x00\x91\x24\x50'
                 b'\x00\x99\x24\x50\x78\xc0\x49\x00\x90\x48\x50'
                 b'\x78\x80\x3c\x00\x00\x80\x48\x00\x00\x81\x24\x00\x00\x89\x24\x00\x00\xff\x2f\x00')
        song = parse_midi(b'MThd' + struct.pack('>IHHH', 6, 0, 1, 480) + b'MTrk' + struct.pack('>I', len(track)) + track)
        self.assertEqual(len(song.notes), 4)
        self.assertEqual(len(song.track_info(include_drums=True)), 4)
        self.assertEqual(len(song.track_info()), 3)
        self.assertEqual({n.pitch: n.program for n in song.notes if n.channel == 0}, {60: 40, 72: 73})
        self.assertEqual(set(song.part_sources.values()), {0})
        self.assertTrue(any('Flute' in p['instrument'] for p in song.track_info()))

    def test_legacy_physical_track_preset_expands_to_all_new_parts_and_is_backed_up(self):
        with tempfile.TemporaryDirectory() as d:
            store = PresetStore(d)
            path = store.path('a' * 64, 'piano')
            path.parent.mkdir()
            old = {'schema': 'nte-arrangement-v1', 'sha256': 'a' * 64, 'instrument': 'piano',
                   'settings': {**DEFAULTS, 'tracks': [1]}}
            path.write_text(json.dumps(old), encoding='utf-8')
            settings = store.load('a' * 64, 'piano', [0, 1, 2], {0: 1, 1: 1, 2: 2})
            self.assertEqual(settings['tracks'], [0, 1])
            store.save('a' * 64, 'piano', settings)
            self.assertEqual(json.loads(path.with_suffix('.v1.backup.json').read_text())['schema'], 'nte-arrangement-v1')
