"""Offline workflow contracts. Fixtures are not model-accuracy evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from nte_music_desk.audio_pipeline import AudioPipeline, AudioRequest, python_engine
from nte_music_desk.rights import MUSCRIPTOR_TERMS, GAME_TERMS
from nte_music_desk.midi import MidiNote, MidiSong, write_midi, read_midi


def fixture_request(source, **options):
    return AudioRequest(source, rights_basis='original', rights_reference='self-created test fixture',
                        accepted_models=(MUSCRIPTOR_TERMS, GAME_TERMS), **options)


class FixturePipeline(AudioPipeline):
    def __init__(self):
        super().__init__()
        self.operations=[]

    def worker(self, executable, operation, directory, config, notify=None):
        self.operations.append(operation)
        if operation=='prepare':
            Path(config['output']).write_bytes(b'decoded audio fixture')
            return {'seconds':4,'source_end_seconds':config['start']+4}
        if operation=='separate':
            for name in ('accompaniment.wav','vocals.wav'):
                (directory/name).write_bytes(b'stem fixture')
            return {}
        if operation=='diagnose':
            return {'muscriptor':'0.3.0','audio-separator':'0.47.1','soundfile':'0.14.0',
                    'imageio-ffmpeg':'0.6.0','decoder':True,'model_login_configured':True,'muscriptor_weights_cached':False,'cuda_available':False,'torch':'2.8.0','onnxruntime':'1.22.1','onnxruntime_ready':True}
        raise AssertionError(operation)


class AudioPipelineChecks(unittest.TestCase):
    def fixture(self, root):
        source=root/'原唱 有空格.wav'
        source.write_bytes(b'original audio fixture')
        midi=root/'fixture.mid'
        write_midi(MidiSong('known',1,480,[MidiNote(0,0,60,90,1.25,2),MidiNote(1,1,48,75,0,1)],['strings','bass'],[(0,500000)],4,[]),midi)
        engine=root/'engine.py'
        engine.write_text('import sys,pathlib\npathlib.Path(sys.argv[1]).write_bytes(pathlib.Path('+repr(str(midi))+').read_bytes())\n',encoding='utf-8')
        return source,engine

    def test_instrumental_publishes_valid_multitrack_midi_with_timeline(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d); source,engine=self.fixture(root)
            job=FixturePipeline()
            with patch('nte_music_desk.audio_pipeline.transcription_command',side_effect=lambda e,s,o,*a:[sys.executable,str(engine),str(o)]):
                result=job.accompaniment(sys.executable,fixture_request(source,start=52,end=56),root)
            self.assertEqual(job.operations,['diagnose','prepare'])
            self.assertTrue(result.accompaniment.is_file())
            self.assertTrue(result.accompaniment_audio.is_file())
            self.assertEqual([n.start for n in read_midi(result.accompaniment).notes],[0,1.25])
            metadata=json.loads((result.directory/'provenance.json').read_text(encoding='utf-8'))
            self.assertEqual((metadata['source_start_seconds'],metadata['source_end_seconds']),(52,56))
            self.assertFalse(list(result.directory.glob('*.partial.mid')))
            self.assertEqual(source.read_bytes(),b'original audio fixture')

    def test_instrumental_skips_vocal_separation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,engine=self.fixture(root)
            job=FixturePipeline()
            with patch('nte_music_desk.audio_pipeline.transcription_command',side_effect=lambda e,s,o,*a:[sys.executable,str(engine),str(o)]):
                result=job.accompaniment(sys.executable,fixture_request(source,source_kind='instrumental'),root)
            self.assertEqual(job.operations,['diagnose','prepare'])
            self.assertEqual(result.source_audio,result.accompaniment_audio)

    def test_invalid_result_never_publishes_success(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,engine=self.fixture(root)
            engine.write_text('import sys,pathlib\npathlib.Path(sys.argv[1]).write_bytes(b"not midi")\n')
            with patch('nte_music_desk.audio_pipeline.transcription_command',side_effect=lambda e,s,o,*a:[sys.executable,str(engine),str(o)]):
                with self.assertRaises(ValueError):
                    FixturePipeline().accompaniment(sys.executable,fixture_request(source),root)
            self.assertFalse(list((root/'transcriptions').rglob('*.mid')))

    def test_options_and_executable_are_checked_before_work(self):
        with tempfile.TemporaryDirectory() as d:
            source=Path(d)/'a.mp3';source.write_bytes(b'a')
            for settings in ({'start':float('nan')},{'start':True},{'end':0},{'end':1801},{'source_kind':'unknown'},
                             {'device':'shell'},{'model':'unknown'},{'melody_beta':1},
                             {'source_kind':'instrumental','melody_beta':True}):
                with self.assertRaises(ValueError):fixture_request(source,**settings).validate()
            with self.assertRaises(ValueError):python_engine(Path(d)/'muscriptor.exe')

    def test_missing_model_login_is_actionable_before_separation(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source,_=self.fixture(root)
            job=FixturePipeline()
            original=job.worker
            def worker(e,op,p,c,n=None):
                result=original(e,op,p,c,n)
                if op=='diagnose':result['model_login_configured']=False
                return result
            job.worker=worker
            with self.assertRaisesRegex(ValueError,'模型授权'):
                job.accompaniment(sys.executable,fixture_request(source),root)
            self.assertEqual(job.operations,['diagnose'])


if __name__=='__main__':unittest.main()
