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
    def test_audio_dialog_configuration_help_and_close_without_engine(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            try:
                app.open_audio()
                dialog = app.audio_dialog
                root.update_idletasks()
                self.assertTrue(dialog.window.winfo_exists())
                dialog.transcribe()
                self.assertIsNone(dialog.job)
                self.assertIn('安装', dialog.state.get())
                from nte_music_desk.audio_ui import FLOWS, KINDS
                from nte_music_desk.rights import SOURCE_BASES
                self.assertEqual(dialog.flow.get(),FLOWS['accompaniment'])
                self.assertEqual(dialog.source_kind.get(),KINDS['instrumental'])
                self.assertFalse(dialog.muscriptor_terms.get())
                self.assertFalse(dialog.game_terms.get())
                dialog.flow.set(FLOWS['melody']);dialog.flow_changed()
                self.assertEqual(dialog.source_kind.get(),KINDS['original'])
                dialog.flow.set(FLOWS['accompaniment']);dialog.flow_changed()
                self.assertEqual(dialog.source_kind.get(),KINDS['instrumental'])
                source=Path(directory)/'own.wav';source.write_bytes(b'fixture')
                dialog.executable.set(sys.executable);dialog.source.set(str(source))
                dialog.rights_basis.set(SOURCE_BASES['original']);dialog.rights_reference.set('self recorded')
                dialog.transcribe()
                self.assertIsNone(dialog.job)
                self.assertIn('模型条款',dialog.state.get())
                dialog.muscriptor_terms.set(True)
                with patch.object(dialog,'begin') as begin:
                    dialog.transcribe()
                    begin.assert_called_once()
                dialog.source.set(str(Path(directory)/'another.wav'))
                self.assertEqual(dialog.rights_reference.get(),'')
                self.assertNotIn(dialog.rights_basis.get(),SOURCE_BASES.values())
                from nte_music_desk.transcription import ProcessJob
                dialog.job = ProcessJob()
                dialog.job.cancel()
                dialog.messages.put(('done', ('transcribed', Path(directory) / 'late.mid')))
                dialog.window.after_cancel(dialog.poll_id)
                dialog.poll()
                self.assertIsNone(dialog.result)
                self.assertIn('取消', dialog.state.get())
                dialog.help()
                dialog.close()
                self.assertIsNone(app.audio_dialog)
            finally:
                app.close()

    def test_corrupt_preset_is_not_overwritten_without_explicit_reset(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            try:
                path = app.preset_store.path(app.song_fingerprint, app.applied_instrument)
                path.write_text('{ broken future data', encoding='utf-8')
                app.restore_arrangement()
                app.update_score()
                self.assertEqual(path.read_text(), '{ broken future data')
                app.reset_settings()
                self.assertEqual(path.with_suffix('.unreadable.backup.json').read_text(), '{ broken future data')
                self.assertEqual(json.loads(path.read_text())['schema'], 'nte-arrangement-v2')
            finally:
                app.close()

    def test_role_settings_are_isolated_between_instruments(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            try:
                part = str(app.tracks.rows[0]['index'])
                app.tracks.roles[part] = 'bass'
                app.update_score()
                app.instrument.set('钢琴 · Shift 黑键')
                app.update_score()
                self.assertEqual(app.tracks.roles[part], app.tracks.rows[0]['role'])
                app.instrument.set('吉他 · 钢琴模式')
                app.update_score()
                self.assertEqual(app.tracks.roles[part], 'bass')
            finally:
                app.close()

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

    def test_local_only_import_keeps_legacy_title_and_musicxml_export(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.midi import read_midi
        with tempfile.TemporaryDirectory() as directory:
            target=Path(directory)/'downloaded_midis'/'legacy.mid'
            target.parent.mkdir()
            target.write_bytes((asset_dir()/'scores/twinkle.mid').read_bytes())
            target.with_suffix('.source.json').write_text(json.dumps({'filename':target.name,'title':'本地旧曲谱'}),encoding='utf-8')
            root=tk.Tk();root.withdraw()
            with patch('socket.socket.connect',side_effect=AssertionError('local import must not connect')):
                app=App(root,SimpleNamespace(ROOT=Path(directory),ASSETS=asset_dir(),key_schedule=cli.key_schedule))
                try:
                    self.assertFalse(hasattr(app,'open_online'))
                    self.assertFalse(root.bind('<Control-f>'))
                    self.assertTrue(app.open_path(target))
                    self.assertEqual(app.song.title,'本地旧曲谱')
                    self.assertTrue(app.open_path(asset_dir()/'scores/twinkle.musicxml'))
                    destination=Path(directory)/'exported.mid'
                    with patch('nte_music_desk.ui.filedialog.asksaveasfilename',return_value=str(destination)):
                        app.export_midi()
                    self.assertEqual(len(read_midi(destination).notes),42)
                    self.assertIsNone(app.active)
                    self.assertTrue(target.is_file())
                finally:app.close()

    def test_isolated_bootstrap_and_read_only_assets(self):
        assets=ROOT/"src/nte_music_desk/assets"
        before={str(p.relative_to(assets)):p.read_bytes() for p in assets.rglob("*") if p.is_file()}
        with tempfile.TemporaryDirectory() as directory:
            report=Path(directory)/"result.json"
            completed=subprocess.run([sys.executable,"-X","utf8","-I",str(ROOT/"src/nte_music_desk/_bootstrap.py"),
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
