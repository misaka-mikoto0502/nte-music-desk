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
