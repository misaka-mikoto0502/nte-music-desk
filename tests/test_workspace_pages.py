"""Integrated page state, reusable projects and delayed community responses."""
from copy import deepcopy
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import tkinter as tk

from nte_music_desk import cli
from nte_music_desk.analysis import recommend_transpositions
from nte_music_desk.arrangement import compile_arrangement
from nte_music_desk.community import project_document, read_project
from nte_music_desk.instruments import INSTRUMENTS
from nte_music_desk.paths import asset_dir
from nte_music_desk.performance import performance_plan
from nte_music_desk.ui import App


class WorkspacePageChecks(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = App(self.root, SimpleNamespace(ROOT=Path(self.folder.name), ASSETS=asset_dir(),
                                                  key_schedule=cli.key_schedule))
        self.addCleanup(self.app.close)
        self.app.open_path(asset_dir() / 'scores/twinkle.mid')

    def test_wheel_over_closed_selectors_scrolls_without_changing_values(self):
        from tkinter import ttk
        app, page = self.app, self.app.segment_page
        app.show_page('segments')
        self.root.deiconify(); self.root.update()
        choices = [widget for widget, _ in page.buttons if isinstance(widget, ttk.Combobox)]
        self.assertEqual(len(choices), 2)
        selected, errors = [], []
        self.root.report_callback_exception = lambda kind, error, trace: errors.append(str(error))
        for choice in choices:
            choice.bind('<<ComboboxSelected>>', lambda event: selected.append(event.widget), add='+')
            original = choice.get()
            for sequence in ('<MouseWheel>', '<Shift-MouseWheel>'):
                for delta in (-120, 120):
                    with self.subTest(choice=str(choice), sequence=sequence, delta=delta):
                        page.canvas.yview_moveto(.2); self.root.update()
                        before = page.canvas.yview()
                        choice.event_generate(sequence, delta=delta, when='now')
                        self.root.update()
                        self.assertEqual(choice.get(), original)
                        self.assertNotEqual(page.canvas.yview(), before)
        self.assertFalse(selected)
        # A selector in a separate dialog must not scroll the page behind it.
        dialog = tk.Toplevel(self.root)
        try:
            choice = ttk.Combobox(dialog, values=('A', 'B'), state='readonly')
            choice.current(0); choice.pack(); self.root.update()
            before = page.canvas.yview()
            choice.event_generate('<MouseWheel>', delta=-120, when='now')
            self.root.update()
            self.assertEqual(choice.get(), 'A')
            self.assertEqual(page.canvas.yview(), before)
        finally:
            dialog.destroy()
        self.assertFalse(errors)

    def test_segment_draft_survives_page_switch_and_undo_redo_after_instrument_change(self):
        app, page = self.app, self.app.segment_page
        app.show_page('segments')
        page.set_range(1, 4)
        page.transpose.set('2')
        page.apply()
        self.assertEqual(app.segment_edits[0]['transpose'], 2)
        page.tree.selection_set('0')
        self.root.update()
        page.transpose.set('5')
        page.set_range(1.5, 3)
        for name in ('performance', 'transcription', 'community', 'segments'):
            app.show_page(name)
            self.root.update()
        self.assertEqual(page.transpose.get(), '5')
        self.assertEqual(page.range(), (1.5, 3))
        before = deepcopy(app.segment_edits)
        page.apply()
        self.assertEqual(len(app.segment_edits), 3)
        page.undo()
        self.assertEqual(app.segment_edits, before)
        page.redo()
        self.assertEqual(len(app.segment_edits), 3)
        page.instrument.set(INSTRUMENTS['piano'].title)
        page.instrument_changed()
        self.assertFalse(page.history)
        page.set_range(1.5, 3)
        page.transpose.set('5')
        page.apply()
        self.assertEqual(app.current_instrument().id, 'piano')
        self.assertEqual(len(page.history), 1)
        page.undo()
        self.assertFalse(app.segment_edits)
        page.redo()
        self.assertEqual(app.segment_edits[0]['transpose'], 5)

    def test_drag_preserves_note_items_and_zoom_or_applied_regions_refresh_them(self):
        page = self.app.segment_page
        self.app.show_page('segments')
        self.root.deiconify(); self.root.update()
        original = page.timeline.find_withtag('source-note')
        self.assertTrue(original)
        onsets = page.onsets
        images = set(self.root.tk.call('image', 'names'))
        item_count = len(page.timeline.find_all())
        for index in range(80):
            start = 1 + index * .02
            page.set_range(start, start + 3)
            page.cursor = start + 1
            page.draw()
            self.assertEqual(page.timeline.find_withtag('source-note'), original)
            self.assertIs(page.onsets, onsets)
        self.assertEqual(set(self.root.tk.call('image', 'names')), images)
        self.assertEqual(len(page.timeline.find_all()), item_count)
        page.zoom()
        self.assertNotEqual(page.timeline.find_withtag('source-note'), original)
        before_edit = page.timeline.find_withtag('source-note')
        page.transpose.set('2'); page.apply()
        self.assertNotEqual(page.timeline.find_withtag('source-note'), before_edit)
        self.assertTrue(page.timeline.find_withtag('edited-note'))

    def test_save_reuses_only_the_successfully_validated_update_inputs(self):
        app = self.app
        with patch('nte_music_desk.arrangement.compile_arrangement', wraps=compile_arrangement) as compile_score:
            self.assertIsNotNone(app.update_score(quiet=True))
            self.assertEqual(compile_score.call_count, 1)
            app.save_arrangement()
            self.assertEqual(compile_score.call_count, 2, 'Standalone saves retain full validation')
            verified = (app.song_fingerprint, app.applied_instrument, deepcopy(app.arrangement_settings()))
            app.transpose.set('1')
            app.save_arrangement(validated=verified)
            self.assertEqual(compile_score.call_count, 3, 'Changed settings cannot reuse previous validation')
            path = app.preset_store.path(app.song_fingerprint, app.applied_instrument)
            before = path.read_bytes()
            app.transpose.set('invalid')
            app.save_arrangement(validated=verified)
            self.assertEqual(path.read_bytes(), before)

    def test_dense_overview_keeps_all_repeating_pitch_lanes(self):
        from PIL import ImageTk
        from nte_music_desk.midi import MidiNote, MidiSong, write_midi
        song = MidiSong('repeating pitches', 1, 480,
                        [MidiNote(0, 0, 60 + i % 12, 90, i * .1, i * .1 + .08) for i in range(2400)],
                        ['voice'], [(0, 500000)], 240, [])
        path = Path(self.folder.name) / 'dense.mid'
        write_midi(song, path)
        self.assertTrue(self.app.open_path(path))
        self.app.show_page('segments'); self.root.deiconify(); self.root.update()
        image = ImageTk.getimage(self.app.segment_page._note_layers['unmodified-note'])
        alpha = image.getchannel('A')
        occupied = [bool(alpha.crop((0, y, image.width, y + 1)).getbbox()) for y in range(image.height)]
        bands = sum(value and not previous for previous, value in zip([False, *occupied], occupied))
        self.assertEqual(bands, 12, 'Overview sampling must not discard periodic pitch lanes')

    def test_scroll_does_not_request_drawing_for_controls_outside_the_viewport(self):
        page = self.app.segment_page
        self.app.show_page('segments')
        self.root.deiconify(); self.root.update()
        tree = page.tree
        self.assertGreater(tree.winfo_rooty(), page.canvas.winfo_rooty() + page.canvas.winfo_height())
        paints = []
        tree.bind('<Expose>', lambda event: paints.append(True), add='+')
        page.canvas.yview_scroll(1, 'units')
        self.assertFalse(paints)
        page.canvas.yview_moveto(1)
        self.assertTrue(paints, 'Newly visible controls still need the complete paint notification')

    def test_applied_notes_change_color_and_undo_restores_original_marks(self):
        from PIL import ImageTk
        from nte_music_desk.segment_ui import EDITED_COLOR
        from nte_music_desk.appearance import COLORS
        app, page = self.app, self.app.segment_page
        app.show_page('segments')
        self.root.deiconify(); self.root.update()
        self.assertGreaterEqual(int(page.timeline.cget('height')), 170)
        self.assertFalse(page.timeline.find_withtag('edited-note'))
        page.set_range(1, 4)
        page.transpose.set('2')
        with patch.object(app, 'start_game_playback'):
            page.try_in_game(True)
        self.assertFalse(page.timeline.find_withtag('edited-note'), 'A candidate is not an applied edit')
        page.apply()
        edited = page.timeline.find_withtag('edited-note')
        self.assertTrue(edited)
        self.assertTrue(page.timeline.find_withtag('unmodified-note'))
        self.assertTrue(page.timeline.find_withtag('edited-region'))
        image = ImageTk.getimage(page._note_layers['edited-note'])
        colors = {rgba[:3] for _, rgba in image.getcolors() if rgba[3]}
        self.assertEqual(colors, {tuple(int(EDITED_COLOR[i:i + 2], 16) for i in (1, 3, 5))})
        self.assertNotEqual(EDITED_COLOR, COLORS['teal'])
        page.undo()
        self.assertFalse(page.timeline.find_withtag('edited-note'))
        page.redo()
        self.assertTrue(page.timeline.find_withtag('edited-note'))
        app.open_path(asset_dir() / 'scores/twinkle.mid')
        self.assertTrue(page.timeline.find_withtag('edited-note'))

    def test_view_buttons_follow_actual_zoom_and_keep_selection_after_refresh(self):
        from PIL import ImageTk
        from nte_music_desk.appearance import COLORS
        app, page = self.app, self.app.segment_page
        app.show_page('segments'); self.root.deiconify(); self.root.update()
        def selected(mode):
            for key, button in page.view_buttons.items():
                self.assertEqual(button.cget('text').startswith('✓ '), key == mode)
                self.assertEqual(button.cget('bg'), COLORS['teal'] if key == mode else COLORS['bg'])
                self.assertEqual(button.cget('fg'), COLORS['paper'] if key == mode else COLORS['ink'])
            button = page.view_buttons[mode]
            pixel = ImageTk.getimage(button._skin).getpixel((button._skin.width() // 2, button._skin.height() // 2))
            self.assertEqual(pixel[:3], (50, 107, 82))
        selected('full')
        widths = [button.winfo_reqwidth() for button in page.view_buttons.values()]
        page.set_range(2, 4)
        page.view_buttons['selection'].invoke(); self.root.update()
        selected('selection')
        self.assertLess(page.viewport[1] - page.viewport[0], app.song.seconds)
        app.show_page('adjustments'); app.show_page('segments'); self.root.update()
        selected('selection')
        self.assertEqual([button.winfo_reqwidth() for button in page.view_buttons.values()], widths)
        page.start.set('无效时间')
        before = page.viewport
        page.view_buttons['selection'].invoke()
        self.assertEqual(page.viewport, before)
        selected('selection')
        page.set_range(2, 4)
        page.view_buttons['full'].invoke(); self.root.update()
        self.assertEqual(page.viewport, (0, app.song.seconds))
        selected('full')
        # Zooming an already full-song selection is still the full-song view.
        page.set_range(0, app.song.seconds)
        page.view_buttons['selection'].invoke()
        selected('full')
        page.set_range(2, 4); page.view_buttons['selection'].invoke()
        page.instrument.set(INSTRUMENTS['piano'].title)
        page.instrument_changed(); self.root.update()
        selected('full')
        for button in page.view_buttons.values():
            app.enabled(button, False)
        page.refresh_controls(); self.root.update()
        selected('full')
        app.clear_current_song()
        for button in page.view_buttons.values():
            self.assertEqual(str(button.cget('state')), 'disabled')
            self.assertFalse(button.cget('text').startswith('✓ '))

    def test_endpoint_drags_preserve_cursor_even_when_handles_overlap_it(self):
        app, page = self.app, self.app.segment_page
        app.show_page('segments')
        self.root.deiconify(); self.root.update()
        for edge, endpoint, target, expected in (('start', 2, 1, (1, 4)), ('end', 4, 5, (2, 5))):
            for cursor in (6, endpoint):
                for y in (32, 36, 70):
                    with self.subTest(edge=edge, cursor=cursor, y=y):
                        page.set_range(2, 4)
                        page.cursor = cursor
                        page.draw()
                        page.begin_selection(SimpleNamespace(x=page.x(endpoint), y=y))
                        self.assertEqual(page.cursor, cursor, 'Pressing a boundary must not move the cursor')
                        page.drag_selection(SimpleNamespace(x=page.x((endpoint + target) / 2), y=20))
                        self.assertEqual(page.cursor, cursor, 'Crossing the ruler must keep the captured boundary drag')
                        page.end_selection(SimpleNamespace(x=page.x(target), y=70))
                        self.assertEqual(page.range(), expected)
                        self.assertEqual(page.cursor, cursor)
                        line = page.timeline.find_withtag('cursor-ui')[0]
                        self.assertEqual(page.timeline.coords(line)[0], page.x(cursor))

    def test_timeline_cursor_resize_move_and_saved_region_have_distinct_behaviors(self):
        app, page = self.app, self.app.segment_page
        app.show_page('segments')
        self.root.deiconify(); self.root.update()
        page.set_range(2, 4)
        def event(seconds, y=70):
            return SimpleNamespace(x=page.x(seconds), y=y)
        page.hover(event(2))
        self.assertEqual(page.timeline.cget('cursor'), 'sb_h_double_arrow')
        page.begin_selection(event(2)); page.end_selection(event(1))
        self.assertEqual(page.range(), (1, 4))
        self.assertEqual(page.cursor, 0)
        page.hover(event(6, 10))
        self.assertEqual(page.timeline.cget('cursor'), 'hand2')
        page.begin_selection(event(6, 10)); page.end_selection(event(7, 10))
        self.assertEqual(page.range(), (1, 4))
        self.assertAlmostEqual(page.cursor, 7, places=2)
        page.hover(event(2))
        self.assertEqual(page.timeline.cget('cursor'), 'fleur')
        page.begin_selection(event(2)); page.end_selection(event(5))
        self.assertEqual(page.range(), (4, 7))
        self.assertAlmostEqual(page.cursor, 7, places=2)
        page.hover(event(10))
        self.assertEqual(page.timeline.cget('cursor'), 'crosshair')
        page.begin_selection(event(10)); page.end_selection(event(12))
        self.assertEqual(page.range(), (10, 12))
        self.assertAlmostEqual(page.cursor, 7, places=2)
        page.transpose.set('2'); page.apply()
        page.set_range(0, 1)
        marker = event(11, int(page.timeline.cget('height')) - 8)
        page.hover(marker)
        self.assertEqual(page.timeline.cget('cursor'), 'hand2')
        page.begin_selection(marker)
        self.assertEqual(page.range(), (10, 12))
        page.begin_selection(event(11)); page.end_selection(event(app.song.seconds + 10))
        self.assertEqual(page.range(), (app.song.seconds - 2, app.song.seconds))

    def test_instrument_is_selected_before_region_and_shared_by_both_previews(self):
        app, page = self.app, self.app.segment_page
        app.show_page('segments')
        page.instrument.set(INSTRUMENTS['piano'].title)
        page.instrument_changed()
        self.assertEqual(app.current_instrument().id, 'piano')
        self.assertEqual(str(page.instrument_box.cget('textvariable')), str(app.instrument))
        page.set_range(1, 4)
        page.transpose.set('12')
        with patch.object(app, 'start_game_playback') as preview:
            page.try_in_game(False)
            page.try_in_game(True)
        self.assertEqual(preview.call_count, 2)
        scores = [call.kwargs['score'] for call in preview.call_args_list]
        self.assertEqual([score['instrument'] for score in scores], ['piano', 'piano'])
        self.assertFalse(app.segment_edits)
        page.apply()
        self.assertEqual(app.segment_edits[0]['transpose'], 12)
        page.instrument.set(INSTRUMENTS['guitar'].title)
        page.instrument_changed()
        self.assertFalse(app.segment_edits)
        page.instrument.set(INSTRUMENTS['piano'].title)
        page.instrument_changed()
        self.assertEqual(app.segment_edits[0]['transpose'], 12)

    def test_instrument_switch_after_selecting_any_mode_keeps_offscreen_background_alive(self):
        from nte_music_desk.ui import MODES
        app, page = self.app, self.app.segment_page
        errors = []
        self.root.report_callback_exception = lambda kind, error, trace: errors.append(str(error))
        self.root.geometry('1000x714+0+0')
        app.show_page('segments'); self.root.deiconify(); self.root.update()
        # The user visits the editor first, then scrolls back to the instrument.
        page.canvas.yview_moveto(1); self.root.update()
        layer = app.backdrop.records[page.track_frame]['layer']
        for mode in MODES.values():
            for instrument in ('piano', 'guitar'):
                with self.subTest(mode=mode, instrument=instrument):
                    page.mode.set(mode)
                    page.canvas.yview_moveto(0); self.root.update()
                    self.assertGreaterEqual(page.track_frame.winfo_rooty(),
                                            page.canvas.winfo_rooty() + page.canvas.winfo_height())
                    page.instrument.set(INSTRUMENTS[instrument].title)
                    page.instrument_box.event_generate('<<ComboboxSelected>>', when='now')
                    self.root.update()
                    self.assertFalse(errors)
                    self.assertTrue(layer.winfo_exists(), 'Voice refresh must preserve its background')
                    self.assertEqual(app.score['instrument'], instrument)
                    page.set_range(1, 4)
                    with patch.object(app, 'start_game_playback') as preview:
                        page.try_in_game(False); page.try_in_game(True)
                    self.assertEqual(preview.call_count, 2)
                    self.assertEqual([call.kwargs['score']['instrument'] for call in preview.call_args_list],
                                     [instrument, instrument])
                    page.canvas.yview_moveto(1); self.root.update()
                    self.assertTrue(app.backdrop.records[page.track_frame]['layer'].winfo_ismapped())

    def test_global_recommendation_respects_fixed_segment_overrides(self):
        settings = self.app.arrangement_settings()
        settings['segments'] = [dict(start=0, end=self.app.song.seconds, mode='faithful',
                                    transpose=12, tracks=settings['tracks'], name='全曲覆盖')]
        options = {k: v for k, v in settings.items() if k != 'countdown'}
        candidates = recommend_transpositions(self.app.song, instrument='piano', **options)
        self.assertEqual(len(candidates), 3)
        self.assertEqual(candidates[0]['transpose'], settings['transpose'])
        self.assertEqual(len({c['cost'] for c in candidates}), 1)

    def demo_community(self):
        from nte_music_desk.community_ui import CommunityDemoPage
        self.app.community_page.close()
        for widget in self.app.pages['community'].winfo_children():
            widget.destroy()
        page = self.app.community_page = CommunityDemoPage(self.app, self.app.pages['community'])
        page.on_song_changed()
        page.refresh_controls()
        return page

    def test_community_is_a_planned_placeholder_without_demo_controls_or_requests(self):
        from tkinter import ttk
        app = self.app
        def descendants(widget):
            for child in widget.winfo_children():
                yield child
                yield from descendants(child)
        with patch('nte_music_desk.community_ui.CommunityDemo') as service, \
             patch('nte_music_desk.community_ui.request_json') as request:
            for name in ('community', 'segments', 'performance', 'community'):
                app.show_page(name)
                self.root.deiconify(); self.root.update()
            widgets = list(descendants(app.pages['community']))
            self.assertTrue(any(isinstance(widget, tk.Label) and widget.cget('text') == '计划实现'
                                for widget in widgets))
            self.assertFalse(any(isinstance(widget, (tk.Button, tk.Checkbutton, ttk.Entry, ttk.Treeview))
                                 for widget in widgets))
            self.assertFalse(hasattr(app.community_page, 'poll_id'))
            self.assertTrue(app.open_path(asset_dir() / 'scores/twinkle.musicxml'))
            from nte_music_desk.community import write_project
            path = Path(self.folder.name) / '已有工程.nteproject'
            write_project(path, project_document(app.song, app.arrangement_settings(), app.current_instrument().id,
                                                 title='已有工程', author='本地作者'))
            self.assertTrue(app.import_local_file(path))
            self.assertEqual(app.current_path, path)
            app.show_page('community'); self.root.update()
            service.assert_not_called()
            request.assert_not_called()

    def test_export_import_reproduces_plan_and_delayed_download_preserves_current_song(self):
        app, page = self.app, self.demo_community()
        app.show_page('segments')
        app.segment_page.set_range(1, 4)
        app.segment_page.transpose.set('7')
        app.segment_page.apply()
        expected = performance_plan(app.build_score()).key_events
        path = Path(self.folder.name) / '分享.nteproject'
        with patch('nte_music_desk.community_ui.filedialog.asksaveasfilename', return_value=str(path)):
            page.export_file()
        document = read_project(path)
        self.assertEqual(document['settings']['segments'][0]['transpose'], 7)
        app.segment_edits = []
        page.load_document(document, origin='a' * 64)
        self.assertEqual(performance_plan(app.build_score()).key_events, expected)
        self.assertEqual(read_project(app.current_path)['parent'], 'a' * 64)
        app.open_path(asset_dir() / 'scores/twinkle.mid')
        original_path, revision = app.current_path, app.song_revision
        page.download_revision = revision - 1
        page.pending = True
        page.messages.put(('download', {'project': document, 'id': 'b' * 64}, None))
        self.root.after_cancel(page.poll_id)
        page.poll()
        self.assertEqual(app.current_path, original_path)
        self.assertIn('当前曲目继续保留', page.status.get())
        self.assertTrue(any('shared-projects' in item['path'] for item in app.preferences['shelf_files']))

    def test_malformed_remote_list_leaves_page_usable(self):
        page = self.demo_community()
        for project in ({'id': 'a' * 64, 'title': []}, {'id': 123}, {'id': 'z' * 64}):
            page.pending = True
            page.messages.put(('list', {'projects': [project]}, None))
            self.root.after_cancel(page.poll_id)
            page.poll()
            self.assertEqual(page.status.get(), '社区列表格式无效。')
            self.assertFalse(page.pending)
            self.assertEqual(str(page.address.cget('state')), 'normal')

    def test_background_download_does_not_interrupt_audition_or_replace_publish_draft(self):
        app, page = self.app, self.demo_community()
        page.title.set('当前曲目的分享草稿')
        page.author.set('作者')
        document = page.document()
        for mode in ('synthesis', 'comparison', 'left-page'):
            with self.subTest(mode=mode):
                app.show_page('community')
                current = app.current_path
                page.title.set('尚未提交的标题')
                page.description.set('尚未提交的说明')
                app.preview_token = 'playing' if mode == 'synthesis' else None
                app.audio_audition = SimpleNamespace(closed=False, close=lambda: None) if mode == 'comparison' else None
                if mode == 'left-page':
                    app.show_page('performance')
                page.download_revision = app.song_revision
                page.pending = True
                page.messages.put(('download', {'project': document, 'id': 'c' * 64}, None))
                self.root.after_cancel(page.poll_id)
                page.poll()
                self.assertEqual(app.current_path, current)
                self.assertEqual(page.title.get(), '尚未提交的标题')
                self.assertEqual(page.description.get(), '尚未提交的说明')
                if mode == 'synthesis':
                    self.assertEqual(app.preview_token, 'playing')
                app.preview_token = None
                app.audio_audition = None

    def test_changing_song_clears_previous_publish_description(self):
        page = self.demo_community()
        page.description.set('只属于上一首曲目的说明')
        self.app.open_path(asset_dir() / 'scores/twinkle.musicxml')
        self.assertEqual(page.description.get(), '')

    def test_double_click_during_pending_download_cannot_rebind_its_song_revision(self):
        app, page = self.app, self.demo_community()
        app.show_page('community')
        page.author.set('作者')
        document = page.document()
        page.projects = [dict(id='d' * 64)]
        page.tree.insert('', 'end', iid='0')
        page.tree.selection_set('0')
        page.download_revision = app.song_revision
        page.pending = True
        app.open_path(asset_dir() / 'scores/twinkle.musicxml')
        current = app.current_path
        # Tree double-click remains available while the download button is
        # disabled. It must not overwrite the in-flight request's revision.
        page.download()
        page.messages.put(('download', {'project': document, 'id': 'd' * 64}, None))
        self.root.after_cancel(page.poll_id)
        page.poll()
        self.assertEqual(app.current_path, current)
        self.assertIn('当前曲目继续保留', page.status.get())

    def test_playback_footer_only_occupies_space_on_performance_page(self):
        app = self.app
        app.show_page('performance')
        self.root.deiconify()
        self.root.update()
        original_height = app.performance_page.winfo_height()
        footer_height = app.playback_footer.winfo_height()
        original_controls = tuple(app.playback_footer.winfo_children())
        self.assertGreater(footer_height, 100, (self.root.geometry(), app.playback_footer.pack_info(),
                                                [str(w) for w in app.workspace.master.pack_slaves()]))
        for name in ('adjustments', 'segments', 'transcription', 'community'):
            with self.subTest(page=name):
                app.show_page(name)
                self.root.update_idletasks()
                self.assertFalse(app.playback_footer.winfo_ismapped())
                self.assertGreaterEqual(app.pages[name].winfo_height(), original_height + footer_height)
                self.assertEqual(tuple(app.playback_footer.winfo_children()), original_controls)
                app.show_page('performance')
                self.root.update_idletasks()
                self.assertTrue(app.playback_footer.winfo_ismapped())
                self.assertEqual(app.performance_page.winfo_height(), original_height)
                self.assertGreaterEqual(app.playback_footer.winfo_rooty(),
                                        app.performance_page.winfo_rooty() + original_height)

    def test_primary_segment_actions_stay_visible_at_top_and_bottom(self):
        app, page = self.app, self.app.segment_page
        app.show_page('segments')
        self.root.deiconify()
        self.root.update_idletasks()
        action = next(control for control, _ in page.buttons
                      if hasattr(control, 'cget') and control.winfo_class() == 'Button'
                      and control.cget('text') == '应用到这段')
        for position in (0, 1):
            page.canvas.yview_moveto(position)
            self.root.update_idletasks()
            self.assertGreaterEqual(action.winfo_rooty(), app.pages['segments'].winfo_rooty())
            self.assertLessEqual(action.winfo_rooty() + action.winfo_height(),
                                 app.pages['segments'].winfo_rooty() + app.pages['segments'].winfo_height())
            trials = [button for button, _ in page.buttons if button.winfo_class() == 'Button'
                      and button.cget('text').startswith('游戏试奏')]
            self.assertEqual(len(trials), 2)
            row = [*trials, page.trial_stop_button, action]
            for left, right in zip(row, row[1:]):
                self.assertLessEqual(left.winfo_rootx() + left.winfo_width(), right.winfo_rootx())


if __name__ == '__main__':
    unittest.main()
