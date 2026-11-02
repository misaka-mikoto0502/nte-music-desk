import ctypes as C
from ctypes import wintypes as W
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))


@unittest.skipUnless(sys.platform=='win32','Windows desktop')
class MiniPlayerChecks(unittest.TestCase):
    def create(self,directory):
        import tkinter as tk
        from nte_music_desk.ui import App
        from nte_music_desk import cli
        from nte_music_desk.paths import asset_dir
        root=tk.Tk();root.withdraw()
        return App(root,SimpleNamespace(ROOT=Path(directory),ASSETS=asset_dir(),key_schedule=cli.key_schedule))

    def test_own_window_topmost_noactivate_message_and_saved_position(self):
        with tempfile.TemporaryDirectory() as d:
            app=self.create(d)
            try:
                mini=app.mini
                self.assertTrue(mini.window.attributes('-topmost'))
                self.assertEqual(mini.window.state(),'withdrawn')
                u=mini.native.user32
                style=u.GetWindowLongPtrW(mini.native.hwnd,-20)
                self.assertTrue(style&0x08000000)
                self.assertTrue(style&0x80)
                u.SendMessageW.argtypes=[W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.SendMessageW.restype=C.c_ssize_t
                self.assertEqual(u.SendMessageW(mini.native.hwnd,0x21,0,0),3)
                mini.show();app.root.update_idletasks()
                self.assertTrue(u.IsWindowVisible(mini.native.hwnd))
                app.root.iconify();app.root.update_idletasks()
                self.assertTrue(u.IsWindowVisible(mini.native.hwnd))
                mini.position=(32,48);mini.hide()
                data=json.loads((Path(d)/'midi_ui_settings.json').read_text(encoding='utf-8'))
                self.assertEqual(data['mini_player_position'],[32,48])
                self.assertFalse(data['mini_player_visible'])
            finally:app.close()

    def test_seek_position_is_saved_and_restored_in_source_time(self):
        with tempfile.TemporaryDirectory() as d:
            app=self.create(d)
            try:
                app.seek_fraction(.4)
                before=app.playback_offset()
                self.assertGreater(before,0)
                app.speed.set('.8');app.update_score(quiet=True)
                self.assertAlmostEqual(app.playback_offset(),before/.8,places=4)
                saved=app.playback_offset()
                self.assertTrue(app.progress_bar.bind('<ButtonPress-1>'))
                self.assertTrue(app.mini.progress.bind('<ButtonPress-1>'))
            finally:app.close()
            app=self.create(d)
            try:self.assertAlmostEqual(app.playback_offset(),saved,places=4)
            finally:app.close()

    def test_play_launch_uses_the_selected_position_without_native_game_input(self):
        with tempfile.TemporaryDirectory() as d:
            app=self.create(d);captured=[]
            try:
                app.seek_fraction(.3);position=app.playback_offset()
                def fake_worker(_,arguments):
                    captured.extend(arguments)
                    path=Path(arguments[arguments.index('--report')+1])
                    path.write_text(json.dumps({'status':'stopped','elapsed':position,'control_sequence':0}))
                    return 2
                app.engine.run_playback_and_wait=fake_worker
                app.play(None)
                message=app.messages.get(timeout=3)
                self.assertEqual(message['kind'],'game_done')
                self.assertAlmostEqual(float(captured[captured.index('--position')+1]),position,places=4)
                app.handle_message(message)
                self.assertAlmostEqual(app.playback_offset(),position,places=4)
            finally:app.close()

    def test_alignment_choice_is_saved_per_instrument(self):
        with tempfile.TemporaryDirectory() as d:
            app=self.create(d)
            try:
                app.chord_align.set(True);app.update_score(quiet=True)
                self.assertEqual(app.score['settings']['chord_alignment_ms'],24)
                app.instrument.set('钢琴 · Shift 黑键');app.update_score(quiet=True)
                self.assertFalse(app.chord_align.get())
                app.instrument.set('吉他 · 钢琴模式');app.update_score(quiet=True)
                self.assertTrue(app.chord_align.get())
            finally:app.close()
            app=self.create(d)
            try:self.assertTrue(app.chord_align.get())
            finally:app.close()

    def test_seek_preserves_pause_and_ignores_old_progress_until_acknowledged(self):
        with tempfile.TemporaryDirectory() as d:
            app=self.create(d);folder=Path(d)
            try:
                app.active={'control':folder/'control.json','cancel':folder/'stop','progress':folder/'progress.json',
                    'length':10,'origin':0,'speed':1,'elapsed':1,'phase':'paused','pause_requested':True,'control_sequence':0}
                app.seek_fraction(.6)
                command=json.loads((folder/'control.json').read_text())
                self.assertEqual((command['seek_to'],command['paused']),(6,True))
                (folder/'progress.json').write_text(json.dumps({'phase':'paused','elapsed':1,'control_sequence':0}))
                app.update_progress();self.assertEqual(app.progress.get(),60)
                (folder/'progress.json').write_text(json.dumps({'phase':'paused','elapsed':6,'control_sequence':1}))
                app.update_progress();self.assertEqual(app.progress.get(),60)
                self.assertTrue(app.active['pause_requested'])
                app.toggle_pause()
                command=json.loads((folder/'control.json').read_text())
                self.assertEqual((command['seek_sequence'],command['sequence'],command['paused']),(1,2,False))
                app.handle_message({'kind':'game_done','code':2,'result':{'status':'stopped','elapsed':6,'control_sequence':2}})
                self.assertGreater(app.playback_offset(),0)
            finally:app.close()

    def test_ui_pause_resume_commands_and_paused_progress_remain_in_sync(self):
        with tempfile.TemporaryDirectory() as d:
            app=self.create(d)
            try:
                root=Path(d)
                app.active={'control':root/'control.json','cancel':root/'stop','progress':root/'progress.json',
                            'length':10,'phase':'playing','pause_requested':False,'control_sequence':0}
                app.refresh_controls()
                app.mini.play.invoke()
                command=json.loads((root/'control.json').read_text())
                self.assertEqual((command['sequence'],command['paused']),(1,True))
                (root/'progress.json').write_text(json.dumps({'phase':'paused','elapsed':3.5,'control_sequence':1}))
                app.update_progress();app.update_progress()
                self.assertEqual(app.progress.get(),35)
                self.assertEqual(app.time_text.get(),'00:03 / 00:10')
                self.assertIn('继续',app.mini.play.cget('text'))
                app.mini.play.invoke()
                command=json.loads((root/'control.json').read_text())
                self.assertEqual((command['sequence'],command['paused']),(2,False))
                # A stale progress message cannot undo the newer resume request.
                app.update_progress()
                self.assertFalse(app.active['pause_requested'])
                app.mini.stop.invoke()
                self.assertTrue((root/'stop').exists())
            finally:app.close()
