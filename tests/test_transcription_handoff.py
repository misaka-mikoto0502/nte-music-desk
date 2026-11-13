from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

from nte_music_desk.ui import App
from nte_music_desk.paths import asset_dir
from nte_music_desk import cli


class TranscriptionHandoffChecks(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='win32','Windows desktop integration')
    def test_dropped_local_midi_is_on_shelf_once_and_survives_restart(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as d:
            directory=Path(d).resolve();source=directory/'普通导入.mid'
            source.write_bytes((asset_dir()/'scores/twinkle.mid').read_bytes())
            engine=SimpleNamespace(ROOT=directory,ASSETS=asset_dir(),key_schedule=cli.key_schedule)
            root=tk.Tk();root.withdraw();app=App(root,engine)
            try:
                self.assertTrue(app.import_local_file(source))
                self.assertTrue(app.import_local_file(source))
                self.assertEqual([p for _,p in app.library_buttons].count(source),1)
            finally:app.close()
            root=tk.Tk();root.withdraw();app=App(root,engine)
            try:self.assertEqual([p for _,p in app.library_buttons].count(source),1)
            finally:app.close()
