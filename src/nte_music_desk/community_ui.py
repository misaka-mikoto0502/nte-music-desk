"""Planned community page and an inactive development demo implementation."""
from copy import deepcopy
import hashlib
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from .appearance import COLORS as C, RoundedPanel
from .community import (CommunityDemo, encode, project_document, read_project,
                        request_json, validate_project, write_project)
from .instruments import INSTRUMENTS
from .notation import read_score
from .presets import DEFAULTS
from .workspace_pages import ScrollArea


class CommunityPage:
    """Keep the navigation slot without exposing unfinished community actions."""
    def __init__(self, app, parent):
        self.closed = False
        area = ScrollArea(parent)
        area.pack(fill='both', expand=True)
        self.canvas = area.canvas
        card = RoundedPanel(area.body, padx=28, pady=48)
        card.pack(fill='x', pady=(24, 0))
        app.label(card, '社区共创', 10, color=C['teal'], bold=True).pack()
        app.label(card, '计划实现', 22, bold=True).pack(pady=(12, 10))
        app.label(card, '这里将用于分享与交流优化后的编排。', 10).pack()

    def on_song_changed(self, project=None):
        pass

    def refresh_controls(self):
        pass

    def close(self):
        self.closed = True


class CommunityDemoPage:
    """Retained for development; the workbench does not instantiate this demo."""
    def __init__(self, app, parent):
        self.app, self.service, self.pending = app, None, False
        self.messages = queue.Queue()
        self.closed = False
        self.projects = []
        self.parent_id = ''
        self.download_revision = None
        self.endpoint = tk.StringVar(value='http://127.0.0.1:8765')
        self.title = tk.StringVar()
        self.author = tk.StringVar(value=app.preferences.get('community_author', ''))
        self.description = tk.StringVar()
        self.permission = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value='本机 Demo 可体验发布、浏览和下载，作品保存在这台电脑。')
        area = ScrollArea(parent)
        area.pack(fill='both', expand=True)
        self.canvas = area.canvas
        top = tk.Frame(area.body, bg=C['bg'])
        top.pack(fill='x', pady=(0, 12))
        app.label(top, '一起把曲子弹好', 18, bold=True).pack(side='left')
        app.button(top, '导入工程', self.import_file, 'nav', 9).pack(side='right')
        self.export_button = app.button(top, '导出我的编排', self.export_file, 'nav', 9)
        self.export_button.pack(side='right', padx=(0, 10))
        connect = RoundedPanel(area.body, padx=18, pady=16)
        connect.pack(fill='x', pady=(0, 12))
        row = tk.Frame(connect, bg=C['paper'])
        row.pack(fill='x')
        self.address = ttk.Entry(row, textvariable=self.endpoint)
        self.address.pack(side='left', fill='x', expand=True, padx=(0, 10))
        self.refresh_button = app.button(row, '连接 / 刷新', self.reload, size=9)
        self.refresh_button.pack(side='right')
        self.demo_button = app.button(row, '本机 Demo', self.start_demo, 'preview', 9)
        self.demo_button.pack(side='right', padx=(0, 8))
        app.label(connect, textvariable=self.status, size=9, wraplength=640, justify='left').pack(anchor='w', pady=(10, 0))

        library = RoundedPanel(area.body, padx=18, pady=16)
        library.pack(fill='x', pady=(0, 12))
        self.tree = ttk.Treeview(library, columns=('title', 'author', 'instrument', 'segments'),
                                 show='headings', height=4, style='Desk.Treeview', selectmode='browse')
        for key, caption, width in (('title', '作品', 220), ('author', '编排者', 130),
                                     ('instrument', '乐器', 100), ('segments', '分段', 50)):
            self.tree.heading(key, text=caption)
            self.tree.column(key, width=width, minwidth=45, stretch=key in ('title', 'author'))
        self.tree.pack(fill='x')
        self.tree.bind('<<TreeviewSelect>>', self.select)
        self.tree.bind('<Double-1>', lambda _: self.download())
        self.detail = tk.StringVar(value='选择作品查看说明，再下载到曲目列表。')
        app.label(library, textvariable=self.detail, size=9, wraplength=620, justify='left').pack(anchor='w', pady=(12, 0))
        row = tk.Frame(library, bg=C['paper'])
        row.pack(fill='x', pady=(12, 0))
        self.download_button = app.button(row, '下载并载入', self.download, 'primary', 10)
        self.download_button.pack(side='right')

        publish = RoundedPanel(area.body, padx=18, pady=16)
        publish.pack(fill='x', pady=(0, 16))
        app.label(publish, '分享当前编排', 11, bold=True).pack(anchor='w')
        form = tk.Frame(publish, bg=C['paper'])
        form.pack(fill='x', pady=(12, 0))
        form.columnconfigure(0, weight=2)
        form.columnconfigure(1, weight=1)
        for column, (caption, variable) in enumerate((('作品名称', self.title), ('编排者', self.author))):
            box = tk.Frame(form, bg=C['paper'])
            box.grid(row=0, column=column, sticky='ew', padx=(0, 12) if column == 0 else 0)
            app.label(box, caption, 9).pack(anchor='w', pady=(0, 5))
            ttk.Entry(box, textvariable=variable).pack(fill='x')
        self.description_entry = ttk.Entry(publish, textvariable=self.description)
        self.description_entry.pack(fill='x', pady=(12, 8))
        self.description.set('')
        app.label(publish, '说明可写改进了哪个片段，方便其他人接着调整。', 9).pack(anchor='w')
        row = tk.Frame(publish, bg=C['paper'])
        row.pack(fill='x', pady=(12, 0))
        tk.Checkbutton(row, text='我有权分享工程内的曲谱与编排', variable=self.permission,
                       bg=C['paper'], fg=C['ink'], activebackground=C['paper'],
                       selectcolor=C['paper'], font=('Microsoft YaHei UI', 9)).pack(side='left')
        self.publish_button = app.button(row, '发布作品', self.publish, 'primary', 10)
        self.publish_button.pack(side='right')
        self.poll_id = app.root.after(100, self.poll)

    def on_song_changed(self, project=None):
        self.parent_id = project['parent'] if project else ''
        self.title.set(self.app.song.title + ' · 我的编排')
        self.description.set(project['description'] if project else '')
        self.permission.set(False)

    def refresh_controls(self):
        ready = bool(self.app.song) and self.app.active is None
        self.app.enabled(self.export_button, ready and not self.pending)
        self.app.enabled(self.publish_button, ready and not self.pending)
        self.app.enabled(self.download_button, bool(self.tree.selection()) and not self.pending and self.app.active is None)
        self.app.enabled(self.refresh_button, not self.pending)
        self.app.enabled(self.demo_button, not self.pending)
        self.address.configure(state='disabled' if self.pending else 'normal')
        if self.app.song and not self.title.get():
            self.title.set(self.app.song.title + ' · 我的编排')

    def start_demo(self):
        try:
            if self.service is None:
                self.service = CommunityDemo(self.app.directory / 'community-demo')
                if not self.service.list_projects():
                    song = read_score(self.app.assets / 'scores/twinkle.mid')
                    settings = {**deepcopy(DEFAULTS), 'mode': 'faithful', 'tracks': [p['index'] for p in song.track_info()]}
                    for instrument, caption, mode in (('guitar', '小星星 · 明亮和弦', 'chords'),
                                                       ('piano', '小星星 · 前后两段', 'melody')):
                        local = deepcopy(settings)
                        local['segments'] = [dict(start=song.seconds / 2, end=song.seconds,
                                                   mode=mode, transpose=0, tracks=local['tracks'], name='后半段')]
                        project = project_document(song, local, instrument, title=caption, author='工作台示例',
                                                   description='自行编码的小星星示例。下载后可在「分段」页继续编辑，再发布你的版本。')
                        self.service.publish(project)
            self.endpoint.set(self.service.endpoint)
            self.reload()
        except (OSError, ValueError) as error:
            self.status.set(str(error))

    def run(self, kind, operation):
        if self.pending:
            return
        self.pending = True
        self.status.set('正在连接社区…' if kind == 'list' else '正在发布…' if kind == 'publish' else '正在下载工程…')
        self.refresh_controls()

        def worker():
            try:
                self.messages.put((kind, operation(), None))
            except Exception as error:
                self.messages.put((kind, None, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def reload(self):
        endpoint = self.endpoint.get()
        self.run('list', lambda: request_json(endpoint))

    def select(self, _=None):
        selection = self.tree.selection()
        if selection:
            item = self.projects[int(selection[0])]
            prefix = '基于已有作品改编。' if item.get('parent') else ''
            self.detail.set(prefix + item.get('description', ''))
        self.refresh_controls()

    def download(self):
        selection = self.tree.selection()
        if not selection or self.app.active or self.pending:
            return
        endpoint = self.endpoint.get()
        key = self.projects[int(selection[0])]['id']
        if len(key) != 64 or any(c not in '0123456789abcdef' for c in key):
            self.status.set('社区作品标识无效。')
            return
        self.download_revision = self.app.song_revision
        self.run('download', lambda: request_json(endpoint, '/projects/' + key))

    def document(self):
        if self.app.song is None:
            raise ValueError('先导入一首曲谱，完成编排后再分享。')
        return project_document(self.app.song, self.app.arrangement_settings(), self.app.current_instrument().id,
                                 title=self.title.get(), author=self.author.get(),
                                 description=self.description.get(), parent=self.parent_id)

    def publish(self):
        if self.app.active:
            return
        if not self.permission.get():
            self.status.set('发布前请确认有权分享工程内的曲谱。工程包含音符和分段设置。')
            return
        try:
            project = self.document()
            endpoint = self.endpoint.get()
            self.app.preferences['community_author'] = project['author']
            self.app.save_preferences()
            self.run('publish', lambda: request_json(endpoint, project=project))
        except ValueError as error:
            self.status.set(str(error))

    def load_document(self, document, *, origin='', auto_load=True):
        project = validate_project(document)
        directory = self.app.directory / 'shared-projects'
        directory.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(encode(project)).hexdigest()
        path = directory / (key + '.nteproject')
        if origin:
            project['parent'] = origin
        write_project(path, project)
        if self.app.active or not auto_load:
            saved = self.app.preferences.get('shelf_files', [])
            if not isinstance(saved, list):
                saved = []
            self.app.preferences['shelf_files'] = [dict(path=str(path), title=project['title']),
                                                  *(item for item in saved if isinstance(item, dict) and item.get('path') != str(path))]
            self.app.refresh_library()
            self.app.save_preferences()
            self.status.set('工程已下载到曲目列表。当前曲目继续保留，可稍后选取新工程。')
            return
        if self.app.open_path(path):
            self.parent_id = origin or project['parent']
            self.title.set(project['title'])
            self.author.set(self.app.preferences.get('community_author', ''))
            self.description.set(project['description'])
            self.permission.set(False)
            self.app.show_page('segments')
            self.app.set_status('共享工程已载入，可以试听或继续分段编排。')

    def export_file(self):
        if self.app.active:
            return
        try:
            from .ui import export_name
            if not self.title.get() and self.app.song:
                self.title.set(self.app.song.title)
            author = self.author.get()
            if not author.strip():
                self.author.set('未署名')
            document = self.document()
            path = filedialog.asksaveasfilename(parent=self.app.root, title='导出演奏工程',
                                                defaultextension='.nteproject', initialfile=export_name(document['title']) + '.nteproject',
                                                filetypes=[('工作台演奏工程', '*.nteproject')])
            if path:
                write_project(path, document)
                self.status.set('已导出演奏工程，包含原始音符及分段设置。')
        except (ValueError, OSError) as error:
            self.status.set(str(error))

    def import_file(self):
        if self.app.active:
            return
        path = filedialog.askopenfilename(parent=self.app.root, title='导入演奏工程',
                                          filetypes=[('工作台演奏工程', '*.nteproject')])
        if path:
            try:
                self.load_document(read_project(path))
            except (ValueError, OSError) as error:
                self.status.set(str(error))

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                kind, value, error = self.messages.get_nowait()
                self.pending = False
                if error:
                    self.status.set(error)
                elif kind == 'list':
                    projects = value.get('projects') if isinstance(value, dict) else None
                    if (not isinstance(projects, list) or len(projects) > 200
                            or any(not isinstance(p, dict)
                                   or any(not isinstance(p.get(k, ''), str) or len(p.get(k, '')) > maximum
                                          for k, maximum in (('id', 64), ('title', 120), ('author', 80),
                                                             ('description', 1500), ('instrument', 40), ('parent', 64)))
                                   or len(p.get('id', '')) != 64
                                   or any(c not in '0123456789abcdef' for c in p.get('id', ''))
                                   or type(p.get('segments', 0)) is not int or not 0 <= p.get('segments', 0) <= 128
                                   for p in projects)):
                        self.status.set('社区列表格式无效。')
                        self.refresh_controls()
                        continue
                    self.projects = projects
                    self.tree.delete(*self.tree.get_children())
                    for index, item in enumerate(self.projects):
                        profile = INSTRUMENTS.get(item.get('instrument'), INSTRUMENTS['guitar'])
                        self.tree.insert('', 'end', iid=str(index), values=(item.get('title', '')[:120],
                                         item.get('author', '')[:80], '钢琴' if profile.id == 'piano' else '吉他钢琴', item.get('segments', 0)))
                    self.status.set(('本机 Demo · 作品保存在这台电脑。' if value.get('demo') else '已连接社区。')
                                    + f' 共 {len(projects)} 个作品。')
                elif kind == 'publish':
                    self.status.set('作品已发布，其他连接同一服务的工作台可下载。')
                    self.reload()
                elif kind == 'download':
                    try:
                        self.load_document(value['project'], origin=value['id'],
                                           auto_load=(self.download_revision == self.app.song_revision
                                                      and self.app.current_page == 'community'
                                                      and not self.app.playback_busy()))
                    except (ValueError, KeyError, OSError) as exception:
                        self.status.set(str(exception))
                self.refresh_controls()
        except queue.Empty:
            pass
        self.poll_id = self.app.root.after(100, self.poll)

    def close(self):
        self.closed = True
        self.app.root.after_cancel(self.poll_id)
        if self.service:
            self.service.close()
