"""Audio transcription setup and job view; all widget access stays on Tk thread."""
import json
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog
import webbrowser

from .transcription import ProcessJob, managed_python, engine_command, clean_log
from .appearance import RoundedPanel


class AudioDialog:
    def __init__(self, app):
        self.app, self.closed, self.job = app, False, None
        self.messages = queue.Queue()
        self.config = app.directory / 'audio-engine.json'
        try:
            settings = json.loads(self.config.read_text(encoding='utf-8'))
            if not isinstance(settings, dict): settings = {}
        except (OSError, ValueError):
            settings = {}
        self.window = tk.Toplevel(app.root)
        self.window.title('音频转谱 · MuScriptor')
        self.window.geometry('840x690')
        self.window.minsize(740, 630)
        self.window.configure(bg='#EDECE6')
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.executable = tk.StringVar(value=settings.get('executable', str(managed_python(app.directory))))
        self.source = tk.StringVar()
        self.model = tk.StringVar(value=settings.get('model', 'small'))
        self.device = tk.StringVar(value=settings.get('device', 'cpu'))
        self.state = tk.StringVar(value='选择音频 → 配置一次引擎 → 转为 MIDI → 多轨试听与适配')
        self.result = None
        body = RoundedPanel(self.window, padx=22, pady=18)
        body.pack(fill='both', expand=True, padx=18, pady=18)
        app.label(body, '把音乐带入工作台', 18, bold=True).pack(anchor='w')
        app.label(body, '多乐器自动识别 · 保留原始 MIDI · 转谱后手动试听，再开始游戏演奏', 10, '#738078').pack(anchor='w', pady=(6, 16))
        self.controls = []
        self.path_row(body, '音频文件', self.source, self.choose_audio)
        self.path_row(body, '引擎 Python / EXE', self.executable, self.choose_engine)
        options = tk.Frame(body, bg='#FCFBF7')
        options.pack(fill='x', pady=(8, 10))
        for text, var, values in [('模型', self.model, ('small', 'medium', 'large')), ('设备', self.device, ('cpu', 'auto', 'cuda'))]:
            app.label(options, text, 10).pack(side='left', padx=(0, 8))
            widget = ttk.Combobox(options, textvariable=var, values=values, state='readonly', width=12)
            widget.pack(side='left', padx=(0, 20))
            self.controls.append((widget, 'readonly'))
        app.label(body, 'small 适合 CPU；medium / large 更占资源。建议先用 15–30 秒片段核对。\n人声、鼓点、混音可能产生错音和漏音；识别不恢复原曲力度、踏板或原音色。', 9, '#738078', justify='left').pack(anchor='w')
        setup = tk.Frame(body, bg='#FCFBF7')
        setup.pack(fill='x', pady=(14, 8))
        install = app.button(setup, '安装 / 更新独立引擎…', self.install, size=9)
        install.pack(side='left')
        self.controls.append((install, 'normal'))
        app.button(setup, '模型授权页面', self.open_license, size=9).pack(side='left', padx=8)
        app.button(setup, '配置说明', self.help, size=9).pack(side='left')
        app.label(body, '首次安装需要完整 Python 3.10+，会下载 PyTorch 等较大依赖。\n模型须自行接受 CC BY-NC 4.0 许可并登录 Hugging Face；软件不包含模型。', 9, '#95620D', justify='left').pack(anchor='w', pady=(0, 12))
        app.label(body, textvariable=self.state, size=10, wraplength=720, justify='left').pack(anchor='w', pady=(0, 8))
        self.progress = ttk.Progressbar(body, mode='indeterminate', style='Desk.Horizontal.TProgressbar')
        self.progress.pack(fill='x')
        self.log = tk.Text(body, height=7, wrap='word', relief='flat', bg='#F3F2EB', padx=10, pady=8, state='disabled', font=('Consolas', 9))
        self.log.pack(fill='both', expand=True, pady=10)
        actions = tk.Frame(body, bg='#FCFBF7')
        actions.pack(fill='x')
        self.start_button = app.button(actions, '开始音频转谱', self.transcribe, 'primary', 11)
        self.start_button.pack(side='right')
        self.controls.append((self.start_button, 'normal'))
        self.cancel_button = app.button(actions, '取消任务', self.cancel, 'stop', 9, state='disabled')
        self.cancel_button.pack(side='right', padx=10)
        self.import_button = app.button(actions, '导入结果', self.import_result, size=9, state='disabled')
        self.import_button.pack(side='left')
        self.poll_id = self.window.after(120, self.poll)

    def path_row(self, body, label, variable, command):
        row = tk.Frame(body, bg='#FCFBF7')
        row.pack(fill='x', pady=5)
        self.app.label(row, label, 10, width=19, anchor='w').pack(side='left')
        entry = ttk.Entry(row, textvariable=variable)
        entry.pack(side='left', fill='x', expand=True)
        button = self.app.button(row, '浏览…', command, size=9)
        button.pack(side='left', padx=(8, 0))
        self.controls += [(entry, 'normal'), (button, 'normal')]

    def choose_audio(self):
        path = filedialog.askopenfilename(parent=self.window, title='选择音频', filetypes=[('音频', '*.wav *.mp3 *.flac *.ogg *.m4a *.aif *.aiff'), ('所有文件', '*.*')])
        if path: self.source.set(path)

    def choose_engine(self):
        path = filedialog.askopenfilename(parent=self.window, title='选择已安装 MuScriptor 的 python.exe 或 muscriptor.exe', filetypes=[('解释器 / 引擎', '*.exe'), ('所有文件', '*.*')])
        if path: self.executable.set(path)

    def open_license(self):
        model = self.model.get() if self.model.get() in ('small', 'medium', 'large') else 'small'
        webbrowser.open('https://huggingface.co/MuScriptor/muscriptor-' + model)

    def help(self):
        self.app.show_help(filename='AUDIO_TRANSCRIPTION.md')

    def save(self):
        self.config.write_text(json.dumps({'executable': self.executable.get(), 'model': self.model.get(), 'device': self.device.get()}, indent=2), encoding='utf-8')

    def begin(self, operation, caption):
        if self.job or self.app.active:
            return
        self.app.stop_preview()
        self.job = ProcessJob()
        job = self.job
        for widget, _ in self.controls: widget.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self.import_button.configure(state='disabled')
        self.state.set(caption)
        self.progress.start(12)
        self.app.refresh_controls()
        def worker():
            try:
                result = operation(job, lambda text: self.messages.put(('log', text)))
                self.messages.put(('done', result))
            except Exception as error:
                self.messages.put(('error', str(error)))
        # Keep cleanup alive until a cancelled engine process has exited.
        threading.Thread(target=worker, daemon=False).start()

    def install(self):
        path = filedialog.askopenfilename(parent=self.window, title='选择完整 Python 3.10+ 的 python.exe（将创建独立环境，不修改原环境）', filetypes=[('Python', 'python.exe'), ('所有文件', '*.*')])
        if path:
            self.begin(lambda job, log: ('installed', job.install(path, self.app.directory, log)), '正在安装独立引擎；依赖下载可能较大，请稍候…')

    def transcribe(self):
        executable, source, model, device = self.executable.get(), self.source.get(), self.model.get(), self.device.get()
        try:
            engine_command(executable)
            if not source.strip(): raise ValueError('请先选择音频文件。')
            self.save()
        except (ValueError, OSError) as error:
            self.state.set(str(error))
            return
        self.begin(lambda job, log: ('transcribed', job.transcribe(executable, source, self.app.directory, model, device, log)), '引擎正在加载模型或转谱；首次运行可能需要下载已授权的模型…')

    def cancel(self):
        if self.job:
            self.job.cancel()
            self.state.set('正在停止引擎，请稍候…')

    def import_result(self):
        if self.result and not self.app.active and not self.job:
            self.app.open_path(self.result)
            self.state.set('已导入原始 MIDI。请在多轨工作区核对声部，再试听适配结果。')

    def poll(self):
        while not self.messages.empty():
            kind, value = self.messages.get_nowait()
            if kind == 'log':
                self.log.configure(state='normal')
                self.log.delete('1.0', 'end')
                self.log.insert('end', clean_log(value))
                self.log.configure(state='disabled')
                continue
            cancelled = self.job is not None and self.job.cancelled.is_set()
            self.job = None
            self.progress.stop()
            for widget, state in self.controls: widget.configure(state=state)
            self.cancel_button.configure(state='disabled')
            self.app.refresh_controls()
            if cancelled:
                self.state.set('任务已取消；未自动导入结果。')
            elif kind == 'error':
                detail = clean_log(value)
                self.state.set(detail.splitlines()[0][:200])
                self.log.configure(state='normal')
                self.log.delete('1.0', 'end')
                self.log.insert('end', detail)
                self.log.configure(state='disabled')
            elif value[0] == 'installed':
                self.executable.set(str(value[1]))
                self.save()
                self.state.set('引擎已安装。请完成模型授权与登录，然后开始音频转谱。')
            else:
                self.result = value[1]
                self.import_button.configure(state='normal')
                self.import_result()
        if not self.closed:
            self.poll_id = self.window.after(120, self.poll)

    def close(self):
        if self.closed: return
        self.closed = True
        self.cancel()
        self.window.after_cancel(self.poll_id)
        self.window.destroy()
        self.app.audio_dialog = None
        if not self.app.closed: self.app.refresh_controls()
