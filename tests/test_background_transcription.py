"""Bundled transcription may coexist with playback without replacing its score."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from nte_music_desk import cli
from nte_music_desk.paths import asset_dir
from nte_music_desk.ui import App


@unittest.skipUnless(sys.platform == 'win32', 'Windows workbench')
class BackgroundTranscriptionChecks(unittest.TestCase):
    def create(self):
        import tkinter as tk
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = tk.Tk(); root.withdraw()
        app = App(root, SimpleNamespace(ROOT=Path(temporary.name).resolve(), ASSETS=asset_dir(),
                                        key_schedule=cli.key_schedule))
        def close():
            app.active = None
            app.close()
        self.addCleanup(close)
        app.load_demo()
        source = app.directory/'new.wav'; source.touch()
        app.open_offline_audio(source)
        app.offline_dialog.window.withdraw()
        return app, app.offline_dialog

    def job(self):
        return SimpleNamespace(cancelled=threading.Event(), start=MagicMock(), cancel=MagicMock())

    def result(self, app):
        midi = app.directory/'offline-transcriptions/new/结果_本地转谱.mid'
        midi.parent.mkdir(parents=True, exist_ok=True)
        midi.write_bytes((asset_dir()/'scores/twinkle.mid').read_bytes())
        (midi.parent/'result.json').write_text(json.dumps({'status':'ok','midi':str(midi)}))
        return {'kind':'done','midi':str(midi),'notes':42,'start':0}

    def test_main_and_mini_remain_available_during_transcription(self):
        app, dialog = self.create()
        dialog.job = self.job()
        app.refresh_controls()
        self.assertTrue(app.audio_busy())
        self.assertEqual(str(app.play_button.cget('state')), 'normal')
        self.assertEqual(str(app.mini.play.cget('state')), 'normal')
        self.assertEqual(str(app.import_button.cget('state')), 'normal')
    def test_background_start_and_cancel_do_not_stop_existing_preview(self):
        app, dialog = self.create()
        app.preview_token = 'existing-preview'
        job = self.job()
        with patch('nte_music_desk.offline_audio_ui.OfflineJob', return_value=job), patch.object(app, 'stop_preview') as stop:
            dialog.begin()
            self.assertIs(dialog.job, job)
            job.start.assert_called_once()
            self.assertEqual(app.preview_token, 'existing-preview')
            dialog.cancel()
            job.cancel.assert_called_once()
            stop.assert_not_called()
        self.assertEqual(app.preview_token, 'existing-preview')

    def test_completion_preserves_playing_preview_comparison_or_changed_song(self):
        for mode in ('game', 'preview', 'comparison', 'changed-song'):
            with self.subTest(mode=mode):
                app, dialog = self.create()
                dialog.workbench_path = app.current_path
                if mode == 'game': app.active = {'phase':'playing'}
                elif mode == 'preview': app.preview_token = 'ongoing'
                elif mode == 'comparison': app.audio_audition = SimpleNamespace(closed=False, close=MagicMock())
                else:
                    other = app.directory/'selected.mid'
                    other.write_bytes((asset_dir()/'scores/twinkle.mid').read_bytes())
                    app.open_path(other)
                song, score, path = app.song, app.score, app.current_path
                active, token, audition = app.active, app.preview_token, app.audio_audition
                dialog.job = self.job()
                result = self.result(app)
                dialog.finish(result)
                self.assertIs(app.song, song); self.assertIs(app.score, score)
                self.assertEqual(app.current_path, path)
                self.assertIs(app.active, active); self.assertEqual(app.preview_token, token)
                self.assertIs(app.audio_audition, audition)
                self.assertIn(Path(result['midi']), [p for _,p in app.library_buttons])
                if audition: audition.close.assert_not_called()
                app.active = None

    def test_idle_completion_still_loads_and_second_audio_is_rejected(self):
        app, dialog = self.create()
        dialog.job = self.job()
        job = dialog.job
        other = app.directory/'other.wav'; other.touch()
        with patch.object(app, 'open_offline_audio') as show:
            self.assertFalse(app.import_local_file(other))
            show.assert_called_once_with()
        self.assertIs(dialog.job, job)
        score = app.directory/'another.mid'
        score.write_bytes((asset_dir()/'scores/twinkle.mid').read_bytes())
        self.assertTrue(app.import_local_file(score))
        dialog.workbench_path = app.current_path
        result = self.result(app)
        dialog.finish(result)
        self.assertEqual(app.current_path, Path(result['midi']))

    def test_choosing_another_song_and_returning_still_preserves_the_user_selection(self):
        app,dialog=self.create()
        original=app.current_path
        other=app.directory/'another.mid';other.write_bytes(original.read_bytes())
        with patch('nte_music_desk.offline_audio_ui.OfflineJob',return_value=self.job()):
            dialog.begin()
        app.open_path(other);app.open_path(original)
        self.assertEqual(app.current_path,dialog.workbench_path)
        self.assertNotEqual(app.song_revision,dialog.workbench_revision)
        result=self.result(app);dialog.finish(result)
        self.assertEqual(app.current_path,original)
        self.assertIn(Path(result['midi']),[p for _,p in app.library_buttons])

    def test_background_button_hides_without_cancelling_and_does_not_autoload(self):
        app, dialog = self.create()
        dialog.job = self.job()
        job, original = dialog.job, app.current_path
        dialog.run_in_background()
        self.assertEqual(dialog.window.state(), 'withdrawn')
        job.cancel.assert_not_called()
        self.assertEqual(app.transcription_button.cget('text'), '查看转谱进度')
        self.assertEqual(app.transcription_button.winfo_manager(), 'pack')
        app.transcription_button.invoke()
        self.assertFalse(app.transcription_button.winfo_manager())
        self.assertIs(app.offline_dialog, dialog)
        self.assertIs(dialog.job, job)
        result = self.result(app)
        dialog.finish(result)
        self.assertEqual(app.current_path, original)
        self.assertIn(Path(result['midi']), [p for _,p in app.library_buttons])
        self.assertFalse(dialog.background_button.winfo_manager())

    def test_game_pause_seek_and_stop_are_separate_from_transcription_cancel(self):
        app, dialog = self.create()
        dialog.job = self.job()
        job = dialog.job
        with patch('nte_music_desk.ui.threading.Thread') as thread:
            app.play(None)
        thread.assert_called_once()
        self.assertIsNotNone(app.active)
        app.active['phase'] = 'playing'
        app.refresh_controls()
        app.mini.play.invoke()
        control = json.loads(app.active['control'].read_text())
        self.assertTrue(control['paused'])
        app.seek_fraction(.3)
        app.stop()
        self.assertTrue(app.active['cancel'].is_file())
        job.cancel.assert_not_called()

    def test_priority_is_applied_only_to_worker_and_inherited_by_child(self):
        root = Path(__file__).resolve().parents[1]
        code = '''import ctypes,subprocess,sys,json
from ctypes import wintypes
from nte_music_desk.offline_audio import background_priority
k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=wintypes.HANDLE
k.GetPriorityClass.argtypes=[wintypes.HANDLE];k.GetPriorityClass.restype=wintypes.DWORD
background_priority()
child="import ctypes;from ctypes import wintypes;k=ctypes.WinDLL('kernel32');k.GetCurrentProcess.restype=wintypes.HANDLE;k.GetPriorityClass.argtypes=[wintypes.HANDLE];print(k.GetPriorityClass(k.GetCurrentProcess()))"
print(json.dumps([k.GetPriorityClass(k.GetCurrentProcess()),int(subprocess.check_output([sys.executable,'-c',child]))]))
'''
        result = subprocess.run([sys.executable,'-c',code], cwd=root, text=True, capture_output=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [0x4000, 0x4000])
