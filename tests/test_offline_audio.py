import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import MagicMock, patch

import numpy as np

from nte_music_desk.offline_audio import OfflineRequest, ProcessOwner, notes_to_song, verify_bundle
from nte_music_desk.piano_transcription import decode_intervals, subframe
from nte_music_desk.local_library import generated_scores
from nte_music_desk.startup import is_task


class OfflineAudioChecks(unittest.TestCase):
    def test_native_statistics_do_not_break_progress_and_failure_is_reported(self):
        from nte_music_desk.offline_audio import run_song_engine
        with tempfile.TemporaryDirectory() as folder:
            process = MagicMock()
            process.__enter__.return_value = process
            process.wait.return_value = 0
            process.stdout = iter(['{"backend":"CPU","threads":8}\n',
                                   '{"progress":0.5}\n',
                                   '{"native_seconds":12.5,"peak_working_set_bytes":500000000}\n'])
            emit = MagicMock()
            with patch('nte_music_desk.offline_audio.subprocess.Popen', return_value=process):
                stats = run_song_engine(Path(folder)/'input.f32', Path(folder), 30, emit)
            self.assertEqual(stats['backend'], 'CPU')
            self.assertEqual(stats['native_seconds'], 12.5)
            emit.assert_called_once_with('recognize', .64, duration=30)
            process.wait.return_value = 1
            process.stdout = iter([])
            with patch('nte_music_desk.offline_audio.subprocess.Popen', return_value=process):
                with self.assertRaisesRegex(ValueError, 'native.log'):
                    run_song_engine(Path(folder)/'input.f32', Path(folder), 30, emit)

    def test_cancel_cleanup_preserves_predictions_midi_and_source_audio(self):
        from nte_music_desk.offline_audio import remove_temporary_audio
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            temporary = ['input.f32', 'vocal.f32', 'result.partial']
            durable = ['source.wav', 'raw-notes.json', 'result.json', 'score.mid']
            for name in temporary + durable: (root/name).write_bytes(b'keep')
            remove_temporary_audio(root)
            self.assertEqual(sorted(p.name for p in root.iterdir()), sorted(durable))
            remove_temporary_audio(root)

    def test_request_rejects_missing_files_bad_times_and_unknown_profiles(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / '自己的钢琴.wav'; source.touch()
            OfflineRequest(source, 'piano', 1, 10).validate()
            for values in [('wrong', 0, None), ('piano', float('nan'), None), ('song', 5, 4), ('song', 0, 3601)]:
                with self.assertRaises(ValueError): OfflineRequest(source, *values).validate()
            with self.assertRaises(ValueError): OfflineRequest(source.with_suffix('.missing')).validate()
        self.assertTrue(is_task(['--offline-audio-worker=local-request.json']))

    def test_missing_and_traversing_bundle_are_rejected_without_download(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            with self.assertRaises(ValueError): verify_bundle(root)
            (root / 'manifest.json').write_text(json.dumps({'schema': 1, 'files': [{'file': '../outside', 'bytes': 1, 'sha256': '0' * 64}]}))
            with self.assertRaises(ValueError): verify_bundle(root, hashes=True)

    def test_midi_keeps_chords_velocity_and_original_pitch_and_timing(self):
        notes = [dict(pitch=p, start=.123, end=1.25, velocity=v, program=0) for p, v in [(36, 34), (60, 82), (64, 90), (67, 113)]]
        notes += [dict(pitch=38, start=.123, end=.14, program=128, drum=True)]
        song = notes_to_song(notes, '和弦', 2)
        self.assertEqual([(n.pitch, n.velocity, n.start, n.end) for n in song.notes], [(36, 34, .123, 1.25), (60, 82, .123, 1.25), (64, 90, .123, 1.25), (67, 113, .123, 1.25)])
        self.assertEqual(len(notes), 5)  # Input/raw events are untouched.
        with self.assertRaises(ValueError): notes_to_song([dict(pitch=60, start=float('nan'), end=1)], 'bad', 2)

    def test_extra_instruments_are_consolidated_without_losing_notes(self):
        events = [dict(pitch=60 + p % 12, start=p / 10, end=p / 10 + .15, program=p) for p in range(20)]
        song = notes_to_song(events, 'mixed', 3)
        self.assertEqual(len(song.notes), 20)
        self.assertLessEqual(len(song.track_names), 15)

    def test_only_committed_successful_offline_results_enter_shelf(self):
        with tempfile.TemporaryDirectory() as folder:
            job = Path(folder) / 'offline-transcriptions/job'; job.mkdir(parents=True)
            midi = job / '自己的音乐_本地转谱.mid'; midi.write_bytes(b'test')
            self.assertEqual(generated_scores(folder), [])
            report = job / 'result.json'; report.write_text(json.dumps({'status': 'error', 'midi': str(midi)}))
            self.assertEqual(generated_scores(folder), [])
            report.write_text(json.dumps({'status': 'ok', 'midi': str(midi)}))
            self.assertEqual(generated_scores(folder), [midi.resolve()])

    def test_semicrf_keeps_chords_and_respects_continuation_positions(self):
        score = np.full((7, 7, 3), -20, np.float32)
        score[2, 1, :] = 5
        score[5, 4, :] = 7
        found = decode_intervals(score, [0, 0, 0])
        self.assertEqual(found, [[(1, 2), (4, 5)]] * 3)
        continued = decode_intervals(score, [3, 0, 6])
        self.assertEqual(continued, [[(4, 5)], [(1, 2), (4, 5)], []])
        self.assertEqual(decode_intervals(np.zeros((2, 2, 1), np.float32), [0]), [[]])

    def test_subframe_values_are_finite_continuous_and_symmetric(self):
        for value in [0, .001, .00399, .00401, 1, 40, 1000]:
            self.assertLessEqual(abs(subframe(value)), .5)
            self.assertAlmostEqual(subframe(-value), -subframe(value), places=8)
        self.assertLess(abs(subframe(.00399) - subframe(.00401)), .00001)

    def test_vocal_merge_removes_duplicate_pitch_but_keeps_chord_and_bass(self):
        from nte_music_desk.vocal_transcription import merge_vocal
        accompaniment = [dict(pitch=p, start=.1, end=.9, program=0, velocity=77) for p in (36, 60, 64, 67)]
        vocal = [dict(pitch=60, start=.12, end=.88, program=0, role='vocal', velocity=90)]
        merged = merge_vocal(accompaniment, vocal)
        self.assertEqual(sorted(n['pitch'] for n in merged), [36, 60, 64, 67])
        song = notes_to_song(merged, '歌曲', 1)
        self.assertEqual(song.track_names[0], '演唱主旋律')
        self.assertEqual(len(song.track_names), 2)
        self.assertEqual(len(accompaniment), 4)

    def test_cancelled_completion_never_imports_a_late_result(self):
        from nte_music_desk.offline_audio_ui import OfflineAudioDialog
        dialog = OfflineAudioDialog.__new__(OfflineAudioDialog)
        dialog.app = MagicMock(); dialog.job = MagicMock(); dialog.job.cancelled.is_set.return_value = True
        dialog.cancel_button = dialog.start_button = dialog.state = dialog.eta = MagicMock()
        dialog.controls = []; dialog.profile = 'piano'; dialog.select_profile = MagicMock(); dialog.fit_window = MagicMock()
        dialog.clear_result = MagicMock()
        dialog.background_requested = False
        dialog.finish({'kind': 'done', 'midi': 'should-not-import.mid'})
        dialog.app.accept_transcription.assert_not_called()
        self.assertIsNone(dialog.job)

    @unittest.skipUnless(sys.platform == 'win32', 'Windows job objects')
    def test_job_owner_terminates_only_its_process_tree(self):
        with tempfile.TemporaryDirectory() as folder:
            pidfile = Path(folder) / 'child.txt'
            code = 'import subprocess,sys,time,pathlib;p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(40)"]);pathlib.Path(sys.argv[1]).write_text(str(p.pid));time.sleep(40)'
            process = subprocess.Popen([sys.executable, '-c', code, str(pidfile)], creationflags=0x08000000)
            owner = ProcessOwner(process)
            try:
                deadline = time.monotonic() + 5
                while not pidfile.exists() and time.monotonic() < deadline: time.sleep(.02)
                self.assertTrue(pidfile.exists())
                import ctypes as c
                api = c.WinDLL('kernel32', use_last_error=True)
                api.OpenProcess.argtypes = [c.c_ulong, c.c_int, c.c_ulong]; api.OpenProcess.restype = c.c_void_p
                api.WaitForSingleObject.argtypes = [c.c_void_p, c.c_ulong]
                api.CloseHandle.argtypes = [c.c_void_p]
                child = api.OpenProcess(0x100000, False, int(pidfile.read_text()))
                self.assertTrue(child)
                try:
                    owner.close(); process.wait(timeout=5)
                    self.assertEqual(api.WaitForSingleObject(child, 5000), 0)
                finally: api.CloseHandle(child)
            finally:
                owner.close()
                if process.poll() is None: process.kill(); process.wait()


@unittest.skipUnless(sys.platform == 'win32', 'Native Windows workbench')
class OfflineWindowChecks(unittest.TestCase):
    def make_dialog(self):
        import tkinter as tk
        from types import SimpleNamespace
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        directory = Path(temporary.name)
        root = tk.Tk(); root.withdraw()
        app = App(root, SimpleNamespace(ROOT=directory, ASSETS=asset_dir(), key_schedule=cli.key_schedule))
        self.addCleanup(app.close)
        source = directory/'原音频.wav'; source.touch()
        app.open_offline_audio(source)
        dialog = app.offline_dialog; dialog.window.withdraw()
        return app, dialog, directory

    def complete(self, dialog, directory):
        from types import SimpleNamespace
        from nte_music_desk.paths import asset_dir
        midi = directory/'offline-transcriptions/success/示例_本地转谱.mid'
        midi.parent.mkdir(parents=True, exist_ok=True)
        midi.write_bytes((asset_dir()/'scores/twinkle.mid').read_bytes())
        (midi.parent/'result.json').write_text(json.dumps({'status':'ok','midi':str(midi)}))
        dialog.job = SimpleNamespace(cancelled=threading.Event())
        dialog.finish({'kind':'done','midi':str(midi),'notes':42,'start':0})
        self.assertEqual(dialog.value.get(), 100)
        self.assertEqual(dialog.start_button.cget('text'), '再次转谱')
        self.assertTrue(dialog.result_row.winfo_manager())
        return midi

    def assert_ready(self, dialog):
        from nte_music_desk.offline_audio_ui import READY_MESSAGE
        self.assertIsNone(dialog.result)
        self.assertEqual(dialog.value.get(), 0)
        self.assertEqual(dialog.eta.get(), '')
        self.assertEqual(dialog.state.get(), READY_MESSAGE)
        self.assertEqual(dialog.start_button.cget('text'), '开始转谱')
        self.assertFalse(dialog.result_row.winfo_manager())
        self.assertFalse(dialog.progress_row.winfo_manager())
        self.assertIsNone(dialog.audio_seconds)

    def test_all_file_selection_routes_clear_results_and_reset_excerpt(self):
        app, dialog, directory = self.make_dialog()
        for route in ('picker', 'drop', 'entry'):
            with self.subTest(route=route):
                dialog.start.set('0:10'); dialog.end.set('0:20')
                midi = self.complete(dialog, directory)
                new_file = directory/(route+'.wav'); new_file.touch()
                if route == 'picker':
                    with patch('nte_music_desk.offline_audio_ui.filedialog.askopenfilename', return_value=str(new_file)):
                        dialog.choose()
                elif route == 'drop':
                    app.open_offline_audio(new_file)
                    self.assertIs(app.offline_dialog, dialog)
                else:
                    dialog.source.set(str(new_file))
                self.assert_ready(dialog)
                self.assertEqual((dialog.start.get(), dialog.end.get()), ('0:00', ''))
                self.assertTrue(midi.is_file())
                self.assertEqual(app.current_path, midi.resolve())
                with patch('nte_music_desk.offline_audio_ui.os.startfile') as open_folder:
                    dialog.open_folder()
                    open_folder.assert_not_called()
                with patch('nte_music_desk.audio_audition.AuditionWindow') as audition:
                    dialog.compare()
                    audition.assert_not_called()

    def test_changed_settings_clear_result_but_same_selection_preserves_it(self):
        app, dialog, directory = self.make_dialog()
        self.complete(dialog, directory)
        saved = dialog.result
        with patch('nte_music_desk.offline_audio_ui.filedialog.askopenfilename', return_value=''):
            dialog.choose()
        dialog.choose_source(Path(dialog.source.get()))
        dialog.select_profile(dialog.profile)
        dialog.start.set(dialog.start.get())
        dialog.toggle_segment()
        self.assertIs(dialog.result, saved)
        for variable in (dialog.start, dialog.end):
            self.complete(dialog, directory)
            variable.set('0:05')
            self.assert_ready(dialog)
        self.complete(dialog, directory)
        audition = MagicMock()
        dialog.audition = audition
        dialog.select_profile('song' if dialog.profile == 'piano' else 'piano')
        self.assert_ready(dialog)
        audition.close.assert_called_once()
        self.assertEqual((dialog.start.get(), dialog.end.get()), ('0:05', '0:05'))

    def test_error_cancel_and_invalid_retry_cannot_show_previous_success(self):
        app, dialog, directory = self.make_dialog()
        for message in ({'kind':'error','error':'解码失败'}, {'kind':'cancelled'}):
            self.complete(dialog, directory)
            dialog.finish(message)
            self.assertIsNone(dialog.result)
            self.assertFalse(dialog.result_row.winfo_manager())
            self.assertFalse(dialog.progress_row.winfo_manager())
            self.assertEqual(dialog.value.get(), 0)
            self.assertEqual(dialog.start_button.cget('text'), '开始转谱')
        self.complete(dialog, directory)
        with patch('nte_music_desk.offline_audio_ui.OfflineJob', side_effect=ValueError('文件不可读取')):
            dialog.begin()
        self.assertIsNone(dialog.result)
        self.assertEqual(dialog.state.get(), '文件不可读取')
        self.assertFalse(dialog.result_row.winfo_manager())

    def test_old_worker_notifications_cannot_override_next_job(self):
        from types import SimpleNamespace
        app, dialog, directory = self.make_dialog()
        callbacks = []
        def create_job(directory, request, notify):
            callbacks.append(notify)
            return SimpleNamespace(cancelled=threading.Event(), start=MagicMock(), cancel=MagicMock())
        with patch('nte_music_desk.offline_audio_ui.OfflineJob', side_effect=create_job):
            dialog.begin()
            old_queue = dialog.messages
            dialog.finish({'kind':'cancelled'})
            dialog.choose_source(directory/'下一首.wav')
            dialog.begin()
            self.assertIsNot(dialog.messages, old_queue)
            callbacks[0]({'kind':'done','midi':'old.mid','notes':99,'start':0})
            self.assertTrue(dialog.messages.empty())
            self.assertIsNone(dialog.result)
            self.assertEqual(dialog.start_button.cget('text'), '正在转谱')

    def test_expanded_states_keep_primary_action_inside_window_and_import_result(self):
        import tkinter as tk
        from types import SimpleNamespace
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        with tempfile.TemporaryDirectory() as folder:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(folder), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            try:
                app.open_offline_audio()
                dialog = app.offline_dialog; dialog.window.withdraw()
                dialog.toggle_segment()
                dialog.progress_row.pack(fill='x', before=dialog.start_button.master)
                dialog.fit_window(); root.update_idletasks()
                def check_action_visible():
                    action_bottom = dialog.start_button.winfo_rooty() + dialog.start_button.winfo_height()
                    client_bottom = dialog.window.winfo_rooty() + dialog.window.winfo_height()
                    self.assertLessEqual(action_bottom, client_bottom)
                    self.assertGreater(dialog.start_button.winfo_height(), 30)
                check_action_visible()
                self.assertTrue(dialog.segment_visible)
                path = Path(folder)/'offline-transcriptions/job/示例_本地转谱.mid'; path.parent.mkdir(parents=True)
                path.write_bytes((asset_dir()/'scores/twinkle.mid').read_bytes())
                (path.parent/'result.json').write_text(json.dumps({'status':'ok','midi':str(path)}))
                dialog.job = SimpleNamespace(cancelled=threading.Event())
                self.assertTrue(app.audio_busy())
                dialog.finish({'kind':'done','midi':str(path),'notes':42,'start':0})
                self.assertEqual(app.current_path,path.resolve())
                self.assertFalse(app.audio_busy())
                check_action_visible()
            finally: app.close()
