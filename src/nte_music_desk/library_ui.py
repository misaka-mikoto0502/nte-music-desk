"""Search/download library window, sharing the performance desk's visual style."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk
import uuid
import webbrowser

from .catalog import Cancelled, DownloadResult, SOURCES, safe_url
from .ui import C, FONT, Tooltip, duration_label


def local_date(value):
    try:
        return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    except (ValueError, TypeError):
        return "—"


class OnlineLibrary:
    def __init__(self, app):
        self.app, self.client = app, app.online_client
        self.window = tk.Toplevel(app.root)
        self.window.title("在线曲库 · 搜索并导入 MIDI")
        self.window.configure(bg=C["bg"])
        width, height = min(1060, app.root.winfo_screenwidth()-80), min(740, app.root.winfo_screenheight()-100)
        x = max(12, min(app.root.winfo_rootx() + (app.root.winfo_width()-width)//2, app.root.winfo_screenwidth()-width-12))
        y = max(12, min(app.root.winfo_rooty() + (app.root.winfo_height()-height)//2, app.root.winfo_screenheight()-height-40))
        self.window.geometry(f"{width}x{height}+{x}+{y}")
        self.window.minsize(860, 600)
        self.window.transient(app.root)
        self.messages = queue.Queue()
        self.token, self.cancel, self.busy, self.closed = None, None, False, False
        self.hits, self.local_items = {}, {}
        self.query = tk.StringVar()
        self.source = tk.StringVar(value="全部曲库")
        self.status = tk.StringVar(value="输入曲名开始搜索，或点击下方的示例关键词。")
        self.selection_text = tk.StringVar(value="选择一个版本，下载后自动分析音轨并载入演奏页。")
        self.build_layout()
        self.reload_downloaded()
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.bind("<Escape>", lambda _: self.close())
        self.window.grab_set()
        self.entry.focus_set()
        self.poll_job = self.window.after(100, self.poll)
        self.refresh_controls()

    def build_layout(self):
        app = self.app
        outer = tk.Frame(self.window, bg=C["bg"], padx=24, pady=20)
        outer.pack(fill="both", expand=True)
        top = tk.Frame(outer, bg=C["bg"])
        top.pack(fill="x")
        app.label(top, "在线曲库", 22, bold=True).pack(side="left")
        self.refresh_button = app.button(top, "更新目录", self.refresh_catalogs, size=9,
                                          tip="联网更新三个公开曲库的清单。\n只更新目录，选择曲目后才下载 MIDI 文件。")
        self.refresh_button.pack(side="right")
        app.label(outer, "搜曲名 → 选择版本 → 下载并导入", 11, C["teal"], True).pack(anchor="w", pady=(7, 4))
        app.label(outer, "Mutopia 古典与钢琴 + BitMidi + 动漫公开目录 · 支持中文曲名和作曲家别名", 9, C["muted"]).pack(anchor="w", pady=(0, 17))
        row = tk.Frame(outer, bg=C["bg"])
        row.pack(fill="x")
        self.entry = tk.Entry(row, textvariable=self.query, font=(FONT, 12), relief="solid", borderwidth=1,
                              bg=C["paper"], fg=C["ink"], insertbackground=C["teal"])
        self.entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 9))
        self.entry.bind("<Return>", lambda _: self.search())
        self.source_box = ttk.Combobox(row, textvariable=self.source, values=["全部曲库", *SOURCES.values()], state="readonly", width=15)
        self.source_box.pack(side="left", padx=(0, 9), ipady=5)
        self.search_button = app.button(row, "搜索曲目", self.search, "primary", 11,
                                         "按曲名或关键词搜索，支持部分常用曲目的中英日别名。\n也可按 Enter 搜索。")
        self.search_button.pack(side="left")
        examples = tk.Frame(outer, bg=C["bg"])
        examples.pack(fill="x", pady=(8, 12))
        app.label(examples, "试试：", 9, C["muted"]).pack(side="left")
        self.example_buttons = []
        for title in ("致爱丽丝", "贝多芬 月光", "肖邦 夜曲", "巴赫 前奏曲"):
            button = app.button(examples, title, lambda text=title: self.use_example(text,"Mutopia 古典"), size=8)
            button.configure(pady=3, padx=9)
            button.pack(side="left", padx=(0, 6))
            self.example_buttons.append(button)

        style = ttk.Style(self.window)
        style.configure("Library.TNotebook", background=C["bg"], borderwidth=0)
        style.configure("Library.TNotebook.Tab", padding=(17, 9), font=(FONT, 10), background="#E8EDF4", foreground=C["muted"])
        style.map("Library.TNotebook.Tab", background=[("selected", "white")], foreground=[("selected", C["teal"])])
        style.configure("Desk.Treeview.Heading", background="#F5F8FC", foreground=C["muted"], borderwidth=0, relief="flat")
        self.notebook = ttk.Notebook(outer, style="Library.TNotebook")
        self.notebook.pack(fill="both", expand=True)
        self.online_tab = tk.Frame(self.notebook, bg=C["paper"])
        self.downloaded_tab = tk.Frame(self.notebook, bg=C["paper"])
        self.notebook.add(self.online_tab, text="在线搜索")
        self.notebook.add(self.downloaded_tab, text="已下载 · 0")
        self.notebook.bind("<<NotebookTabChanged>>", self.tab_changed)
        self.results = self.make_tree(self.online_tab, [("title", "曲目与版本", 370), ("source", "来源", 130), ("key", "作曲家 / 文件标识", 350)])
        self.saved = self.make_tree(self.downloaded_tab, [("title", "已下载曲目", 370), ("seconds", "旋律版时长", 120), ("source", "来源", 130), ("date", "保存日期", 150)])
        for tree in (self.results, self.saved):
            tree.bind("<<TreeviewSelect>>", self.selected)
            tree.bind("<Double-1>", lambda _: self.import_selected())
        footer = tk.Frame(outer, bg=C["bg"])
        footer.pack(side="bottom", fill="x", before=self.notebook, pady=(12, 0))
        self.status_label = app.label(footer, size=9, color=C["muted"], textvariable=self.status,
                                      wraplength=970, justify="left", anchor="w")
        self.status_label.pack(fill="x")
        selected = app.card(footer)
        selected.pack(fill="x", pady=(10, 0))
        app.label(selected, size=10, textvariable=self.selection_text, wraplength=920, justify="left", anchor="w").pack(fill="x")
        buttons = tk.Frame(footer, bg=C["bg"])
        buttons.pack(fill="x", pady=(12, 0))
        self.close_button = app.button(buttons, "返回演奏", self.close, size=10)
        self.close_button.pack(side="left")
        self.page_button = app.button(buttons, "查看来源网页 ↗", self.open_source, size=9,
                                       tip="在浏览器中打开当前曲目的原始网页。")
        self.page_button.pack(side="left", padx=8)
        self.import_button = app.button(buttons, "↓  下载并导入", self.import_selected, "primary", 12,
                                         "保存 MIDI 到本机，自动载入曲谱并选择推荐旋律轨。")
        self.import_button.pack(side="right")
        self.cancel_button = app.button(buttons, "取消操作", self.cancel_operation, "stop", 10)
        self.cancel_button.pack(side="right", padx=9)

    def make_tree(self, parent, columns):
        frame = tk.Frame(parent, bg=C["paper"])
        frame.pack(fill="both", expand=True, padx=1, pady=1)
        tree = ttk.Treeview(frame, columns=[c[0] for c in columns], show="headings", style="Desk.Treeview", selectmode="browse")
        for column, text, width in columns:
            tree.heading(column, text=text)
            tree.column(column, width=width, minwidth=90, anchor="w")
        ybar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        xbar = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        tree.grid(row=0, column=0, sticky="nsew")
        ybar.grid(row=0, column=1, sticky="ns")
        xbar.grid(row=1, column=0, sticky="ew")
        return tree

    def is_local(self):
        return self.notebook.select() == str(self.downloaded_tab)

    def tab_changed(self, _=None):
        if self.closed:
            return
        if self.is_local():
            self.reload_downloaded()
            self.status.set("这些曲目已保存在本机，可直接载入，无需重复下载。")
        self.selected()
        self.refresh_controls()

    def current_item(self):
        tree, items = (self.saved, self.local_items) if self.is_local() else (self.results, self.hits)
        selection = tree.selection()
        return items.get(selection[0]) if selection else None

    def selected(self, _=None):
        item = self.current_item()
        if item is None:
            self.selection_text.set("选择一个版本，下载后自动分析音轨并载入演奏页。")
        elif self.is_local():
            path, data = item
            summary = data.get("summary", {})
            summary = summary if isinstance(summary, dict) else {}
            self.selection_text.set(f'{data["title"]}\n已下载 · {summary.get("notes", "—")} 音 · 保存于 {path.name}')
        else:
            size = f" · {item.size / 1024:.1f} KB" if item.size else ""
            details = f"{item.composer} · {item.instrument} · {item.license}" if item.source=="mutopia" else f"{SOURCES[item.source]}{size} · 导入时自动分析音轨和音域"
            if item.download_path.lower().endswith(".zip"):
                details += "\n多乐章 ZIP：默认载入第一首，其余乐章可从已下载页切换。"
            self.selection_text.set(f"{item.title}\n{details}")
        self.refresh_controls()

    def refresh_controls(self):
        if not hasattr(self, "cancel_button"):
            return
        for widget in [self.entry, self.search_button, self.refresh_button, *self.example_buttons]:
            self.app.enabled(widget, not self.busy)
        self.app.enabled(self.source_box, not self.busy and not self.is_local(), "readonly")
        self.app.enabled(self.import_button, not self.busy and self.current_item() is not None)
        self.app.enabled(self.page_button, not self.busy and self.current_item() is not None)
        self.app.enabled(self.cancel_button, self.busy)
        self.import_button.configure(text="载入曲目" if self.is_local() else "↓  下载并导入")
        self.search_button.configure(text="筛选曲目" if self.is_local() else "搜索曲目")

    def use_example(self, text, source=None):
        if not self.busy:
            if source:self.source.set(source)
            self.notebook.select(self.online_tab)
            self.query.set(text)
            self.search()

    def begin(self):
        if self.busy:
            return None
        self.token, self.cancel = uuid.uuid4().hex, threading.Event()
        self.busy = True
        self.status_label.configure(fg=C["blue"])
        self.refresh_controls()
        return self.token, self.cancel

    def search(self):
        if self.busy:
            return
        if self.is_local():
            self.reload_downloaded(self.query.get())
            self.status.set(f"当前显示 {len(self.local_items)} 首已下载曲目。")
            return
        query = self.query.get().strip()
        if not 2 <= len(query) <= 120:
            self.status.set("请输入 2–120 个字的曲名或关键词。")
            self.status_label.configure(fg=C["amber"])
            return
        state = self.begin()
        if state is None:
            return
        token, cancel = state
        source = {"全部曲库": "all", **{name:key for key,name in SOURCES.items()}}[self.source.get()]
        self.status.set("正在检索曲库清单…")

        def worker():
            try:
                result = self.client.search(query, source, cancel)
                self.messages.put((token, "search", result))
            except Exception as error:
                self.messages.put((token, "error", str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def render_results(self, result):
        self.results.delete(*self.results.get_children())
        self.hits = {}
        for index, entry in enumerate(result.entries):
            iid = str(index)
            self.hits[iid] = entry
            self.results.insert("", "end", iid=iid, values=(entry.title, SOURCES[entry.source], entry.composer or entry.key))
        if self.hits:
            self.results.selection_set("0")
            self.results.focus("0")
        date = local_date(result.updated_at)
        self.status.set(f"找到 {result.total:,} 个版本，显示前 {len(result.entries)} 个 · 已索引 {result.catalog_count:,} 条 · 目录更新 {date}" if result.entries else
                        "没有找到匹配曲目。可试试英文、日文、拼音或更短的关键词，也可更新目录。")
        self.status_label.configure(fg=C["muted"] if result.entries else C["amber"])
        self.selected()

    def reload_downloaded(self, query=""):
        from .catalog import normalized
        self.saved.delete(*self.saved.get_children())
        self.local_items = {}
        records = self.client.downloaded()
        self.notebook.tab(self.downloaded_tab, text=f"已下载 · {len(records)}")
        for path, data in records:
            if query and normalized(query) not in normalized(data["title"]):
                continue
            iid = str(len(self.local_items))
            self.local_items[iid] = (path, data)
            summary = data.get("summary", {})
            summary = summary if isinstance(summary, dict) else {}
            length = summary.get("seconds", 0)
            length = length if isinstance(length, (int, float)) else 0
            self.saved.insert("", "end", iid=iid, values=(data["title"], duration_label(length), SOURCES.get(data.get("source"), "本地"), local_date(data.get("downloaded_at", ""))))
        if self.local_items:
            self.saved.selection_set("0")

    def import_selected(self):
        if self.busy:
            return
        item = self.current_item()
        if item is None:
            return
        if self.is_local():
            path, data = item
            self.open_result(DownloadResult(path, data["title"], data.get("source", ""), data.get("page_url", ""), data.get("summary", {})))
            return
        state = self.begin()
        if state is None:
            return
        token, cancel = state
        self.status.set("准备下载所选 MIDI…")

        def worker():
            try:
                result = self.client.download(item, cancel, lambda text: self.messages.put((token, "status", text)))
                self.messages.put((token, "download", result))
            except Exception as error:
                self.messages.put((token, "error", str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def open_result(self, result):
        count = len(result) if isinstance(result,list) else 1
        if isinstance(result,list):result = result[0]
        if self.app.active:
            self.status.set("曲目已保存；请先停止当前演奏，再从“已下载”载入。")
            self.reload_downloaded()
            return
        if self.app.open_path(result.path):
            text = f"已保存 {count} 个乐章并载入第一首，其余可在已下载页切换。" if count>1 else f"已导入《{result.title}》，可以试听或开始演奏。"
            self.app.set_status(text, "导入成功", "teal")
            self.close()
            self.app.root.lift()

    def refresh_catalogs(self):
        state = self.begin()
        if state is None:
            return
        token, cancel = state
        self.status.set("正在连接公开曲库，更新曲目清单…")

        def worker():
            try:
                result = self.client.refresh(cancel, lambda text: self.messages.put((token, "status", text)))
                self.messages.put((token, "refresh", result))
            except Exception as error:
                self.messages.put((token, "error", str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def open_source(self):
        item = self.current_item()
        if item is not None:
            url = item[1].get("page_url", "") if self.is_local() else item.page_url
            try:
                webbrowser.open(safe_url(url))
            except Exception as error:
                self.status.set(str(error))

    def cancel_operation(self):
        if self.cancel is not None:
            self.cancel.set()
        self.token, self.busy = None, False
        self.status.set("操作已取消，可以重新搜索或选择其他版本。")
        self.status_label.configure(fg=C["muted"])
        self.refresh_controls()

    def handle_message(self, token, kind, payload):
        if token != self.token or self.closed:
            return
        if kind == "status":
            self.status.set(payload)
            return
        self.busy = False
        if kind == "search":
            self.render_results(payload)
        elif kind == "download":
            self.open_result(payload)
        elif kind == "refresh":
            counts, failures = payload
            self.status.set("目录已更新：" + " · ".join(f"{SOURCES[source]} {count:,} 条" for source, count in counts.items()) + ("；" + "；".join(failures) if failures else "。现在可以搜索。"))
            self.status_label.configure(fg=C["amber"] if failures else C["teal"])
        elif kind == "error":
            self.status.set(payload)
            self.status_label.configure(fg=C["red"])
        if not self.closed:
            self.refresh_controls()

    def poll(self):
        if self.closed:
            return
        try:
            while not self.closed:
                self.handle_message(*self.messages.get_nowait())
        except queue.Empty:
            pass
        if not self.closed:
            self.poll_job = self.window.after(100, self.poll)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.cancel is not None:
            self.cancel.set()
        self.window.after_cancel(self.poll_job)
        self.window.grab_release()
        self.window.destroy()
        self.app.online_dialog = None
