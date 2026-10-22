import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from nte_music_desk.melody import events_to_song, combine_with_accompaniment, unpack_model
from nte_music_desk.midi import MidiSong, MidiNote, read_midi, write_midi
from nte_music_desk.audio_pipeline import AudioRequest
from test_audio_pipeline import FixturePipeline


class MelodyChecks(unittest.TestCase):
    def test_beta_timeline_preserves_rests_and_combines_in_seconds(self):
        melody=events_to_song({'seconds':6,'notes':[{'pitch':64,'start':2.25,'end':2.8},{'pitch':65,'start':4,'end':4.5}]},'beta')
        backing=MidiSong('a',1,480,[MidiNote(0,0,48,80,0,.8,32),MidiNote(1,9,36,90,0,.1,0)],['bass','drums'],[],6,[])
        combined=combine_with_accompaniment(backing,melody,'all')
        self.assertEqual([(n.start,n.pitch) for n in combined.notes],[(0,48),(2.25,64),(4,65)])
        self.assertTrue(all(n.program==0 for n in combined.notes))
        self.assertEqual(backing.notes[0].program,32)
        self.assertIn('Beta',combined.track_names[-1])
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'all.mid';write_midi(combined,p)
            self.assertEqual([(n.start,n.pitch) for n in read_midi(p).notes],[(0,48),(2.25,64),(4,65)])

    def test_invalid_pitch_timing_overlap_and_model_hash_are_rejected(self):
        for notes in ([],[{'pitch':float('nan'),'start':0,'end':1}],
                      [{'pitch':128,'start':0,'end':1}],
                      [{'pitch':60,'start':float('nan'),'end':1}],
                      [{'pitch':60,'start':0,'end':3}],
                      [{'pitch':60,'start':2.01,'end':2.02}],
                      [{'pitch':60,'start':0,'end':1},{'pitch':61,'start':.5,'end':1.5}]):
            with self.assertRaises(ValueError):events_to_song({'seconds':2,'notes':notes},'bad')
        with tempfile.TemporaryDirectory() as d:
            archive=Path(d)/'model.zip';archive.write_bytes(b'bad')
            with self.assertRaisesRegex(ValueError,'校验失败'):unpack_model(archive,Path(d)/'model')
            self.assertFalse((Path(d)/'model').exists())

    def test_standalone_beta_publishes_timed_result_and_provenance(self):
        from test_audio_pipeline import fixture_request
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'own-recording.wav';source.write_bytes(b'fixture')
            song=events_to_song({'seconds':4,'notes':[{'pitch':60,'start':1.25,'end':2}]},'beta')
            def extract(job,executable,audio,target,models,notify=None,language='auto',*,accepted_terms=False):
                self.assertTrue(accepted_terms)
                path=target/'melody-beta.mid';write_midi(song,path)
                return path,{'seconds':4,'notes':[{}],'engine':'test fixture'}
            with patch('nte_music_desk.melody.extract_beta',side_effect=extract):
                result=FixturePipeline().melody_only(sys.executable,fixture_request(source,source_kind='original'),root)
            self.assertIsNone(result.accompaniment)
            self.assertEqual(read_midi(result.melody).notes[0].start,1.25)
            record=json.loads((result.directory/'provenance.json').read_text(encoding='utf-8'))
            self.assertEqual(record['rights']['status'],'user_statement_not_verified')
            self.assertEqual(record['rights']['publication_rights'].split(';')[0],'not_verified')


if __name__=='__main__':unittest.main()
