import json,tempfile,threading,unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from nte_music_desk.audio_ui import AudioDialog
from nte_music_desk.light_audio import LightAudioSession

class AudioTaskGateChecks(unittest.TestCase):
    def test_already_open_advanced_window_cannot_start_during_light_task(self):
        dialog=AudioDialog.__new__(AudioDialog);dialog.job=None;dialog.state=MagicMock()
        dialog.app=SimpleNamespace(active=None,task_lock=threading.RLock(),light_audio=SimpleNamespace(busy=True),stop_preview=MagicMock())
        operation=MagicMock();dialog.begin(operation,'start')
        self.assertIsNone(dialog.job);operation.assert_not_called();dialog.app.stop_preview.assert_not_called()
        self.assertIn('转谱',dialog.state.set.call_args.args[0])

    def test_http_claim_and_application_gate_are_atomic(self):
        gate=threading.RLock();checks=[]
        def can_start():checks.append(gate._is_owned());return False
        with tempfile.TemporaryDirectory() as d:
            session=LightAudioSession(d,lambda _:None,can_start=can_start,gate=gate)
            self.addCleanup(session.close)
            source={'name':'fixture.wav','bytes':100,'duration':10,'start':0,'end':10,'sha256':'a'*64,'profile':'polyphonic'}
            with self.assertRaises(HTTPError):urlopen(Request(session.url+'begin',json.dumps(source).encode(),
                {'Content-Type':'application/json','Origin':session.origin}))
            self.assertEqual(checks,[True]);self.assertFalse(session.busy)
