"""Focused checks for portrait seeking, transparent values and button states."""
from pathlib import Path
import tempfile
from types import SimpleNamespace
import tkinter as tk
import unittest

from nte_music_desk import cli
from nte_music_desk.controls import CharacterProgress, GlassEntry, NumberStepper
from nte_music_desk.paths import asset_dir
from nte_music_desk.ui import App


class GlassControlChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = tk.Tk(); self.root.withdraw()
        self.app = App(self.root, SimpleNamespace(ROOT=Path(self.directory.name), ASSETS=asset_dir(),
                                                  key_schedule=cli.key_schedule))
        self.addCleanup(self.app.close)
        self.errors = []
        self.root.report_callback_exception = lambda kind, error, trace: self.errors.append(str(error))
        self.root.deiconify(); self.root.update()

    def test_main_portrait_progress_seeks_and_keeps_background_during_updates(self):
        app, bar = self.app, self.app.progress_bar
        app.show_page('performance'); self.root.update(); app.backdrop.refresh()
        self.assertIsInstance(bar, CharacterProgress)
        self.assertIsInstance(app.mini.progress, CharacterProgress)
        self.assertEqual(len(bar.find_withtag('portrait')), 1)
        background = bar.find_withtag('workspace-background')
        self.assertEqual(len(background), 1)
        for percent in (100, 0, 50):
            app.progress.set(percent)
            self.assertEqual(bar.fraction, percent / 100)
            self.assertEqual(bar.find_withtag('workspace-background'), background)
            self.assertEqual(len(bar.find_withtag('portrait')), 1)
        self.assertEqual(bar.fraction_at(bar.inset), 0)
        self.assertEqual(bar.fraction_at(bar.winfo_width() - bar.inset), 1)
        app.begin_seek(SimpleNamespace(widget=bar, x=bar.inset))
        app.end_seek(SimpleNamespace(widget=bar, x=bar.winfo_width() / 2))
        self.assertAlmostEqual(app.playback_offset(), app.ready_duration / 2, places=3)
        self.assertIsNone(app.active)
        self.assertFalse(self.errors)

    def test_numeric_value_is_transparent_at_rest_and_native_while_editing(self):
        app = self.app
        app.show_page('adjustments'); self.root.update(); app.backdrop.refresh()
        field = app.speed_entry
        self.assertIsInstance(field, GlassEntry)
        background = field.find_withtag('workspace-background')
        self.assertEqual(len(background), 1)
        self.assertFalse(field.editor.winfo_manager())
        field.begin(); self.root.update_idletasks()
        self.assertEqual(field.editor.winfo_class(), 'Entry')
        self.assertTrue(field.editor.winfo_ismapped())
        field.delete(0, 'end'); field.insert(0, '1.25')
        field.finish(SimpleNamespace(keysym='Return'))
        self.assertEqual(app.speed.get(), '1.25')
        self.assertFalse(field.editor.winfo_manager())
        self.assertEqual(field.find_withtag('workspace-background'), background)
        self.assertEqual(field.itemcget(field.find_withtag('value')[0], 'text'), '1.25')
        field.begin(); field.delete(0, 'end'); field.insert(0, '1.75'); field.cancel()
        self.assertEqual(app.speed.get(), '1.25')
        field.configure(state='disabled'); field.begin()
        self.assertFalse(field.editing)
        stepper = next(widget for widget, _ in app.controls if isinstance(widget, NumberStepper))
        self.assertTrue(stepper.entry.editor.bind('<Up>'))
        self.assertTrue(stepper.entry.editor.bind('<Down>'))
        self.assertFalse(self.errors)

    def test_secondary_button_retains_shape_after_disable_and_reenable(self):
        button = self.app.preview_button
        # The mapped test window may already be under the user's pointer.
        # Start in a defined state before testing the hover transition.
        button._enter(False)
        button._press(False)
        button.configure(state='disabled')
        button.invoke()
        self.assertIsNone(self.app.preview_token)
        button.configure(state='normal')
        self.assertGreater(button._skin.width(), 24)
        self.assertGreater(button._skin.height(), 24)
        normal = str(button._skin)
        button._enter(True)
        self.assertNotEqual(str(button._skin), normal)
        hovered = str(button._skin)
        button._press(True)
        self.assertNotEqual(str(button._skin), hovered)
        before_width = button.winfo_reqwidth()
        button.configure(text='这是一段更长的按钮操作说明')
        self.root.update_idletasks()
        self.assertGreater(button.winfo_reqwidth(), before_width)
        self.assertFalse(self.errors)


class PortraitRenderingChecks(unittest.TestCase):
    def test_portrait_uses_display_pixels_at_common_dpi_without_recreating_on_progress(self):
        import hashlib
        from PIL import ImageTk
        from nte_music_desk.display import pixels
        path = asset_dir() / 'mingyin-icon.webp'
        original = hashlib.sha256(path.read_bytes()).hexdigest()
        root = tk.Tk(); root.withdraw()
        try:
            for factor in (1, 1.25, 1.5, 2):
                with self.subTest(scale=factor):
                    root.tk.call('tk', 'scaling', factor * 96 / 72)
                    bar = CharacterProgress(root, path)
                    try:
                        bar.pack(); root.update_idletasks()
                        self.assertAlmostEqual(bar.avatar.width(), round(32 * factor), delta=1)
                        self.assertEqual(bar.avatar.width(), pixels(root, 32))
                        bitmap = ImageTk.getimage(bar.avatar)
                        self.assertEqual(bitmap.getpixel((0, 0))[3], 0)
                        self.assertEqual(bitmap.getpixel((bitmap.width // 2, bitmap.height // 2))[3], 255)
                        photo = bar.avatar
                        images = set(root.tk.call('image', 'names'))
                        for index in range(81):
                            fraction = index / 80
                            bar.draw(fraction)
                            left, top, right, bottom = bar.bbox('portrait')
                            self.assertGreaterEqual(min(left, top), 0)
                            self.assertLessEqual(right, int(bar.cget('width')))
                            self.assertLessEqual(bottom, int(bar.cget('height')))
                        self.assertIs(bar.avatar, photo)
                        self.assertEqual(set(root.tk.call('image', 'names')), images)
                        self.assertEqual(len(bar.find_withtag('portrait')), 1)
                    finally:
                        bar.destroy()
        finally:
            root.destroy()
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), original)


if __name__ == '__main__':
    unittest.main()
