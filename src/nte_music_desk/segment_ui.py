"""Compact source-time selection and reversible segment arrangement controls."""
from copy import deepcopy
from bisect import bisect_left, bisect_right
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageDraw, ImageTk

from .appearance import COLORS as C, RoundedPanel
from .arrangement import apply_region, compile_arrangement
from .controls import NumberStepper
from .display import pixels
from .instruments import INSTRUMENTS
from .segments import parse_time
from .workspace_pages import ScrollArea


# A local annotation color, distinct from the workbench's green selection.
EDITED_COLOR = '#A66528'
TIMELINE_HELP = '拖空白框选 · 拖两端改范围 · 拖选区移动 · 点击上方刻度定位游标'


class SegmentPage:
    def __init__(self, app, parent):
        from .ui import MODES
        self.app, self.modes = app, MODES
        self.identity = None
        self.history, self.future = [], []
        self.viewport = (0, 1)
        self.cursor = 0
        self.drag = None
        self.selected = None
        self.rendered_segments = None
        self._drawing_song = self._drawing_key = None
        self._note_layers = {}
        self.onsets = []
        self.start, self.end = tk.StringVar(value='0:00.000'), tk.StringVar(value='0:08.000')
        self.name = tk.StringVar(value='我的片段')
        self.mode = tk.StringVar(value=MODES['faithful'])
        self.transpose = tk.StringVar(value='0')
        self.instrument = app.instrument
        self.note = tk.StringVar(value='先在游戏内比较 A/B，点击“应用到这段”后保存候选调整。')
        self.guide = tk.StringVar(value=TIMELINE_HELP)
        self.track_vars = {}
        self.buttons = []
        area = ScrollArea(parent)
        area.pack(fill='both', expand=True)
        self.canvas = area.canvas
        header = tk.Frame(area.body, bg=C['bg'])
        header.pack(fill='x', pady=(0, 12))
        app.label(header, '1  选择乐器', 10, bold=True).pack(side='left', padx=(0, 12))
        self.instrument_box = ttk.Combobox(header, textvariable=self.instrument,
                                           values=[p.title for p in INSTRUMENTS.values()],
                                           state='readonly', width=22)
        self.instrument_box.pack(side='left')
        self.instrument_box.bind('<<ComboboxSelected>>', self.instrument_changed)
        self.buttons.append((self.instrument_box, 'readonly'))
        app.label(header, '整首共用', 9).pack(side='left', padx=(10, 0))
        self.undo_button = app.button(header, '撤销', self.undo, 'nav', 9)
        self.undo_button.pack(side='right')
        self.redo_button = app.button(header, '重做', self.redo, 'nav', 9)
        self.redo_button.pack(side='right', padx=(0, 8))
        timeline_panel = RoundedPanel(area.body, padx=18, pady=10)
        timeline_panel.pack(fill='x', pady=(0, 10))
        legend = tk.Frame(timeline_panel, bg=C['paper'])
        legend.pack(fill='x', pady=(2, 10))
        app.label(legend, '2  选择片段', 10, bold=True).pack(side='left')
        app.label(legend, '━ 已调整', 9, color=EDITED_COLOR).pack(side='right')
        app.label(legend, '━ 未调整', 9, color=C['teal']).pack(side='right', padx=(0, 16))
        self.timeline = tk.Canvas(timeline_panel, height=180, bg=C['paper'], highlightthickness=0,
                                  cursor='crosshair')
        self.timeline.pack(fill='x')
        self.timeline.bind('<Configure>', lambda _: self.draw())
        self.timeline.bind('<ButtonPress-1>', self.begin_selection)
        self.timeline.bind('<B1-Motion>', self.drag_selection)
        self.timeline.bind('<ButtonRelease-1>', self.end_selection)
        self.timeline.bind('<Motion>', self.hover)
        self.timeline.bind('<Leave>', self.leave)
        app.label(timeline_panel, textvariable=self.guide, size=9, wraplength=650,
                  justify='left').pack(anchor='w', pady=(8, 0))
        row = tk.Frame(timeline_panel, bg=C['paper'])
        row.pack(fill='x', pady=(8, 0))
        views = RoundedPanel(row, fill=C['bg'], padx=3, pady=3, radius=12)
        views.pack(side='left')
        self.view_buttons = {}
        for mode, caption, command in (('selection', '放大选段', self.zoom), ('full', '查看全曲', self.zoom_out)):
            button = self.add_button(views, caption, command, 'nav')
            button.configure(padx=12, pady=6, min_width=pixels(row, 112))
            button.pack(side='left')
            self.view_buttons[mode] = button
        self.add_button(row, '在游标处分割', self.split, 'nav').pack(side='right')

        editor = RoundedPanel(area.body, padx=20, pady=14)
        editor.pack(fill='x', pady=(0, 12))
        app.label(editor, '3  调整片段', 10, bold=True).pack(anchor='w', pady=(0, 12))
        times = tk.Frame(timeline_panel, bg=C['paper'])
        times.pack(fill='x', pady=(10, 0), before=row)
        for caption, variable in (('起点', self.start), ('终点', self.end)):
            app.label(times, caption, 9).pack(side='left', padx=(0, 8))
            entry = ttk.Entry(times, textvariable=variable, width=12)
            entry.pack(side='left', padx=(0, 16))
            entry.bind('<Return>', lambda _: self.redraw_range())
            entry.bind('<FocusOut>', lambda _: self.redraw_range())
            self.buttons.append((entry, 'normal'))
        self.add_button(times, '定位到起点', self.seek, 'nav').pack(side='right')

        fields = tk.Frame(editor, bg=C['paper'])
        fields.pack(fill='x')
        fields.columnconfigure(0, weight=3)
        fields.columnconfigure(1, weight=1)
        cell = tk.Frame(fields, bg=C['paper'])
        cell.grid(row=0, column=0, sticky='ew', padx=(0, 14))
        app.label(cell, '演奏方案', 9).pack(anchor='w', pady=(0, 8))
        choice = ttk.Combobox(cell, textvariable=self.mode, values=list(MODES.values()), state='readonly')
        choice.pack(fill='x')
        self.buttons.append((choice, 'readonly'))
        cell = tk.Frame(fields, bg=C['paper'])
        cell.grid(row=0, column=1, sticky='ew')
        app.label(cell, '移调 · 半音', 9).pack(anchor='w', pady=(0, 8))
        step = NumberStepper(cell, self.transpose, -36, 36)
        step.pack(fill='x')
        self.buttons.append((step, 'normal'))
        self.track_frame = tk.Frame(editor, bg=C['paper'])
        self.track_frame.pack(fill='x', pady=(14, 0))
        app.label(editor, '以上设置只影响选段；全曲速度在「调整」页设置。', 9).pack(anchor='w', pady=(12, 0))
        footer = RoundedPanel(parent, padx=18, pady=10)
        footer.pack(side='bottom', fill='x', pady=(8, 0), before=area)
        actions = tk.Frame(footer, bg=C['paper'])
        actions.pack(fill='x')
        self.add_button(actions, '游戏试奏 A · 当前', lambda: self.try_in_game(False), 'trial').pack(side='left')
        self.add_button(actions, '游戏试奏 B · 候选', lambda: self.try_in_game(True), 'trial').pack(side='left', padx=8)
        self.trial_stop_button = app.button(actions, '停止试奏', app.stop, 'stop', 9)
        self.trial_stop_button.pack(side='left')
        self.add_button(actions, '应用到这段', self.apply, 'primary').pack(side='right')
        app.label(footer, '先打开对应乐器的 36 键界面；自动切回游戏并倒计时。每次最多 60 秒，F7 暂停／继续，F8 停止。',
                  9, wraplength=620, justify='left').pack(anchor='w', pady=(8, 0))
        app.label(footer, textvariable=self.note, size=9, wraplength=620, justify='left').pack(anchor='w', pady=(6, 0))

        saved = RoundedPanel(area.body, padx=20, pady=16)
        saved.pack(fill='x', pady=(0, 14))
        top = tk.Frame(saved, bg=C['paper'])
        top.pack(fill='x', pady=(0, 10))
        app.label(top, '已应用的片段', 11, bold=True).pack(side='left')
        self.remove_button = self.add_button(top, '恢复选中段', self.remove, 'nav')
        self.remove_button.pack(side='right')
        self.tree = ttk.Treeview(saved, columns=('range', 'mode', 'transpose'), show='headings',
                                 height=3, style='Desk.Treeview', selectmode='browse')
        for key, title, width in (('range', '原曲位置', 190), ('mode', '演奏方案', 240), ('transpose', '移调', 70)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=60, stretch=key != 'transpose')
        self.tree.pack(fill='x')
        self.tree.bind('<<TreeviewSelect>>', self.select_saved)

    def add_button(self, parent, text, command, kind='neutral'):
        button = self.app.button(parent, text, command, kind, 9)
        self.buttons.append((button, 'normal'))
        return button

    def range(self):
        start, end = parse_time(self.start.get()), parse_time(self.end.get())
        if self.app.song is None or not 0 <= start < end <= self.app.song.seconds + .000501:
            raise ValueError('请选择原曲范围内的起点与终点。')
        return start, min(end, self.app.song.seconds)

    def instrument_changed(self, _=None):
        self.app.update_score(quiet=True)
        self.note.set('已切换整首乐器，恢复该乐器的编排。接下来选区域，再调整。')

    def set_range(self, start, end):
        from .ui import position_label
        self.start.set(position_label(start))
        self.end.set(position_label(end))
        self.draw()

    def refresh(self):
        identity = (self.app.song_fingerprint, self.app.applied_instrument)
        if identity != self.identity:
            self.identity = identity
            self.history, self.future = [], []
            self.selected = None
            self.rendered_segments = None
            self.viewport = (0, max(.01, self.app.song.seconds if self.app.song else 1))
            self.cursor = 0
            self.mode.set(self.app.mode.get())
            self.transpose.set(self.app.transpose.get())
            self.set_range(0, min(8, self.viewport[1]))
            for widget in self.track_frame.winfo_children():
                # Only voice controls belong to this rebuild. The shared
                # backdrop also owns a decorative child of the same frame.
                if isinstance(widget, tk.Checkbutton):
                    widget.destroy()
            self.track_vars = {}
            if self.app.song:
                enabled = self.app.arrangement_settings()['tracks']
                for index, track in enumerate(self.app.song.track_info()):
                    variable = tk.BooleanVar(value=track['index'] in enabled)
                    self.track_vars[track['index']] = variable
                    choice = tk.Checkbutton(self.track_frame, text=track['name'][:20], variable=variable,
                                            bg=C['paper'], fg=C['ink'], activebackground=C['paper'],
                                            selectcolor=C['paper'], font=('Microsoft YaHei UI', 9), anchor='w')
                    choice.grid(row=index // 3, column=index % 3, sticky='w', padx=(0, 16))
        from .ui import position_label
        if self.rendered_segments != self.app.segment_edits:
            self.selected = None
            self.tree.delete(*self.tree.get_children())
            for index, segment in enumerate(self.app.segment_edits):
                self.tree.insert('', 'end', iid=str(index), values=(
                    position_label(segment['start']) + ' – ' + position_label(segment['end']),
                    self.modes[segment['mode']], f'{segment["transpose"]:+d}'))
            self.rendered_segments = deepcopy(self.app.segment_edits)
        self.draw()
        self.refresh_controls()

    def refresh_controls(self):
        ready = self.app.song is not None and self.app.active is None
        for control, state in self.buttons:
            self.app.enabled(control, ready, state)
        for choice in self.track_frame.winfo_children():
            if isinstance(choice, tk.Checkbutton):
                choice.configure(state='normal' if ready else 'disabled')
        self.app.enabled(self.undo_button, ready and bool(self.history))
        self.app.enabled(self.redo_button, ready and bool(self.future))
        self.app.enabled(self.remove_button, ready and self.selected is not None)
        trial = self.app.active and self.app.active.get('comparison')
        self.app.enabled(self.trial_stop_button, bool(trial) and not self.app.stop_requested)
        if trial:
            self.note.set(f'{trial} · {self.app.status.get()}')
        if not ready:
            self.drag = None
            self.timeline.configure(cursor='arrow')
        elif not self.drag:
            self.timeline.configure(cursor='crosshair')

    def x(self, seconds):
        left, right = self.viewport
        return 12 + (seconds - left) / max(.01, right - left) * max(1, self.timeline.winfo_width() - 24)

    def time_at(self, x):
        left, right = self.viewport
        value = left + max(0, min(1, (x - 12) / max(1, self.timeline.winfo_width() - 24))) * (right - left)
        # Gentle onset snapping gets more precise as the timeline is zoomed.
        candidates = getattr(self, 'onsets', [])
        index = bisect_left(candidates, value)
        nearby = candidates[max(0, index - 1):index + 1]
        if nearby:
            onset = min(nearby, key=lambda t: abs(t - value))
            if abs(onset - value) < (right - left) * .008:
                value = onset
        return round(value, 3)

    def draw(self):
        self.update_view_buttons()
        canvas = self.timeline
        if self.app.song is None:
            canvas.delete('all')
            self._drawing_song = self._drawing_key = None
            self._note_layers = {}
            self.onsets = []
            canvas.create_text(18, 55, text='从左侧导入一首曲谱，开始分段编排。', anchor='w', fill=C['ink'])
            return
        song = self.app.song
        height = int(canvas.cget('height'))
        top, bottom = 36, height - 30
        left, right = self.viewport
        key = (canvas.winfo_width(), height, self.viewport,
               tuple((segment['start'], segment['end']) for segment in self.app.segment_edits))
        if song is not self._drawing_song or key != self._drawing_key:
            # Source notes, ticks and applied-region marks do not change while
            # dragging a selection or cursor. Keep those native Canvas items.
            canvas.delete('all')
            self._note_layers = {}
            if song is not self._drawing_song:
                self.onsets = sorted({0.0, song.seconds, *(note.start for note in song.notes)})
            self._drawing_song, self._drawing_key = song, key
            from .ui import duration_label
            for index in range(6):
                value = left + (right - left) * index / 5
                canvas.create_text(self.x(value), 10, text=duration_label(value), fill=C['ink'],
                                   font=('Microsoft YaHei UI', 8), anchor='w' if index == 0 else 'e' if index == 5 else 'center')
            notes = [note for note in song.notes if note.start < right and note.end > left and note.channel != 9]
            low = min((note.pitch for note in notes), default=48)
            high = max((note.pitch for note in notes), default=84)
            starts = [segment['start'] for segment in self.app.segment_edits]
            layers, pens = {}, {}
            scale = max(1, canvas.winfo_width() - 24) / max(.01, right - left)
            for note in notes:
                y = bottom - 10 - (note.pitch - low) / max(1, high - low) * (bottom - top - 20)
                index = bisect_right(starts, note.start) - 1
                edited = index >= 0 and note.start < self.app.segment_edits[index]['end']
                tag = 'edited-note' if edited else 'unmodified-note'
                if tag not in layers:
                    layers[tag] = Image.new('RGBA', (max(1, canvas.winfo_width()), height))
                    pens[tag] = ImageDraw.Draw(layers[tag])
                pens[tag].line((12 + (max(left, note.start) - left) * scale, y,
                                12 + (min(right, note.end) - left) * scale, y),
                                fill=EDITED_COLOR if edited else C['teal'], width=2)
            # A fixed overview is cheap to compose as two transparent images.
            # Native scrolling then repaints images rather than thousands of
            # GDI lines. Selection and cursor remain live Canvas items.
            for tag, image in layers.items():
                self._note_layers[tag] = ImageTk.PhotoImage(image, master=canvas)
                canvas.create_image(0, 0, anchor='nw', image=self._note_layers[tag], tags=('source-note', tag))
            for segment in self.app.segment_edits:
                if segment['start'] < right and segment['end'] > left:
                    canvas.create_rectangle(self.x(max(left, segment['start'])), height - 16,
                                             self.x(min(right, segment['end'])), height - 3,
                                             fill=EDITED_COLOR, outline=C['paper'], width=2, tags='edited-region')
        canvas.delete('range-ui')
        canvas.delete('cursor-ui')
        try:
            start, end = self.range()
            canvas.create_rectangle(self.x(start), top, self.x(end), bottom, fill=C['bg'], outline='',
                                    tags=('range-ui', 'range-fill'))
            canvas.tag_lower('range-fill')
            for point in (start, end):
                canvas.create_line(self.x(point), top, self.x(point), bottom + 4, fill=C['teal'], width=2, tags='range-ui')
                canvas.create_oval(self.x(point) - 4, top - 4, self.x(point) + 4, top + 4,
                                   fill=C['teal'], outline='', tags='range-ui')
        except ValueError:
            pass
        x = self.x(self.cursor)
        canvas.create_line(x, 30, x, height - 2, fill=C['ink'], dash=(2, 3), tags='cursor-ui')
        canvas.create_polygon(x - 5, 24, x + 5, 24, x, 31, fill=C['ink'], outline='', tags='cursor-ui')
        canvas.create_text(x + 8 if x < canvas.winfo_width() - 50 else x - 8, 26, text='游标',
                           anchor='w' if x < canvas.winfo_width() - 50 else 'e',
                           fill=C['ink'], font=('Microsoft YaHei UI', 8), tags='cursor-ui')

    def hit_test(self, event):
        if self.app.song is None or self.app.active:
            return 'disabled'
        # The endpoint handles begin at y=32, just below the cursor ruler.
        if event.y < 32:
            return 'cursor'
        if event.y >= int(self.timeline.cget('height')) - 18:
            if self.region_at(event.x) is not None:
                return 'saved'
        try:
            start, end = self.range()
            if abs(event.x - self.x(start)) <= 8:
                return 'start'
            if abs(event.x - self.x(end)) <= 8:
                return 'end'
            if abs(event.x - self.x(self.cursor)) <= 5:
                return 'cursor'
            if self.x(start) < event.x < self.x(end):
                return 'move'
        except ValueError:
            pass
        return 'new'

    def region_at(self, x):
        value = self.viewport[0] + (x - 12) / max(1, self.timeline.winfo_width() - 24) * (self.viewport[1] - self.viewport[0])
        return next((index for index, segment in enumerate(self.app.segment_edits)
                     if segment['start'] <= value < segment['end']), None)

    def show_pointer(self, kind):
        cursor, hint = {
            'start': ('sb_h_double_arrow', '拖动左边界，调整片段起点；游标保持不变。'),
            'end': ('sb_h_double_arrow', '拖动右边界，调整片段终点；游标保持不变。'),
            'move': ('fleur', '拖动选区整体移动，保持片段长度。'),
            'cursor': ('hand2', '点击或拖动定位游标；选区保持不变，可在游标处分割。'),
            'saved': ('hand2', '点击橙色标记，选中已调整的片段继续编辑。'),
            'new': ('crosshair', '按住并拖动，框选一个新片段。'),
            'disabled': ('arrow', '先导入曲谱；游戏演奏结束后可编辑片段。'),
        }[kind]
        self.timeline.configure(cursor=cursor)
        self.guide.set(hint)

    def hover(self, event):
        if not self.drag:
            self.show_pointer(self.hit_test(event))

    def leave(self, _=None):
        if not self.drag:
            self.guide.set(TIMELINE_HELP)
            self.timeline.configure(cursor='arrow' if self.app.active or self.app.song is None else 'crosshair')

    def begin_selection(self, event):
        if self.app.song is None or self.app.active:
            return
        self.app.stop_preview()
        edge = self.hit_test(event)
        if edge == 'saved':
            index = self.region_at(event.x)
            self.tree.selection_set(str(index))
            self.select_saved()
            self.show_pointer(edge)
            return
        # The mouse anchor drives range edits independently of the cursor.
        anchor = self.time_at(event.x)
        if edge == 'cursor':
            self.cursor = anchor
        try:
            start, end = self.range()
        except ValueError:
            start, end = 0, self.app.song.seconds
        self.drag = (edge, anchor, start, end)
        self.show_pointer(edge)
        self.draw()

    def drag_selection(self, event):
        if not self.drag or self.app.active:
            return
        edge, anchor, start, end = self.drag
        value = self.time_at(event.x)
        if edge == 'cursor':
            self.cursor = value
            self.draw()
            return
        if edge == 'move':
            delta = max(-start, min(value - anchor, self.app.song.seconds - end))
            start, end = start + delta, end + delta
        elif edge == 'start':
            start = min(value, end - .01)
        elif edge == 'end':
            end = max(start + .01, value)
        else:
            start, end = min(anchor, value), max(anchor, value)
        if end > start:
            self.set_range(max(0, start), min(self.app.song.seconds, end))

    def end_selection(self, event):
        if self.drag:
            self.drag_selection(event)
        self.drag = None
        self.hover(event)

    def redraw_range(self):
        try:
            self.range()
            self.draw()
        except ValueError as error:
            self.note.set(str(error))

    def update_view_buttons(self):
        # Indicate the actual viewport, including resets and a selection that
        # already covers the whole song. Dragging leaves these styles cached.
        selected = None
        if self.app.song is not None:
            selected = ('full' if self.viewport[0] <= 0 and self.viewport[1] >= self.app.song.seconds
                        else 'selection')
        for mode, caption in (('selection', '放大选段'), ('full', '查看全曲')):
            active = mode == selected
            palette = (C['teal'], C['paper'], C['teal']) if active else (C['bg'], C['ink'], C['paper'])
            button = self.view_buttons[mode]
            if button.palette != palette:
                button.palette = palette
                button.configure(text=('✓ ' if active else '') + caption,
                                 activebackground=palette[2], activeforeground=palette[1])
                self.app.enabled(button, self.app.song is not None and self.app.active is None)

    def zoom(self):
        try:
            start, end = self.range()
            margin = (end - start) * .12
            self.viewport = (max(0, start - margin), min(self.app.song.seconds, end + margin))
            self.draw()
        except ValueError as error:
            self.note.set(str(error))

    def zoom_out(self):
        if self.app.song:
            self.viewport = (0, self.app.song.seconds)
            self.draw()

    def candidate(self):
        start, end = self.range()
        selected = [key for key, value in self.track_vars.items() if value.get()]
        if not selected:
            raise ValueError('请为这段保留至少一个声部。')
        return dict(start=start, end=end, mode=next(key for key, text in self.modes.items() if text == self.mode.get()),
                    transpose=int(self.transpose.get()), tracks=selected, name=self.name.get())

    def try_in_game(self, candidate):
        if not self.app.song or self.app.active:
            return
        try:
            start, end = self.range()
            settings = deepcopy(self.app.arrangement_settings())
            instrument = self.app.current_instrument().id
            if candidate:
                settings['segments'] = apply_region(settings['segments'], self.candidate())
            score = compile_arrangement(self.app.song, settings, instrument)
            # The converter may trim initial silence. Restore any part of that
            # silence inside this selection so A and B begin at the same time.
            origin = score['summary']['source_origin_seconds']
            if origin > start:
                lead = (origin - start) / settings['speed']
                for event in score['events']:
                    event['at'] += lead
                score['summary']['seconds'] += lead
                score['summary']['source_origin_seconds'] = start
            offset = max(0, (start - score['summary']['source_origin_seconds']) / settings['speed'])
            stop = (end - score['summary']['source_origin_seconds']) / settings['speed']
            if stop <= offset:
                raise ValueError('所选片段没有可演奏的音符，请调整选区或声部。')
            self.app.start_game_playback(score=score, start_at=offset, seconds=min(60, stop - offset),
                                         comparison='B 候选' if candidate else 'A 当前')
        except (ValueError, StopIteration) as error:
            self.note.set(str(error))

    def commit(self, segments):
        settings = deepcopy(self.app.arrangement_settings())
        settings['segments'] = segments
        from .performance import performance_plan
        performance_plan(compile_arrangement(self.app.song, settings, self.app.current_instrument().id), settings['hold_ms'])
        previous = deepcopy(self.app.segment_edits)
        self.app.stop_preview()
        self.history.append(previous)
        self.history = self.history[-40:]
        self.future = []
        self.app.segment_edits = segments
        self.app.update_score(quiet=True)

    def apply(self):
        if self.app.active:
            return
        try:
            candidate = self.candidate()
            self.commit(apply_region(self.app.segment_edits, candidate))
            self.note.set('已应用并自动保存，橙色表示已调整。可用“游戏试奏 A”复听当前编排。')
        except ValueError as error:
            self.note.set(str(error))

    def split(self):
        if self.app.song is None or self.app.active:
            return
        try:
            point = self.cursor
            if not .01 < point < self.app.song.seconds - .01:
                raise ValueError('先在时间轴点击曲目中间的位置，再分割。')
            settings = self.app.arrangement_settings()
            region = next((s for s in self.app.segment_edits if s['start'] < point < s['end']), None)
            if region is None:
                left = max((s['end'] for s in self.app.segment_edits if s['end'] <= point), default=0)
                right = min((s['start'] for s in self.app.segment_edits if s['start'] >= point), default=self.app.song.seconds)
                region = dict(start=left, end=right, name='片段', **{k: settings[k] for k in ('mode', 'transpose', 'tracks')})
            edits = apply_region(self.app.segment_edits, {**region, 'end': point})
            edits = apply_region(edits, {**region, 'start': point})
            self.commit(edits)
            self.set_range(point, region['end'])
            self.note.set('已分割。选择其中一段调整方案或移调。')
        except ValueError as error:
            self.note.set(str(error))

    def select_saved(self, _=None):
        selected = self.tree.selection()
        if not selected:
            return
        index = int(selected[0])
        if index == self.selected or index >= len(self.app.segment_edits):
            return
        self.selected = index
        segment = self.app.segment_edits[index]
        self.set_range(segment['start'], segment['end'])
        self.mode.set(self.modes[segment['mode']])
        self.transpose.set(str(segment['transpose']))
        for key, variable in self.track_vars.items():
            variable.set(key in segment['tracks'])
        self.refresh_controls()

    def remove(self):
        if self.selected is not None and not self.app.active:
            edits = [s for index, s in enumerate(self.app.segment_edits) if index != self.selected]
            self.selected = None
            self.commit(edits)
            self.note.set('这段已恢复为全曲默认设置。')

    def undo(self):
        if self.history and not self.app.active:
            self.app.stop_preview()
            self.future.append(deepcopy(self.app.segment_edits))
            self.app.segment_edits = self.history.pop()
            self.app.update_score(quiet=True)
            self.refresh()

    def redo(self):
        if self.future and not self.app.active:
            self.app.stop_preview()
            self.history.append(deepcopy(self.app.segment_edits))
            self.app.segment_edits = self.future.pop()
            self.app.update_score(quiet=True)
            self.refresh()

    def seek(self):
        try:
            start, _ = self.range()
            origin, speed, length = self.app.position_frame()
            self.app.seek_fraction((start - origin) / speed / max(.001, length))
        except ValueError as error:
            self.note.set(str(error))
