"""Tkinter performance desk. Local files only; game input lives in the engine."""
from __future__ import annotations

import json
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import uuid
import logging
import os
import re

from .midi import convert, note_name, save_score, validate_score, write_midi
from .notation import read_score
from .catalog import CatalogClient
from .instruments import INSTRUMENTS, score_instrument
from . import APP_NAME, __version__
from .presets import PresetStore, fingerprint, DEFAULTS
from .segments import parse_time
from .analysis import recommend_transpositions, adaptation_report
from .performance import performance_plan


C = {"bg": "#F1F4F8", "paper": "#FFFFFF", "ink": "#1B2A41", "muted": "#718096",
     "line": "#E2E8F0", "nav": "#14243A", "nav_hover": "#20364E", "nav_active": "#24445B",
     "teal": "#087F8C", "teal_hover": "#066B76", "teal_light": "#E4F4F2", "mint": "#65D6C4",
     "blue": "#285DBF", "blue_light": "#EAF1FF", "amber": "#95620D", "amber_light": "#FFF2D8",
     "red": "#BE354B", "red_light": "#FCECEF", "disabled": "#EBEFF4", "disabled_ink": "#9AA6B5"}
FONT = "Microsoft YaHei UI"


def export_name(title):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]',"_",title).strip(" .")[:100] or "曲谱"


def duration_label(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class Tooltip:
    def __init__(self, widget, text):
        self.widget, self.text, self.pending, self.window = widget, text, None, None
        widget.bind("<Enter>", self.schedule, add="+")
        widget.bind("<Leave>", self.hide, add="+")
        widget.bind("<ButtonPress>", self.hide, add="+")
        widget.bind("<Destroy>", self.hide, add="+")

    def schedule(self, _=None):
        self.hide()
        self.pending = self.widget.after(450, self.show)

    def show(self):
        self.pending = None
        if not self.widget.winfo_exists():
            return
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        label = tk.Label(self.window, text=self.text, bg=C["nav"], fg="white", font=(FONT, 9),
                         wraplength=300, justify="left", padx=12, pady=9)
        label.pack()
        self.window.update_idletasks()
        x = min(self.widget.winfo_rootx(), self.widget.winfo_screenwidth() - self.window.winfo_reqwidth() - 12)
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        if y + self.window.winfo_reqheight() > self.widget.winfo_screenheight() - 16:
            y = self.widget.winfo_rooty() - self.window.winfo_reqheight() - 6
        self.window.geometry(f"+{max(8, x)}+{max(8, y)}")

    def hide(self, _=None):
        if self.pending is not None:
            self.widget.after_cancel(self.pending)
            self.pending = None
        if self.window is not None:
            self.window.destroy()
            self.window = None


class App:
    def __init__(self, root, engine):
        self.root, self.engine, self.directory = root, engine, engine.ROOT
        self.directory.mkdir(parents=True, exist_ok=True)
        self.assets = getattr(engine, "ASSETS", self.directory)
        self.online_client, self.online_dialog = CatalogClient(self.directory, resources=self.assets), None
        self.song, self.score, self.active = None, None, None
        self.track_ids, self.controls, self.library_buttons = [], [], []
        self.messages, self.refresh_job = queue.Queue(), None
        self.preview_token, self.preview_started, self.preview_length = None, None, 0
        self.recommend_token = None
        self.stop_requested, self.syncing_speed, self.closed = False, False, False
        self.advanced_visible, self.notes_visible = False, False
        self.preferences = self.read_preferences()
        self.preset_store = PresetStore(self.directory)
        self.song_fingerprint, self.syncing_settings = None, False
        self.speed = tk.StringVar(value=str(self.preferences.get("speed", "1.0")))
        self.transpose = tk.StringVar(value=str(self.preferences.get("transpose", "0")))
        self.start, self.countdown, self.hold_ms = tk.StringVar(value="0"), tk.StringVar(value="7"), tk.StringVar(value="300")
        self.end = tk.StringVar(value="")
        self.mode = tk.StringVar(value="旋律版（推荐）")
        selected = INSTRUMENTS.get(self.preferences.get("instrument"), INSTRUMENTS["guitar"])
        self.instrument = tk.StringVar(value=selected.title)
        self.applied_instrument = selected.id
        self.range_policy = tk.StringVar(value="超出音域折回八度")
        self.speed_slider = tk.DoubleVar(value=1.0)
        self.title, self.subtitle = tk.StringVar(value="选择一首曲子"), tk.StringVar(value="从左侧曲库开始，或导入自己的 MIDI")
        self.status = tk.StringVar(value="先选曲，再试听，最后开始游戏演奏。")
        self.notice = tk.StringVar(value="")
        self.time_text, self.progress = tk.StringVar(value="00:00 / 00:00"), tk.DoubleVar(value=0)
        self.root.title(f"{APP_NAME} · v{__version__}")
        try:
            root.iconbitmap(str(self.assets / "icon.ico"))
        except tk.TclError:
            pass
        width = min(1160, root.winfo_screenwidth() - 70)
        height = min(850, root.winfo_screenheight() - 90)
        root.geometry(f"{width}x{height}")
        root.minsize(1000, 700)
        root.configure(bg=C["bg"])
        root.option_add("*Font", (FONT, 10))
        self.configure_styles()
        self.build_layout()
        self.build_menu()
        for variable in (self.speed, self.transpose, self.start, self.end, self.mode, self.range_policy, self.countdown, self.hold_ms, self.instrument):
            variable.trace_add("write", self.queue_refresh)
        self.tracks.bind("<<ListboxSelect>>", self.queue_refresh)
        root.bind("<Control-o>", lambda _: self.open_file())
        root.bind("<Control-f>", lambda _: self.open_online())
        root.bind("<Control-Return>", lambda _: self.play(None))
        root.bind("<F8>", lambda _: self.stop())
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.report_callback_exception = self.callback_error
        last = self.preferences.get("last_file", "")
        candidate = Path(last) if isinstance(last, str) and last else self.assets / "scores/twinkle.mid"
        if not candidate.is_file():
            candidate = self.assets / "scores/twinkle.mid"
        if candidate.is_file():
            self.open_path(candidate)
        self.refresh_controls()
        self.poll_job = root.after(120, self.poll)

    def build_menu(self):
        menu = tk.Menu(self.root)
        files = tk.Menu(menu, tearoff=False)
        files.add_command(label="导入曲谱…", command=self.open_file, accelerator="Ctrl+O")
        files.add_command(label="另存原曲为 MIDI…", command=self.export_midi)
        files.add_command(label="在线搜曲…", command=self.open_online, accelerator="Ctrl+F")
        files.add_separator()
        files.add_command(label="打开数据目录", command=lambda: os.startfile(self.directory))
        files.add_command(label="退出", command=self.close)
        menu.add_cascade(label="文件", menu=files)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="使用说明", command=self.show_help)
        help_menu.add_command(label="关于", command=lambda: messagebox.showinfo(
            "关于", f"{APP_NAME}\nv{__version__}\n\n支持吉他钢琴模式、钢琴 Shift 黑键、MIDI 旋律与和弦。\n\n数据目录：\n{self.directory}\n\n与游戏官方无关联。", parent=self.root))
        menu.add_cascade(label="帮助", menu=help_menu)
        self.root.configure(menu=menu)

    def show_help(self):
        path = self.assets / "USAGE.md"
        window = tk.Toplevel(self.root)
        window.title("使用说明")
        window.geometry("800x620")
        text = tk.Text(window, wrap="word", padx=20, pady=15, font=(FONT, 10), relief="flat")
        bar = ttk.Scrollbar(window, command=text.yview)
        bar.pack(side="right", fill="y")
        text.configure(yscrollcommand=bar.set)
        text.pack(fill="both", expand=True)
        text.insert("1.0", path.read_text(encoding="utf-8"))
        text.configure(state="disabled")

    def choose_library(self, title, path):
        if path is not None:
            self.open_path(path)
        else:
            self.open_online(query=title,source="Mutopia 古典" if title in ("致爱丽丝","月光奏鸣曲") else None)

    def configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TCombobox", font=(FONT, 10), padding=6, fieldbackground="white", bordercolor=C["line"], arrowcolor=C["muted"])
        style.map("TCombobox", fieldbackground=[("readonly", "white"), ("disabled", C["disabled"])],
                  foreground=[("readonly", C["ink"]), ("disabled", C["disabled_ink"])])
        style.configure("Desk.Horizontal.TScale", background="white", troughcolor=C["line"], borderwidth=0,
                        lightcolor=C["teal"], darkcolor=C["teal"])
        style.configure("Desk.Horizontal.TProgressbar", background=C["teal"], troughcolor=C["line"], borderwidth=0,
                        lightcolor=C["teal"], darkcolor=C["teal"], thickness=5)
        style.configure("Desk.Treeview", font=(FONT, 10), rowheight=30, background="white", fieldbackground="white")
        style.configure("Desk.Treeview.Heading", font=(FONT, 10, "bold"), padding=8)
        style.map("Desk.Treeview", background=[("selected", C["teal"])], foreground=[("selected", "white")])
        style.configure("Desk.Vertical.TScrollbar", background=C["line"], troughcolor=C["bg"],
                        bordercolor=C["bg"], lightcolor=C["line"], darkcolor=C["line"], arrowcolor=C["muted"], arrowsize=10)

    def label(self, parent, text=None, size=10, color=None, bold=False, **kwargs):
        return tk.Label(parent, text=text, font=(FONT, size, "bold" if bold else "normal"),
                        bg=parent.cget("bg"), fg=color or C["ink"], **kwargs)

    def button(self, parent, text, command, kind="neutral", size=10, tip=None, **kwargs):
        palettes = {"primary": (C["teal"], "white", C["teal_hover"]),
                    "preview": (C["blue_light"], C["blue"], "#DCE8FF"),
                    "trial": (C["amber_light"], C["amber"], "#FFE7B5"),
                    "stop": (C["red_light"], C["red"], "#F8D6DD"),
                    "neutral": ("#F1F4F8", C["muted"], "#E4EAF2"),
                    "nav": (C["nav_hover"], "#E5EDF5", "#2A425D")}
        bg, fg, hover = palettes[kind]
        button = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover,
                           activeforeground=fg, relief="flat", borderwidth=0, font=(FONT, size, "bold"),
                           padx=14, pady=10, cursor="hand2", highlightthickness=2,
                           highlightbackground=parent.cget("bg"), highlightcolor=C["mint"], **kwargs)
        button.palette = (bg, fg, hover)
        button.bind("<Enter>", lambda _: button.configure(bg=hover) if str(button.cget("state")) != "disabled" else None)
        button.bind("<Leave>", lambda _: button.configure(bg=button.palette[0]) if str(button.cget("state")) != "disabled" else None)
        if tip:
            Tooltip(button, tip)
        return button

    def enabled(self, widget, enabled, normal="normal"):
        widget.configure(state=normal if enabled else "disabled")
        if hasattr(widget, "palette"):
            bg, fg, _ = widget.palette
            widget.configure(bg=bg if enabled else C["disabled"], fg=fg if enabled else C["disabled_ink"],
                             disabledforeground=C["disabled_ink"], cursor="hand2" if enabled else "arrow")

    def card(self, parent):
        return tk.Frame(parent, bg="white", highlightbackground=C["line"], highlightthickness=1, padx=18, pady=15)

    def build_layout(self):
        sidebar = tk.Frame(self.root, bg=C["nav"], width=224, padx=18, pady=25)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self.label(sidebar, "♪  异环", 24, "#FFFFFF", True).pack(anchor="w")
        self.label(sidebar, "演 奏 工 作 台", 11, C["mint"]).pack(anchor="w", pady=(3, 27))
        self.online_button = self.button(sidebar, "⌕  在线搜曲", self.open_online, "primary", 11,
                                         "在公开曲库中搜索，下载并自动导入。\n快捷键：Ctrl + F")
        self.online_button.pack(fill="x", pady=(0, 8))
        self.import_button = self.button(sidebar, "+  导入曲谱", self.open_file, "nav", 11,
                                         "支持 MIDI、KAR、RMI、MusicXML、XML、MXL。\n快捷键：Ctrl + O")
        self.import_button.pack(fill="x")
        nav_area = tk.Frame(sidebar, bg=C["nav"])
        nav_area.pack(fill="both", expand=True, pady=(8, 8))
        self.nav_canvas = tk.Canvas(nav_area, bg=C["nav"], highlightthickness=0, width=170)
        nav_scroll = ttk.Scrollbar(nav_area, orient="vertical", command=self.nav_canvas.yview)
        nav_scroll.pack(side="right", fill="y")
        self.nav_canvas.pack(side="left", fill="both", expand=True)
        self.nav_canvas.configure(yscrollcommand=nav_scroll.set)
        self.nav_content = tk.Frame(self.nav_canvas, bg=C["nav"])
        nav_window = self.nav_canvas.create_window((0,0), window=self.nav_content, anchor="nw")
        self.nav_content.bind("<Configure>", lambda _: self.nav_canvas.configure(scrollregion=self.nav_canvas.bbox("all")))
        self.nav_canvas.bind("<Configure>", lambda e: self.nav_canvas.itemconfigure(nav_window, width=e.width))
        self.label(self.nav_content, "我的曲库", 9, "#90A6BF", True).pack(anchor="w", pady=(15, 10))
        for name, filename, caption in [("小星星", "twinkle.mid", "内置示例 · 离线可用"), ("致爱丽丝",None,"Mutopia · 古典钢琴"),
                ("月光奏鸣曲",None,"Mutopia · 多乐章"), ("三叶的主题曲", None, "在线获取 MIDI"), ("黄昏之时", None, "在线获取 MIDI")]:
            path = self.assets / "scores" / filename if filename else None
            button = self.button(self.nav_content, f"{name}\n{caption}", lambda n=name, p=path: self.choose_library(n,p), "nav", 10, "载入内置示例，或搜索并下载所选曲目。", anchor="w", justify="left")
            button.pack(fill="x", pady=(0, 8))
            self.library_buttons.append((button, path))
        self.label(self.nav_content, "最近导入", 9, "#90A6BF", True).pack(anchor="w", pady=(17, 8))
        self.recent_frame = tk.Frame(self.nav_content, bg=C["nav"])
        self.recent_frame.pack(fill="x")
        self.render_recents()
        bottom = tk.Frame(sidebar, bg=C["nav"])
        bottom.pack(side="bottom", fill="x", before=nav_area)
        self.instrument_label = self.label(bottom, self.instrument.get(), 11, "#DCE8F5", True)
        self.instrument_label.pack(anchor="w")
        self.range_label = self.label(bottom, "36 键 · E3–D#6", 9, "#90A6BF")
        self.range_label.pack(anchor="w", pady=(3, 19))
        tk.Frame(bottom, bg="#2B3D53", height=1).pack(fill="x", pady=(0, 15))
        for key, action in [("Ctrl + F", "在线搜曲"), ("Ctrl + O", "导入曲谱"), ("Ctrl + Enter", "完整演奏"), ("F8", "停止演奏")]:
            row = tk.Frame(bottom, bg=C["nav"])
            row.pack(fill="x", pady=4)
            self.label(row, key, 9, "#DAE6F2", True).pack(side="left")
            self.label(row, action, 9, "#90A6BF").pack(side="right")

        main = tk.Frame(self.root, bg=C["bg"])
        main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg=C["bg"], padx=25, pady=19)
        header.pack(fill="x")
        self.label(header, "01  选曲     /     02  试听     /     03  游戏演奏", 9, C["muted"]).pack(anchor="w")
        heading = tk.Frame(header, bg=C["bg"])
        heading.pack(fill="x", pady=(9, 3))
        self.label(heading, size=23, bold=True, textvariable=self.title).pack(side="left")
        self.badge = self.label(heading, "等待选曲", 9, C["muted"], True, padx=12, pady=5)
        self.badge.pack(side="right")
        self.source_label = self.label(header, size=9, color=C["muted"], textvariable=self.subtitle)
        self.source_label.pack(anchor="w")
        instrument_row = tk.Frame(header, bg=C["bg"])
        instrument_row.pack(fill="x", pady=(12, 0))
        self.label(instrument_row, "演奏乐器", 10, bold=True).pack(side="left", padx=(0, 12))
        self.instrument_box = ttk.Combobox(instrument_row, textvariable=self.instrument,
                                         values=[p.title for p in INSTRUMENTS.values()], state="readonly", width=24)
        self.instrument_box.pack(side="left")
        self.controls.append((self.instrument_box, "readonly"))
        self.instrument_hint = self.label(instrument_row, "", 8, C["muted"])
        self.instrument_hint.pack(side="left", padx=12)
        self.arrangement_label = self.label(header, "本曲设置自动保存 · 钢琴与吉他独立恢复", 8, C["muted"])
        self.arrangement_label.pack(anchor="w", pady=(6, 0))

        self.build_footer(main)
        body = tk.Frame(main, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=(25, 13))
        canvas = tk.Canvas(body, bg=C["bg"], highlightthickness=0, borderwidth=0)
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=canvas.yview, style="Desk.Vertical.TScrollbar")
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        content = tk.Frame(canvas, bg=C["bg"])
        window = canvas.create_window((0, 0), window=content, anchor="nw")
        content.bind("<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        self.body_canvas = canvas
        self.root.bind_all("<MouseWheel>", self.scroll_body, add="+")

        metrics = tk.Frame(content, bg=C["bg"])
        metrics.pack(fill="x", pady=(0, 14))
        self.metric_values, self.metric_details = [], []
        for index, (label, color, detail) in enumerate([("演奏时长", C["ink"], "保留 MIDI 的节奏"), ("有效音符", C["blue"], "自动转换为游戏键位"), ("音域适配", C["teal"], "当前范围 E3–D♯6")]):
            metrics.columnconfigure(index, weight=1, uniform="stats")
            card = self.card(metrics)
            card.grid(row=0, column=index, sticky="nsew", padx=(0, 12 if index < 2 else 0))
            self.label(card, label, 9, C["muted"]).pack(anchor="w")
            value = self.label(card, "—", 24, color, True)
            value.pack(anchor="w", pady=(3, 2))
            detail_label = self.label(card, detail, 8, C["muted"])
            detail_label.pack(anchor="w")
            self.metric_values.append(value)
            self.metric_details.append(detail_label)

        middle = tk.Frame(content, bg=C["bg"])
        middle.pack(fill="x")
        middle.columnconfigure(0, weight=1, uniform="middle")
        middle.columnconfigure(1, weight=1, uniform="middle")
        settings = self.card(middle)
        settings.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.label(settings, "演奏设置", 12, bold=True).pack(anchor="w")
        self.label(settings, "参数修改后，曲谱自动更新", 8, C["muted"]).pack(anchor="w", pady=(3, 13))
        speed_row = tk.Frame(settings, bg="white")
        speed_row.pack(fill="x")
        self.label(speed_row, "播放速度", 10).pack(side="left")
        speed_entry = tk.Entry(speed_row, textvariable=self.speed, width=6, justify="right", relief="flat", fg=C["teal"], bg="#F4FAFA", font=(FONT, 14, "bold"))
        speed_entry.pack(side="right")
        self.label(speed_row, "×", 12, C["teal"]).pack(side="right", padx=3)
        self.controls.append((speed_entry, "normal"))
        self.scale = ttk.Scale(settings, variable=self.speed_slider, from_=0.25, to=2.0, command=self.slide_speed, style="Desk.Horizontal.TScale")
        self.scale.pack(fill="x", pady=(5, 4))
        self.controls.append((self.scale, "normal"))
        presets = tk.Frame(settings, bg="white")
        presets.pack(fill="x", pady=(0, 13))
        for value, label in [(0.75, "慢速 0.75×"), (1.0, "原速"), (1.25, "快速 1.25×")]:
            button = self.button(presets, label, lambda v=value: self.speed.set(str(v)), size=8)
            button.configure(pady=4, padx=8)
            button.pack(side="left", padx=(0, 5))
            self.controls.append((button, "normal"))
        row = tk.Frame(settings, bg="white")
        row.pack(fill="x")
        self.label(row, "移调", 10).pack(side="left")
        spin = tk.Spinbox(row, from_=-36, to=36, textvariable=self.transpose, width=5, justify="center", relief="solid", borderwidth=1, font=(FONT, 11))
        spin.pack(side="left", padx=(12, 7))
        self.label(row, "半音", 9, C["muted"]).pack(side="left")
        Tooltip(spin, "12 个半音 = 一个八度。\n负数降低音高，正数升高音高。")
        self.controls.append((spin, "normal"))
        reset = self.button(row, "恢复默认", self.reset_settings, size=8, tip="恢复原速、零移调和推荐的旋律设置。")
        reset.configure(padx=8, pady=5)
        reset.pack(side="right")
        self.controls.append((reset, "normal"))
        self.recommend_button = self.button(settings, "推荐移调方案…", self.recommend_transpose, "preview", 9,
            "比较音域折回、丢音、冲突和旋律走向，给出最多 3 个可试听候选；不会自动修改或开始演奏。")
        self.recommend_button.configure(pady=6)
        self.recommend_button.pack(fill="x", pady=(10, 0))

        tracks_card = self.card(middle)
        tracks_card.grid(row=0, column=1, sticky="nsew")
        self.label(tracks_card, "旋律音轨", 12, bold=True).pack(anchor="w")
        self.label(tracks_card, "已自动推荐 · 按 Ctrl 可多选", 8, C["muted"]).pack(anchor="w", pady=(3, 10))
        self.tracks = tk.Listbox(tracks_card, selectmode="extended", exportselection=False, height=4,
                                 bg="#F7F9FC", fg=C["ink"], selectbackground=C["teal"], selectforeground="white",
                                 activestyle="none", relief="flat", borderwidth=0, highlightthickness=0,
                                 font=(FONT, 9))
        self.tracks.pack(fill="both", expand=True, ipady=5)
        self.controls.append((self.tracks, "normal"))
        self.track_preview_button = self.button(tracks_card, "♫  单独试听当前轨", self.preview_track, "preview", 9,
            "试听最后点选的音轨，保留原始声部，不折回音域、不删减和弦；不会改变演奏选轨。")
        self.track_preview_button.configure(pady=5)
        self.track_preview_button.pack(fill="x", pady=(7, 0))
        mode_box = ttk.Combobox(tracks_card, textvariable=self.mode, values=["旋律版（推荐）", "和弦版（最多 6 音）"], state="readonly")
        mode_box.pack(fill="x", pady=(10, 0))
        self.mode_box = mode_box
        self.controls.append((mode_box, "readonly"))
        Tooltip(mode_box, "旋律版：同一时刻只保留最高音。\n和弦版：最多保留 6 音。钢琴混合黑白键会快速分组。\n需要伴奏时，请按 Ctrl 多选对应音轨。")

        segment = self.card(content)
        segment.pack(fill="x", pady=(12, 0))
        self.label(segment, "演奏片段", 11, bold=True).pack(side="left", padx=(0, 12))
        for label, variable in (("从", self.start), ("到", self.end)):
            self.label(segment, label, 9, C["muted"]).pack(side="left", padx=(4, 5))
            entry = tk.Entry(segment, textvariable=variable, width=8, relief="solid", borderwidth=1)
            entry.pack(side="left", ipady=5)
            self.controls.append((entry, "normal"))
            Tooltip(entry, "按原曲时间输入秒数或 分:秒；终点留空表示到曲末。\n片段内的休止和跨越起点的长音会保留。")
        whole = self.button(segment, "整首", self.reset_segment, size=8)
        whole.configure(padx=7, pady=5)
        whole.pack(side="left", padx=8)
        self.controls.append((whole, "normal"))
        self.source_preview_button = self.button(segment, "♫ 原谱对照", self.preview_source, "preview", 9,
            "试听所选音轨的原始声部；与电脑试听使用相同片段、速度和移调，保留完整音域及和弦。")
        self.source_preview_button.configure(padx=8, pady=5)
        self.source_preview_button.pack(side="right")

        advanced_head = tk.Frame(content, bg=C["bg"])
        advanced_head.pack(fill="x", pady=(10, 4))
        self.advanced_button = self.button(advanced_head, "▸  高级设置", self.toggle_advanced, size=9,
                                            tip="设置起始位置、倒计时、按键时长和音域处理方式。")
        self.advanced_button.configure(padx=0, pady=6, bg=C["bg"])
        self.advanced_button.pack(side="left")
        self.notes_button = self.button(advanced_head, "键位预览  ▸", self.toggle_notes, size=9,
                                         tip="展开前 8 个音的游戏键位，也可继续查看整首音符明细。")
        self.notes_button.configure(pady=6)
        self.notes_button.pack(side="right")
        self.report_button = self.button(advanced_head, "适配报告 ↗", self.show_adaptation, size=9,
            tip="查看折回、丢弃、重合与简化音符发生的位置，并导出适配报告。")
        self.report_button.configure(pady=6)
        self.report_button.pack(side="right", padx=8)
        self.advanced = self.card(content)
        grid = tk.Frame(self.advanced, bg="white")
        grid.pack(fill="x")
        for col, (label, variable, lower, upper, tip) in enumerate([
                ("开始前倒计时", self.countdown, 0, 60, "确认权限后，给你切回乐器界面和松开键鼠的时间。"),
                ("按键上限 / 毫秒", self.hold_ms, 20, 400, "每个音按住的时长上限。默认 300 毫秒；长音只触发一次。")]):
            grid.columnconfigure(col, weight=1)
            cell = tk.Frame(grid, bg="white")
            cell.grid(row=0, column=col, sticky="ew", padx=(0, 14 if col < 2 else 0))
            self.label(cell, label, 9, C["muted"]).pack(anchor="w", pady=(0, 5))
            spin = tk.Spinbox(cell, from_=lower, to=upper, textvariable=variable, width=10, relief="solid", borderwidth=1)
            spin.pack(fill="x")
            self.controls.append((spin, "normal"))
            Tooltip(spin, tip)
        range_box = ttk.Combobox(self.advanced, textvariable=self.range_policy, values=["超出音域折回八度", "丢弃超出音域的音", "超出音域时报错"], state="readonly")
        range_box.pack(fill="x", pady=(12, 0))
        self.controls.append((range_box, "readonly"))
        Tooltip(range_box, "折回八度会保留音名，但可能改变旋律的上下走势。\n原音域已适配的曲目不会被改动。")

        self.notes_card = self.card(content)
        row = tk.Frame(self.notes_card, bg="white")
        row.pack(fill="x", pady=(0, 11))
        self.label(row, "键位预览", 11, bold=True).pack(side="left")
        self.details_button = self.button(row, "查看全部音符 ↗", self.show_details, size=8,
                                           tip="查看整首曲谱的时间、音名和实际游戏按键。")
        self.details_button.configure(padx=8, pady=3)
        self.details_button.pack(side="right")
        self.key_cells = []
        caps = tk.Frame(self.notes_card, bg="white")
        caps.pack(fill="x")
        for index in range(8):
            caps.columnconfigure(index, weight=1, uniform="caps")
            cap = tk.Frame(caps, bg="#F4F7FB", padx=4, pady=8)
            cap.grid(row=0, column=index, sticky="ew", padx=(0, 7 if index < 7 else 0))
            key = self.label(cap, "—", 17, C["blue"], True)
            key.pack()
            note = self.label(cap, "", 8, C["muted"])
            note.pack(pady=(3, 0))
            self.key_cells.append((key, note))
        self.notice_label = self.label(content, color=C["muted"], size=9, textvariable=self.notice,
                                       anchor="w", justify="left", wraplength=760)
        self.notice_label.pack(fill="x", pady=(0, 12))

    def build_footer(self, main):
        footer = tk.Frame(main, bg="white", padx=25, pady=16, highlightbackground=C["line"], highlightthickness=1)
        footer.pack(side="bottom", fill="x", pady=(10, 0))
        status_row = tk.Frame(footer, bg="white")
        status_row.pack(fill="x")
        self.status_dot = self.label(status_row, "●", 9, C["teal"])
        self.status_dot.pack(side="left", padx=(0, 7))
        self.label(status_row, size=9, textvariable=self.status, anchor="w").pack(side="left", fill="x", expand=True)
        self.label(status_row, size=9, color=C["muted"], textvariable=self.time_text).pack(side="right", padx=(8, 0))
        self.progress_bar = tk.Canvas(footer, height=4, bg=C["line"], borderwidth=0, highlightthickness=0)
        self.progress_bar.pack(fill="x", pady=(10, 13))
        self.progress_bar.bind("<Configure>", self.draw_progress)
        self.progress.trace_add("write", self.draw_progress)
        actions = tk.Frame(footer, bg="white")
        actions.pack(fill="x")
        for index, weight in enumerate((3, 2, 2, 1)):
            actions.columnconfigure(index, weight=weight, uniform="actions" if index else "primary")
        self.play_button = self.button(actions, "▶  完整演奏", lambda: self.play(None), "primary", 14,
                                        "将整首曲谱发送到游戏。\n请先进入所选乐器的 36 键界面，再确认权限。\n快捷键：Ctrl + Enter")
        self.play_button.configure(pady=17)
        self.preview_button = self.button(actions, "♫  时序试听", self.preview, "preview", 11,
                                           "试听前 20 秒的合成旋律，只在电脑播放声音，不操作游戏。")
        self.trial_button = self.button(actions, "▷  游戏试奏", lambda: self.play(20), "trial", 11,
                                         "向游戏发送前 20 秒的按键，适合先确认音色和旋律。")
        self.stop_button = self.button(actions, "■  停止", self.stop, "stop", 11,
                                        "立即请求停止并释放脚本按住的琴键。\n游戏内也可按 F8；切出游戏会自动停止。")
        for index, button in enumerate((self.play_button, self.preview_button, self.trial_button, self.stop_button)):
            button.grid(row=0, column=index, sticky="ew", padx=(0, 9 if index < 3 else 0))
        for index, text in enumerate(("演奏整首曲目", "合成音色 · 前 20 秒", "游戏内验证 · 前 20 秒", "快捷键 F8")):
            self.label(actions, text, 8, C["muted"]).grid(row=1, column=index, sticky="w", pady=(6, 0), padx=(3, 0))
        footer_row = tk.Frame(footer, bg="white")
        footer_row.pack(fill="x", pady=(12, 0))
        self.label(footer_row, "游戏演奏：先进入乐器界面，确认权限后保持游戏在前台。", 8, C["muted"]).pack(side="left")
        self.export_button = self.button(footer_row, "导出曲谱", self.export, size=8, tip="把当前设置下的转换结果保存为 JSON 曲谱。")
        self.export_button.configure(padx=8, pady=3)
        self.export_button.pack(side="right")
        self.midi_export_button = self.button(footer_row,"另存 MIDI",self.export_midi,size=8,
                                             tip="将导入的原曲全部声部另存为标准 MIDI。\n不应用游戏演奏的移调、变速和简化设置。")
        self.midi_export_button.configure(padx=8,pady=3)
        self.midi_export_button.pack(side="right",padx=(0,8))

    def scroll_body(self, event):
        widget = event.widget
        while widget is not None and widget is not self.root:
            if widget in (self.nav_content, self.nav_canvas):
                self.nav_canvas.yview_scroll(-int(event.delta / 120), "units")
                return
            widget = getattr(widget, "master", None)
        if isinstance(event.widget, (tk.Listbox, tk.Text, ttk.Treeview, ttk.Combobox, tk.Spinbox)):
            return
        if self.body_canvas.winfo_height() < self.body_canvas.bbox("all")[3]:
            self.body_canvas.yview_scroll(-int(event.delta / 120), "units")

    def draw_progress(self, *_):
        self.progress_bar.delete("fill")
        width = self.progress_bar.winfo_width() * min(100, max(0, self.progress.get())) / 100
        self.progress_bar.create_rectangle(0, 0, width, 4, fill=C["teal"], outline="", tags="fill")

    def read_preferences(self):
        try:
            data = json.loads((self.directory / "midi_ui_settings.json").read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def save_preferences(self):
        try:
            values = {"last_file": str(self.current_path), "recent": self.preferences.get("recent", []),
                      "speed": self.speed.get(), "transpose": self.transpose.get(), "instrument": self.current_instrument().id}
            path = self.directory / "midi_ui_settings.json"
            temporary = path.with_suffix(".tmp")
            temporary.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(path)
        except (OSError, AttributeError):
            pass  # A read-only folder must not prevent playing a selected score.

    def render_recents(self):
        for child in self.recent_frame.winfo_children():
            child.destroy()
        self.recent_buttons = []
        recent = self.preferences.get("recent", [])
        if not isinstance(recent, list):
            recent = []
        paths = [Path(p) for p in recent if isinstance(p, str) and Path(p).is_file()][:3]
        if not paths:
            self.label(self.recent_frame, "导入自己的曲谱后\n会显示在这里", 9, "#90A6BF", justify="left").pack(anchor="w")
        for path in paths:
            title = self.online_client.title_for(path) or path.stem
            title = title if len(title) < 17 else title[:15] + "…"
            button = self.button(self.recent_frame, title, lambda p=path: self.open_path(p), "nav", 9, str(path), anchor="w")
            button.configure(pady=7, padx=9)
            button.pack(fill="x", pady=(0, 4))
            self.recent_buttons.append(button)

    def open_file(self):
        if self.active:
            return
        path = filedialog.askopenfilename(parent=self.root, title="导入曲谱", filetypes=[("支持的曲谱", "*.mid *.midi *.kar *.rmi *.musicxml *.xml *.mxl"),
                    ("MIDI / Karaoke", "*.mid *.midi *.kar *.rmi"),("MusicXML", "*.musicxml *.xml *.mxl")])
        if path:
            self.open_path(path)

    def open_online(self, query=None, source=None):
        if self.active:
            return
        self.stop_preview()
        self.refresh_controls()
        if self.online_dialog is not None and not self.online_dialog.closed:
            self.online_dialog.window.lift()
            return
        from .library_ui import OnlineLibrary
        self.online_dialog = OnlineLibrary(self)
        if query:
            self.online_dialog.use_example(query,source)

    def open_path(self, path):
        if self.active:
            return
        try:
            path = Path(path).resolve()
            song = read_score(path)
            recommended = song.suggested_track()
            digest = fingerprint(path)
            self.save_arrangement()
            self.stop_preview()
            examples = {self.assets / "scores/twinkle.mid": "小星星"}
            song.title = examples.get(path, self.online_client.title_for(path) or song.title)
            self.song, self.current_path = song, path
            self.song_fingerprint = digest
            self.title.set(song.title)
            kind = "MusicXML" if path.suffix.lower() in (".xml",".musicxml",".mxl") else "MIDI"
            self.subtitle.set(f"{kind} 曲谱  ·  {path.name}")
            self.tracks.delete(0, "end")
            self.track_ids = []
            for item in song.track_info():
                self.track_ids.append(item["index"])
                name = item["name"][:19]
                marker = "推荐 · " if item["index"] == recommended else ""
                self.tracks.insert("end", f'{marker}{item["index"]}  {name}   {note_name(item["low"])}–{note_name(item["high"])}')
                if item["index"] == recommended:
                    self.tracks.selection_set(len(self.track_ids) - 1)
            self.restore_arrangement()
            for button, preset in self.library_buttons:
                selected = path == preset
                button.palette = (C["nav_active"] if selected else C["nav_hover"], "white", "#2A425D")
                button.configure(highlightbackground=C["mint"] if selected else C["nav"], bg=button.palette[0])
            if path not in examples:
                recent = self.preferences.get("recent", [])
                recent = recent if isinstance(recent, list) else []
                self.preferences["recent"] = [str(path), *[p for p in recent if isinstance(p, str) and p != str(path)]][:5]
                self.render_recents()
            self.update_score(quiet=True)
            self.save_preferences()
            return True
        except Exception as error:
            self.show_error(error)
            return False

    def slide_speed(self, value):
        if not self.syncing_speed:
            self.speed.set(f"{float(value):.2f}")

    def queue_refresh(self, *_):
        if self.syncing_settings:
            return
        self.recommend_token = None
        if self.current_instrument().id != self.applied_instrument:
            self.save_arrangement()
            self.restore_arrangement()
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
        if self.preview_token:
            self.stop_preview()
        self.refresh_job = self.root.after(220, lambda: self.update_score(quiet=True))

    def arrangement_settings(self):
        return {"tracks": [self.track_ids[int(i)] for i in self.tracks.curselection()],
                "mode": "melody" if self.mode.get().startswith("旋律") else "chords",
                "speed": float(self.speed.get()), "transpose": int(self.transpose.get()),
                "range_policy": {"超出音域折回八度": "fold", "丢弃超出音域的音": "drop", "超出音域时报错": "strict"}[self.range_policy.get()],
                "start": parse_time(self.start.get()), "end": parse_time(self.end.get()) if self.end.get().strip() else None,
                "countdown": int(self.countdown.get()), "hold_ms": int(self.hold_ms.get())}

    def save_arrangement(self):
        if not self.song_fingerprint or self.syncing_settings or self.song is None:
            return
        try:
            settings = self.arrangement_settings()
            convert(self.song, settings["tracks"], settings["mode"], settings["speed"], settings["transpose"],
                    settings["range_policy"], settings["start"], self.applied_instrument, settings["end"])
            self.preset_store.save(self.song_fingerprint, self.applied_instrument, settings)
        except (OSError, ValueError, KeyError, tk.TclError):
            pass  # Incomplete edits must not replace a usable arrangement.

    def restore_arrangement(self):
        self.applied_instrument = self.current_instrument().id
        if self.song is None:
            return
        settings = {**DEFAULTS, "tracks": [self.song.suggested_track()]}
        message = "本曲使用默认方案 · 修改后自动保存"
        try:
            saved = self.preset_store.load(self.song_fingerprint, self.applied_instrument, self.track_ids)
            if saved:
                settings = saved
                message = "已恢复本曲方案 · 钢琴与吉他独立保存"
        except (OSError, ValueError):
            message = "保存的方案无法读取，已使用默认设置"
        self.syncing_settings = True
        try:
            for name in ("speed", "transpose", "start", "countdown", "hold_ms"):
                getattr(self, name).set(str(settings[name]))
            self.end.set("" if settings["end"] is None else str(settings["end"]))
            self.mode.set("旋律版（推荐）" if settings["mode"] == "melody" else "和弦版（最多 6 音）")
            self.range_policy.set({"fold": "超出音域折回八度", "drop": "丢弃超出音域的音", "strict": "超出音域时报错"}[settings["range_policy"]])
            self.tracks.selection_clear(0, "end")
            for index, track in enumerate(self.track_ids):
                if track in settings["tracks"]:
                    self.tracks.selection_set(index)
            self.arrangement_label.configure(text=message)
        finally:
            self.syncing_settings = False

    def build_score(self):
        if self.song is None:
            raise ValueError("请先从左侧选曲，或导入 MIDI。")
        tracks = [self.track_ids[int(index)] for index in self.tracks.curselection()]
        policies = {"超出音域折回八度": "fold", "丢弃超出音域的音": "drop", "超出音域时报错": "strict"}
        countdown, hold = int(self.countdown.get()), int(self.hold_ms.get())
        if not 0 <= countdown <= 60 or not 20 <= hold <= 400:
            raise ValueError("倒计时应为 0–60 秒，按键上限应为 20–400 毫秒。")
        score = convert(self.song, tracks, "melody" if self.mode.get().startswith("旋律") else "chords",
                        float(self.speed.get()), int(self.transpose.get()), policies[self.range_policy.get()], parse_time(self.start.get()), self.current_instrument().id,
                        parse_time(self.end.get()) if self.end.get().strip() else None)
        if hasattr(self.engine, "key_schedule"):
            self.engine.key_schedule(score, hold)
        return validate_score(score)

    def current_instrument(self):
        return next((p for p in INSTRUMENTS.values() if p.title == self.instrument.get()), INSTRUMENTS["guitar"])

    def recommend_transpose(self):
        if self.song is None or self.active or self.recommend_token:
            return
        try:
            settings = self.arrangement_settings()
        except ValueError as error:
            self.show_error(error)
            return
        token, song, digest, instrument = uuid.uuid4().hex, self.song, self.song_fingerprint, self.current_instrument().id
        self.recommend_token = token
        self.set_status("正在比较移调候选…", "分析中", "blue")
        self.refresh_controls()
        def worker():
            try:
                options = {k: v for k, v in settings.items() if k != "countdown"}
                candidates = recommend_transpositions(song, instrument=instrument, planner=self.engine.key_schedule, **options)
                self.messages.put({"kind": "transpose_ready", "token": token, "candidates": candidates,
                                   "settings": settings, "digest": digest, "instrument": instrument})
            except Exception as error:
                self.messages.put({"kind": "transpose_error", "token": token, "text": str(error)})
        threading.Thread(target=worker, daemon=True).start()

    def show_transpositions(self, message):
        window = tk.Toplevel(self.root)
        window.title("推荐移调方案")
        window.geometry("700x350")
        window.configure(bg=C["bg"])
        self.label(window, "选择一个方案应用，再试听比较", 14, bold=True, padx=18, pady=16).pack(anchor="w")
        self.label(window, "按折回、丢音、冲突与旋律走向排序；这是规则建议，不是听感评分。", 9, C["muted"], padx=18).pack(anchor="w")
        tree = ttk.Treeview(window, columns=("shift", "folded", "dropped", "collisions", "mixed"), show="headings", height=3, style="Desk.Treeview")
        for col, title in (("shift", "移调 / 半音"), ("folded", "折回音"), ("dropped", "丢弃音"), ("collisions", "重合音"), ("mixed", "黑白混合组")):
            tree.heading(col, text=title)
            tree.column(col, width=125, anchor="center", stretch=True)
        for i, candidate in enumerate(message["candidates"]):
            tree.insert("", "end", iid=str(i), values=(f'{candidate["transpose"]:+d}', candidate["folded"], candidate["dropped"], candidate["collisions"], candidate["mixed_groups"]))
        tree.pack(fill="x", padx=18, pady=15)
        tree.selection_set("0")
        def apply():
            if self.active:
                return
            try:
                if self.song_fingerprint != message["digest"] or self.current_instrument().id != message["instrument"] or self.arrangement_settings() != message["settings"]:
                    raise ValueError("曲谱或设置已改变，请关闭窗口后重新推荐。")
                selected = tree.selection()
                if not selected:
                    return
                self.transpose.set(str(message["candidates"][int(selected[0])]["transpose"]))
                self.update_score()
                window.destroy()
            except ValueError as error:
                self.show_error(error)
        self.button(window, "应用所选方案", apply, "primary").pack(anchor="e", padx=18)

    def update_score(self, quiet=False):
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
        self.refresh_job = None
        if self.active:
            return self.score
        try:
            profile = self.current_instrument()
            self.mode_box.configure(values=["旋律版（推荐）", "和弦版（最多 6 音）"])
            self.instrument_label.configure(text=profile.title)
            self.range_label.configure(text=f"36 键 · {profile.range_label}")
            self.instrument_hint.configure(text="Shift 黑键 · 混合和弦快速分组" if profile.id == "piano" else "三排独立半音键 · 支持和弦版")
            score = self.build_score()
            self.score = score
            summary = score["summary"]
            self.metric_values[0].configure(text=duration_label(summary["seconds"]))
            self.metric_values[1].configure(text=f'{summary["notes"]:,}')
            changed = summary["folded"] + summary["dropped"]
            self.metric_values[2].configure(text=f"{changed} 音" if changed else "直接适配", fg=C["amber"] if changed else C["teal"])
            self.metric_details[2].configure(text=f'折回 {summary["folded"]} 音 · 丢弃 {summary["dropped"]} 音' if changed else "音域全部在当前键位内")
            self.metric_details[0].configure(text=f'原曲 {duration_label(self.song.seconds)} · {float(self.speed.get()):g}× 速度')
            for index, (key_label, note_label) in enumerate(self.key_cells):
                if index < len(score["events"]):
                    event = score["events"][index]
                    name = note_name(event["midi"])
                    key = profile.keys[name].label
                    key_label.configure(text=key, font=(FONT, 12 if len(key) > 2 else 17, "bold"))
                    note_label.configure(text=f'{name} · {event["at"]:.1f}s')
                else:
                    key_label.configure(text="—")
                    note_label.configure(text="")
            warnings = list(score["warnings"])
            if profile.id == "piano":
                warnings.insert(0, "钢琴暂按 C3–B5 编排；绝对音高待实听校准，可用移调 ±12 调整八度。")
            if score["mode"] == "chords" and profile.id == "guitar":
                warnings.insert(0, "和弦版同时发送多个音，建议先在游戏中试奏。")
            self.notice.set("  ".join(warnings) if warnings else "已选推荐旋律轨；中间停顿与 MIDI 节奏保留。")
            self.notice_label.configure(fg=C["amber"] if warnings else C["muted"])
            speed = float(self.speed.get())
            self.syncing_speed = True
            self.speed_slider.set(speed)
            self.syncing_speed = False
            self.progress.set(0)
            self.time_text.set(f'00:00 / {duration_label(summary["seconds"])}')
            self.set_status("曲谱已就绪，可以先试听，也可以开始游戏演奏。", "就绪", "teal")
            self.refresh_controls()
            self.save_preferences()
            self.save_arrangement()
            return score
        except Exception as error:
            self.score = None
            self.set_status(str(error), "请调整设置", "amber")
            self.notice.set(str(error))
            self.notice_label.configure(fg=C["amber"])
            self.refresh_controls()
            if not quiet:
                self.show_error(error)
            return None

    def reset_settings(self):
        for variable, value in [(self.speed, "1.0"), (self.transpose, "0"), (self.start, "0"),
                                (self.end, ""),
                                (self.mode, "旋律版（推荐）"), (self.range_policy, "超出音域折回八度"),
                                (self.countdown, "7"), (self.hold_ms, "300")]:
            variable.set(value)
        self.update_score(quiet=True)

    def reset_segment(self):
        self.start.set("0")
        self.end.set("")
        self.update_score(quiet=True)

    def toggle_advanced(self):
        self.advanced_visible = not self.advanced_visible
        if self.advanced_visible:
            self.advanced.pack(fill="x", before=self.notes_card if self.notes_visible else self.notice_label, pady=(0, 8))
        else:
            self.advanced.pack_forget()
        self.advanced_button.configure(text="▾  收起高级设置" if self.advanced_visible else "▸  高级设置")

    def toggle_notes(self):
        self.notes_visible = not self.notes_visible
        if self.notes_visible:
            self.notes_card.pack(fill="x", before=self.notice_label, pady=(6, 10))
        else:
            self.notes_card.pack_forget()
        self.notes_button.configure(text="键位预览  ▾" if self.notes_visible else "键位预览  ▸")

    def set_status(self, text, badge="就绪", tone="teal"):
        self.status.set(text)
        color = C.get(tone, C["muted"])
        self.status_dot.configure(fg=color)
        self.badge.configure(text=badge, fg=color, bg=C.get(tone + "_light", C["disabled"]))

    def refresh_controls(self):
        ready, locked = self.score is not None, self.active is not None
        for widget, normal in self.controls:
            self.enabled(widget, not locked, normal)
        for button in [self.online_button, self.import_button, *self.recent_buttons, *[b for b, _ in self.library_buttons]]:
            self.enabled(button, not locked)
        for button in [self.play_button, self.trial_button, self.export_button, self.details_button, self.notes_button, self.report_button]:
            self.enabled(button, ready and not locked)
        self.enabled(self.preview_button, ready and not locked and not self.preview_token)
        self.enabled(self.track_preview_button, self.song is not None and not locked and not self.preview_token)
        self.enabled(self.source_preview_button, self.song is not None and not locked and not self.preview_token)
        self.enabled(self.recommend_button, self.song is not None and not locked and not self.recommend_token)
        self.enabled(self.midi_export_button,self.song is not None and not locked)
        self.enabled(self.stop_button, locked or bool(self.preview_token))
        if locked or self.preview_token:
            self.stop_button.configure(bg=C["red"], fg="white", activebackground="#A52B40", activeforeground="white")
        self.play_button.configure(text="演奏进行中…" if locked else "▶  完整演奏")

    def preview(self):
        if self.active or self.preview_token:
            return
        score = self.update_score()
        if score is None:
            return
        self.start_preview(score=score)

    def preview_track(self):
        if self.song is None or self.active or self.preview_token:
            return
        selected = list(self.tracks.curselection())
        if not selected:
            self.show_error(ValueError("请先点选一条音轨。"))
            return
        focused = self.tracks.index("active")
        index = focused if focused in selected else selected[0]
        try:
            options = {"tracks": [self.track_ids[index]], "start": parse_time(self.start.get()),
                       "end": parse_time(self.end.get()) if self.end.get().strip() else None,
                       "speed": float(self.speed.get()), "transpose": int(self.transpose.get())}
            self.start_preview(source=self.song, options=options, caption=f"音轨 {self.track_ids[index]} 原声部")
        except ValueError as error:
            self.show_error(error)

    def preview_source(self):
        if self.song is None or self.active or self.preview_token:
            return
        try:
            options = {"tracks": [self.track_ids[int(i)] for i in self.tracks.curselection()],
                       "start": parse_time(self.start.get()), "end": parse_time(self.end.get()) if self.end.get().strip() else None,
                       "speed": float(self.speed.get()), "transpose": int(self.transpose.get())}
            self.start_preview(source=self.song, options=options, caption="原谱声部")
        except ValueError as error:
            self.show_error(error)

    def start_preview(self, score=None, source=None, options=None, caption="适配曲谱"):
        hold_ms = int(self.hold_ms.get()) if source is None else 300
        token = uuid.uuid4().hex
        self.preview_token, self.preview_started = token, None
        self.set_status("正在准备电脑试听…", "准备试听", "blue")
        self.refresh_controls()

        def worker():
            try:
                runs = self.directory / "runs"
                runs.mkdir(exist_ok=True)
                path = runs / f"preview_{token}.wav"
                seconds = (self.engine.render_song_preview(source, path, **options) if source is not None
                           else self.engine.render_preview(score, path, hold_ms=hold_ms))
                self.messages.put({"kind": "preview_ready", "token": token, "path": path, "seconds": seconds, "caption": caption})
            except Exception as error:
                self.messages.put({"kind": "preview_error", "token": token, "text": str(error)})

        threading.Thread(target=worker, daemon=True).start()

    def stop_preview(self):
        self.preview_token, self.preview_started = None, None
        import winsound
        winsound.PlaySound(None, 0)

    def play(self, seconds):
        if self.active:
            return
        self.stop_preview()
        score = self.update_score()
        if score is None:
            return
        try:
            if seconds:
                score = self.engine.limit_score(score, seconds)
            run = self.directory / "runs" / uuid.uuid4().hex
            run.mkdir(parents=True)
            path, cancel, report = run / "score.json", run / "stop", run / "result.json"
            save_score(score, path)
            length = performance_plan(score, int(self.hold_ms.get())).duration
            self.active = {"cancel": cancel, "report": report, "progress": report.with_suffix(".progress.json"), "length": length}
            self.stop_requested = False
            self.progress.set(0)
            self.time_text.set(f"00:00 / {duration_label(length)}")
            self.set_status(f"请确认权限，随后进入 {score_instrument(score).title} 的 36 键界面。", "等待确认", "amber")
            self.refresh_controls()
            countdown, hold = int(self.countdown.get()), int(self.hold_ms.get())

            def worker():
                try:
                    arguments = ["--play", str(path), "--cancel-file", str(cancel), "--report", str(report),
                                 "--countdown", str(countdown), "--hold-ms", str(hold)]
                    arguments.extend(["--data-dir", str(self.directory)])
                    code = self.engine.run_elevated_and_wait(None, arguments)
                    result = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
                    self.messages.put({"kind": "game_done", "code": code, "result": result})
                except Exception as error:
                    self.messages.put({"kind": "game_done", "code": 1, "result": {"reason": str(error)}})

            threading.Thread(target=worker, daemon=True).start()
        except Exception as error:
            self.active = None
            self.refresh_controls()
            self.show_error(error)

    def stop(self):
        self.stop_preview()
        if self.active:
            try:
                self.active["cancel"].touch()
                self.stop_requested = True
                self.set_status("正在停止并释放琴键…", "停止中", "red")
            except OSError as error:
                self.set_status(f"请在游戏里按 F8 停止：{error}", "请按 F8", "red")
        else:
            self.set_status("已停止电脑试听。", "已停止", "muted")
        self.refresh_controls()

    def update_progress(self):
        if self.active and not self.stop_requested:
            try:
                data = json.loads(self.active["progress"].read_text(encoding="utf-8"))
                phase = data.get("phase")
                if phase == "countdown":
                    self.set_status(f'请保持游戏在前台，{data["remaining"]} 秒后开始。', f'{data["remaining"]} 秒后开始', "amber")
                elif phase == "playing":
                    elapsed = min(self.active["length"], max(0, time.time() - data["started_at"]))
                    self.progress.set(elapsed / self.active["length"] * 100)
                    self.time_text.set(f'{duration_label(elapsed)} / {duration_label(self.active["length"])}')
                    self.set_status("正在游戏中演奏 · F8 停止 · 切出游戏会自动停止", "演奏中", "teal")
            except (OSError, ValueError, KeyError, TypeError):
                pass
        elif self.preview_started is not None:
            elapsed = min(self.preview_length, max(0, time.perf_counter() - self.preview_started))
            self.progress.set(elapsed / self.preview_length * 100)
            self.time_text.set(f"{duration_label(elapsed)} / {duration_label(self.preview_length)}")
            if elapsed >= self.preview_length + 0.0:
                self.stop_preview()
                self.set_status("电脑试听结束，可以在游戏中试奏。", "试听完成", "blue")
                self.refresh_controls()

    def handle_message(self, message):
        kind = message["kind"]
        if kind.startswith("transpose"):
            if message["token"] != self.recommend_token:
                return
            self.recommend_token = None
            self.refresh_controls()
            if kind == "transpose_error":
                self.set_status(message["text"], "推荐失败", "amber")
            else:
                self.set_status("移调候选已就绪，应用后可试听对比。", "分析完成", "blue")
                self.show_transpositions(message)
        elif kind.startswith("preview"):
            if message["token"] != self.preview_token:
                return
            if kind == "preview_error":
                self.stop_preview()
                self.set_status(message["text"], "试听失败", "red")
            else:
                import winsound
                winsound.PlaySound(str(message["path"]), winsound.SND_FILENAME | winsound.SND_ASYNC)
                self.preview_started, self.preview_length = time.perf_counter(), message["seconds"]
                self.set_status(f'正在试听{message.get("caption", "适配曲谱")} · 最长 20 秒 · 合成音色', "电脑试听", "blue")
            self.refresh_controls()
        elif kind == "game_done":
            result = message["result"]
            if result.get("status") == "completed":
                self.progress.set(100)
                self.time_text.set(f'{duration_label(self.active["length"])} / {duration_label(self.active["length"])}')
                self.set_status("整段按键已发送完毕。", "演奏完成", "teal")
            else:
                stopped = result.get("status") == "stopped" or message["code"] == 2
                reason = result.get("reason") or ("权限确认已取消。" if message["code"] == 2 else f'演奏进程退出：{message["code"]}')
                self.set_status(reason, "已停止" if stopped else "演奏失败", "muted" if stopped else "red")
            self.active, self.stop_requested = None, False
            self.refresh_controls()

    def poll(self):
        if self.closed:
            return
        try:
            while True:
                self.handle_message(self.messages.get_nowait())
        except queue.Empty:
            pass
        self.update_progress()
        self.poll_job = self.root.after(120, self.poll)

    def show_details(self):
        score = self.score if self.refresh_job is None else self.update_score()
        if score is None:
            return
        window = tk.Toplevel(self.root)
        window.title(f"{self.song.title} · 曲谱明细")
        window.geometry("760x570")
        window.configure(bg=C["bg"])
        self.label(window, self.song.title, 18, bold=True, padx=20, pady=17).pack(anchor="w")
        self.label(window, str(self.current_path), 9, C["muted"], wraplength=710, justify="left", padx=20).pack(anchor="w")
        summary = score["summary"]
        self.label(window, f'{summary["notes"]} 音 · {summary["seconds"]:.2f} 秒 · 折回 {summary["folded"]} 音 · 简化和弦音 {summary["chord_notes_removed"]} 个', 9, C["muted"], padx=20, pady=12).pack(anchor="w")
        frame = tk.Frame(window, bg="white")
        frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))
        tree = ttk.Treeview(frame, columns=("index", "time", "note", "key", "duration"), show="headings", style="Desk.Treeview")
        for column, text, width in [("index", "序号", 60), ("time", "开始 / 秒", 120), ("note", "音名", 100), ("key", "游戏按键", 100), ("duration", "时值 / 秒", 120)]:
            tree.heading(column, text=text)
            tree.column(column, width=width, anchor="center")
        scroll = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        scroll.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill="both", expand=True)
        for index, event in enumerate(score["events"], 1):
            name = note_name(event["midi"])
            tree.insert("", "end", values=(index, f'{event["at"]:.3f}', name, score_instrument(score).keys[name].label, f'{event["duration"]:.3f}'))

    def show_adaptation(self):
        score = self.update_score()
        if score is None:
            return
        report = adaptation_report(score, performance_plan(score, int(self.hold_ms.get())))
        window = tk.Toplevel(self.root)
        window.title(f'{self.song.title} · 适配报告')
        window.geometry("790x590")
        window.configure(bg=C["bg"])
        self.label(window, "曲谱适配报告", 18, bold=True, padx=20, pady=15).pack(anchor="w")
        summary = report["summary"]
        text = (f'选中 {summary["source_notes"]} 音 → 保留 {summary["notes"]} 音  ·  简化 {summary["chord_notes_removed"]}  ·  '
                f'折回 {summary["folded"]}  ·  丢弃 {summary["dropped"]}  ·  重合合并 {summary.get("merged", 0)}')
        self.label(window, text, 9, C["muted"], padx=20).pack(anchor="w")
        self.label(window, f'混合黑白键 {report["performance"]["mixed_groups"]} 组 · 试听与演奏共享时序；以下变更位置按原曲时间显示。', 9, C["muted"], padx=20, pady=8).pack(anchor="w")
        footer = tk.Frame(window, bg=C["bg"])
        footer.pack(side="bottom", fill="x", padx=20, pady=15)
        self.label(footer, f'变更操作 {report["total_changes"]} 条' + (' · 明细只保留前 2000 条，计数完整' if report['truncated'] else ''), 9, C['muted']).pack(side='left')
        def export_report():
            path = filedialog.asksaveasfilename(parent=window, title="导出适配报告", defaultextension=".json",
                initialfile=export_name(report["title"]) + "_adaptation.json", filetypes=[("适配报告", "*.json")])
            if path:
                try:
                    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
                    self.set_status("适配报告已导出。", "导出成功", "teal")
                except OSError as error:
                    self.show_error(error)
        self.button(footer, "导出报告", export_report, "preview", 9).pack(side="right")
        frame = tk.Frame(window, bg='white')
        frame.pack(fill='both', expand=True, padx=20, pady=8)
        tree = ttk.Treeview(frame, columns=('time', 'track', 'action', 'source', 'target'), show='headings', style='Desk.Treeview')
        for key, title, width in [('time', '原曲 / 秒', 120), ('track', '音轨', 70), ('action', '处理', 140), ('source', '原音 → 移调', 175), ('target', '适配音', 100)]:
            tree.heading(key, text=title)
            tree.column(key, width=width, anchor='center')
        scroll = ttk.Scrollbar(frame, command=tree.yview)
        scroll.pack(side='right', fill='y')
        tree.configure(yscrollcommand=scroll.set)
        tree.pack(fill='both', expand=True)
        names = {'simplified': '声部简化', 'folded': '八度折回', 'dropped': '越界丢弃', 'merged': '同音重合合并'}
        for change in report['changes']:
            tree.insert('', 'end', values=(f'{change["source_at"]:.3f}', change['track'], names[change['action']],
                f'{note_name(change["source_midi"])} → {note_name(change["requested_midi"])}',
                note_name(change['midi']) if change['midi'] is not None else '—'))

    def export(self):
        score = self.score if self.refresh_job is None else self.update_score()
        if score is None:
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="导出游戏曲谱", defaultextension=".json", initialfile=export_name(self.song.title) + "_" + score_instrument(score).id + ".json", filetypes=[("游戏曲谱", "*.json")])
        if path:
            try:
                save_score(score, path)
                self.set_status(f"已导出：{Path(path).name}", "导出成功", "teal")
            except Exception as error:
                self.show_error(error)

    def export_midi(self):
        if self.song is None or self.active:return
        path = filedialog.asksaveasfilename(parent=self.root,title="另存原曲为 MIDI",defaultextension=".mid",
                    initialfile=export_name(self.song.title)+".mid",filetypes=[("标准 MIDI", "*.mid")])
        if path:
            try:
                write_midi(self.song,path)
                self.set_status(f"已另存原曲的全部声部：{Path(path).name}","MIDI 已保存","teal")
            except Exception as error:self.show_error(error)

    def callback_error(self, exception, error, traceback):
        self.show_error(error)

    def show_error(self, error):
        logging.getLogger(__name__).error("UI operation failed: %s", error)
        messagebox.showerror("无法完成", str(error), parent=self.root)

    def close(self):
        if self.online_dialog is not None:
            self.online_dialog.close()
        self.save_preferences()
        self.save_arrangement()
        self.stop()
        self.closed = True
        self.root.after_cancel(self.poll_job)
        if self.refresh_job is not None:
            self.root.after_cancel(self.refresh_job)
        self.root.destroy()
