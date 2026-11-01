import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from nte_music_desk.light_audio import LightAudioSession, notes_to_song, validate_source, align_chords
from nte_music_desk.midi import read_midi


def source():
    return {'name':'自己的录音.wav','bytes':12345,'duration':10,'start':2,'end':8,
            'sha256':'a'*64,'profile':'polyphonic'}


def note():
    return {'pitchMidi':60,'startTimeSeconds':1.25,'durationSeconds':.75,'amplitude':.8}


class LightAudioChecks(unittest.TestCase):
    def test_optional_alignment_is_bounded_preserves_repeats_releases_and_original(self):
        events=[{**note(),'pitchMidi':p,'startTimeSeconds':t,'durationSeconds':.2}
                for p,t in [(60,1),(64,1.012),(67,1.023),(72,1.045),
                            (60,2),(60,2.01),(64,2.02),(67,3),(72,3.04)]]
        song=notes_to_song(events,6,'fixture')
        unchanged,off=align_chords(song,0)
        self.assertIs(unchanged,song);self.assertEqual(off['moved_notes'],0)
        aligned,report=align_chords(song,24)
        self.assertEqual(len(aligned.notes),len(song.notes))
        self.assertEqual([n.start for n in aligned.notes[:4]],[1,1,1,1.045])
        self.assertEqual(aligned.notes[4:],song.notes[4:])
        self.assertEqual([n.end for n in aligned.notes],[n.end for n in song.notes])
        self.assertEqual(song.notes[1].start,1.012)
        self.assertEqual(report['moved_notes'],2);self.assertLessEqual(report['max_shift_ms'],24)
        for value in (True,-1,25,'24'):
            with self.assertRaises(ValueError):validate_source({**source(),'align_ms':value})
        self.assertEqual(validate_source({**source(),'profile':'detail','align_ms':24})['align_ms'],24)

    def test_alignment_http_keeps_selected_midi_and_records_settings(self):
        with tempfile.TemporaryDirectory() as d:
            session=LightAudioSession(d,lambda m:None);self.addCleanup(session.close)
            def post(route,data):
                with urlopen(Request(session.url+route,json.dumps(data).encode(),
                    {'Content-Type':'application/json','Origin':session.origin})) as response:return json.load(response)
            job=post('begin',{**source(),'profile':'detail','align_ms':24})['job_id']
            post('complete',{'job_id':job,'notes':[note(),{**note(),'pitchMidi':64,'startTimeSeconds':1.273}]})
            folder=Path(d)/'light-transcriptions'/job
            selected=read_midi(folder/'model_selected.mid');final=read_midi(next(folder.glob('*Beta.mid')))
            self.assertGreater(selected.notes[1].start,selected.notes[0].start)
            self.assertEqual(final.notes[1].start,final.notes[0].start)
            record=json.loads((folder/'provenance.json').read_text(encoding='utf-8'))
            self.assertEqual(record['processing']['alignment']['moved_notes'],1)
            self.assertEqual(record['processing']['thresholds']['onset'],.55)
            with urlopen(session.url+'state') as response:published=json.load(response)['latest_result']
            self.assertEqual(published['stats']['aligned_notes'],1)
            self.assertEqual(published['stats']['preset'],'detail')
            self.assertEqual(len(published['alternatives']),2)
            for item in published['alternatives']:
                with urlopen(session.url+item['result']) as response:
                    self.assertTrue(response.read().startswith(b'MThd'))
                    self.assertIn("filename*=UTF-8''",response.headers['Content-Disposition'])

    def test_desktop_audio_handoff_is_limited_to_explicit_selection(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d); audio=folder/'自己的 音频.wav';audio.write_bytes(b'local audio')
            session=LightAudioSession(folder,lambda m:None);self.addCleanup(session.close)
            session.select_desktop_audio(audio)
            with urlopen(session.url+'state') as response: state=json.load(response)
            selected=state['desktop_file'];self.assertEqual(selected['name'],audio.name)
            self.assertNotIn('path',selected)
            url=session.url+'input/'+selected['id']
            with urlopen(url) as response:self.assertEqual(response.read(),b'local audio')
            with self.assertRaises(HTTPError):urlopen(session.url+'input/unknown')
            audio.write_bytes(b'changed')
            with self.assertRaises(HTTPError):urlopen(url)
            session.run_id='busy';session.last_seen=time.monotonic()-15
            self.assertTrue(session.busy)  # Background tabs can delay timer heartbeats.
            with self.assertRaises(ValueError):session.select_desktop_audio(audio)
            session.run_id=None;session.select_desktop_audio(audio)
            with self.assertRaises(HTTPError):urlopen(url)

    def test_downloads_keep_their_original_result_and_restore_after_reload(self):
        with tempfile.TemporaryDirectory() as d:
            session=LightAudioSession(d,lambda m:None);self.addCleanup(session.close)
            def post(route,data):
                with urlopen(Request(session.url+route,json.dumps(data).encode(),
                    {'Content-Type':'application/json','Origin':session.origin})) as response:return json.load(response)
            first=post('begin',source())['job_id']
            a=post('complete',{'job_id':first,'notes':[note()]})
            with urlopen(session.url+a['result']) as response:
                original=response.read();self.assertIn('attachment;',response.headers['Content-Disposition'])
                self.assertIn("filename*=UTF-8''",response.headers['Content-Disposition'])
            second=post('begin',source())['job_id']
            b=post('complete',{'job_id':second,'notes':[{**note(),'pitchMidi':64}]})
            self.assertNotEqual(a['result'],b['result'])
            with urlopen(session.url+a['result']) as response:self.assertEqual(response.read(),original)
            with urlopen(session.url+'state') as response:self.assertEqual(json.load(response)['latest_result'],b)
            self.assertEqual(len(list(Path(d).rglob('provenance.json'))),2)

    def test_local_source_bounds_and_notes_are_validated_without_declaration(self):
        self.assertEqual(validate_source(source())['rights']['status'],'local_file_provided')
        legacy = validate_source({**source(), 'basis':'permission','reference':'an old client statement'})
        self.assertEqual(legacy['rights']['basis'],'local-file')
        self.assertNotIn('reference',legacy['rights'])
        for field,value in [('bytes',True),('bytes',100_000_000),('duration',float('nan')),('duration',601),('end',200),
                            ('start',-1),('sha256','bad'),('profile','shell')]:
            with self.assertRaises(ValueError):validate_source({**source(),field:value})
        song=notes_to_song([note()],6,'fixture')
        self.assertEqual((song.notes[0].start,song.notes[0].end),(1.25,2))
        for field,value in [('pitchMidi',True),('pitchMidi',109),('startTimeSeconds',float('nan')),
                            ('durationSeconds',0),('amplitude',2)]:
            with self.assertRaises(ValueError):notes_to_song([{**note(),field:value}],6,'fixture')

    def test_expired_job_cannot_resume_or_publish_a_late_result(self):
        with tempfile.TemporaryDirectory() as d:
            messages=[]
            session=LightAudioSession(d,messages.append);self.addCleanup(session.close)
            def post(route,data):
                with urlopen(Request(session.url+route,json.dumps(data).encode(),
                    {'Content-Type':'application/json','Origin':session.origin}),timeout=3) as response:return json.load(response)
            for route in ('pulse','complete'):
                job=post('begin',source())['job_id']
                session.last_seen=time.monotonic()-121
                self.assertFalse(session.busy)
                with self.assertRaises(HTTPError):post(route,{'job_id':job,'notes':[note()]})
                self.assertIsNone(session.run_id)
                self.assertFalse(list(Path(d).rglob('*.mid')))
                self.assertFalse(any(m['kind']=='light_done' for m in messages))
            job=post('begin',source())['job_id']
            self.assertEqual(post('complete',{'job_id':job,'notes':[note()]})['notes'],1)

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
