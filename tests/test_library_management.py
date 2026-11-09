"""Shelf edits must survive rescanning/restarts without changing source scores."""
from contextlib import contextmanager
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from nte_music_desk import cli
from nte_music_desk.local_library import shelf_customizations
from nte_music_desk.paths import asset_dir
from nte_music_desk.ui import App


@contextmanager
def workbench(directory):
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    def fail(app, error):raise AssertionError(str(error))
    app = None
    try:
        with patch.object(App, 'show_error', fail):
            app = App(root, SimpleNamespace(ROOT=directory, ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            yield app
    finally:
        if app is not None:app.close()
        else:root.destroy()


class ShelfMetadataChecks(unittest.TestCase):
    def test_bad_saved_metadata_is_ignored(self):
        self.assertEqual(shelf_customizations({'shelf_names': [], 'shelf_hidden': {}}), ({}, set()))
        names, hidden = shelf_customizations({
            'shelf_names': {'bad\0path': 'name', '': 'empty', 'valid.mid': ' ', 'too-long.mid': 'x' * 181,
                            'good.mid': '  A  -  B  ', 'wrong.mid': False},
            'shelf_hidden': [False, {}, '', 'bad\0path', 'hidden.mid']})
        self.assertEqual(names, {Path('good.mid').resolve(): 'A - B'})
        self.assertEqual(hidden, {Path('hidden.mid').resolve()})


@unittest.skipUnless(sys.platform == 'win32', 'Windows desktop integration')
class ShelfManagementChecks(unittest.TestCase):
    def score_file(self, directory, name):
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((asset_dir() / 'scores/twinkle.mid').read_bytes())
        return path

    def button(self, app, path):
        return next(button for button, entry in app.library_buttons if entry == path)

    def test_alias_updates_both_titles_and_mini_and_preserves_arrangement_after_restart(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d).resolve()
            path = self.score_file(directory, '原文件.mid')
            original = path.read_bytes()
            with workbench(directory) as app:
                self.assertTrue(app.open_path(path))
                app.speed.set('0.85')
                app.update_score()
                app.seek_fraction(.4)
                position = app.playback_offset()
                self.assertTrue(app.set_library_name(path, '  我的练习 - 第一段  '))
                self.assertEqual(self.button(app, path).cget('text'), '我的练习 - 第一段')
                self.assertEqual(app.title.get(), '我的练习 - 第一段')
                self.assertEqual(app.mini.title.cget('text'), '我的练习 - 第一段')
                self.assertEqual(self.button(app, path).palette[1], '#326B52')
                self.assertEqual(path.read_bytes(), original)
            with workbench(directory) as app:
                self.assertEqual(app.current_path, path)
                self.assertEqual(app.title.get(), '我的练习 - 第一段')
                self.assertEqual(self.button(app, path).cget('text'), '我的练习 - 第一段')
                self.assertEqual(float(app.speed.get()), .85)
                self.assertAlmostEqual(app.playback_offset(), position, places=5)
                self.assertEqual(path.read_bytes(), original)

    def test_editing_another_entry_does_not_switch_or_rename_current_song(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d).resolve()
            path = self.score_file(directory, '另一个文件.mid')
            with workbench(directory) as app:
                app.open_path(path)
                example = asset_dir() / 'scores/twinkle.mid'
                app.open_path(example)
                self.assertTrue(app.set_library_name(path, '另一个名字'))
                self.assertEqual(app.current_path, example)
                self.assertEqual(app.title.get(), '小星星')
                self.assertEqual(self.button(app, path).cget('text'), '另一个名字')
                self.assertTrue(app.remove_library(path))
                self.assertEqual(app.current_path, example)
                self.assertEqual(app.title.get(), '小星星')
                self.assertTrue(path.is_file())

    def test_generated_entry_stays_removed_after_rescan_and_restart_and_reimport_restores_alias(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d).resolve()
            path = self.score_file(directory, 'light-transcriptions/job/自己的录音_轻量Beta.mid')
            original = path.read_bytes()
            with workbench(directory) as app:
                self.assertIn(path, [entry for _, entry in app.library_buttons])
                app.open_path(path)
                app.set_library_name(path, '音频练习')
                app.speed.set('.8')
                app.update_score()
                app.seek_fraction(.25)
                position = app.playback_offset()
                self.assertTrue(app.remove_library(path))
                app.refresh_library()
                self.assertNotIn(path, [entry for _, entry in app.library_buttons])
                self.assertNotEqual(app.current_path, path)
                self.assertEqual(path.read_bytes(), original)
            with workbench(directory) as app:
                self.assertNotIn(path, [entry for _, entry in app.library_buttons])
                self.assertTrue(app.import_local_file(path))
                self.assertEqual(app.title.get(), '音频练习')
                self.assertEqual(self.button(app, path).cget('text'), '音频练习')
                self.assertEqual(float(app.speed.get()), .8)
                self.assertAlmostEqual(app.playback_offset(), position, places=5)
                self.assertEqual(path.read_bytes(), original)

    def test_removing_every_entry_clears_workspace_and_does_not_restore_example_on_restart(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d).resolve()
            path = self.score_file(directory, '最后一首.mid')
            with workbench(directory) as app:
                app.open_path(path)
                app.tracks.show_workspace()
                for _, entry in list(app.library_buttons):self.assertTrue(app.remove_library(entry))
                self.assertEqual(app.library_buttons, [])
                self.assertIsNone(app.song)
                self.assertIsNone(app.score)
                self.assertIsNone(app.current_path)
                self.assertEqual(app.title.get(), '选择一首曲子')
                self.assertEqual(app.tracks.rows, [])
                self.assertEqual(app.tracks.tree.get_children(), ())
                self.assertEqual(str(app.play_button.cget('state')), 'disabled')
                self.assertEqual(json.loads((directory / 'midi_ui_settings.json').read_text(encoding='utf-8'))['last_file'], '')
            with workbench(directory) as app:
                self.assertEqual(app.library_buttons, [])
                self.assertIsNone(app.score)
                self.assertTrue(app.open_path(asset_dir() / 'scores/twinkle.mid'))
                self.assertEqual(len(app.library_buttons), 1)
                self.assertEqual(app.title.get(), '小星星')

    def test_right_click_menu_targets_clicked_entry_and_rename_dialog_validates_input(self):
        import tkinter as tk
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d).resolve()
            path = self.score_file(directory, '右键目标.mid')
            with workbench(directory) as app:
                app.open_path(path)
                example = asset_dir() / 'scores/twinkle.mid'
                app.open_path(example)
                button = self.button(app, path)
                self.assertTrue(button.bind('<Button-3>'))
                self.assertTrue(button.bind('<Shift-F10>'))
                event = SimpleNamespace(widget=button, num=3, x_root=100, y_root=200)
                with patch.object(tk.Menu, 'tk_popup') as popup:
                    self.assertEqual(app.show_library_menu(event, path), 'break')
                    popup.assert_called_once_with(100, 200)
                self.assertEqual(app.current_path, example)
                self.assertEqual(app.library_menu.entrycget(0, 'label'), '重命名…')
                self.assertEqual(app.library_menu.entrycget(2, 'label'), '从列表移除')
                app.library_menu.invoke(0)
                window = app.rename_window
                entry = next(child for child in window.winfo_children() if isinstance(child, tk.Entry))
                save = next(child for frame in window.winfo_children() if isinstance(frame, tk.Frame)
                            for child in frame.winfo_children() if isinstance(child, tk.Button) and child.cget('text') == '保存名称')
                entry.delete(0, 'end')
                save.invoke()
                self.assertTrue(window.winfo_exists())
                entry.insert(0, '右键新名字')
                save.invoke()
                self.assertFalse(window.winfo_exists())
                self.assertEqual(self.button(app, path).cget('text'), '右键新名字')
                self.assertEqual(app.title.get(), '小星星')
                app.library_menu.invoke(2)
                self.assertNotIn(path, [entry for _, entry in app.library_buttons])
                self.assertTrue(path.is_file())

    def test_invalid_names_cancel_and_busy_operations_leave_shelf_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d).resolve()
            with workbench(directory) as app:
                path = app.current_path
                original = dict(app.preferences)
                for name in ('', '  ', 'x' * 181, 'a\nb', 'a\0b'):
                    with self.assertRaises(ValueError):app.set_library_name(path, name)
                self.assertEqual(app.preferences, original)
                app.rename_library(path)
                app.rename_window.destroy()
                self.assertEqual(app.title.get(), '小星星')
                for field, value in [('active', {'phase': 'playing'}), ('preview_token', 'preview'),
                                     ('light_audio', SimpleNamespace(busy=True)), ('audio_dialog', SimpleNamespace(job=True))]:
                    previous = getattr(app, field)
                    try:
                        setattr(app, field, value)
                        self.assertFalse(app.remove_library(path))
                        self.assertFalse(app.set_library_name(path, '不应保存'))
                    finally:setattr(app, field, previous)
                self.assertEqual(app.preferences, original)
                self.assertIn(path, [entry for _, entry in app.library_buttons])


if __name__ == '__main__':unittest.main()
