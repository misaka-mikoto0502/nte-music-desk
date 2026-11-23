"""A shared, softly tinted scene behind native Tk widgets; no window alpha."""
import logging
import tkinter as tk
from PIL import Image, ImageDraw, ImageOps, ImageTk

from .appearance import COLORS, RoundedButton, RoundedPanel, rounded_bitmap


# The bundled scene is a prepared crop, without the original frame/info strip.
SCENE_STRENGTH = .22
PANEL_WHITE = .76


def scene_color(color):
    # Tk's winfo_rgb/paint_color produces lowercase hex, while the palette is
    # uppercase. Both must resolve to the same translucent surface.
    color = color.upper()
    return COLORS['paper'] if color == 'WHITE' else color


def load_scene(path):
    with Image.open(path) as original:
        scene = original.convert('RGB')
    scene.thumbnail((2560, 1600), Image.Resampling.LANCZOS)
    return scene


def fit_scene(scene, size):
    """Cover the viewport without stretching, keeping the central character."""
    cover = ImageOps.fit(scene, size, Image.Resampling.LANCZOS, centering=(.5, .55))
    return Image.blend(Image.new('RGB', size, COLORS['bg']), cover, SCENE_STRENGTH)


class WorkspaceBackdrop:
    def __init__(self, root, path):
        self.root, self.closed, self.timer = root, False, None
        self.scene = self.bitmap = None
        self.planes = {}
        self.scroll_hosts = {}
        self._scrolling = False
        self.generation = 0
        self.records, self.bindings = {}, []
        try:
            self.scene = load_scene(path)
        except (OSError, ValueError) as error:
            logging.getLogger(__name__).warning('Background unavailable: %s', error)
        self.enabled = self.scene is not None
        root._workspace_backdrop = self
        root.bind('<Destroy>', self.destroyed, add='+')
        if self.enabled:
            for sequence in ('<Configure>', '<Map>'):
                self.bindings.append((sequence, root.bind(sequence, self.request, add='+')))
            self.request()

    def request(self, event=None):
        if self.closed or not self.enabled or getattr(getattr(event, 'widget', None), '_scene_layer', False):
            return
        if self.timer is not None:
            self.root.after_cancel(self.timer)
        # Resize is debounced; scrolling must align before the next paint.
        resizing = self.bitmap is None or self.bitmap.size != (self.root.winfo_width(), self.root.winfo_height())
        self.timer = (self.root.after(65, self.refresh) if resizing else self.root.after_idle(self.refresh))

    def position(self, widget):
        ancestor = widget
        while ancestor is not None and ancestor is not self.root:
            if ancestor in self.scroll_hosts:
                canvas, item = self.scroll_hosts[ancestor]
                coordinates = canvas.coords(item)
                if coordinates:
                    x, y = self.position(canvas)
                    # Use the canvas's current origin, even before Tk moves
                    # its native child windows on the next display pass.
                    return (round(x + coordinates[0] - canvas.canvasx(0) + widget.winfo_rootx() - ancestor.winfo_rootx()),
                            round(y + coordinates[1] - canvas.canvasy(0) + widget.winfo_rooty() - ancestor.winfo_rooty()))
            ancestor = getattr(ancestor, 'master', None)
        return (widget.winfo_rootx() - self.root.winfo_rootx(),
                widget.winfo_rooty() - self.root.winfo_rooty())

    def watch_scroll(self, canvas, body, item, callback):
        self.scroll_hosts[body] = (canvas, item)
        canvas._scene_viewport = True
        def changed(first, last):
            callback(first, last)
            if (self.closed or not self.enabled or self._scrolling
                    or getattr(canvas, '_committing_scroll', False)):
                return
            self._scrolling = True
            try:
                self.refresh(scroll_canvas=canvas)
            finally:
                self._scrolling = False
        canvas.configure(yscrollcommand=changed)

    def patch(self, widget, color, size=None, offset=(0, 0)):
        color = scene_color(color)
        size = size or (widget.winfo_width(), widget.winfo_height())
        x, y = self.position(widget)
        x, y = x + offset[0], y + offset[1]
        # A clipped, scrolling child may extend beyond the viewport. Padding
        # keeps off-screen pixels harmless without allocating its full height.
        result = Image.new('RGB', size, COLORS['bg'])
        if self.bitmap is not None:
            left, top = max(0, x), max(0, y)
            right, bottom = min(self.bitmap.width, x + size[0]), min(self.bitmap.height, y + size[1])
            if right > left and bottom > top:
                result.paste(self.bitmap.crop((left, top, right, bottom)), (left - x, top - y))
        if color == COLORS['paper']:
            result = Image.blend(result, Image.new('RGB', size, color), PANEL_WHITE)
        elif color != COLORS['bg']:
            result = Image.new('RGB', size, color)
        return result

    def rounded(self, widget, width, height, fill, outside, radius, border=None):
        image = self.patch(widget, outside, (width, height))
        inside = self.patch(widget, fill, (width, height))
        mask = rounded_bitmap(width, height, '#FFFFFF', '#000000', radius).convert('L')
        image.paste(inside, (0, 0), mask)
        if border:
            ImageDraw.Draw(image).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, outline=border)
        return image

    def native_color(self, widget, color, size):
        rgb = self.patch(widget, color, size).resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
        return '#%02x%02x%02x' % rgb

    def walk(self, widget):
        if getattr(widget, '_scene_layer', False) or widget.winfo_toplevel() != self.root:
            return
        yield widget
        for child in widget.winfo_children():
            yield from self.walk(child)

    def register(self, widget):
        if widget in self.records:
            record = self.records[widget]
            if record['kind'] not in ('frame', 'viewport') or record['layer'].winfo_exists():
                return record
            self.records.pop(widget)
        if isinstance(widget, RoundedPanel):
            kind, color = 'panel', widget.fill
        elif isinstance(widget, RoundedButton):
            kind, color = 'button', widget.cget('bg')
        elif hasattr(widget, '_backdrop_artwork'):
            kind, color = 'artwork', COLORS['paper']
        elif isinstance(widget, (tk.Tk, tk.Frame)):
            kind, color = 'frame', widget.cget('bg')
        elif isinstance(widget, tk.Canvas):
            if isinstance(widget.master, RoundedPanel) and widget is widget.master.surface:
                return None
            color = getattr(widget, '_scene_surface', widget.cget('bg'))
            # Plotting / progress canvases stay clean. Canvas text and native
            # scrolling window containers can share the continuous backdrop.
            viewport = getattr(widget, '_scene_viewport', False)
            if not hasattr(widget, '_scene_surface') and color != COLORS['bg'] and not viewport:
                return None
            # Scroll containers opt in at registration. Never query the type
            # of thousands of plot items merely to classify a static chart.
            kind = 'viewport' if viewport else 'canvas'
        elif isinstance(widget, (tk.Label, tk.Checkbutton)) and not widget.cget('image'):
            kind, color = 'text', widget.cget('bg')
        else:
            return None
        color = scene_color(color)
        if color not in (COLORS['bg'], COLORS['paper'], COLORS['teal']):
            return None
        record = self.records[widget] = dict(kind=kind, color=color, key=None)
        if kind in ('frame', 'viewport'):
            layer = tk.Label(widget, borderwidth=0, highlightthickness=0, padx=0, pady=0,
                             anchor='nw', takefocus=False)
            layer._scene_layer = True
            layer.lower()
            record['layer'] = layer
        return record

    def refresh(self, scroll_canvas=None):
        if scroll_canvas is None:
            if self.timer is not None:
                self.root.after_cancel(self.timer)
            self.timer = None
        if self.closed or not self.root.winfo_exists() or not self.root.winfo_ismapped():
            return
        size = self.root.winfo_width(), self.root.winfo_height()
        if min(size) < 2:
            return
        if self.bitmap is None or self.bitmap.size != size:
            if self.timer is not None:
                self.root.after_cancel(self.timer)
                self.timer = None
            scroll_canvas = None
            self.bitmap = fit_scene(self.scene, size)
            self.planes = {COLORS['bg']: ImageTk.PhotoImage(self.bitmap, master=self.root),
                           COLORS['paper']: ImageTk.PhotoImage(Image.blend(self.bitmap,
                               Image.new('RGB', size, COLORS['paper']), PANEL_WHITE), master=self.root)}
            self.generation += 1
        for widget, record in list(self.records.items()):
            # Content rebuilds can remove a decorative child while leaving
            # its host alive. Prune that record before visibility filtering;
            # an offscreen host must never operate on the deleted layer.
            if (not widget.winfo_exists()
                    or (record['kind'] in ('frame', 'viewport') and not record['layer'].winfo_exists())):
                self.records.pop(widget)
        for body, (canvas, _) in list(self.scroll_hosts.items()):
            if not body.winfo_exists() or not canvas.winfo_exists():
                self.scroll_hosts.pop(body)
        viewports = {}
        for body, (canvas, _) in self.scroll_hosts.items():
            x, y = self.position(canvas)
            viewports[body] = (x, y, x + canvas.winfo_width(), y + canvas.winfo_height())
        scope = (0, 0, *size)
        if scroll_canvas is not None:
            x, y = self.position(scroll_canvas)
            scope = (x, y, x + scroll_canvas.winfo_width(), y + scroll_canvas.winfo_height())
        # Freeze traversal before adding decorative children.
        for widget in list(self.walk(scroll_canvas or self.root)):
            if not widget.winfo_ismapped():
                continue
            x, y = self.position(widget)
            width, height = widget.winfo_width(), widget.winfo_height()
            clip = scope
            ancestor = widget
            while ancestor is not None:
                if ancestor in viewports:
                    clip = viewports[ancestor]
                    break
                ancestor = getattr(ancestor, 'master', None)
            if x >= clip[2] or y >= clip[3] or x + width <= clip[0] or y + height <= clip[1]:
                record = self.records.get(widget)
                if record and record['kind'] in ('frame', 'viewport'):
                    record['layer'].place_forget()
                    record['key'] = None
                continue
            record = self.register(widget)
            if record is None:
                continue
            if record['kind'] in ('frame', 'canvas', 'viewport'):
                color = scene_color(getattr(widget, '_scene_surface', widget.cget('bg')))
                if color != record['color']:
                    record.update(color=color, key=None)
            key = (self.generation, x, y, width, height)
            if record['kind'] in ('frame', 'viewport'):
                # A scoped scroll refresh and a full refresh must agree on
                # the key for the same visible crop, especially the stationary
                # viewport behind the moving body.
                key += (max(0, x, clip[0]), max(0, y, clip[1]),
                        min(size[0], x + width, clip[2]), min(size[1], y + height, clip[3]))
            if record['kind'] == 'canvas':
                key += (widget.canvasx(0), widget.canvasy(0))
                if not widget.type(record.get('item', '')):
                    record['key'] = None
            if min(width, height) < 2 or record['key'] == key:
                continue
            record['key'] = key
            kind, color = record['kind'], record['color']
            if kind == 'panel':
                widget._key = None
                widget._paint()
                continue
            if kind == 'button':
                widget._skin_key = None
                widget._paint()
                continue
            if kind in ('frame', 'viewport'):
                if color not in self.planes or x >= size[0] or y >= size[1] or x + width <= 0 or y + height <= 0:
                    record['layer'].place_forget()
                    continue
                # A Label paints an off-screen buffer at its own full size,
                # even when its parent clips it. Use a visible crop instead
                # of a window-sized Label for every tiny native container.
                left, top = max(0, x, clip[0]), max(0, y, clip[1])
                right, bottom = min(size[0], x + width, clip[2]), min(size[1], y + height, clip[3])
                if right <= left or bottom <= top:
                    record['layer'].place_forget()
                    continue
                offset = left - x, top - y
                crop_size = right - left, bottom - top
                record['photo'] = (self.planes[color] if (left, top, *crop_size) == (0, 0, *size)
                                   else ImageTk.PhotoImage(self.patch(widget, color, crop_size, offset), master=self.root))
                record['layer'].configure(image=record['photo'])
                record['layer'].place(x=offset[0], y=offset[1], width=crop_size[0], height=crop_size[1], bordermode='outside')
                record['layer'].lower()
                continue
            image = self.patch(widget, color, (width, height))
            if kind == 'text':
                # Native text stays native; a local mean avoids opaque white
                # text boxes over the very faint panel texture.
                rgb = image.resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
                background = '#%02x%02x%02x' % rgb
                widget.configure(bg=background)
                if isinstance(widget, tk.Checkbutton):
                    widget.configure(activebackground=background)
                continue
            if kind == 'artwork':
                artwork = widget._backdrop_artwork
                image.paste(artwork, ((width - artwork.width) // 2, (height - artwork.height) // 2), artwork)
                record['photo'] = widget.artwork = ImageTk.PhotoImage(image, master=self.root)
                widget.configure(image=record['photo'])
                continue
            record['photo'] = ImageTk.PhotoImage(image, master=self.root)
            item = record.get('item')
            if item is None or not widget.type(item):
                record['item'] = widget.create_image(0, 0, anchor='nw', image=record['photo'], tags='workspace-background')
            else:
                widget.itemconfigure(item, image=record['photo'])
            widget.coords(record['item'], widget.canvasx(0), widget.canvasy(0))
            widget.tag_lower(record['item'])

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer = None
        for sequence, identifier in self.bindings:
            self.root.unbind(sequence, identifier)

    def destroyed(self, event):
        if event.widget == self.root:
            self.close()
            # Keep PhotoImages alive through child-widget shutdown callbacks.
            self.records.clear()
            self.planes.clear()
            self.scroll_hosts.clear()
