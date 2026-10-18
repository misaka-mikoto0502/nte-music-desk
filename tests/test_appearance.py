"""Behavior checks for custom desktop surfaces; no pixel-perfect snapshots."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


@unittest.skipUnless(sys.platform == 'win32', 'Windows desktop')
class AppearanceChecks(unittest.TestCase):
    def test_native_button_disable_invoke_and_round_panel_geometry(self):
        import tkinter as tk
        from nte_music_desk.appearance import RoundedPanel, RoundedButton
        root = tk.Tk(); root.withdraw()
        try:
            panel = RoundedPanel(root)
            panel.pack()
            invoked = []
            button = RoundedButton(panel, text='开始', command=lambda: invoked.append(True), font=('Arial', 12), bg='#32634F')
            button.pack()
            root.update_idletasks()
            self.assertIsInstance(button, tk.Button)
            button.invoke()
            button.configure(state='disabled')
            button.invoke()
            self.assertEqual(invoked, [True])
            button.configure(state='normal', text='继续演奏', padx=20)
            button.invoke()
            self.assertEqual(len(invoked), 2)
            self.assertEqual(panel.surface.place_info()['bordermode'], 'outside')
        finally:
            root.destroy()

    def test_background_preference_and_long_title_do_not_change_arrangement(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            try:
                score = app.build_score()
                app.background_opacity.set(0)
                app.set_background_strength()
                self.assertEqual(app.artwork.opacity, 0)
                stored = json.loads((Path(directory)/'midi_ui_settings.json').read_text(encoding='utf-8'))
                self.assertEqual(stored['background_strength'], 0)
                self.assertEqual(score, app.build_score())
                app.title.set('一首很长的曲目标题' * 30)
                displayed = app.artwork.itemcget(app.heading_label.item, 'text')
                self.assertTrue(displayed.endswith('…'))
                self.assertLess(len(displayed), len(app.title.get()))
                root.update_idletasks()
            finally:
                app.close()
