"""Focused numeric controls for the performance settings panel."""
from pathlib import Path
import tkinter as tk
from PIL import Image, ImageDraw, ImageOps, ImageTk

from .appearance import COLORS as C, RoundedButton, RoundedPanel
from .display import pixels


def character_thumb(master, path, size=36):
    """Render the existing portrait without changing the bundled artwork."""
    size = pixels(master, size)
    mask_size = max(96, size * 3)
    with Image.open(Path(path)) as source:
        portrait = ImageOps.fit(source.convert('RGBA'), (mask_size, mask_size), method=Image.Resampling.LANCZOS)
    mask = Image.new('L', portrait.size)
    ImageDraw.Draw(mask).ellipse((0, 0, mask_size - 1, mask_size - 1), fill=255)
    face = Image.new('RGBA', portrait.size, C['paper'])
    face.alpha_composite(portrait); face.putalpha(mask)
    return ImageTk.PhotoImage(face.resize((size, size), Image.Resampling.LANCZOS), master=master)


class CharacterProgress(tk.Canvas):
    """A compact portrait thumb; seek coordinates include its end margins."""
    def __init__(self, parent, avatar):
        super().__init__(parent, height=pixels(parent, 36), width=pixels(parent, 320), bg=C['paper'], borderwidth=0,
                         highlightthickness=0, cursor='hand2', takefocus=False)
        self.inset = pixels(parent, 18)
        self.avatar = character_thumb(self, avatar, 26)
        self.fraction = 0
        self.bind('<Configure>', lambda _: self.draw(self.fraction))

    def fraction_at(self, x):
        return min(1, max(0, (x-self.inset)/max(1, self.winfo_width()-2*self.inset)))

    def draw(self, fraction):
        self.fraction = min(1, max(0, fraction))
        width = self.winfo_width() if self.winfo_width()>1 else int(self.cget('width'))
        left, right, y = self.inset, max(self.inset+1, width-self.inset), self.inset
        x = left+(right-left)*self.fraction
        radius, thickness = pixels(self, 15), max(1, pixels(self, 5))
        self.delete('all')
        self.create_line(left,y,right,y,fill=C['bg'],width=thickness,capstyle='round',tags='track')
        self.create_line(left,y,x,y,fill=C['teal'],width=thickness,capstyle='round',tags='track')
        self.create_oval(x-radius,y-radius,x+radius,y+radius,fill=C['paper'],outline=C['teal'],tags='thumb')
        self.create_image(x,y,image=self.avatar,tags='portrait')


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
        super().__init__(parent, height=pixels(parent, 76), width=pixels(parent, 220), bg=C['paper'],
            highlightthickness=0, borderwidth=0, takefocus=True, cursor='hand2')
        self.variable, self.command = variable, command
        self.inset = pixels(parent, 22)
        self._focused = False
        # The original artwork is retained; this mask is only the widget's view.
        self.avatar = character_thumb(self, avatar)
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
        fraction = min(1, max(0, (event.x - self.inset) / max(1, self.winfo_width() - 2 * self.inset)))
        self.set_value(self.minimum + fraction * (self.maximum - self.minimum))

    def focus_ring(self, focused):
        self._focused = focused
        self.draw()

    def draw(self, *_):
        if not self.winfo_exists():
            return
        left, right, y = self.inset, max(self.inset + 1, self.winfo_width() - self.inset), pixels(self, 26)
        x = left + (right - left) * (self.value() - self.minimum) / (self.maximum - self.minimum)
        self.delete('all')
        thickness = max(1, pixels(self, 5))
        self.create_line(left, y, right, y, fill=C['bg'], width=thickness, capstyle='round')
        self.create_line(left, y, x, y, fill=C['teal'], width=thickness, capstyle='round')
        for value, label, anchor in ((.25, '0.25×', 'w'), (1, '1×', 'center'), (2, '2×', 'e')):
            tick = left + (right - left) * (value - self.minimum) / (self.maximum - self.minimum)
            self.create_line(tick, y + pixels(self, 9), tick, y + pixels(self, 13), fill=C['ink'])
            self.create_text(tick, pixels(self, 57), text=label, anchor=anchor,
                fill=C['ink'], font=('Microsoft YaHei UI', 8))
        radius = pixels(self, 22 if self._focused else 21)
        self.create_oval(x-radius, y-radius, x+radius, y+radius,
            fill=C['paper'], outline=C['teal'], width=2 if self._focused else 1)
        self.create_image(x, y, image=self.avatar)

    def dispose(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self._trace)
