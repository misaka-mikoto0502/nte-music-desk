"""Quiet, rounded desktop surfaces. Native Tk buttons retain their input behavior."""
from functools import lru_cache
import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

COLORS = {
    # Four paints: background, content, text/borders, primary action/selection.
    'bg': '#F3F2ED', 'paper': '#FFFFFF', 'ink': '#293A32', 'teal': '#326B52',
    'muted': '#293A32', 'line': '#F3F2ED',
    'nav': '#FFFFFF', 'nav_hover': '#F3F2ED', 'nav_active': '#F3F2ED',
    'teal_hover': '#326B52', 'teal_light': '#FFFFFF', 'mint': '#326B52',
    'blue': '#293A32', 'blue_light': '#FFFFFF', 'amber': '#293A32', 'amber_light': '#FFFFFF',
    'red': '#293A32', 'red_light': '#FFFFFF', 'disabled': '#F3F2ED', 'disabled_ink': '#293A32',
}


def paint_color(widget, color):
    red, green, blue = widget.winfo_rgb(color)
    return f'#{red // 256:02x}{green // 256:02x}{blue // 256:02x}'


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
        self._outer = paint_color(master, master.cget('bg'))
        self._fill = kwargs.pop('bg', COLORS['paper'])
        self._hover_fill = kwargs.pop('activebackground', self._fill)
        self._padding = [kwargs.pop('padx', 14), kwargs.pop('pady', 9)]
        self._ink = kwargs.get('fg', COLORS['ink'])
        self._outline = kwargs.pop('outline', None)
        self._flat = kwargs.pop('flat', False)
        self._min_width = kwargs.pop('min_width', 0)
        self._min_height = kwargs.pop('min_height', 0)
        self._hover, self._focused, self._pressed, self._skin_key = False, False, False, None
        for key in ('relief', 'borderwidth', 'highlightthickness', 'highlightbackground', 'highlightcolor'):
            kwargs.pop(key, None)
        placeholder = tk.PhotoImage(master=master, width=1, height=1)
        takefocus=kwargs.pop('takefocus',True)
        super().__init__(master, image=placeholder, compound='center', bg=self._outer,
            activebackground=self._outer, relief='flat', borderwidth=0, highlightthickness=0,
            padx=0, pady=0, takefocus=takefocus, disabledforeground=COLORS['disabled_ink'], **kwargs)
        self._skin = placeholder
        self._ready = True
        self.bind('<Configure>', self._paint, add='+')
        self.bind('<Enter>', lambda _: self._enter(True), add='+')
        self.bind('<Leave>', lambda _: self._enter(False), add='+')
        self.bind('<FocusIn>', lambda _: self._focus(True), add='+')
        self.bind('<FocusOut>', lambda _: self._focus(False), add='+')
        self.bind('<ButtonPress-1>', lambda _: self._press(True), add='+')
        self.bind('<ButtonRelease-1>', lambda _: self._press(False), add='+')
        self.bind('<KeyPress-space>', lambda _: self._press(True), add='+')
        self.bind('<KeyRelease-space>', lambda _: self._press(False), add='+')
        self._request()

    def _request(self):
        font = tkfont.Font(root=self, font=super().cget('font'))
        lines = str(super().cget('text')).splitlines() or ['']
        width = max(font.measure(line) for line in lines) + 2*int(self._padding[0]) + 8
        height = font.metrics('linespace') * len(lines) + 2*int(self._padding[1]) + 4
        super().configure(width=max(24, self._min_width, width), height=max(24, self._min_height, height))
        self._paint()

    def _enter(self, value):
        self._hover = value
        self._paint()

    def _focus(self, value):
        self._focused = value
        if not value:
            self._pressed = False
        self._paint()

    def _press(self, value):
        self._pressed = value and str(super().cget('state')) != 'disabled'
        self._paint()

    def _paint(self, _=None):
        if not self._ready or not self.winfo_exists(): return
        width, height = max(24, self.winfo_width()), max(24, self.winfo_height())
        if width <= 24: width = int(super().cget('width'))
        if height <= 24: height = int(super().cget('height'))
        enabled = str(super().cget('state')) != 'disabled'
        fill = (self._hover_fill if self._hover else self._fill) if enabled else COLORS['disabled']
        primary = self._fill == COLORS['teal']
        if self._pressed and enabled:
            fill = COLORS['ink'] if primary else COLORS['paper']
        super().configure(fg=self._ink if enabled else COLORS['disabled_ink'])
        border = COLORS['teal'] if self._focused and enabled else self._outline
        if enabled and self._hover and not self._flat and not primary:
            border = COLORS['teal'] if self._focused or self._pressed else COLORS['ink']
        key = (width, height, fill, self._outer, border)
        if key == self._skin_key: return
        self._skin_key = key
        self._skin = (ImageTk.PhotoImage(rounded_bitmap(width, height, fill, self._outer, 10, border), master=self)
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
        if 'min_width' in values: self._min_width = values.pop('min_width')
        if 'min_height' in values: self._min_height = values.pop('min_height')
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


def style_comboboxes(root):
    """Round native ttk fields while retaining their popup and keyboard bindings."""
    style = ttk.Style(root)
    if 'Desk.Combobox.field' not in style.element_names():
        images = {}
        for name, border in (('normal', None), ('hover', None), ('focus', COLORS['teal'])):
            images[name] = ImageTk.PhotoImage(rounded_bitmap(64, 44, COLORS['bg'], COLORS['paper'], 10, border), master=root)
        for name, color in (('arrow', COLORS['ink']), ('arrow_focus', COLORS['teal'])):
            arrow = Image.new('RGBA', (72, 60))
            draw = ImageDraw.Draw(arrow)
            draw.line(((21, 23), (36, 38), (51, 23)), fill=color, width=5, joint='curve')
            images[name] = ImageTk.PhotoImage(arrow.resize((18, 15), Image.Resampling.LANCZOS), master=root)
        # Tcl elements keep image names, so Python must retain their owners too.
        root._desk_combobox_images = images
        style.element_create('Desk.Combobox.field', 'image', images['normal'],
            ('disabled', images['normal']), ('focus', images['focus']), ('active', images['hover']),
            border=(10, 8, 10, 8), sticky='nsew')
        style.element_create('Desk.Combobox.downarrow', 'image', images['arrow'],
            ('focus', images['arrow_focus']), sticky='')
    style.layout('TCombobox', [('Desk.Combobox.field', {'sticky': 'nsew', 'children': [
        ('Desk.Combobox.downarrow', {'side': 'right', 'sticky': 'ns'}),
        ('Combobox.padding', {'sticky': 'nsew', 'children': [
            ('Combobox.textarea', {'sticky': 'nsew'})]})]})])
    style.configure('TCombobox', padding=(6, 5), foreground=COLORS['ink'],
                    fieldbackground=COLORS['bg'], postoffset=(0, 4, 0, 0))
    style.map('TCombobox', fieldbackground=[('readonly', COLORS['bg']), ('disabled', COLORS['bg'])])
    style.configure('ComboboxPopdownFrame', background=COLORS['paper'], bordercolor=COLORS['bg'],
                    lightcolor=COLORS['paper'], darkcolor=COLORS['paper'], relief='solid', borderwidth=1)
    for option, value in (('background', COLORS['paper']), ('foreground', COLORS['ink']),
            ('selectBackground', COLORS['bg']), ('selectForeground', COLORS['teal']),
            ('font', ('Microsoft YaHei UI', 11)), ('borderWidth', 0), ('highlightThickness', 8),
            ('highlightBackground', COLORS['paper']), ('highlightColor', COLORS['paper'])):
        root.option_add(f'*TCombobox*Listbox.{option}', value)


class RoundedPanel(tk.Frame):
    def __init__(self, master, fill=None, padx=18, pady=15, radius=12):
        self.fill, self.outside = fill or COLORS['paper'], paint_color(master, master.cget('bg'))
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


class CanvasLabel:
    """Configure-compatible canvas text for the current score heading."""
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
