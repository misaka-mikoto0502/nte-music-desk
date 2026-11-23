"""Commit a native scroll and its scene textures as one Windows paint batch.

Tk moves Canvas window items independently of their PIL-backed decorations.
Refreshing those decorations in yscrollcommand fixes the final position, but
can still expose the old texture during the move. These viewports hold native
redraw until layout and scene sampling have both settled, then let Tk finish
painting the visible subtree. Input widgets remain ordinary Tk widgets.
"""
from contextlib import contextmanager
import ctypes
import logging
import sys
import tkinter as tk


class _WindowsPaintBatch:
    def __init__(self, canvas):
        from ctypes import wintypes as w
        self.canvas = canvas
        self.api = ctypes.WinDLL('user32', use_last_error=True)
        self.get_style = self.api.GetWindowLongPtrW
        self.get_style.argtypes, self.get_style.restype = (w.HWND, ctypes.c_int), ctypes.c_ssize_t
        self.send = self.api.SendMessageW
        self.send.argtypes = (w.HWND, w.UINT, w.WPARAM, w.LPARAM)
        self.send.restype = ctypes.c_ssize_t
        self.redraw = self.api.RedrawWindow
        self.redraw.argtypes = (w.HWND, ctypes.c_void_p, w.HRGN, w.UINT)
        self.redraw.restype = w.BOOL
        self.show = self.api.ShowWindow
        self.show.argtypes, self.show.restype = (w.HWND, ctypes.c_int), w.BOOL

    def _children(self, widget):
        yield widget
        for child in widget.winfo_children():
            yield from self._children(child)

    @contextmanager
    def hold(self):
        # Snapshot before WM_SETREDRAW changes native WS_VISIBLE. A widget
        # hidden by Tk during the batch must stay hidden when redraw resumes.
        windows = [(widget, widget.winfo_id()) for widget in self._children(self.canvas)
                   if widget.winfo_ismapped()]
        windows = [(widget, hwnd) for widget, hwnd in windows
                   if self.get_style(hwnd, -16) & 0x10000000]
        try:
            for _, hwnd in windows:
                self.send(hwnd, 0x000B, False, 0)  # WM_SETREDRAW
            yield
        finally:
            for widget, hwnd in reversed(windows):
                if not widget.winfo_exists():
                    continue
                mapped = widget.winfo_ismapped()
                self.send(hwnd, 0x000B, True, 0)
                if not mapped:
                    self.show(hwnd, 0)  # Undo WM_SETREDRAW's implicit show.
            if self.canvas.winfo_exists():
                # WM_PAINT becomes a Tk Expose event; the actual widget draw
                # may run later from Tk's idle queue. Do not use COMPOSITED:
                # Windows can present its unpainted buffer as black before
                # that idle drawing, even when the PIL textures are correct.
                self.redraw(self.canvas.winfo_id(), None, None, 0x185)
                # A scroll normally runs inside a Tk input callback, where
                # native WM_PAINT may only enqueue Expose events. Idle-only
                # updates do not dispatch that window-event queue. Deliver
                # repaint notifications directly, after every HWND is visible,
                # then drain the resulting widget draw work without pumping
                # unrelated input or timers through a nested update() loop.
                viewport_x, viewport_y = self.canvas.winfo_rootx(), self.canvas.winfo_rooty()
                viewport_right = viewport_x + self.canvas.winfo_width()
                viewport_bottom = viewport_y + self.canvas.winfo_height()
                rectangles, content = {}, {}
                for widget in list(self._children(self.canvas)):
                    if widget.winfo_ismapped():
                        x, y = widget.winfo_rootx(), widget.winfo_rooty()
                        rect = (x, y, x + widget.winfo_width(), y + widget.winfo_height())
                        rectangles[widget] = rect
                        if not getattr(widget, '_scene_layer', False):
                            content.setdefault(widget.master, []).append(rect)
                for widget, (x, y, x2, y2) in rectangles.items():
                    left, top = max(x, viewport_x), max(y, viewport_y)
                    right, bottom = min(x2, viewport_right), min(y2, viewport_bottom)
                    if right <= left or bottom <= top:
                        continue
                    # Scene decorations are always lowered behind opaque Tk
                    # siblings. A body filling the viewport already covers its
                    # backdrop; forcing that hidden image to paint is wasted.
                    if getattr(widget, '_scene_layer', False) and any(
                            a <= left and b <= top and c >= right and d >= bottom
                            for a, b, c, d in content.get(widget.master, ())):
                        continue
                    widget.event_generate('<Expose>', x=left - x, y=top - y,
                                          width=right - left, height=bottom - top, when='now')
                self.canvas.update_idletasks()


class SceneScrollCanvas(tk.Canvas):
    """Canvas API with a complete scene/layout frame for each scroll command."""
    def __init__(self, master, **options):
        super().__init__(master, **options)
        self._paint_batch = None
        self._committing_scroll = False
        self.bind('<Map>', self._mapped, add='+')
        if sys.platform == 'win32':
            try:
                self._paint_batch = _WindowsPaintBatch(self)
            except (OSError, AttributeError) as error:
                logging.getLogger(__name__).warning('Scroll buffering unavailable: %s', error)

    def _mapped(self, event):
        if event.widget is not self:
            return
        # Tk unmaps Canvas window items when a page is hidden. Mapping the
        # unchanged viewport again need not schedule their display procedure.
        # Invalidate the items explicitly, preserving state and scroll origin;
        # do not rely on the user's next scroll to make the body reappear.
        for item in self.find_all():
            if self.type(item) == 'window':
                self.itemconfigure(item, state=self.itemcget(item, 'state'))

    def yview(self, *args):
        if not args or self._committing_scroll or not self.winfo_ismapped():
            return super().yview(*args)
        self._committing_scroll = True
        try:
            if self._paint_batch is None:
                return self._scroll_frame(args)
            with self._paint_batch.hold():
                return self._scroll_frame(args)
        finally:
            self._committing_scroll = False

    def _scroll_frame(self, args):
        result = super().yview(*args)
        # Scene sampling uses the logical Canvas origin, so it can precede
        # native window movement. Settle the move and new textures together
        # rather than drawing the subtree once with old textures first.
        backdrop = getattr(self.winfo_toplevel(), '_workspace_backdrop', None)
        if backdrop is not None and backdrop.enabled and not backdrop.closed:
            backdrop.refresh(scroll_canvas=self)
        self.update_idletasks()
        return result

    def yview_scroll(self, number, what):
        return self.yview('scroll', number, what)

    def yview_moveto(self, fraction):
        return self.yview('moveto', fraction)
