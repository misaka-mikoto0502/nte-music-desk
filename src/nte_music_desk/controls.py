"""Focused numeric controls for the performance settings panel."""
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageDraw, ImageOps, ImageTk

from .appearance import COLORS as C, RoundedButton, RoundedPanel


class NumberStepper(RoundedPanel):
    """A direct-entry number with separate, keyboard-accessible minus/plus keys."""
    def __init__(self, parent, variable, minimum, maximum):
        super().__init__(parent, fill=C['bg'], padx=4, pady=3, radius=10)
        self.variable, self.minimum, self.maximum = variable, minimum, maximum
        self._state = 'normal'
        self.minus = RoundedButton(self, text='−', command=lambda: self.adjust(-1),
            font=('Microsoft YaHei UI', 12), fg=C['ink'], bg=C['bg'],
            activebackground=C['paper'], flat=True, min_width=34, min_height=34, padx=3, pady=2)
        self.minus.pack(side='left')
        self.entry = tk.Entry(self, textvariable=variable, width=5, justify='center',
            font=('Microsoft YaHei UI', 11), bg=C['bg'], fg=C['ink'],
            disabledbackground=C['bg'], disabledforeground=C['ink'], relief='flat', borderwidth=0)
        self.entry.pack(side='left', fill='x', expand=True, padx=4)
        self.plus = RoundedButton(self, text='+', command=lambda: self.adjust(1),
            font=('Microsoft YaHei UI', 12), fg=C['ink'], bg=C['bg'],
            activebackground=C['paper'], flat=True, min_width=34, min_height=34, padx=3, pady=2)
        self.plus.pack(side='right')
        self.entry.bind('<Up>', lambda _: self.adjust(1))
        self.entry.bind('<Down>', lambda _: self.adjust(-1))

    def adjust(self, step):
        if self._state == 'disabled':
            return 'break'
        try:
            value = int(self.variable.get())
        except ValueError:
            value = min(self.maximum, max(self.minimum, 0))
        self.variable.set(str(min(self.maximum, max(self.minimum, value + step))))
        return 'break'

    def configure(self, cnf=None, **kwargs):
        if cnf is not None and not isinstance(cnf, dict):
            return super().configure(cnf, **kwargs)
        values = {**(cnf or {}), **kwargs}
        if 'state' in values:
            self._state = values.pop('state')
            for child in (self.minus, self.entry, self.plus):
                child.configure(state=self._state)
        if values or not (cnf or kwargs):
            return super().configure(values)
    config = configure

    def cget(self, key):
        return self._state if key == 'state' else super().cget(key)


class CharacterSpeedScale(tk.Canvas):
    """A small character portrait is the draggable thumb, with keyboard support."""
    minimum, maximum = .25, 2.0

    def __init__(self, parent, variable, command, avatar):
        super().__init__(parent, height=76, width=220, bg=C['paper'],
            highlightthickness=0, borderwidth=0, takefocus=True, cursor='hand2')
        self.variable, self.command = variable, command
        self._focused = False
        # The original artwork is retained; this mask is only the widget's view.
        with Image.open(Path(avatar)) as source:
            portrait = ImageOps.fit(source.convert('RGBA'), (96, 96), method=Image.Resampling.LANCZOS)
        mask = Image.new('L', portrait.size)
        ImageDraw.Draw(mask).ellipse((0, 0, 95, 95), fill=255)
        face = Image.new('RGBA', portrait.size, C['paper'])
        face.alpha_composite(portrait)
        face.putalpha(mask)
        self.avatar = ImageTk.PhotoImage(face.resize((36, 36), Image.Resampling.LANCZOS), master=self)
        self._trace = variable.trace_add('write', self.draw)
        self.bind('<Configure>', self.draw)
        self.bind('<Button-1>', self.drag)
        self.bind('<B1-Motion>', self.drag)
        for key, step in (('Left', -.01), ('Down', -.01), ('Right', .01), ('Up', .01)):
            self.bind(f'<{key}>', lambda _, delta=step: self.set_value(self.value() + delta))
        self.bind('<Home>', lambda _: self.set_value(self.minimum))
        self.bind('<End>', lambda _: self.set_value(self.maximum))
        self.bind('<Double-Button-1>', lambda _: self.set_value(1))
        self.bind('<FocusIn>', lambda _: self.focus_ring(True))
        self.bind('<FocusOut>', lambda _: self.focus_ring(False))
        self.bind('<Destroy>', self.dispose)

    def value(self):
        try:
            return min(self.maximum, max(self.minimum, float(self.variable.get())))
        except (ValueError, tk.TclError):
            return 1.0

    def set_value(self, value):
        if self.cget('state') != 'disabled':
            value = round(min(self.maximum, max(self.minimum, value)), 2)
            self.variable.set(value)
            self.command(value)
        return 'break'

    def drag(self, event):
        if self.cget('state') == 'disabled':
            return
        self.focus_set()
        fraction = min(1, max(0, (event.x - 22) / max(1, self.winfo_width() - 44)))
        self.set_value(self.minimum + fraction * (self.maximum - self.minimum))

    def focus_ring(self, focused):
        self._focused = focused
        self.draw()

    def draw(self, *_):
        if not self.winfo_exists():
            return
        left, right, y = 22, max(23, self.winfo_width() - 22), 26
        x = left + (right - left) * (self.value() - self.minimum) / (self.maximum - self.minimum)
        self.delete('all')
        self.create_line(left, y, right, y, fill=C['bg'], width=5, capstyle='round')
        self.create_line(left, y, x, y, fill=C['teal'], width=5, capstyle='round')
        for value, label, anchor in ((.25, '0.25×', 'w'), (1, '1×', 'center'), (2, '2×', 'e')):
            tick = left + (right - left) * (value - self.minimum) / (self.maximum - self.minimum)
            self.create_line(tick, y + 9, tick, y + 13, fill=C['ink'])
            self.create_text(tick, 57, text=label, anchor=anchor,
                fill=C['ink'], font=('Microsoft YaHei UI', 8))
        radius = 22 if self._focused else 21
        self.create_oval(x-radius, y-radius, x+radius, y+radius,
            fill=C['paper'], outline=C['teal'], width=2 if self._focused else 1)
        self.create_image(x, y, image=self.avatar)

    def dispose(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self._trace)
