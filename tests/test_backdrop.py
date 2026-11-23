"""Only the new background's crop, scaling, lifecycle and page integration."""
import hashlib
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops, ImageDraw

from nte_music_desk.appearance import COLORS
from nte_music_desk.backdrop import WorkspaceBackdrop, fit_scene, load_scene


class SceneChecks(unittest.TestCase):
    def test_prepared_scene_loads_without_writing_project_asset(self):
        from nte_music_desk.paths import asset_dir
        path = asset_dir() / 'background-city-cropped.png'
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        scene = load_scene(path)
        self.assertGreater(scene.width, 1400)
        self.assertAlmostEqual(scene.width / scene.height, 16 / 9, delta=.01)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), before)

    def test_wide_and_tall_windows_cover_without_distorting_subject(self):
        scene = Image.new('RGB', (400, 200), 'white')
        ImageDraw.Draw(scene).ellipse((170, 70, 230, 130), fill='blue')
        for size in ((800, 600), (1400, 500), (700, 1000)):
            with self.subTest(size=size):
                image = fit_scene(scene, size)
                self.assertEqual(image.size, size)
                red, _, blue = image.split()
                mask = ImageChops.subtract(blue, red).point(lambda value: 255 if value > 35 else 0)
                bounds = mask.getbbox()
                self.assertIsNotNone(bounds)
                self.assertLessEqual(abs((bounds[2] - bounds[0]) - (bounds[3] - bounds[1])), 2)
                self.assertGreater(min(image.getpixel((0, 0))), 180)


class BackdropWindowChecks(unittest.TestCase):
    def assert_visible_background_pixels(self, root, backdrop, record):
        layer = record['layer']
        left, top = layer.winfo_rootx() - root.winfo_rootx(), layer.winfo_rooty() - root.winfo_rooty()
        width, height = layer.winfo_width(), layer.winfo_height()
        self.assertGreaterEqual(min(left, top), 0)
        self.assertLessEqual(left + width, root.winfo_width())
        self.assertLessEqual(top + height, root.winfo_height())
        for x, y in ((0, 0), (width // 2, height // 2), (width - 1, height - 1)):
            actual = tuple(root.tk.call(str(record['photo']), 'get', x, y))
            expected = backdrop.patch(root, record['color'], (1, 1), (left + x, top + y)).getpixel((0, 0))
            self.assertEqual(actual, expected, 'Visible crops must still sample the fixed window photograph')

    def test_page_content_reappears_on_every_visit_without_scrolling(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.ui import App
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            errors = []
            root.report_callback_exception = lambda kind, error, trace: errors.append(str(error))
            try:
                root.deiconify(); root.update()
                # A first visit alone misses the bug: Tk may leave a Canvas
                # window item unmapped when an unchanged page is packed again.
                for name in ('segments', 'transcription', 'performance', 'segments',
                             'transcription', 'community', 'transcription', 'segments'):
                    app.show_page(name)
                    root.update()
                    if name not in ('segments', 'transcription'):
                        continue
                    canvas = app.segment_page.canvas if name == 'segments' else app.offline_dialog.canvas
                    bodies = [body for body, (host, _) in app.backdrop.scroll_hosts.items() if host is canvas]
                    self.assertEqual(len(bodies), 1)
                    self.assertTrue(canvas.winfo_ismapped())
                    self.assertTrue(bodies[0].winfo_ismapped(), f'{name} content must appear without a scroll')
                    if name == 'segments':
                        self.assertTrue(app.segment_page.timeline.winfo_ismapped())
                    else:
                        self.assertTrue(app.offline_dialog.start_button.winfo_ismapped())
                        self.assertFalse(app.offline_dialog.segment.winfo_ismapped())
                # Showing the body must not simulate a wheel movement or
                # reset the position the user left on either page.
                for name, canvas in (('segments', app.segment_page.canvas),
                                     ('transcription', app.offline_dialog.canvas)):
                    app.show_page(name); root.update()
                    canvas.yview_moveto(.5)
                    position = canvas.yview()
                    self.assertGreater(position[0], 0)
                    app.show_page('performance'); root.update()
                    app.show_page(name); root.update()
                    self.assertEqual(canvas.yview(), position)
                    body = next(body for body, (host, _) in app.backdrop.scroll_hosts.items() if host is canvas)
                    self.assertTrue(body.winfo_ismapped())
                self.assertFalse(errors)
            finally:
                app.close()

    def test_background_follows_resize_scroll_and_pages_without_changing_score(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.ui import App
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            callback_errors = []
            root.report_callback_exception = lambda kind, error, trace: callback_errors.append(str(error))
            try:
                score, native_target = app.build_score(), app.file_drop.hwnd
                root.deiconify(); root.update()
                app.backdrop.refresh()
                self.assertTrue(app.backdrop.enabled)
                self.assertEqual(app.backdrop.bitmap.size, (root.winfo_width(), root.winfo_height()))
                self.assertEqual(len(app.heading_canvas.find_withtag('workspace-background')), 1)
                self.assertEqual(app.heading_canvas.type(app.heading_label.item), 'text')
                for color in (COLORS['bg'], COLORS['paper']):
                    expected = app.backdrop.patch(app.preview_button, color, (30, 20))
                    actual = app.backdrop.patch(app.preview_button, color.lower(), (30, 20))
                    self.assertEqual(expected.tobytes(), actual.tobytes())
                outside = app.preview_button._outer
                rounded = app.backdrop.rounded(app.preview_button, 30, 20, COLORS['paper'], outside, 6)
                self.assertEqual(rounded.getpixel((0, 0)),
                                 app.backdrop.patch(app.preview_button, outside.upper(), (30, 20)).getpixel((0, 0)))
                for size in ('1200x820', '1050x730'):
                    root.geometry(size); root.update()
                    app.backdrop.refresh()
                    self.assertEqual(app.backdrop.bitmap.size, (root.winfo_width(), root.winfo_height()))
                for page in ('segments', 'transcription', 'community', 'adjustments', 'performance'):
                    app.show_page(page); root.update(); app.backdrop.refresh()
                    self.assertEqual(score, app.build_score())
                    self.assertEqual(native_target, app.file_drop.hwnd)
                    selected_index = tuple(app.pages).index(page)
                    for index, (_, line) in enumerate(app.page_tabs):
                        self.assertEqual(app.backdrop.records[line]['color'],
                                         COLORS['teal'] if index == selected_index else COLORS['bg'])
                app.show_page('segments'); root.update(); app.backdrop.refresh()
                canvas = app.segment_page.canvas
                canvas.yview_moveto(1); root.update(); app.backdrop.refresh()
                record = app.backdrop.records[canvas]
                self.assertEqual(record['kind'], 'viewport')
                self.assert_visible_background_pixels(root, app.backdrop, record)
                self.assertFalse(canvas.find_withtag('workspace-background'))
                body = app.segment_page.track_frame.master.master
                layer = app.backdrop.records[body]['layer']
                self.assert_visible_background_pixels(root, app.backdrop, app.backdrop.records[body])
                self.assertLess(app.backdrop.records[body]['photo'].width(), root.winfo_width())
                # Rebuilding native voice controls/shelf can destroy decorative
                # children too; new layers must be registered on the next draw.
                app.instrument.set('钢琴 · Shift 黑键')
                app.update_score(quiet=True); root.update(); app.backdrop.refresh()
                self.assertTrue(app.backdrop.records[app.segment_page.track_frame]['layer'].winfo_exists())
                app.open_path(asset_dir() / 'scores/twinkle.musicxml')
                root.update(); app.backdrop.refresh()
                self.assertTrue(app.backdrop.records[app.shelf_content]['layer'].winfo_exists())
                root.update_idletasks()
                for record in app.backdrop.records.values():
                    if record['kind'] in ('frame', 'viewport') and record['layer'].winfo_ismapped():
                        self.assert_visible_background_pixels(root, app.backdrop, record)
                self.assertEqual(len(set(COLORS.values())), 4)
                self.assertFalse(callback_errors)
            finally:
                app.close()
                self.assertTrue(app.backdrop.closed)

    def test_scroll_updates_panel_textures_without_manual_background_refresh(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.ui import App
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            callback_errors = []
            root.report_callback_exception = lambda kind, error, trace: callback_errors.append(str(error))
            try:
                app.show_page('adjustments'); root.deiconify(); root.update()
                app.backdrop.refresh(); root.update_idletasks()
                canvas, panel = app.body_canvas, app.scale.master
                origin_x, origin_y = panel.winfo_rootx(), panel.winfo_rooty()
                local_y = min(140, panel.winfo_height() // 3)
                global_y = origin_y + local_y
                before = root.tk.call(str(panel._skin), 'get', 30, local_y)
                plane = app.backdrop.planes[COLORS['bg']]
                viewport_photo = app.backdrop.records[canvas]['photo']
                canvas.yview_scroll(2, 'units')
                # Let normal Tk notifications run. Calling backdrop.refresh()
                # here would hide the very bug this regression must detect.
                root.update_idletasks()
                self.assertLess(panel.winfo_rooty(), origin_y)
                shifted_y = global_y - panel.winfo_rooty()
                self.assertLess(shifted_y, panel.winfo_height() - 12)
                after = root.tk.call(str(panel._skin), 'get', origin_x + 30 - panel.winfo_rootx(), shifted_y)
                self.assertEqual(before, after, 'A fixed viewport point must keep the same photograph pixel')
                self.assertIs(app.backdrop.planes[COLORS['bg']], plane)
                self.assertIs(app.backdrop.records[canvas]['photo'], viewport_photo,
                              'Scrolling must not rebuild the stationary viewport texture')
                self.assertFalse(canvas.find_withtag('workspace-background'))
                canvas.yview('moveto', 0)
                root.update_idletasks()
                self.assertEqual(panel.winfo_rooty(), origin_y)
                self.assertEqual(root.tk.call(str(panel._skin), 'get', 30, local_y), before)
                viewport = app.backdrop.records[canvas]['layer']
                self.assert_visible_background_pixels(root, app.backdrop, app.backdrop.records[canvas])
                self.assertFalse(callback_errors)
            finally:
                app.close()

    def test_destroyed_offscreen_decoration_recovers_when_scrolled_back(self):
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.ui import App
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            errors = []
            root.report_callback_exception = lambda kind, error, trace: errors.append(str(error))
            try:
                root.geometry('1000x714+0+0')
                app.show_page('segments'); root.deiconify(); root.update()
                canvas, frame = app.segment_page.canvas, app.segment_page.track_frame
                canvas.yview_moveto(1); root.update()
                layer = app.backdrop.records[frame]['layer']
                canvas.yview_moveto(0); root.update()
                # Generic content rebuilding may remove decorative children.
                # Recovery must work even before this container reenters view.
                layer.destroy()
                app.backdrop.request(); root.update()
                self.assertFalse(errors)
                record = app.backdrop.records.get(frame)
                self.assertTrue(record is None or record['layer'].winfo_exists())
                canvas.yview_moveto(1); root.update()
                record = app.backdrop.records[frame]
                self.assertIsNot(record['layer'], layer)
                self.assertTrue(record['layer'].winfo_ismapped())
                self.assert_visible_background_pixels(root, app.backdrop, record)
                self.assertFalse(errors)
            finally:
                app.close()

    def test_missing_image_keeps_plain_native_interface(self):
        import tkinter as tk
        root = tk.Tk(); root.withdraw()
        try:
            with self.assertLogs('nte_music_desk.backdrop', level='WARNING'):
                backdrop = WorkspaceBackdrop(root, Path('missing-background-file.png'))
            self.assertFalse(backdrop.enabled)
            backdrop.request()
            self.assertIsNone(backdrop.timer)
            backdrop.close()
        finally:
            root.destroy()

    def test_wheel_finishes_repainting_segment_and_transcription_content(self):
        import sys
        if sys.platform != 'win32':
            self.skipTest('Windows native repaint completion')
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.ui import App
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            errors = []
            root.report_callback_exception = lambda kind, error, trace: errors.append(str(error))
            try:
                root.deiconify(); root.update()
                for name in ('segments', 'transcription'):
                    with self.subTest(page=name):
                        app.show_page(name); root.update()
                        canvas = app.segment_page.canvas if name == 'segments' else app.offline_dialog.canvas
                        body = next(body for body, (host, _) in app.backdrop.scroll_hosts.items() if host is canvas)
                        paints = []
                        binding = body.bind('<Expose>', lambda event: paints.append(True), add='+')
                        for delta in (-120, -240, 120, 240):
                            before = len(paints)
                            # Use the real wheel binding, with no update() or
                            # manual background refresh after it returns.
                            canvas.event_generate('<MouseWheel>', delta=delta, when='now')
                            self.assertGreater(len(paints), before)
                            self.assertTrue(body.winfo_ismapped())
                        body.unbind('<Expose>', binding)
                self.assertFalse(errors)
            finally:
                app.close()

    def test_native_scroll_repaints_content_without_windows_composited_buffers(self):
        import sys
        if sys.platform != 'win32':
            self.skipTest('Windows native presentation contract')
        import tkinter as tk
        from nte_music_desk import cli
        from nte_music_desk.paths import asset_dir
        from nte_music_desk.scrolling import SceneScrollCanvas
        from nte_music_desk.ui import App
        with tempfile.TemporaryDirectory() as directory:
            root = tk.Tk(); root.withdraw()
            app = App(root, SimpleNamespace(ROOT=Path(directory), ASSETS=asset_dir(), key_schedule=cli.key_schedule))
            errors = []
            root.report_callback_exception = lambda kind, error, trace: errors.append(str(error))
            try:
                app.show_page('adjustments'); root.deiconify(); root.update()
                app.backdrop.refresh(); root.update_idletasks()
                canvas, editor = app.body_canvas, app.speed_entry.editor
                for host, _ in app.backdrop.scroll_hosts.values():
                    self.assertIsInstance(host, SceneScrollCanvas)
                batch = canvas._paint_batch
                self.assertIsNotNone(batch, 'Windows must use the native scroll frame')
                hwnd = canvas.winfo_id()
                original_style = batch.get_style(hwnd, -20)
                self.assertFalse(editor.winfo_ismapped())
                refresh, redraw = app.backdrop.refresh, batch.redraw
                held, presented, paints = [], [], []
                def content_painted(event):
                    paints.append((batch.get_style(hwnd, -20),
                                   bool(batch.get_style(hwnd, -16) & 0x10000000),
                                   bool(batch.get_style(app.scale.winfo_id(), -16) & 0x10000000)))
                app.scale.bind('<Expose>', content_painted, add='+')

                def sample(*args, **kwargs):
                    if kwargs.get('scroll_canvas') is canvas and canvas._committing_scroll:
                        # The old texture can never be exposed while content
                        # windows are moving or a new patch is being generated.
                        self.assertFalse(batch.get_style(hwnd, -16) & 0x10000000)
                        held.append(canvas.canvasy(0))
                    return refresh(*args, **kwargs)

                def present(*args):
                    self.assertTrue(canvas._committing_scroll)
                    self.assertTrue(batch.get_style(hwnd, -16) & 0x10000000)
                    # Tk paints from its idle queue after WM_PAINT. Windows'
                    # COMPOSITED buffer can be presented before that drawing,
                    # producing black content although textures are correct.
                    self.assertEqual(batch.get_style(hwnd, -20), original_style)
                    self.assertFalse(editor.winfo_ismapped())
                    for widget in app.backdrop.walk(canvas):
                        record = app.backdrop.records.get(widget)
                        if record and record['kind'] in ('frame', 'viewport') and record['layer'].winfo_ismapped():
                            self.assert_visible_background_pixels(root, app.backdrop, record)
                    presented.append(canvas.canvasy(0))
                    return redraw(*args)

                with patch.object(app.backdrop, 'refresh', side_effect=sample), patch.object(batch, 'redraw', side_effect=present):
                    # Wheel API, scrollbar API and direct yview all converge
                    # on the same complete frame, including rapid reversals.
                    for index in range(6):
                        canvas.yview_scroll(2 if index % 2 == 0 else -2, 'units')
                        canvas.yview_moveto(.75 if index % 2 == 0 else 0)
                        canvas.yview('scroll', -1, 'units')
                        self.assertEqual(batch.get_style(hwnd, -20), original_style)
                self.assertEqual(len(presented), 18)
                self.assertGreaterEqual(len(held), len(presented))
                self.assertTrue(paints, 'Content must receive repaint events before the scroll returns')
                self.assertTrue(all(paint == (original_style, True, True) for paint in paints),
                                'Widgets must repaint after their native windows become visible')
                self.assertFalse(errors)
                # A failed frame must release redraw too, and allow recovery.
                with patch.object(canvas, '_scroll_frame', side_effect=ValueError('failed frame')):
                    with self.assertRaisesRegex(ValueError, 'failed frame'):
                        canvas.yview_moveto(0)
                self.assertFalse(canvas._committing_scroll)
                self.assertTrue(batch.get_style(hwnd, -16) & 0x10000000)
                self.assertEqual(batch.get_style(hwnd, -20), original_style)
                canvas.yview_moveto(0)
                self.assertFalse(editor.winfo_ismapped())
                self.assertFalse(app.segment_page.canvas.winfo_ismapped())
            finally:
                app.close()


if __name__ == '__main__':
    unittest.main()
