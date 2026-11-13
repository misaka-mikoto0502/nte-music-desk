"""Behavior checks for custom desktop surfaces; no pixel-perfect snapshots."""
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))


@unittest.skipUnless(sys.platform == 'win32', 'Windows desktop')
class AppearanceChecks(unittest.TestCase):
    def test_density_adaptation_statistics_and_full_key_table_share_the_performance(self):
        import tkinter as tk
        from tkinter import ttk
        from nte_music_desk import cli
        from nte_music_desk.midi import MidiNote, MidiSong, write_midi
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.performance import performance_plan
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'dense.mid'
            song = MidiSong('dense', 1, 480,
                [MidiNote(0, 0, 60+i%2, 80, i*.001, .3+i*.001) for i in range(80)],
                ['piano'], [(0, 500000)], .4, [])
            write_midi(song, path); original = path.read_bytes()
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            try:
                app.syncing_settings = True
                app.instrument.set('钢琴 · Shift 黑键'); app.applied_instrument = 'piano'
                app.syncing_settings = False
                self.assertTrue(app.open_path(path))
                score = app.update_score(); plan = performance_plan(score, int(app.hold_ms.get()))
                self.assertGreater(plan.pruned_notes, 0)
                self.assertEqual(app.metric_values[1].cget('text'), f'{len(plan.notes):,}')
                app.show_details()
                def descendants(widget):
                    for child in widget.winfo_children():
                        yield child
                        yield from descendants(child)
                tables = [w for w in descendants(root) if isinstance(w, ttk.Treeview) and w['columns'][0] == 'index']
                self.assertEqual(len(tables), 1)
                rows = tables[0].get_children()
                self.assertEqual(len(rows), len(plan.notes))
                first = tables[0].item(rows[0], 'values')
                self.assertEqual(first[1], f'{plan.notes[0].at:.3f}')
                self.assertEqual(first[4], f'{plan.notes[0].duration:.3f}')
                self.assertEqual(path.read_bytes(), original)
            finally:
                app.close()

    def test_readonly_selection_clears_without_breaking_editable_fields_or_bindings(self):
        import tkinter as tk
        from tkinter import ttk
        from nte_music_desk.appearance import style_comboboxes
        root = tk.Tk(); root.withdraw()
        try:
            style_comboboxes(root)
            binding = root.bind_class('TCombobox', '<<ComboboxSelected>>')
            style_comboboxes(root)
            self.assertEqual(binding, root.bind_class('TCombobox', '<<ComboboxSelected>>'))
            readonly = ttk.Combobox(root, state='readonly', values=('钢琴', '吉他'))
            editable = ttk.Combobox(root, values=('可编辑',)); editable.set('可编辑')
            entry = ttk.Entry(root); entry.insert(0, '重命名')
            for widget in (readonly, editable, entry):
                widget.pack(); widget.configure(exportselection=False)
            readonly.current(1)
            for sequence in ('<<ComboboxSelected>>', '<FocusIn>', '<FocusOut>'):
                for widget in (readonly, editable, entry): widget.selection_range(0, 'end')
                readonly.event_generate(sequence)
                editable.event_generate(sequence)
                root.update_idletasks()
                self.assertFalse(readonly.selection_present())
                self.assertTrue(editable.selection_present())
                self.assertTrue(entry.selection_present())
                self.assertEqual(readonly.get(), '吉他')
            self.assertIn('ttk::combobox::Post', root.bind_class('TCombobox', '<Down>'))
            tree = ttk.Treeview(root); row = tree.insert('', 'end', text='当前曲目')
            tree.selection_set(row)
            readonly.event_generate('<<ComboboxSelected>>'); root.update_idletasks()
            self.assertEqual(tree.selection(), (row,))
            # Deferred selection cleanup is safe when a dialog closes first.
            readonly.event_generate('<<ComboboxSelected>>'); readonly.destroy()
            root.update_idletasks()
        finally:
            root.destroy()

    def test_numeric_controls_respect_bounds_and_disabled_state(self):
        import tkinter as tk
        from nte_music_desk.controls import NumberStepper, CharacterSpeedScale
        from nte_music_desk.paths import asset_dir
        root = tk.Tk()
        root.withdraw()
        try:
            number = tk.StringVar(value='35')
            stepper = NumberStepper(root, number, -36, 36)
            stepper.plus.invoke()
            stepper.plus.invoke()
            self.assertEqual(number.get(), '36')
            stepper.configure(state='disabled')
            stepper.minus.invoke()
            self.assertEqual(number.get(), '36')
            stepper.configure(state='normal')
            stepper.minus.invoke()
            self.assertEqual(number.get(), '35')
            speed, changes = tk.DoubleVar(value=1), []
            scale = CharacterSpeedScale(root, speed, changes.append, asset_dir() / 'mingyin-icon.webp')
            scale.set_value(3)
            self.assertEqual(speed.get(), 2)
            scale.set_value(.1)
            self.assertEqual(speed.get(), .25)
            scale.configure(state='disabled')
            scale.set_value(1)
            self.assertEqual(speed.get(), .25)
            speed.set(1.5)
            self.assertEqual(changes, [2, .25])
            self.assertEqual(scale.value(), 1.5)
        finally:
            root.destroy()

    def test_unified_import_and_source_comparison_follow_progress(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            try:
                source = asset_dir() / 'scores/twinkle.musicxml'
                with patch('nte_music_desk.ui.filedialog.askopenfilename', return_value=str(source)):
                    app.import_button.invoke()
                self.assertEqual(app.current_path, source.resolve())
                self.assertEqual(app.file_drop.hwnd, app.import_button.winfo_id())
                audio = Path(directory) / 'local.wav'
                audio.write_bytes(b'local routing fixture')
                with patch.object(app, 'open_offline_audio') as open_audio:
                    with patch('nte_music_desk.ui.filedialog.askopenfilename', return_value=str(audio)):
                        app.import_button.invoke()
                    open_audio.assert_called_once_with(audio)
                app.speed.set('1.25')
                app.transpose.set('2')
                app.update_score()
                app.seek_fraction(.4)
                origin, speed, _ = app.position_frame()
                raw_position = origin + app.playback_offset() * speed
                with patch.object(app, 'start_preview') as preview:
                    app.source_preview_button.invoke()
                    options = preview.call_args.kwargs['options']
                    self.assertAlmostEqual(options['start'], raw_position)
                    self.assertEqual((options['speed'], options['transpose'], options['end']), (1.25, 2, None))
                    self.assertIs(preview.call_args.kwargs['source'], app.song)
                app.preview_token = 'preview-fixture'
                app.refresh_controls()
                self.assertEqual(str(app.import_button.cget('state')), 'disabled')
                with patch('nte_music_desk.ui.filedialog.askopenfilename') as choose:
                    app.import_button.invoke()
                    choose.assert_not_called()
            finally:
                app.preview_token = None
                app.close()

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
            button.configure(min_width=180, min_height=48)
            root.update_idletasks()
            size = (button.winfo_reqwidth(), button.winfo_reqheight())
            button.configure(text='暂停')
            root.update_idletasks()
            self.assertEqual(size, (button.winfo_reqwidth(), button.winfo_reqheight()))
        finally:
            root.destroy()

    def test_combobox_skin_keeps_native_values_and_images_across_reconfiguration(self):
        import gc
        import tkinter as tk
        from tkinter import ttk
        from nte_music_desk.appearance import style_comboboxes
        root = tk.Tk()
        root.withdraw()
        try:
            style = ttk.Style(root)
            style.theme_use('clam')
            style_comboboxes(root)
            value = tk.StringVar(value='钢琴')
            box = ttk.Combobox(root, textvariable=value, values=('钢琴', '吉他'), state='readonly')
            box.pack()
            box.current(1)
            self.assertEqual(value.get(), '吉他')
            box.configure(values=('均衡', '旋律', '和弦'))
            box.current(2)
            self.assertEqual(value.get(), '和弦')
            box.configure(state='disabled')
            self.assertTrue(box.instate(['disabled']))
            style_comboboxes(root)
            gc.collect()
            root.update_idletasks()
            self.assertEqual(style.layout('TCombobox')[0][0], 'Desk.Combobox.field')
            for image in root._desk_combobox_images.values():
                self.assertEqual(root.tk.call('image', 'type', str(image)), 'photo')
        finally:
            root.destroy()

    def test_four_color_workspace_and_long_title_do_not_change_arrangement(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.appearance import COLORS
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / 'midi_ui_settings.json').write_text('{"background_strength":0.52,"show_adjustments":true}', encoding='utf-8')
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            try:
                score = app.build_score()
                self.assertEqual(len(set(COLORS.values())), 4)
                self.assertFalse(app.adjustments_visible)
                self.assertTrue(all(app.heading_canvas.type(item) == 'text' for item in app.heading_canvas.find_all()))
                self.assertEqual(score, app.build_score())
                app.title.set('一首很长的曲目标题' * 30)
                displayed = app.heading_canvas.itemcget(app.heading_label.item, 'text')
                self.assertTrue(displayed.endswith('…'))
                self.assertLess(len(displayed), len(app.title.get()))
                root.update_idletasks()
            finally:
                app.close()

    def test_guidance_and_disclosure_survive_restart_without_changing_the_score(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        with tempfile.TemporaryDirectory() as directory:
            engine = SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule)
            root = tk.Tk()
            root.withdraw()
            app = App(root, engine)
            try:
                score = app.build_score()
                self.assertFalse(app.adjustments_visible)
                app.toggle_adjustments()
                app.toggle_advanced()
                app.toggle_notes()
                app.show_quick_start()
                root.update_idletasks()
                self.assertIsNone(app.active)
                self.assertEqual(score, app.build_score())
                self.assertEqual(app.adjustments_page.winfo_manager(), 'pack')
                self.assertEqual(app.performance_page.winfo_manager(), '')
                self.assertTrue(app.load_demo())
                self.assertEqual(app.playback_offset(), 0)
                self.assertIsNone(app.active)
            finally:
                app.close()
            root = tk.Tk()
            root.withdraw()
            app = App(root, engine)
            try:
                self.assertTrue(app.adjustments_visible)
                self.assertEqual(app.adjustments_page.winfo_manager(), 'pack')
                self.assertIsNone(app.active)
            finally:
                app.close()

    def test_transport_shows_only_actions_for_the_current_task(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.ui import App
        from nte_music_desk.paths import asset_dir
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk()
            root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            try:
                root.update_idletasks()
                actions = app.play_button.master
                initial_size = (actions.winfo_reqwidth(), actions.winfo_reqheight())
                self.assertEqual(app.preview_button.winfo_manager(), 'grid')
                self.assertEqual(app.stop_button.winfo_manager(), '')
                self.assertEqual(app.pause_button.winfo_manager(), '')
                app.preview_token = 'preview-fixture'
                app.refresh_controls()
                self.assertEqual(app.preview_button.winfo_manager(), '')
                self.assertEqual(app.stop_button.cget('text'), '停止试听')
                app.preview_token = None
                app.active = {'phase': 'countdown'}
                app.refresh_controls()
                self.assertEqual(app.play_button.winfo_manager(), '')
                self.assertEqual(app.pause_button.winfo_manager(), '')
                self.assertEqual(app.stop_button.winfo_manager(), 'grid')
                app.active['phase'] = 'playing'
                app.refresh_controls()
                self.assertEqual(app.pause_button.winfo_manager(), 'grid')
                app.active = None
                app.refresh_controls()
                self.assertEqual(app.play_button.winfo_manager(), 'grid')
                self.assertEqual(app.stop_button.winfo_manager(), '')
                root.update_idletasks()
                self.assertEqual(initial_size, (actions.winfo_reqwidth(), actions.winfo_reqheight()))
            finally:
                app.preview_token = None
                app.active = None
                app.close()
