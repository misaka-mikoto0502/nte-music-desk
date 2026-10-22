"""Quiet, rounded desktop surfaces. Native Tk buttons retain their input behavior."""
from functools import lru_cache
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageDraw, ImageTk, ImageOps, ImageEnhance

COLORS = {
    'bg': '#EDECE6', 'paper': '#FCFBF7', 'ink': '#273B36', 'muted': '#738078',
    'line': '#DDDCD2', 'nav': '#263A35', 'nav_hover': '#344C43', 'nav_active': '#405D50',
    'teal': '#32634F', 'teal_hover': '#254D3D', 'teal_light': '#E4ECE2', 'mint': '#C6D9AB',
    'blue': '#466354', 'blue_light': '#E8EDE4', 'amber': '#936C3C', 'amber_light': '#F1E8D8',
    'red': '#A34F4B', 'red_light': '#F1E2DE', 'disabled': '#E8E7E0', 'disabled_ink': '#9B9F94',
}


@lru_cache(maxsize=192)
def rounded_bitmap(width, height, fill, outside, radius=14, border=None):
    """Supersampling avoids jagged corners at ordinary desktop scale."""
    scale = 3
    image = Image.new('RGB', (width * scale, height * scale), outside)
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((scale, scale, (width-1)*scale, (height-1)*scale),
        radius=min(radius, height//2, width//2)*scale, fill=fill, outline=border, width=scale)
    return image.resize((width, height), Image.Resampling.LANCZOS)


class RoundedButton(tk.Button):
    """Image-backed native button: Tab/Space/invoke/disabled all stay native."""
    def __init__(self, master, **kwargs):
        self._ready = False
        self._outer = master.cget('bg')
        self._fill = kwargs.pop('bg', COLORS['paper'])
        self._hover_fill = kwargs.pop('activebackground', self._fill)
        self._padding = [kwargs.pop('padx', 14), kwargs.pop('pady', 9)]
        self._ink = kwargs.get('fg', COLORS['ink'])
        self._hover, self._focused, self._skin_key = False, False, None
        for key in ('relief', 'borderwidth', 'highlightthickness', 'highlightbackground', 'highlightcolor'):
            kwargs.pop(key, None)
        placeholder = tk.PhotoImage(master=master, width=1, height=1)
        super().__init__(master, image=placeholder, compound='center', bg=self._outer,
            activebackground=self._outer, relief='flat', borderwidth=0, highlightthickness=0,
            padx=0, pady=0, takefocus=True, disabledforeground=COLORS['disabled_ink'], **kwargs)
        self._skin = placeholder
        self._ready = True
        self.bind('<Configure>', self._paint, add='+')
        self.bind('<Enter>', lambda _: self._enter(True), add='+')
        self.bind('<Leave>', lambda _: self._enter(False), add='+')
        self.bind('<FocusIn>', lambda _: self._focus(True), add='+')
        self.bind('<FocusOut>', lambda _: self._focus(False), add='+')
        self._request()

    def _request(self):
        font = tkfont.Font(root=self, font=super().cget('font'))
        lines = str(super().cget('text')).splitlines() or ['']
        width = max(font.measure(line) for line in lines) + 2*int(self._padding[0]) + 8
        height = font.metrics('linespace') * len(lines) + 2*int(self._padding[1]) + 4
        super().configure(width=max(24, width), height=max(24, height))
        self._paint()

    def _enter(self, value):
        self._hover = value
        self._paint()

    def _focus(self, value):
        self._focused = value
        self._paint()

    def _paint(self, _=None):
        if not self._ready or not self.winfo_exists(): return
        width, height = max(24, self.winfo_width()), max(24, self.winfo_height())
        if width <= 24: width = int(super().cget('width'))
        if height <= 24: height = int(super().cget('height'))
        enabled = str(super().cget('state')) != 'disabled'
        fill = (self._hover_fill if self._hover else self._fill) if enabled else COLORS['disabled']
        super().configure(fg=self._ink if enabled else COLORS['disabled_ink'])
        border = COLORS['amber'] if self._focused and enabled else None
        key = (width, height, fill, self._outer, border)
        if key == self._skin_key: return
        self._skin_key = key
        self._skin = (ImageTk.PhotoImage(rounded_bitmap(width, height, fill, self._outer, 12, border), master=self)
                      if enabled else tk.PhotoImage(master=self, width=1, height=1))
        super().configure(image=self._skin)

    def configure(self, cnf=None, **kwargs):
        if not self._ready: return super().configure(cnf, **kwargs)
        if cnf is not None and not isinstance(cnf, dict): return super().configure(cnf, **kwargs)
        values = {**(cnf or {}), **kwargs}
        if not values: return super().configure()
        if 'bg' in values: self._fill = values.pop('bg')
        if 'background' in values: self._fill = values.pop('background')
        if 'activebackground' in values: self._hover_fill = values.pop('activebackground')
        if 'fg' in values: self._ink = values['fg']
        values.pop('disabledforeground', None)
        for index, key in enumerate(('padx', 'pady')):
            if key in values: self._padding[index] = values.pop(key)
        for key in ('highlightthickness', 'highlightbackground', 'highlightcolor'):
            values.pop(key, None)
        super().configure(**values)
        self._request()
    config = configure

    def cget(self, key):
        if key in ('bg', 'background'): return self._fill
        if key == 'padx': return self._padding[0]
        if key == 'pady': return self._padding[1]
        return super().cget(key)


class RoundedPanel(tk.Frame):
    def __init__(self, master, fill=None, padx=18, pady=15, radius=20):
        self.fill, self.outside = fill or COLORS['paper'], master.cget('bg')
        super().__init__(master, bg=self.outside, padx=padx, pady=pady, borderwidth=0)
        self.radius, self._key, self._skin = radius, None, None
        self.surface = tk.Canvas(self, highlightthickness=0, borderwidth=0, bg=self.outside)
        self.surface.place(x=0, y=0, relwidth=1, relheight=1, bordermode='outside')
        self.tk.call('lower', self.surface._w)
        self.bind('<Configure>', self._paint, add='+')

    def cget(self, key):
        if key in ('bg', 'background'): return self.fill
        return super().cget(key)

    def _paint(self, _=None):
        width, height = self.winfo_width(), self.winfo_height()
        if width < 2 or height < 2 or self._key == (width, height): return
        self._key = (width, height)
        self._skin = ImageTk.PhotoImage(rounded_bitmap(width, height, self.fill, self.outside, self.radius), master=self)
        self.surface.delete('all')
        self.surface.create_image(0, 0, anchor='nw', image=self._skin)


class SessionArtwork(tk.Canvas):
    """Photo opacity is rendered into this canvas, never onto the app window."""
    def __init__(self, master, path, opacity=.24, height=170, tint=None, **kwargs):
        self.tint = tint or COLORS['bg']
        super().__init__(master, bg=self.tint, height=height, highlightthickness=0, **kwargs)
        self.opacity, self._image, self._photo, self._pending = opacity, None, None, None
        try:
            with Image.open(Path(path)) as source:
                self._image = source.convert('RGB')
        except (OSError, ValueError):
            pass  # A missing optional photo must not prevent opening scores.
        self.bind('<Configure>', self._schedule, add='+')
        self.bind('<Destroy>', self._destroyed, add='+')

    def set_opacity(self, opacity):
        self.opacity = max(0, min(.6, float(opacity)))
        self._schedule()

    def _schedule(self, _=None):
        if self._pending is not None: self.after_cancel(self._pending)
        self._pending = self.after(70, self._paint)

    def _paint(self):
        self._pending = None
        width, height = self.winfo_width(), self.winfo_height()
        if self._image is None or width < 2 or height < 2: return
        plate_width = min(width, 620)
        plate = ImageOps.fit(self._image, (plate_width, height), method=Image.Resampling.LANCZOS, centering=(.58, .28))
        photo = Image.new('RGB', (width, height), self.tint)
        photo.paste(plate, (width - plate_width, 0))
        photo = ImageEnhance.Color(photo).enhance(.65)
        # A horizontal veil keeps text on the left legible while retaining the
        # scene on the right; image strength is bounded, independent of widgets.
        mask = Image.new('L', (width, 1))
        mask.putdata([int(255 * self.opacity * max(0, (x - width + plate_width)/max(1, plate_width))**.7) for x in range(width)])
        photo = Image.composite(photo, Image.new('RGB', photo.size, self.tint), mask.resize(photo.size))
        self._photo = ImageTk.PhotoImage(photo, master=self)
        self.delete('artwork')
        self.create_image(0, 0, anchor='nw', image=self._photo, tags='artwork')
        self.tag_lower('artwork')

    def _destroyed(self, event):
        if event.widget == self and self._pending is not None:
            self.after_cancel(self._pending)
            self._pending = None


class CanvasLabel:
    """Small configure-compatible label used for text over the artwork."""
    def __init__(self, canvas, x, y, variable=None, **kwargs):
        self.canvas = canvas
        self.limit = kwargs.pop('ellipsize', None)
        self.font = kwargs.get('font')
        self.item = canvas.create_text(x, y, anchor='nw', **kwargs)
        self.variable, self.trace = variable, None
        if variable is not None:
            self.trace = variable.trace_add('write', self.update)
            self.update()
            canvas.bind('<Destroy>', self.destroy, add='+')

    def update(self, *_):
        if self.canvas.winfo_exists():
            text = self.variable.get().replace('\n', ' ')
            if self.limit:
                font = tkfont.Font(root=self.canvas, font=self.font)
                if font.measure(text) > self.limit:
                    while text and font.measure(text + '…') > self.limit:
                        text = text[:-1]
                    text += '…'
            self.canvas.itemconfigure(self.item, text=text)

    def configure(self, **kwargs):
        if 'fg' in kwargs: kwargs['fill'] = kwargs.pop('fg')
        kwargs.pop('bg', None)
        self.canvas.itemconfigure(self.item, **kwargs)

    def destroy(self, event):
        if event.widget == self.canvas and self.trace:
            self.variable.trace_remove('write', self.trace)
            self.trace = None
