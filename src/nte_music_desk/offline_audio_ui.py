"""A small native workflow for the bundled offline engines."""
import os
from pathlib import Path
import queue
import time
import tkinter as tk
from tkinter import filedialog, ttk

from .appearance import COLORS as C, RoundedPanel
from .display import available_window_size, pixels
from .offline_audio import OfflineJob, OfflineRequest, PROFILES, verify_bundle
from .segments import parse_time

READY_MESSAGE = '识别在这台电脑上完成，音频不会上传。'


def remaining_label(seconds):
    if seconds < 60:
        low = max(1, int(seconds * .75)); high = max(low + 5, int(seconds * 1.35))
        return f'预计还需 {low}–{high} 秒'
    low = max(1, int(seconds * .75 / 60)); high = max(low + 1, int(seconds * 1.35 / 60 + .99))
    return f'预计还需 {low}–{high} 分钟'


class OfflineAudioDialog:
    def __init__(self, app, source=None):
        self.app, self.closed, self.job = app, False, None
        self.messages = queue.Queue()
        self.result = self.audition = None
        self.background_requested = False
        self.window = tk.Toplevel(app.root)
        self.window.title('本地音频转谱')
        self.window.configure(bg=C['bg'])
        self.window.geometry(f'{pixels(self.window, 700)}x{pixels(self.window, 610)}')
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        try: self.window.iconbitmap(str(app.assets / 'icon.ico'))
        except tk.TclError: pass
        self.source = tk.StringVar(value=str(source) if source else '')
        saved = app.preferences.get('offline_audio_profile', 'piano')
        self.profile = saved if saved in PROFILES else 'piano'
        self.start, self.end = tk.StringVar(value='0:00'), tk.StringVar()
        self.state = tk.StringVar(value=READY_MESSAGE)
        self.eta = tk.StringVar()
        self.value = tk.DoubleVar()
        self.controls = []
        body = RoundedPanel(self.window, padx=24, pady=22)
        body.pack(fill='both', expand=True, padx=18, pady=(18, 12))
        app.label(body, '把录音变成曲谱', 20, bold=True).pack(anchor='w')
        app.label(body, '选择音频类型，即可开始。完整包已包含模型和运行组件。', 10).pack(anchor='w', pady=(7, 24))
        app.label(body, '音频文件', 10, bold=True).pack(anchor='w')
        row = tk.Frame(body, bg=C['paper']); row.pack(fill='x', pady=(9, 24))
        field = RoundedPanel(row, fill=C['bg'], padx=12, pady=10, radius=10)
        field.pack(side='left', fill='x', expand=True, padx=(0, 8))
        entry = tk.Entry(field, textvariable=self.source, relief='flat', bg=C['bg'], fg=C['ink'], font=('Microsoft YaHei UI', 10))
        entry.pack(fill='x'); self.controls.append(entry)
        choose = app.button(row, '选择文件', self.choose, size=10)
        choose.pack(side='right'); self.controls.append(choose)
        app.label(body, '这是什么音乐？', 10, bold=True).pack(anchor='w')
        row = tk.Frame(body, bg=C['paper']); row.pack(fill='x', pady=(10, 7))
        row.columnconfigure((0, 1), weight=1, uniform='profiles')
        self.profile_buttons = {}
        for col, (key, caption) in enumerate(PROFILES.items()):
            button = app.button(row, caption, lambda value=key: self.select_profile(value), size=11)
            button.grid(row=0, column=col, sticky='ew', padx=(0, 7) if col == 0 else (7, 0))
            self.profile_buttons[key] = button; self.controls.append(button)
        self.description = tk.StringVar()
        app.label(body, textvariable=self.description, size=9, wraplength=590, justify='left').pack(anchor='w', pady=(4, 20))
        self.select_profile(self.profile)
        self.segment_button = app.button(body, '选取片段  ›', self.toggle_segment, 'nav', 9)
        self.segment_button.pack(anchor='w'); self.controls.append(self.segment_button)
        self.segment = tk.Frame(body, bg=C['paper'])
        for caption, variable in [('从', self.start), ('到', self.end)]:
            app.label(self.segment, caption, 9).pack(side='left', padx=(0, 8))
            panel = RoundedPanel(self.segment, fill=C['bg'], padx=10, pady=8, radius=9)
            panel.pack(side='left', padx=(0, 14))
            entry = tk.Entry(panel, textvariable=variable, width=9, relief='flat', font=('Microsoft YaHei UI', 10), bg=C['bg'], fg=C['ink'])
            entry.pack(); self.controls.append(entry)
        app.label(self.segment, '分:秒；终点留空至曲末', 9).pack(side='left')
        self.segment_visible = False
        footer = RoundedPanel(self.window, padx=22, pady=18)
        footer.pack(side='bottom', before=body, fill='x', padx=18, pady=(0, 18))
        app.label(footer, textvariable=self.state, size=10, wraplength=610, justify='left').pack(anchor='w')
        self.progress_row = tk.Frame(footer, bg=C['paper'])
        ttk.Progressbar(self.progress_row, maximum=100, variable=self.value, style='Desk.Horizontal.TProgressbar').pack(fill='x', pady=(12, 6))
        app.label(self.progress_row, textvariable=self.eta, size=9).pack(anchor='w')
        self.result_row = tk.Frame(footer, bg=C['paper'])
        app.button(self.result_row, '对照试听', self.compare, 'preview', 9).pack(side='left')
        app.button(self.result_row, '结果文件夹 ↗', self.open_folder, 'nav', 9).pack(side='left', padx=(10, 0))
        actions = tk.Frame(footer, bg=C['paper']); actions.pack(fill='x', pady=(14, 0))
        self.start_button = app.button(actions, '开始转谱', self.begin, 'primary', 11)
        self.start_button.pack(side='right')
        self.cancel_button = app.button(actions, '取消任务', self.cancel, size=10)
        self.background_button = app.button(actions, '后台运行', self.run_in_background, 'nav', 10)
        self.stage, self.fraction, self.audio_seconds = 'decode', 0, None
        self.started = self.recognize_started = self.vocal_started = None
        self._changing_inputs = False
        self._inputs = self.input_settings()
        self._input_traces = [(variable, variable.trace_add('write', self.inputs_changed))
                              for variable in (self.source, self.start, self.end)]
        self.poll_id = self.window.after(100, self.poll)
        self.fit_window()

    def fit_window(self):
        window = self.window
        window.update_idletasks()
        available_width, available_height = available_window_size(window)
        width = min(available_width, max(pixels(window, 700), window.winfo_reqwidth(), window.winfo_width()))
        height = min(available_height, max(pixels(window, 610), window.winfo_reqheight()))
        window.minsize(min(width, pixels(window, 620)), height)
        window.geometry(f'{width}x{height}')

    def select_profile(self, profile):
        if self.job: return
        changed = profile != self.profile
        self.profile = profile
        for key, button in self.profile_buttons.items():
            bg, fg = (C['teal'], C['paper']) if key == profile else (C['bg'], C['ink'])
            button.palette = (bg, fg, bg)
            button.configure(bg=bg, fg=fg, activebackground=bg, activeforeground=fg)
        self.description.set('优先保留钢琴的和弦、低音与力度。适合独奏钢琴录音。' if profile == 'piano' else
                             '尝试识别旋律与伴奏声部；密集配器、混响和人声仍可能出现错漏音。')
        if changed: self.inputs_changed()

    def input_settings(self):
        source = self.source.get().strip()
        if source:
            source = os.path.normcase(os.path.abspath(os.path.expanduser(source)))
        return source, self.profile, self.start.get().strip(), self.end.get().strip()

    def inputs_changed(self, *_):
        if self.closed or self.job or self._changing_inputs: return
        settings = self.input_settings()
        if settings == self._inputs: return
        if settings[0] != self._inputs[0]:
            # A different recording should not inherit the previous excerpt.
            self._changing_inputs = True
            try:
                self.start.set('0:00'); self.end.set('')
            finally:
                self._changing_inputs = False
        self._inputs = self.input_settings()
        self.clear_result()

    def clear_result(self):
        if self.job: return
        if self.audition:
            self.audition.close()
            self.audition = None
        self.result = None
        self.state.set(READY_MESSAGE); self.eta.set(''); self.value.set(0)
        self.stage, self.fraction, self.audio_seconds = 'decode', 0, None
        self.started = self.recognize_started = self.vocal_started = None
        self.result_row.pack_forget(); self.progress_row.pack_forget()
        self.cancel_button.pack_forget()
        self.background_button.pack_forget()
        self.background_requested = False
        self.start_button.configure(state='normal', text='开始转谱')
        self.fit_window()

    def toggle_segment(self):
        self.segment_visible = not self.segment_visible
        if self.segment_visible: self.segment.pack(fill='x', pady=(8, 0))
        else: self.segment.pack_forget()
        self.segment_button.configure(text='收起选段  ‹' if self.segment_visible else '选取片段  ›')
        self.fit_window()

    def choose(self):
        if self.job: return
        source = filedialog.askopenfilename(parent=self.window, title='选择本地音频', filetypes=[('音频文件', '*.wav *.mp3 *.flac *.ogg *.m4a *.aac *.wma *.opus *.webm *.aif *.aiff'), ('所有文件', '*.*')])
        if source: self.choose_source(source)

    def choose_source(self, source):
        if not self.job:
            self.source.set(str(source))
            self.window.deiconify(); self.window.lift()

    def begin(self):
        if self.job or self.app.audio_busy(): return
        self.clear_result()
        try:
            request = OfflineRequest(Path(self.source.get()).expanduser(), self.profile,
                parse_time(self.start.get()), parse_time(self.end.get()) if self.end.get().strip() else None)
            # Bind each worker to its own queue. Late callbacks from an old
            # task cannot change the state of a subsequent recording.
            self.messages = queue.Queue()
            self.workbench_path = self.app.current_path
            self.workbench_revision = self.app.song_revision
            job = OfflineJob(self.app.directory, request, self.messages.put)
            job.start()
            self.job = job
        except (ValueError, OSError) as error:
            self.state.set(str(error)); return
        self.result = None; self.result_row.pack_forget()
        self.started = time.monotonic(); self.recognize_started = None
        self.vocal_started = None
        self.stage, self.fraction, self.audio_seconds = 'decode', 0, None
        self.value.set(0); self.progress_row.pack(fill='x', before=self.start_button.master)
        self.start_button.configure(state='disabled', text='正在转谱')
        self.cancel_button.pack(side='right', padx=(0, 10)); self.cancel_button.configure(state='normal')
        self.background_button.pack(side='left')
        for control in self.controls: control.configure(state='disabled')
        self.app.preferences['offline_audio_profile'] = self.profile
        self.app.save_preferences(); self.app.refresh_controls()
        self.fit_window()

    def cancel(self):
        if self.job:
            self.job.cancel()
            self.state.set('正在取消并停止本地引擎…')
            self.cancel_button.configure(state='disabled')

    def run_in_background(self):
        if not self.job: return
        self.background_requested = True
        self.window.withdraw()
        self.app.refresh_controls()
        if not self.app.playback_busy():
            self.app.set_status('本地转谱在后台进行，可继续选曲和演奏。','后台转谱中','blue')

    def finish(self, message):
        cancelled = self.job and self.job.cancelled.is_set()
        background = self.background_requested
        self.job = None
        self.clear_result()
        for control in self.controls: control.configure(state='normal')
        self.select_profile(self.profile)
        if cancelled or message['kind'] == 'cancelled':
            self.state.set('任务已取消，未自动导入曲谱。'); self.eta.set('')
        elif message['kind'] == 'error':
            self.state.set(message['error']); self.eta.set('处理未完成')
        else:
            self.result = message
            self.start_button.configure(text='再次转谱')
            self.progress_row.pack(fill='x', before=self.start_button.master)
            self.value.set(100); self.eta.set('已完成 · 100%')
            auto_load = (not background and not self.app.playback_busy() and
                         self.app.current_path == getattr(self, 'workbench_path', self.app.current_path) and
                         self.app.song_revision == getattr(self, 'workbench_revision', self.app.song_revision))
            state = self.app.accept_transcription(Path(message['midi']), auto_load=auto_load)
            self.state.set(f"识别出 {message['notes']} 个音符，已保存。" + ('已载入工作台，可先对照试听。' if state == 'loaded' else '请从曲目列表载入。'))
            self.result_row.pack(fill='x', pady=(12, 0), before=self.start_button.master)
        self.app.refresh_controls()
        self.fit_window()

    def poll(self):
        if self.closed: return
        while True:
            try: message = self.messages.get_nowait()
            except queue.Empty: break
            if not self.job: continue
            if message['kind'] == 'progress':
                if self.job.cancelled.is_set(): continue
                self.stage, self.fraction = message['stage'], message['progress']
                if self.stage == 'vocal' and self.vocal_started is None: self.vocal_started = time.monotonic()
                if self.stage == 'recognize' and self.recognize_started is None: self.recognize_started = time.monotonic()
                self.audio_seconds = message.get('duration', self.audio_seconds)
                self.value.set(self.fraction * 100)
            else: self.finish(message)
        if self.job and not self.job.cancelled.is_set():
            elapsed = time.monotonic() - self.started
            captions = {'decode': '读取音频', 'load': '加载本地模型', 'vocal': '识别演唱旋律', 'recognize': '识别钢琴音符' if self.profile == 'piano' else '识别伴奏声部', 'organize': '整理曲谱', 'save': '保存与准备对照试听'}
            self.state.set(f"{captions.get(self.stage, '正在处理')} · {round(self.fraction * 100)}%")
            if self.stage in ('organize', 'save'):
                self.eta.set('预计还需 5–15 秒' if elapsed < 15 or self.stage != 'save' else '正在完成保存与试听准备…')
            elif self.stage == 'recognize' and self.recognize_started is not None and self.fraction > (.35 if self.profile == 'song' else .08):
                base, span = (.34, .60) if self.profile == 'song' else (.04, .90)
                fraction = min(.999, max(.001, (self.fraction - base) / span))
                work = time.monotonic() - self.recognize_started
                self.eta.set(remaining_label(max(5, work * (1 - fraction) / fraction + 8)))
            elif self.stage == 'vocal' and self.vocal_started is not None and self.fraction > .05:
                fraction = min(.999, max(.001, (self.fraction - .04) / .30))
                work = time.monotonic() - self.vocal_started
                # Include the accompaniment still to come; then measure its
                # real throughput when it starts. No completion guarantee.
                remaining = work * (1 - fraction) / fraction + self.audio_seconds * .4 + 8
                self.eta.set(remaining_label(max(5, remaining)) + ' · 按本机进度更新')
            elif self.audio_seconds:
                estimate = self.audio_seconds * (1.5 if self.profile == 'piano' else .6) + 12
                phase_elapsed = time.monotonic() - self.recognize_started if self.stage == 'recognize' and self.recognize_started else elapsed
                self.eta.set(remaining_label(max(10, estimate - phase_elapsed)) + ' · 按本机进度更新')
            else: self.eta.set('正在读取选段长度并估计时间…')
        self.poll_id = self.window.after(100, self.poll)

    def compare(self):
        if not self.result or self.job or self.app.active: return
        from .audio_audition import AuditionWindow
        directory = Path(self.result['midi']).parent
        try:
            self.app.stop_preview()
            self.audition = self.app.audio_audition = AuditionWindow(self.app,
                {'原音频': directory / 'audio-preview.wav', '识别曲谱 · 原调': directory / 'score-preview.wav'}, self.result['start'])
        except (OSError, ValueError) as error: self.state.set(str(error))

    def open_folder(self):
        if self.result: os.startfile(Path(self.result['midi']).parent)

    def close(self):
        if self.closed: return
        self.closed = True
        if self.job: self.job.cancel()
        for variable, trace in self._input_traces:
            variable.trace_remove('write', trace)
        self.window.after_cancel(self.poll_id)
        self.window.destroy()
        self.app.offline_dialog = None
        self.app.refresh_controls()
