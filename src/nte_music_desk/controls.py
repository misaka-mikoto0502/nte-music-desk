"""Focused numeric controls for the performance settings panel."""
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageDraw, ImageTk

from .appearance import COLORS as C, RoundedButton, RoundedPanel, paint_color
from .display import pixels


def character_thumb(master, path, size=36):
    """Render the existing portrait without changing the bundled artwork."""
    size = max(1, pixels(master, size))
    with Image.open(Path(path)) as source:
        # Focus this head-and-shoulders asset on the face. Sample directly
        # from the original into physical display pixels, without an
        # intermediate reduction that softens fine eyes/hair linework.
        width, height = source.size
        portrait = source.convert('RGBA').resize((size, size), Image.Resampling.LANCZOS,
                                                 box=(width / 8, 0, width * 31 / 32, height * 27 / 32))
    mask_size = size * 3
    mask = Image.new('L', (mask_size, mask_size))
    ImageDraw.Draw(mask).ellipse((0, 0, mask_size - 1, mask_size - 1), fill=255)
    face = Image.new('RGBA', portrait.size, C['paper'])
    face.alpha_composite(portrait)
    # Supersample only the circular edge; keep the portrait's pixels intact.
    face.putalpha(mask.resize((size, size), Image.Resampling.LANCZOS))
    return ImageTk.PhotoImage(face, master=master)


class CharacterProgress(tk.Canvas):
    """A compact portrait thumb; seek coordinates include its end margins."""
    def __init__(self, parent, avatar):
        super().__init__(parent, height=pixels(parent, 40), width=pixels(parent, 320), bg=C['paper'], borderwidth=0,
                         highlightthickness=0, cursor='hand2', takefocus=False)
        self.inset = pixels(parent, 20)
        self._scene_surface = parent.cget('bg')
        self.avatar = character_thumb(self, avatar, 32)
        self.fraction = 0
        self.bind('<Configure>', lambda _: self.draw(self.fraction))

    def fraction_at(self, x):
        return min(1, max(0, (x-self.inset)/max(1, self.winfo_width()-2*self.inset)))

    def draw(self, fraction):
        self.fraction = min(1, max(0, fraction))
        width = self.winfo_width() if self.winfo_width()>1 else int(self.cget('width'))
        left, right, y = self.inset, max(self.inset+1, width-self.inset), self.inset
        x = left+(right-left)*self.fraction
        radius, thickness = pixels(self, 18), max(1, pixels(self, 3))
        self.delete('progress')
        self.create_line(left,y,right,y,fill='#B8C6BF',width=thickness,capstyle='round',tags=('track','progress'))
        self.create_line(left,y,x,y,fill=C['teal'],width=thickness,capstyle='round',tags=('track','progress'))
        self.create_oval(x-radius,y-radius,x+radius,y+radius,fill=C['paper'],outline=C['teal'],tags=('thumb','progress'))
        self.create_image(x,y,image=self.avatar,tags=('portrait','progress'))


class GlassEntry(tk.Canvas):
    """Transparent value at rest, with a native text editor on focus/click."""
    def __init__(self, parent, variable, *, width=5, justify='center', font=('Microsoft YaHei UI', 11)):
        self._font = tkfont.Font(root=parent, font=font)
        super().__init__(parent, width=self._font.measure('0' * width) + 10,
                         height=self._font.metrics('linespace') + 8, bg=parent.cget('bg'),
                         highlightthickness=0, borderwidth=0, takefocus=True, cursor='xterm')
        self.variable, self.justify = variable, justify
        self._scene_surface = parent.cget('bg')
        self.editing, self._before = False, ''
        self.editor = tk.Entry(self, textvariable=variable, justify=justify, font=font,
                               bg=C['paper'], fg=C['ink'], insertbackground=C['ink'], relief='flat',
                               borderwidth=0, highlightthickness=1, highlightbackground=C['teal'],
                               highlightcolor=C['teal'], selectbackground=C['teal'], selectforeground=C['paper'])
        self.editor.bind('<Return>', self.finish)
        self.editor.bind('<Escape>', self.cancel)
        self.editor.bind('<FocusOut>', self.finish)
        super().bind('<Button-1>', self.begin)
        super().bind('<FocusIn>', self.begin)
        super().bind('<Configure>', self.draw)
        super().bind('<Destroy>', self.dispose)
        self._trace = variable.trace_add('write', self.draw)
        self.draw()

    def bind(self, sequence=None, func=None, add=None):
        if func is not None and hasattr(self, 'editor'):
            self.editor.bind(sequence, func, add)
        return super().bind(sequence, func, add)

    def begin(self, _=None):
        if self.cget('state') == 'disabled' or self.editing:
            return
        self.editing, self._before = True, self.variable.get()
        backdrop = getattr(self.winfo_toplevel(), '_workspace_backdrop', None)
        color = (backdrop.native_color(self, self._scene_surface, (self.winfo_width(), self.winfo_height()))
                 if backdrop and backdrop.enabled and backdrop.bitmap is not None else C['paper'])
        self.editor.configure(bg=color, disabledbackground=color)
        self.editor.place(x=0, y=0, relwidth=1, relheight=1)
        self.editor.focus_set()
        self.editor.selection_range(0, 'end')
        return 'break'

    def finish(self, event=None):
        if not self.editing:
            return
        self.editing = False
        self.editor.place_forget()
        if event is not None and event.keysym == 'Return':
            self.master.focus_set()
        self.draw()
        return 'break'

    def cancel(self, _=None):
        self.variable.set(self._before)
        self.finish()
        self.master.focus_set()
        return 'break'

    def configure(self, cnf=None, **kwargs):
        values = {**(cnf or {}), **kwargs} if cnf is None or isinstance(cnf, dict) else None
        if values is not None and 'state' in values and hasattr(self, 'editor'):
            disabled = values['state'] == 'disabled'
            self.editor.configure(state=values['state'])
            values['takefocus'] = not disabled
            if disabled:
                self.finish()
        return super().configure(values) if values is not None else super().configure(cnf, **kwargs)
    config = configure

    def get(self):
        return self.editor.get()

    def delete(self, first, last=None):
        return self.editor.delete(first, last)

    def insert(self, index, text):
        return self.editor.insert(index, text)

    def draw(self, *_):
        if not self.winfo_exists():
            return
        # Preserve the shared scene image while updating the text overlay.
        super().delete('value')
        width = self.winfo_width() if self.winfo_width() > 1 else int(self.cget('width'))
        height = self.winfo_height() if self.winfo_height() > 1 else int(self.cget('height'))
        x = width - 4 if self.justify == 'right' else 4 if self.justify == 'left' else width / 2
        self.create_text(x, height / 2, text=self.variable.get(), font=self._font, fill=C['ink'],
                         anchor='e' if self.justify == 'right' else 'w' if self.justify == 'left' else 'center', tags='value')

    def dispose(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self._trace)


class NumberStepper(RoundedPanel):
    """A direct-entry number with separate, keyboard-accessible minus/plus keys."""
    def __init__(self, parent, variable, minimum, maximum):
        surface = paint_color(parent, parent.cget('bg'))
        super().__init__(parent, fill=surface, padx=4, pady=3, radius=10)
        self.variable, self.minimum, self.maximum = variable, minimum, maximum
        self._state = 'normal'
        self.minus = RoundedButton(self, text='−', command=lambda: self.adjust(-1),
            font=('Microsoft YaHei UI', 12), fg=C['ink'], bg=surface,
            activebackground=C['paper'], flat=True, min_width=34, min_height=34, padx=3, pady=2)
        self.minus.pack(side='left')
        self.entry = GlassEntry(self, variable, width=5)
        self.entry.pack(side='left', fill='x', expand=True, padx=4)
        self.plus = RoundedButton(self, text='+', command=lambda: self.adjust(1),
            font=('Microsoft YaHei UI', 12), fg=C['ink'], bg=surface,
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
        self._scene_surface = parent.cget('bg')
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
        self.delete('scale')
        thickness = max(1, pixels(self, 5))
        self.create_line(left, y, right, y, fill='#B8C6BF', width=thickness, capstyle='round', tags='scale')
        self.create_line(left, y, x, y, fill=C['teal'], width=thickness, capstyle='round', tags='scale')
        for value, label, anchor in ((.25, '0.25×', 'w'), (1, '1×', 'center'), (2, '2×', 'e')):
            tick = left + (right - left) * (value - self.minimum) / (self.maximum - self.minimum)
            self.create_line(tick, y + pixels(self, 9), tick, y + pixels(self, 13), fill=C['ink'], tags='scale')
            self.create_text(tick, pixels(self, 57), text=label, anchor=anchor,
                fill=C['ink'], font=('Microsoft YaHei UI', 8), tags='scale')
        radius = pixels(self, 22 if self._focused else 21)
        self.create_oval(x-radius, y-radius, x+radius, y+radius,
            fill=C['paper'], outline=C['teal'], width=2 if self._focused else 1, tags='scale')
        self.create_image(x, y, image=self.avatar, tags='scale')

    def dispose(self, event):
        if event.widget is self:
            self.variable.trace_remove('write', self._trace)
