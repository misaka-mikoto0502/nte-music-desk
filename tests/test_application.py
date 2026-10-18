import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import io
import zipfile

ROOT=Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform=="win32","Desktop integration requires Windows")
class ApplicationChecks(unittest.TestCase):
    def setUp(self):
        sys.path.insert(0, str(ROOT / 'src'))
        def fail(app, error):
            raise AssertionError(str(error))
        self.dialog_errors = patch('nte_music_desk.ui.App.show_error', new=fail)
        self.dialog_errors.start()
        self.addCleanup(self.dialog_errors.stop)

    def test_audition_recommendation_and_report_ui_without_game_input(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        def child(window, text):
            for widget in window.winfo_children():
                if isinstance(widget, tk.Button) and widget.cget('text') == text:
                    return widget
            raise AssertionError(f'Button missing: {text}')
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            engine = SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule,
                                     render_preview=cli.render_preview, render_song_preview=cli.render_song_preview)
            app = App(root, engine)
            try:
                app.end.set('4'); app.update_score()
                app.tracks.show_workspace()
                root.update_idletasks()
                self.assertEqual(len(app.tracks.views), 2)
                self.assertGreater(len(app.tracks.timeline.find_all()), 0)
                selection = app.tracks.curselection()
                app.preview_track()
                message = app.messages.get(timeout=15)
                self.assertEqual(message['kind'], 'preview_ready')
                self.assertIn('原声部', message['caption'])
                self.assertEqual(app.tracks.curselection(), selection)
                app.stop_preview()
                with patch('winsound.PlaySound') as sound:
                    app.handle_message(message)
                    sound.assert_not_called()  # A cancelled async result must stay silent.
                app.preview()
                message = app.messages.get(timeout=15)
                self.assertEqual(message['kind'], 'preview_ready')
                self.assertIn('时序', message['caption'])
                app.stop_preview()
                app.recommend_transpose()
                message = app.messages.get(timeout=15)
                self.assertEqual(message['kind'], 'transpose_ready')
                app.handle_message(message)
                window = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and w.title() == '推荐移调方案')
                child(window, '应用所选方案').invoke()
                self.assertEqual(int(app.transpose.get()), message['candidates'][0]['transpose'])
                app.show_adaptation()
                window = next(w for w in root.winfo_children() if isinstance(w, tk.Toplevel) and '适配报告' in w.title())
                footer = next(w for w in window.winfo_children() if isinstance(w, tk.Frame) and any(isinstance(b, tk.Button) for b in w.winfo_children()))
                report_path = Path(directory) / 'report.json'
                with patch('nte_music_desk.ui.filedialog.asksaveasfilename', return_value=str(report_path)):
                    child(footer, '导出报告').invoke()
                report = json.loads(report_path.read_text(encoding='utf-8'))
                self.assertEqual(report['schema'], 'nte-adaptation-report-v1')
                self.assertGreater(report['performance']['planned_notes'], 0)
                self.assertIsNone(app.active)
            finally:
                app.close()

    def test_arrangement_restores_after_rename_and_instrument_switch(self):
        sys.path.insert(0, str(ROOT / 'src'))
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        with tempfile.TemporaryDirectory() as directory:
            score = Path(directory) / 'song.mid'
            score.write_bytes((asset_dir() / 'scores/twinkle.mid').read_bytes())
            engine = SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule)
            root = tk.Tk(); root.withdraw()
            app = App(root, engine)
            try:
                self.assertTrue(app.open_path(score))
                app.speed.set('.75'); app.mode.set('和弦版（最多 6 音）')
                app.update_score()
                app.instrument.set('钢琴 · Shift 黑键')
                self.assertEqual(float(app.speed.get()), 1)
                app.speed.set('1.25'); app.hold_ms.set('220')
                app.start.set('0:02'); app.end.set('0:09'); app.update_score()
                app.instrument.set('吉他 · 钢琴模式')
                self.assertEqual(float(app.speed.get()), .75)
                self.assertTrue(app.mode.get().startswith('和弦'))
                app.instrument.set('钢琴 · Shift 黑键')
                self.assertEqual(float(app.speed.get()), 1.25)
                self.assertEqual(app.hold_ms.get(), '220')
                self.assertEqual(float(app.end.get()), 9)
            finally:
                app.close()
            renamed = score.rename(Path(directory) / 'renamed.mid')
            root = tk.Tk(); root.withdraw()
            app = App(root, engine)
            try:
                self.assertTrue(app.open_path(renamed))
                self.assertEqual(float(app.speed.get()), 1.25)
                self.assertEqual(app.hold_ms.get(), '220')
                self.assertEqual(float(app.start.get()), 2)
                self.assertEqual(float(app.end.get()), 9)
            finally:
                app.close()

    def test_classical_zip_auto_import_and_musicxml_export_ui(self):
        sys.path.insert(0,str(ROOT/'src'))
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.catalog import CatalogClient
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.midi import read_midi
        import time
        archive=io.BytesIO()
        with zipfile.ZipFile(archive,'w') as z:
            for name in ('movement2.mid','movement1.mid'):
                z.writestr(name,(asset_dir()/'scores/twinkle.mid').read_bytes())
        with tempfile.TemporaryDirectory() as directory:
            root=tk.Tk();root.withdraw();root.lift=lambda:None
            app=App(root,SimpleNamespace(ROOT=Path(directory),ASSETS=asset_dir(),key_schedule=cli.key_schedule))
            try:
                app.online_client=CatalogClient(directory,resources=asset_dir(),fetch=lambda *args,**kwargs:archive.getvalue())
                with patch.object(tk.Toplevel,'grab_set',lambda self:None):
                    app.open_online('贝多芬 月光','Mutopia 古典')
                dialog=app.online_dialog
                def finish():
                    deadline=time.monotonic()+15
                    while dialog.busy and not dialog.closed:
                        message=dialog.messages.get(timeout=max(.1,deadline-time.monotonic()))
                        dialog.handle_message(*message)
                finish()
                self.assertEqual(dialog.current_item().key,'276')
                dialog.import_selected();finish()
                self.assertTrue(dialog.closed)
                self.assertIn('movement1',app.song.title)
                self.assertEqual(len(app.online_client.downloaded()),2)
                self.assertIn('2 个乐章',app.status.get())
                self.assertTrue(app.open_path(asset_dir()/'scores/twinkle.musicxml'))
                destination=Path(directory)/'exported.mid'
                with patch('nte_music_desk.ui.filedialog.asksaveasfilename',return_value=str(destination)):
                    app.export_midi()
                self.assertEqual(len(read_midi(destination).notes),42)
                self.assertIsNone(app.active)
            finally:app.close()

    def test_isolated_bootstrap_and_read_only_assets(self):
        assets=ROOT/"src/nte_music_desk/assets"
        before={str(p.relative_to(assets)):p.read_bytes() for p in assets.rglob("*") if p.is_file()}
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/"result.json"
            completed=subprocess.run([sys.executable,"-X","utf8","-I","-S",str(ROOT/"src/nte_music_desk/_bootstrap.py"),
                                      "--data-dir",str(Path(directory)/"data"),"--self-test",str(report)],
                                     capture_output=True,text=True,encoding="utf-8",timeout=30)
            self.assertEqual(completed.returncode,0,completed.stderr)
            result=json.loads(report.read_text(encoding="utf-8"))
            self.assertEqual(result["status"],"passed")
            self.assertFalse(result["game_input_sent"])
            self.assertTrue((Path(directory)/"data/midi_ui_settings.json").is_file())
        after={str(p.relative_to(assets)):p.read_bytes() for p in assets.rglob("*") if p.is_file()}
        self.assertEqual(before,after)


if __name__=="__main__":unittest.main()
