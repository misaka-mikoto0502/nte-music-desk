import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from nte_music_desk.light_audio import LightAudioSession, notes_to_song, validate_source
from nte_music_desk.midi import read_midi


def source():
    return {'name':'自己的录音.wav','bytes':12345,'duration':10,'start':2,'end':8,
            'sha256':'a'*64,'profile':'polyphonic'}


def note():
    return {'pitchMidi':60,'startTimeSeconds':1.25,'durationSeconds':.75,'amplitude':.8}


class LightAudioChecks(unittest.TestCase):
    def test_local_source_bounds_and_notes_are_validated_without_declaration(self):
        self.assertEqual(validate_source(source())['rights']['status'],'local_file_provided')
        legacy = validate_source({**source(), 'basis':'permission','reference':'an old client statement'})
        self.assertEqual(legacy['rights']['basis'],'local-file')
        self.assertNotIn('reference',legacy['rights'])
        for field,value in [('bytes',True),('bytes',100_000_000),('duration',float('nan')),('end',200),
                            ('start',-1),('sha256','bad'),('profile','shell')]:
            with self.assertRaises(ValueError):validate_source({**source(),field:value})
        song=notes_to_song([note()],6,'fixture')
        self.assertEqual((song.notes[0].start,song.notes[0].end),(1.25,2))
        for field,value in [('pitchMidi',True),('pitchMidi',109),('startTimeSeconds',float('nan')),
                            ('durationSeconds',0),('amplitude',2)]:
            with self.assertRaises(ValueError):notes_to_song([{**note(),field:value}],6,'fixture')

    def test_local_http_result_cancellation_and_origin_boundaries(self):
        with tempfile.TemporaryDirectory() as d:
            messages=[]
            with_session=LightAudioSession(d,messages.append)
            session=with_session
            self.addCleanup(session.close)
            def post(route,data,origin=None):
                request=Request(session.url+route,json.dumps(data).encode(),
                                {'Content-Type':'application/json','Origin':origin or session.origin})
                with urlopen(request,timeout=3) as response:return json.load(response)
            with urlopen(session.url,timeout=3) as response:
                self.assertIn('轻量转谱'.encode(),response.read())
                self.assertIn("connect-src 'self'",response.headers['Content-Security-Policy'])
            self.assertLess(session.asset_bytes,4_500_000)
            with self.assertRaises(HTTPError) as error:post('begin',source(),'https://example.com')
            self.assertEqual(error.exception.code,403)
            with self.assertRaises(HTTPError):urlopen(session.url+'../icon.ico',timeout=3)
            first=post('begin',source())['job_id'];self.assertTrue(session.busy)
            with self.assertRaises(HTTPError):post('begin',source())
            post('cancel',{'job_id':first});self.assertFalse(session.busy)
            with self.assertRaises(HTTPError):post('complete',{'job_id':first,'notes':[note()]})
            self.assertFalse(list(Path(d).rglob('*.mid')))
            job=post('begin',source())['job_id']
            result=post('complete',{'job_id':job,'notes':[note()],'raw_notes':[note()]})
            self.assertEqual(result['notes'],1);self.assertFalse(session.busy)
            midi=read_midi(session.result)
            self.assertEqual((midi.notes[0].start,midi.notes[0].end),(1.25,2))
            provenance=json.loads((session.result.parent/'provenance.json').read_text(encoding='utf-8'))
            self.assertEqual(provenance['source']['start'],2)
            self.assertEqual(provenance['midi_sha256'],hashlib.sha256(session.result.read_bytes()).hexdigest())
            self.assertTrue((session.result.parent/'model_raw.mid').is_file())
            self.assertEqual(messages[-1]['kind'],'light_done')
            self.assertFalse(list(Path(d).rglob('*.wav')))
            session.close()

    def test_game_lock_and_modified_resources_reject_before_start(self):
        with tempfile.TemporaryDirectory() as d:
            session=LightAudioSession(d,lambda m:None,can_start=lambda:False)
            self.addCleanup(session.close)
            request=Request(session.url+'begin',json.dumps(source()).encode(),
                            {'Content-Type':'application/json','Origin':session.origin})
            with self.assertRaises(HTTPError):urlopen(request,timeout=3)
            self.assertIsNone(session.run_id)
            folder=Path(d)/'broken';folder.mkdir()
            (folder/'index.html').write_text('changed')
            (folder/'manifest.json').write_text(json.dumps({'files':{'index.html':'0'*64}}))
            with self.assertRaisesRegex(ValueError,'校验'):LightAudioSession(d,lambda m:None,assets=folder)
