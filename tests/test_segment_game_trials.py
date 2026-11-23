"""In-game A/B trials; engine launches and all game input are mocked."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch

from nte_music_desk import cli
from nte_music_desk.paths import asset_dir
from nte_music_desk.ui import App


class SegmentGameTrialChecks(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = tk.Tk(); self.root.withdraw()
        self.app = App(self.root, SimpleNamespace(ROOT=Path(folder.name), ASSETS=asset_dir(),
                                                  key_schedule=cli.key_schedule))
        self.addCleanup(self.app.close)
        self.page = self.app.segment_page
        self.app.show_page('segments')
        self.page.set_range(2, 4)

    def test_a_and_b_use_shared_game_runner_without_applying_candidate(self):
        app, page = self.app, self.page
        page.transpose.set('2'); page.apply()
        saved = deepcopy(app.segment_edits)
        score = deepcopy(app.score)
        page.transpose.set('5')
        with patch.object(app, 'start_game_playback') as runner, patch.object(app, 'start_preview') as synthetic:
            page.try_in_game(False); page.try_in_game(True)
        self.assertEqual(runner.call_count, 2)
        a, b = [call.kwargs for call in runner.call_args_list]
        self.assertEqual([a['comparison'], b['comparison']], ['A 当前', 'B 候选'])
        self.assertEqual(a['start_at'], b['start_at'])
        self.assertEqual(a['seconds'], b['seconds'])
        self.assertEqual(a['score']['settings']['segments'][0]['transpose'], 2)
        self.assertEqual(b['score']['settings']['segments'][0]['transpose'], 5)
        self.assertEqual(app.segment_edits, saved)
        self.assertEqual(app.score, score)
        self.assertEqual(page.transpose.get(), '5')
        synthetic.assert_not_called()

    def test_worker_uses_countdown_and_game_engine_with_bounded_trial_score(self):
        app, page = self.app, self.page
        app.countdown.set('4'); app.speed.set('2'); app.update_score(quiet=True)
        app.seek_fraction(.5)
        positions = deepcopy(app.preferences['playback_positions'])
        score = deepcopy(app.score)
        preset = app.preset_store.path(app.song_fingerprint, app.applied_instrument)
        saved_preset = preset.read_bytes()
        page.transpose.set('3')
        with patch('nte_music_desk.ui.threading.Thread') as thread:
            page.try_in_game(True)
        self.assertIsNotNone(app.active)
        trial = app.active
        self.assertEqual(trial['comparison'], 'B 候选')
        self.assertAlmostEqual(trial['origin'], 2)
        self.assertAlmostEqual(trial['length'], 1)
        self.assertEqual(trial['elapsed'], 0)
        self.assertEqual(app.progress.get(), 0)
        self.assertEqual(str(page.trial_stop_button.cget('state')), 'normal')
        def run(_, arguments):
            def value(option): return arguments[arguments.index(option) + 1]
            self.assertEqual(value('--countdown'), '4')
            self.assertEqual(float(value('--position')), trial['offset'])
            self.assertEqual(Path(value('--control-file')), trial['control'])
            self.assertEqual(Path(value('--cancel-file')), trial['cancel'])
            sent = json.loads(Path(value('--play')).read_text(encoding='utf-8'))
            self.assertEqual(sent['instrument'], app.current_instrument().id)
            self.assertTrue(all(event['at'] < 2 for event in sent['events']))
            self.assertTrue(all(event['at'] + event['duration'] <= 2.000001 for event in sent['events']))
            Path(value('--report')).write_text(json.dumps({'status': 'completed', 'elapsed': 2}), encoding='utf-8')
            return 0
        # Execute the worker, replacing the only subprocess/game entry point.
        with patch.object(app.engine, 'run_playback_and_wait', side_effect=run, create=True) as engine:
            thread.call_args.kwargs['target']()
        engine.assert_called_once()
        app.handle_message(app.messages.get_nowait())
        self.assertIsNone(app.active)
        self.assertEqual(app.preferences['playback_positions'], positions)
        self.assertEqual(app.score, score)
        self.assertEqual(preset.read_bytes(), saved_preset)
        self.assertEqual(page.transpose.get(), '3')
        self.assertFalse(app.segment_edits)
        self.assertIn('B 候选', page.note.get())
        self.assertEqual(str(page.trial_stop_button.cget('state')), 'disabled')

    def test_trial_progress_pause_seek_stop_and_failures_preserve_full_song_resume(self):
        app, page = self.app, self.page
        app.seek_fraction(.6)
        positions = deepcopy(app.preferences['playback_positions'])
        for status, code in (('stopped', 2), ('error', 1), ('completed', 0)):
            with self.subTest(status=status), patch('nte_music_desk.ui.threading.Thread') as thread:
                page.try_in_game(False)
                trial = app.active
                self.assertIsNotNone(trial)
                page.try_in_game(True)
                self.assertEqual(thread.call_count, 1, 'No overlapping A/B sessions')
                trial['progress'].write_text(json.dumps({'phase': 'playing', 'elapsed': trial['offset'] + .5,
                                                         'control_sequence': 0}), encoding='utf-8')
                app.update_progress()
                self.assertAlmostEqual(trial['elapsed'], .5)
                self.assertAlmostEqual(app.playback_offset(), .5)
                app.request_pause(True)
                app.seek_fraction(.5)
                control = json.loads(trial['control'].read_text(encoding='utf-8'))
                self.assertTrue(control['paused'])
                self.assertAlmostEqual(control['seek_to'], trial['offset'] + trial['length'] / 2)
                page.trial_stop_button.invoke()
                self.assertTrue(trial['cancel'].is_file())
                app.handle_message({'kind': 'game_done', 'code': code,
                                    'result': {'status': status, 'elapsed': trial['offset'] + .8,
                                               'control_sequence': control['sequence'], 'reason': '模拟游戏退出'}})
                self.assertIsNone(app.active)
                self.assertEqual(app.preferences['playback_positions'], positions)
                self.assertIn('A 当前', page.note.get())

    def test_invalid_candidate_and_empty_range_never_launch_game(self):
        app, page = self.app, self.page
        with patch('nte_music_desk.ui.threading.Thread') as thread:
            for variable in page.track_vars.values(): variable.set(False)
            page.try_in_game(True)
            self.assertIsNone(app.active)
            self.assertIn('至少一个', page.note.get())
            page.set_range(.35, .45)  # Between the sample song's actual key presses.
            page.try_in_game(False)
            self.assertIsNone(app.active)
            self.assertIn('没有可演奏', page.note.get())
            thread.assert_not_called()

    def test_sixty_second_limit_and_launch_failure_restore_existing_position(self):
        app, page = self.app, self.page
        app.speed.set('.25'); app.update_score(quiet=True)
        page.set_range(0, app.song.seconds)
        with patch.object(app, 'start_game_playback') as runner:
            page.try_in_game(False)
        self.assertEqual(runner.call_args.kwargs['seconds'], 60)
        app.seek_fraction(.5)
        position = app.progress.get()
        positions = deepcopy(app.preferences['playback_positions'])
        with patch('nte_music_desk.ui.threading.Thread', side_effect=RuntimeError('模拟启动失败')):
            page.try_in_game(True)
        self.assertIsNone(app.active)
        self.assertEqual(app.preferences['playback_positions'], positions)
        self.assertAlmostEqual(app.progress.get(), position)
        self.assertEqual(page.note.get(), '模拟启动失败')

    def test_regular_game_performance_still_updates_full_song_resume(self):
        app = self.app
        app.seek_fraction(.5)
        position = app.playback_offset()
        with patch('nte_music_desk.ui.threading.Thread'):
            app.play(None)
        active = app.active
        self.assertIsNone(active['comparison'])
        self.assertEqual(active['offset'], 0)
        self.assertEqual(active['elapsed'], position)
        active['progress'].write_text(json.dumps({'phase': 'playing', 'elapsed': position + 1,
                                                  'control_sequence': 0}), encoding='utf-8')
        app.update_progress()
        self.assertAlmostEqual(app.preferences['playback_positions'][app.song_fingerprint], position + 1)
        app.handle_message({'kind': 'game_done', 'code': 2,
                            'result': {'status': 'stopped', 'elapsed': position + 2, 'control_sequence': 0}})
        self.assertAlmostEqual(app.playback_offset(), position + 2)

    def test_both_trials_preserve_the_same_leading_rest_inside_selection(self):
        from nte_music_desk.midi import MidiNote, MidiSong, write_midi
        app, page = self.app, self.page
        path = app.directory / 'leading-rest.mid'
        song = MidiSong('rest', 1, 480, [MidiNote(0, 0, 60, 90, 2, 2.4), MidiNote(0, 0, 64, 90, 3, 3.4)],
                        ['voice'], [(0, 500000)], 3.4, [])
        write_midi(song, path)
        app.open_path(path); page.set_range(1, 3)
        with patch.object(app, 'start_game_playback') as runner:
            page.try_in_game(False); page.try_in_game(True)
        self.assertEqual(runner.call_count, 2)
        for call in runner.call_args_list:
            trial = call.kwargs
            score = trial['score']
            self.assertAlmostEqual(score['summary']['source_origin_seconds'] + trial['start_at'], 1)
            self.assertAlmostEqual(score['events'][0]['at'] - trial['start_at'], 1)
            self.assertAlmostEqual(trial['seconds'], 2)


if __name__ == '__main__':
    unittest.main()
