"""Shared voice controls and a multi-track overview, backed by source notes."""
import tkinter as tk
from tkinter import ttk
from .parts import ROLE_NAMES
from .appearance import RoundedPanel, RoundedButton, COLORS as C


def action(parent, text, command):
    return RoundedButton(parent, text=text, command=command, bg=C['blue_light'], fg=C['ink'],
                         activebackground='#DAE4D6', font=('Microsoft YaHei UI', 9), padx=12, pady=7)

COLORS = ('#32634F', '#537766', '#A5814C', '#897A8E', '#AD7666', '#71855F')


class TrackPanel(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, bg='#FCFBF7')
        self.rows, self.enabled_rows, self.roles = [], set(), {}
        self.focused, self.disabled, self.song = 0, False, None
        self.views, self.window, self.timeline, self.playhead = [], None, None, 0
        self.tree = self.make_tree(self, compact=True)

    def make_tree(self, parent, compact=False):
        frame = tk.Frame(parent, bg='#FCFBF7')
        frame.pack(fill='both', expand=True)
        columns = ('enabled', 'name', 'instrument') if compact else ('enabled', 'name', 'instrument', 'channel', 'role', 'notes', 'range')
        tree = ttk.Treeview(frame, columns=columns, show='headings', height=4 if compact else 7,
                            selectmode='browse', style='Desk.Treeview')
        widths = {'enabled': 42, 'name': 120, 'instrument': 150, 'channel': 90, 'role': 75, 'notes': 65, 'range': 110}
        titles = {'enabled': '启用', 'name': '声部', 'instrument': '原乐器', 'channel': '原轨 / 通道', 'role': '角色', 'notes': '音符', 'range': '音域'}
        for col in columns:
            tree.heading(col, text=titles[col])
            tree.column(col, width=widths[col], minwidth=widths[col] if col == 'enabled' else 50, stretch=col in ('name', 'instrument'))
        bar = ttk.Scrollbar(frame, command=tree.yview)
        bar.pack(side='right', fill='y')
        tree.configure(yscrollcommand=bar.set)
        tree.pack(fill='both', expand=True)
        tree.tag_configure('muted', foreground='#93A0AF')
        tree.bind('<Button-1>', lambda event: self.click(event, tree))
        tree.bind('<<TreeviewSelect>>', lambda _: self.focus(tree))
        self.views.append((tree, columns))
        return tree

    def configure(self, cnf=None, **kwargs):
        state = kwargs.pop('state', None)
        if state is not None:
            self.disabled = state == 'disabled'
            if self.window is not None and self.window.winfo_exists() and self.disabled:
                self.window.destroy()
        if cnf or kwargs:
            return super().configure(cnf, **kwargs)
    config = configure

    def load_song(self, song):
        self.song = song
        self.rows = song.track_info(include_drums=True)
        self.enabled_rows = {i for i, row in enumerate(self.rows) if not row['drums']}
        self.roles = {str(row['index']): row['role'] for row in self.rows}
        self.focused = 0
        self.render()

    def curselection(self):
        return tuple(sorted(self.enabled_rows))

    def index(self, value):
        return self.focused if value == 'active' else int(value)

    def selection_clear(self, *_):
        self.enabled_rows.clear()
        self.render()

    def set_enabled_tracks(self, tracks):
        selected = set(tracks)
        self.enabled_rows = {i for i, row in enumerate(self.rows) if not row['drums'] and row['index'] in selected}
        self.focused = min(self.enabled_rows, default=0)
        self.render()

    def selection_set(self, index):
        index = int(index)
        if not self.rows[index]['drums']:
            self.enabled_rows.add(index)
        self.focused = index
        self.render()

    def notify(self):
        self.render()
        self.event_generate('<<ListboxSelect>>')

    def focus(self, tree):
        if tree.selection():
            self.focused = int(tree.selection()[0])

    def click(self, event, tree):
        if self.disabled:
            return 'break'
        row = tree.identify_row(event.y)
        if row and tree.identify_column(event.x) == '#1':
            index = int(row)
            self.focused = index
            if not self.rows[index]['drums']:
                self.enabled_rows.symmetric_difference_update({index})
                self.notify()
            return 'break'

    def render(self):
        from .midi import note_name
        live_views = []
        for tree, columns in self.views:
            if not tree.winfo_exists():
                continue
            live_views.append((tree, columns))
            for i, row in enumerate(self.rows):
                values = {'enabled': '●' if i in self.enabled_rows else '○', 'name': row['name'],
                          'instrument': row['instrument'], 'channel': f'{row["source_track"] + 1} / {row["channel"] + 1}',
                          'role': '鼓组' if row['drums'] else ROLE_NAMES[self.roles[str(row['index'])]],
                          'notes': row['notes'], 'range': f'{note_name(row["low"])}–{note_name(row["high"])}'}
                options = {'values': tuple(values[c] for c in columns), 'tags': () if i in self.enabled_rows else ('muted',)}
                if tree.exists(str(i)):
                    tree.item(str(i), **options)
                else:
                    tree.insert('', 'end', iid=str(i), **options)
            for item in tree.get_children():
                if int(item) >= len(self.rows):
                    tree.delete(item)
        self.views = live_views
        if self.timeline is not None and self.timeline.winfo_exists():
            self.draw_timeline()

    def show_workspace(self):
        if self.disabled or self.song is None:
            return
        if self.window is not None and self.window.winfo_exists():
            self.window.lift()
            return
        window = self.window = tk.Toplevel(self)
        window.title('多轨工作区 · ' + self.song.title)
        window.geometry('1080x700')
        window.minsize(850, 600)
        window.configure(bg='#EDECE6')
        tk.Label(window, text='声部与原曲总览', font=('Microsoft YaHei UI', 18, 'bold'), bg='#EDECE6', fg='#273B36').pack(anchor='w', padx=20, pady=(18, 5))
        tk.Label(window, text='点击启用列开关声部 · 选择一行后可独奏或指定角色 · 原轨与通道使用 1 起始编号', bg='#EDECE6', fg='#738078').pack(anchor='w', padx=20, pady=(0, 12))
        controls = tk.Frame(window, bg='#EDECE6')
        controls.pack(fill='x', padx=20, pady=(0, 10))
        def all_parts():
            self.enabled_rows = {i for i, p in enumerate(self.rows) if not p['drums']}
            self.notify()
        def solo():
            if self.rows and not self.rows[self.focused]['drums']:
                self.enabled_rows = {self.focused}
                self.notify()
        action(controls, '启用全部乐音声部', all_parts).pack(side='left', padx=(0, 8))
        action(controls, '独奏当前声部', solo).pack(side='left', padx=(0, 15))
        role = ttk.Combobox(controls, values=list(ROLE_NAMES.values()), width=9, state='readonly')
        role.set('主旋律')
        role.pack(side='left')
        def set_role():
            if self.rows and not self.rows[self.focused]['drums']:
                self.roles[str(self.rows[self.focused]['index'])] = next(k for k, v in ROLE_NAMES.items() if v == role.get())
                self.notify()
        action(controls, '应用角色', set_role).pack(side='left', padx=8)
        area = RoundedPanel(window, padx=12, pady=12)
        area.pack(fill='both', expand=True, padx=20)
        self.make_tree(area)
        overview = RoundedPanel(window, padx=12, pady=12)
        overview.pack(fill='both', expand=True, padx=20, pady=(12, 8))
        self.timeline = tk.Canvas(overview, height=190, bg='#F5F4ED', highlightthickness=0)
        bar = ttk.Scrollbar(overview, command=self.timeline.yview)
        bar.pack(side='right', fill='y')
        self.timeline.configure(yscrollcommand=bar.set)
        self.timeline.pack(fill='both', expand=True)
        self.timeline.bind('<Configure>', lambda _: self.draw_timeline())
        tk.Label(window, text='彩色为启用声部，灰色为静音；总览对密集音符做显示聚合，演奏数据保持完整。', bg='#EDECE6', fg='#738078').pack(anchor='w', padx=20, pady=(0, 12))
        self.render()

    def draw_timeline(self):
        if not self.song or not self.timeline.winfo_exists():
            return
        canvas = self.timeline
        canvas.delete('all')
        width, left = max(600, canvas.winfo_width()), 175
        scale = (width - left - 20) / max(1, self.song.seconds)
        canvas.create_text(10, 12, text='原曲时间 / 秒', anchor='w', fill='#738078')
        for step in range(6):
            x = left + (width - left - 20) * step / 5
            canvas.create_text(x, 12, text=f'{self.song.seconds * step / 5:.1f}', fill='#738078')
            canvas.create_line(x, 25, x, len(self.rows) * 36 + 30, fill='#DDDCD2')
        by_track = {}
        for note in self.song.notes:
            by_track.setdefault(note.track, []).append(note)
        for i, row in enumerate(self.rows):
            y = 30 + i * 36
            color = COLORS[i % len(COLORS)] if i in self.enabled_rows else '#BCC5D0'
            canvas.create_text(8, y + 14, text=f'{i + 1:02d}  {row["name"][:15]}', anchor='w', fill=color)
            notes = by_track.get(row['index'], [])
            stride = max(1, (len(notes) + 1999) // 2000)
            for note in notes[::stride]:
                height = y + 24 - 19 * (note.pitch - row['low']) / max(1, row['high'] - row['low'])
                canvas.create_rectangle(left + note.start * scale, height, max(left + note.start * scale + 1, left + note.end * scale), height + 3, outline='', fill=color)
        canvas.configure(scrollregion=(0, 0, width, len(self.rows) * 36 + 30))
        self.set_playhead(self.playhead)

    def set_playhead(self, seconds):
        self.playhead = seconds
        if self.timeline is not None and self.timeline.winfo_exists() and self.song:
            canvas = self.timeline
            canvas.delete('playhead')
            x = 175 + (max(600, canvas.winfo_width()) - 195) * seconds / max(1, self.song.seconds)
            canvas.create_line(x, 25, x, len(self.rows) * 36 + 30, fill='#D14D5A', width=2, tags='playhead')
