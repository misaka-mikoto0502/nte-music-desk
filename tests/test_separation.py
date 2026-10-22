"""Real workflow boundaries; fake stems do not measure model quality."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from nte_music_desk.audio_pipeline import AudioPipeline
from nte_music_desk.midi import read_midi, write_midi, MidiSong, MidiNote
from test_audio_pipeline import FixturePipeline, fixture_request
import test_audio_pipeline as fixtures


class SeparationChecks(unittest.TestCase):
    def test_separation_does_not_require_transcription_login_and_keeps_both_stems(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,_=fixtures.AudioPipelineChecks().fixture(root)
            job=FixturePipeline()
            original=job.worker
            def worker(e,op,p,c,n=None):
                result=original(e,op,p,c,n)
                if op=='diagnose':
                    result.update(muscriptor=None,model_login_configured=False,onnxruntime_ready=False)
                return result
            job.worker=worker
            result=job.separate_only(sys.executable,fixture_request(source,source_kind='original'),root)
            self.assertEqual(job.operations,['diagnose','prepare','separate'])
            self.assertTrue(result.vocals_audio.is_file())
            self.assertTrue(result.accompaniment_audio.is_file())
            self.assertIsNone(result.accompaniment)
            record=json.loads((result.directory/'provenance.json').read_text(encoding='utf-8'))
            self.assertEqual(record['model']['license'],'MIT')
            self.assertEqual(record['rights']['model_terms'],{})

    def test_original_routes_separated_accompaniment_to_transcriber(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,engine=fixtures.AudioPipelineChecks().fixture(root)
            inputs=[]
            def command(e,s,o,*a):
                inputs.append(Path(s).name)
                return [sys.executable,str(engine),str(o)]
            with patch('nte_music_desk.audio_pipeline.transcription_command',side_effect=command):
                result=FixturePipeline().accompaniment(sys.executable,fixture_request(source,source_kind='original'),root)
            self.assertEqual(inputs,['accompaniment.wav'])
            self.assertIsNotNone(result.vocals_audio)

    def test_full_workflow_keeps_aligned_results_and_beta_failure_retains_backing(self):
        for fail in (False,True):
            with self.subTest(beta_failure=fail), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);source,engine=fixtures.AudioPipelineChecks().fixture(root)
                def extract(job,e,a,target,models,notify=None,language='auto',*,accepted_terms=False):
                    self.assertEqual(Path(a).name,'vocals.wav')
                    if fail:raise ValueError('no usable singing')
                    path=target/'melody.mid'
                    write_midi(MidiSong('v',1,480,[MidiNote(0,0,64,88,1.25,2)],['v'],[],4,[]),path)
                    return path,{'seconds':4}
                with patch('nte_music_desk.audio_pipeline.transcription_command',side_effect=lambda e,s,o,*a:[sys.executable,str(engine),str(o)]), patch('nte_music_desk.melody.extract_beta',side_effect=extract):
                    result=FixturePipeline().accompaniment(sys.executable,fixture_request(source,source_kind='original',melody_beta=True),root)
                self.assertTrue(result.accompaniment.is_file())
                if fail:
                    self.assertIsNone(result.combined)
                    self.assertIn('伴奏仍可使用',result.warnings[0])
                else:
                    self.assertTrue(result.melody.is_file())
                    self.assertIn(1.25,[n.start for n in read_midi(result.combined).notes])

    def test_preview_caps_duration_and_never_uses_a_model_or_terms(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);source,_=fixtures.AudioPipelineChecks().fixture(root)
            job=FixturePipeline()
            with patch.object(job,'worker',wraps=job.worker) as worker:
                result=job.preview(sys.executable,fixture_request(source,start=12,end=120),root)
            config=worker.call_args.args[3]
            self.assertEqual((config['start'],config['end']),(12,42))
            self.assertTrue(config['allow_short'])
            self.assertTrue(result.is_file())
            self.assertEqual(job.operations,['prepare'])
