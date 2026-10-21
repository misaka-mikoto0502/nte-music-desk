"""Network/process boundaries; user declarations are not proof of copyright."""
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nte_music_desk.audio_pipeline import AudioPipeline, AudioRequest
from nte_music_desk.local_library import local_title
from nte_music_desk.melody import prepare_model
from nte_music_desk.rights import validate_use, MUSCRIPTOR_TERMS, GAME_TERMS
from nte_music_desk.transcription import ProcessJob
from nte_music_desk.paths import asset_dir


class RightsChecks(unittest.TestCase):
    def test_missing_input_basis_or_terms_never_starts_a_worker(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'local.wav';source.write_bytes(b'fixture')
            for fields in ({}, {'rights_basis':'original','rights_reference':'own fixture'},
                           {'rights_basis':'downloaded','rights_reference':'free website','accepted_models':(MUSCRIPTOR_TERMS,)},
                           {'rights_basis':'permission','rights_reference':'','accepted_models':(MUSCRIPTOR_TERMS,)}):
                job=AudioPipeline()
                with patch.object(job,'worker') as worker, patch.object(job,'run') as run:
                    with self.assertRaises(ValueError):job.accompaniment(sys.executable,AudioRequest(source,**fields),root)
                    worker.assert_not_called();run.assert_not_called()
            self.assertFalse((root/'transcriptions').exists())
            with patch.object(ProcessJob,'run') as run:
                with self.assertRaises(ValueError):ProcessJob().transcribe(sys.executable,source,root)
                run.assert_not_called()

    def test_uncleared_separator_remains_disabled_even_after_user_statement(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'own.wav';source.write_bytes(b'fixture')
            request=AudioRequest(source,source_kind='original',rights_basis='original',rights_reference='self recorded',accepted_models=(MUSCRIPTOR_TERMS,))
            job=AudioPipeline()
            with patch.object(job,'worker') as worker:
                with self.assertRaisesRegex(ValueError,'权重许可尚未核实'):job.accompaniment(sys.executable,request,root)
                worker.assert_not_called()
            self.assertFalse((root/'transcriptions').exists())

    def test_game_license_checked_before_download_or_cached_model_use(self):
        with tempfile.TemporaryDirectory() as d:
            with patch('nte_music_desk.melody.model_ready',return_value=True) as cached, patch('urllib.request.urlopen') as network:
                with self.assertRaisesRegex(ValueError,'CC BY-NC-SA'):prepare_model(ProcessJob(),Path(d))
                cached.assert_not_called();network.assert_not_called()
            with patch('nte_music_desk.melody.model_ready',return_value=True):
                self.assertEqual(prepare_model(ProcessJob(),Path(d),accepted_terms=True).name,'game-1.0.3-small')

    def test_direct_separator_worker_cannot_download_or_call_uncleared_weights(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);request=root/'request.json';response=root/'result.json'
            request.write_text(json.dumps({'operation':'separate','response':str(response)}),encoding='utf-8')
            result=subprocess.run([sys.executable,'-X','utf8',str(asset_dir()/'audio_worker.py'),str(request)],capture_output=True,encoding='utf-8',timeout=20)
            self.assertNotEqual(result.returncode,0)
            self.assertIn('ViperX',result.stderr)
            self.assertFalse(response.exists())

    def test_records_model_terms_without_claiming_publication_rights(self):
        record=validate_use('open-license','https://example.test/license',(GAME_TERMS,),[GAME_TERMS])
        self.assertEqual(record['status'],'user_statement_not_verified')
        self.assertIn('not_verified',record['publication_rights'])
        self.assertNotIn(MUSCRIPTOR_TERMS,record['model_terms'])

    def test_legacy_local_title_is_bounded_and_never_deletes_files(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);path=root/'downloaded_midis'/'old.mid';path.parent.mkdir();path.write_bytes(b'old')
            sidecar=path.with_suffix('.source.json')
            sidecar.write_text(json.dumps({'filename':path.name,'title':'旧曲目'}),encoding='utf-8')
            self.assertEqual(local_title(path,root),'旧曲目')
            for value in ([],None,{'filename':'other.mid','title':'wrong'}):
                sidecar.write_text(json.dumps(value),encoding='utf-8')
                self.assertIsNone(local_title(path,root))
            self.assertTrue(path.is_file())
            self.assertIsNone(local_title(root/'other.mid',root))
