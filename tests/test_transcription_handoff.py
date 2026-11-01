import json
from pathlib import Path
import sys,tempfile,time,unittest
from types import SimpleNamespace
from unittest.mock import MagicMock
from urllib.request import Request,urlopen

from nte_music_desk.ui import App
from nte_music_desk.local_library import generated_scores
from nte_music_desk.light_audio import LightAudioSession
from nte_music_desk.paths import asset_dir
from nte_music_desk import cli


class TranscriptionHandoffChecks(unittest.TestCase):
    def test_busy_workbench_queues_then_loads_without_manual_import(self):
        app=App.__new__(App);app.active=object();app.pending_import=None;app.light_audio=MagicMock()
        app.refresh_library=MagicMock();app.open_path=MagicMock(return_value=True)
        app.refresh_controls=MagicMock();app.set_status=MagicMock();app.score={'mode':'faithful'}
        path=Path('new.mid').resolve()
        app.handle_message({'kind':'light_done','path':path})
        app.open_path.assert_not_called();self.assertEqual(app.pending_import,path)
        self.assertEqual(app.light_audio.acknowledge_import.call_args.args[1],'queued')
        app.handle_message({'kind':'game_done','code':2,'result':{'status':'stopped'}})
        app.open_path.assert_called_once_with(path);self.assertIsNone(app.pending_import)
        self.assertEqual(app.light_audio.acknowledge_import.call_args.args[1],'loaded')

    @unittest.skipUnless(sys.platform=='win32','Windows desktop integration')
    def test_http_completion_loads_hidden_workbench_and_survives_restart(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d);engine=SimpleNamespace(ROOT=directory,ASSETS=asset_dir(),key_schedule=cli.key_schedule)
            root=tk.Tk();root.withdraw();app=App(root,engine)
            try:
                session=LightAudioSession(directory,app.messages.put,gate=app.task_lock)
                app.light_audio=session
                def post(route,data):
                    with urlopen(Request(session.url+route,json.dumps(data).encode(),
                        {'Content-Type':'application/json','Origin':session.origin}),timeout=3) as response:return json.load(response)
                job=post('begin',{'name':'自己的短句.wav','bytes':100,'duration':5,'start':0,'end':5,'sha256':'a'*64,'profile':'polyphonic'})['job_id']
                post('complete',{'job_id':job,'notes':[{'pitchMidi':60,'startTimeSeconds':1,'durationSeconds':1,'amplitude':.8}]})
                deadline=time.monotonic()+2
                while app.current_path!=session.result and time.monotonic()<deadline:root.update();time.sleep(.01)
                self.assertEqual(app.current_path,session.result)
                self.assertEqual(session.latest_result['workbench']['state'],'loaded')
                self.assertIn(session.result,[p for _,p in app.library_buttons])
                self.assertEqual(generated_scores(directory),[session.result])
                self.assertFalse(app.active)
                with urlopen(session.url+'state') as response:self.assertEqual(json.load(response)['latest_result']['workbench']['state'],'loaded')
                final=session.result
            finally:app.close()
            root=tk.Tk();root.withdraw();app=App(root,engine)
            try:
                self.assertIn(final,[p for _,p in app.library_buttons])
                self.assertEqual(app.current_path,final)
            finally:app.close()
