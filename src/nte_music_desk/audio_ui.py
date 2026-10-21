"""Accompaniment first; singing melody is an explicit, independent Beta."""
import json
import os
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog
import webbrowser

from .transcription import managed_python, clean_log
from .audio_pipeline import AudioPipeline, AudioRequest, python_engine
from .appearance import RoundedPanel
from .segments import parse_time
from .rights import SOURCE_BASES, MUSCRIPTOR_TERMS, GAME_TERMS

FLOWS={'accompaniment':'伴奏（默认）','melody':'仅主旋律（Beta）'}
KINDS={'instrumental':'已有伴奏 / 纯音乐','original':'原唱 / 含人声（主旋律 Beta）'}
DEVICES={'auto':'自动选择','cpu':'CPU','cuda':'NVIDIA GPU'}
LANGUAGES={'auto':'通用','zh':'中文','ja':'日文','en':'英文','yue':'粤语'}


def selected(mapping,value):
    return next((key for key,label in mapping.items() if label==value),next(iter(mapping)))


class AudioDialog:
    def __init__(self,app):
        self.app,self.closed,self.job=app,False,None
        self.messages=queue.Queue()
        self.config=app.directory/'audio-engine.json'
        try:
            settings=json.loads(self.config.read_text(encoding='utf-8'))
            if not isinstance(settings,dict):settings={}
        except (OSError,ValueError):settings={}
        self.window=tk.Toplevel(app.root)
        self.window.title('音频转谱 · 伴奏与旋律 Beta')
        self.window.geometry('920x820')
        self.window.minsize(800,680)
        self.window.configure(bg='#EDECE6')
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        self.executable=tk.StringVar(value=settings.get('executable',str(managed_python(app.directory))))
        self.source=tk.StringVar()
        self.model=tk.StringVar(value=settings.get('model','medium'))
        self.device=tk.StringVar(value=DEVICES.get(settings.get('device'),DEVICES['auto']))
        self.flow=tk.StringVar(value=FLOWS.get(settings.get('workflow'),FLOWS['accompaniment']))
        self.source_kind=tk.StringVar(value=KINDS['instrumental'])
        self.language=tk.StringVar(value=LANGUAGES.get(settings.get('language'),LANGUAGES['auto']))
        self.start,self.end=tk.StringVar(value='0:00'),tk.StringVar()
        self.rights_basis=tk.StringVar(value='请选择使用依据')
        self.rights_reference=tk.StringVar()
        self.muscriptor_terms,self.game_terms=tk.BooleanVar(),tk.BooleanVar()
        self.source.trace_add('write',self.reset_source_rights)
        self.state=tk.StringVar(value='导入音频，生成伴奏曲谱；也可单独试用主旋律 Beta。')
        self.result=None
        self.result_paths={}
        self.controls=[]
        self.setup_open=False

        footer=RoundedPanel(self.window,padx=18,pady=14)
        footer.pack(side='bottom',fill='x',padx=18,pady=(0,14))
        app.label(footer,textvariable=self.state,size=10,wraplength=840,justify='left').pack(anchor='w')
        self.progress=ttk.Progressbar(footer,mode='indeterminate',style='Desk.Horizontal.TProgressbar')
        self.progress.pack(fill='x',pady=(9,12))
        actions=tk.Frame(footer,bg='#FCFBF7');actions.pack(fill='x')
        self.start_button=app.button(actions,'生成伴奏曲谱',self.transcribe,'primary',11)
        self.start_button.pack(side='right')
        self.controls.append((self.start_button,'normal'))
        self.cancel_button=app.button(actions,'取消任务',self.cancel,'stop',9,state='disabled')
        self.cancel_button.pack(side='right',padx=8)
        self.result_choice=tk.StringVar()
        self.result_selector=ttk.Combobox(actions,textvariable=self.result_choice,values=(),state='disabled',width=23)
        self.result_selector.pack(side='left',fill='x',expand=True,padx=(0,8))
        self.import_button=app.button(actions,'导入工作台',self.import_result,size=9,state='disabled')
        self.import_button.pack(side='left')
        listen=tk.Frame(footer,bg='#FCFBF7');listen.pack(fill='x',pady=(9,0))
        self.original_button=app.button(listen,'♫ 音频片段',self.preview_audio,'preview',9,state='disabled')
        self.original_button.pack(side='left')
        app.button(listen,'停止试听',app.stop_preview,size=9).pack(side='left',padx=8)
        self.folder_button=app.button(listen,'结果文件夹 ↗',self.open_results,size=9,state='disabled')
        self.folder_button.pack(side='right')

        outer=tk.Frame(self.window,bg='#EDECE6')
        outer.pack(fill='both',expand=True,padx=18,pady=(18,12))
        self.canvas=tk.Canvas(outer,bg='#EDECE6',highlightthickness=0)
        scroll=ttk.Scrollbar(outer,orient='vertical',command=self.canvas.yview)
        scroll.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True)
        self.canvas.configure(yscrollcommand=scroll.set)
        body=RoundedPanel(self.canvas,padx=22,pady=18)
        body_id=self.canvas.create_window(0,0,window=body,anchor='nw')
        body.bind('<Configure>',lambda e:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(body_id,width=e.width))
        self.window.bind('<MouseWheel>',self.scroll_body)
        app.label(body,'把音乐带入工作台',18,bold=True).pack(anchor='w')
        app.label(body,'伴奏优先保留低音与和声；主旋律 Beta 独立保存，按需试听。',10,'#738078').pack(anchor='w',pady=(6,15))
        self.path_row(body,'音频文件',self.source,self.choose_audio)
        self.kind_box=self.combo_row(body,'音频类型',self.source_kind,list(KINDS.values()))
        self.flow_box=self.combo_row(body,'生成内容',self.flow,list(FLOWS.values()))
        self.flow_box.bind('<<ComboboxSelected>>',self.flow_changed)

        row=tk.Frame(body,bg='#FCFBF7');row.pack(fill='x',pady=7)
        app.label(row,'音频选段',10,width=19,anchor='w').pack(side='left')
        for caption,var in [('从',self.start),('到',self.end)]:
            app.label(row,caption,9).pack(side='left',padx=(0,6))
            entry=ttk.Entry(row,textvariable=var,width=9)
            entry.pack(side='left',padx=(0,10))
            self.controls.append((entry,'normal'))
        whole=app.button(row,'整段音频',self.whole,size=8)
        whole.pack(side='left');self.controls.append((whole,'normal'))
        app.label(body,'支持 分:秒；终点留空为整段。首次建议先选 15–30 秒核对效果。',9,'#738078').pack(anchor='w',pady=(0,10))
        row=tk.Frame(body,bg='#FCFBF7');row.pack(fill='x',pady=(3,10))
        app.label(row,'伴奏识别',10,width=19,anchor='w').pack(side='left')
        self.model_box=ttk.Combobox(row,textvariable=self.model,values=('small','medium','large'),state='readonly',width=10)
        self.model_box.pack(side='left',padx=(0,12));self.controls.append((self.model_box,'readonly'))
        self.device_box=ttk.Combobox(row,textvariable=self.device,values=list(DEVICES.values()),state='readonly',width=14)
        self.device_box.pack(side='left');self.controls.append((self.device_box,'readonly'))
        self.language_box=self.combo_row(body,'旋律 Beta 语言',self.language,list(LANGUAGES.values()))
        self.description=tk.StringVar()
        app.label(body,textvariable=self.description,size=9,color='#95620D',wraplength=780,justify='left').pack(anchor='w',pady=(3,12))

        self.combo_row(body,'素材使用依据',self.rights_basis,list(SOURCE_BASES.values()))
        row=tk.Frame(body,bg='#FCFBF7');row.pack(fill='x',pady=5)
        app.label(row,'来源 / 授权说明',10,width=19,anchor='w').pack(side='left')
        reference=ttk.Entry(row,textvariable=self.rights_reference)
        reference.pack(side='left',fill='x',expand=True);self.controls.append((reference,'normal'))
        app.label(body,'填写原创录音说明、许可链接或授权记录。仅作来源记录，未经独立核验；公开 MIDI 或视频须另核对权限。',9,'#738078',wraplength=780,justify='left').pack(anchor='w',pady=(3,6))
        self.muscriptor_check=ttk.Checkbutton(body,text='已阅读 MuScriptor 模型条款（CC BY-NC 4.0＋附加条件），本次使用符合非商业限制',variable=self.muscriptor_terms)
        self.game_check=ttk.Checkbutton(body,text='已阅读 GAME 权重条款（CC BY-NC-SA 4.0），本次使用符合非商业限制',variable=self.game_terms)
        for check in (self.muscriptor_check,self.game_check):
            check.pack(anchor='w',pady=3);self.controls.append((check,'normal'))
        links=tk.Frame(body,bg='#FCFBF7');links.pack(fill='x',pady=(0,10))
        app.button(links,'MuScriptor 条款 ↗',self.open_license,size=8).pack(side='left')
        app.button(links,'GAME 条款 ↗',lambda:webbrowser.open('https://github.com/openvpi/GAME/releases/tag/v1.0.0'),size=8).pack(side='left',padx=8)

        self.setup_button=app.button(body,'▸ 引擎配置与检查',self.toggle_setup,size=9)
        self.setup_button.pack(anchor='w',pady=(0,8))
        self.setup_panel=tk.Frame(body,bg='#FCFBF7')
        self.path_row(self.setup_panel,'引擎 Python',self.executable,self.choose_engine)
        row=tk.Frame(self.setup_panel,bg='#FCFBF7');row.pack(fill='x',pady=8)
        for caption,command in [('安装 / 更新独立引擎…',self.install),('检查环境',self.check_environment)]:
            button=app.button(row,caption,command,size=9)
            button.pack(side='left',padx=(0,8));self.controls.append((button,'normal'))
        app.button(row,'伴奏模型授权',self.open_license,size=9).pack(side='left',padx=(0,8))
        app.button(row,'配置说明',self.help,size=9).pack(side='left')
        app.label(self.setup_panel,'伴奏使用 MuScriptor，首次需自行接受模型条款并登录。选择 NVIDIA GPU 后安装会配置 CUDA 组件。\n旋律 Beta 使用 GAME（约 46 MB），确认条款后才下载或调用。音频在本机处理；安装依赖和首次获取模型需要联网。',9,'#738078',wraplength=780,justify='left').pack(anchor='w',pady=(0,12))
        app.label(body,'处理记录',10,bold=True).pack(anchor='w',pady=(6,6))
        self.log=tk.Text(body,height=7,wrap='word',relief='flat',bg='#F3F2EB',padx=10,pady=8,state='disabled',font=('Consolas',9))
        self.log.pack(fill='both',expand=True)
        self.flow_changed()
        if not Path(self.executable.get()).is_file():self.toggle_setup()
        self.poll_id=self.window.after(120,self.poll)

    def scroll_body(self,event):
        if isinstance(event.widget,tk.Text):return 'break'
        if not isinstance(event.widget,(ttk.Combobox,ttk.Entry)):
            self.canvas.yview_scroll(-int(event.delta/120),'units')
        return 'break'

    def path_row(self,body,label,variable,command):
        row=tk.Frame(body,bg='#FCFBF7');row.pack(fill='x',pady=5)
        self.app.label(row,label,10,width=19,anchor='w').pack(side='left')
        entry=ttk.Entry(row,textvariable=variable);entry.pack(side='left',fill='x',expand=True)
        button=self.app.button(row,'浏览…',command,size=9);button.pack(side='left',padx=(8,0))
        self.controls += [(entry,'normal'),(button,'normal')]

    def combo_row(self,body,label,variable,values):
        row=tk.Frame(body,bg='#FCFBF7');row.pack(fill='x',pady=5)
        self.app.label(row,label,10,width=19,anchor='w').pack(side='left')
        box=ttk.Combobox(row,textvariable=variable,values=values,state='readonly')
        box.pack(side='left',fill='x',expand=True)
        self.controls.append((box,'readonly'))
        return box

    def toggle_setup(self):
        self.setup_open=not self.setup_open
        if self.setup_open:self.setup_panel.pack(fill='x',after=self.setup_button)
        else:self.setup_panel.pack_forget()
        self.setup_button.configure(text=('▾' if self.setup_open else '▸')+' 引擎配置与检查')

    def whole(self):self.start.set('0:00');self.end.set('')

    def reset_source_rights(self,*_):
        self.rights_basis.set('请选择使用依据');self.rights_reference.set('')

    def flow_changed(self,*_):
        flow=selected(FLOWS,self.flow.get())
        self.start_button.configure(text={'accompaniment':'生成伴奏曲谱','melody':'试用主旋律 Beta'}[flow])
        only=flow=='melody'
        self.model_box.configure(state='disabled' if only else 'readonly')
        self.device_box.configure(state='disabled' if only else 'readonly')
        self.language_box.configure(state='readonly' if flow!='accompaniment' else 'disabled')
        self.kind_box.configure(state='disabled')
        self.muscriptor_check.configure(state='disabled' if only else 'normal')
        self.game_check.configure(state='normal' if only else 'disabled')
        self.source_kind.set(KINDS['original'] if only else KINDS['instrumental'])
        self.description.set({'accompaniment':'请提供已有伴奏或纯音乐；本版不从原唱分离伴奏。medium 推荐，保留多轨起音与和声，结果仍需试听。',
            'melody':'Beta：直接从已获授权的原唱识别歌声旋律，CPU 即可。复杂合唱与混音可能误识别。原唱分离伴奏暂缓提供。'}[flow])

    def choose_audio(self):
        path=filedialog.askopenfilename(parent=self.window,title='选择音频',filetypes=[('音频','*.wav *.mp3 *.flac *.ogg *.m4a *.aif *.aiff'),('所有文件','*.*')])
        if path:self.source.set(path)

    def choose_engine(self):
        path=filedialog.askopenfilename(parent=self.window,title='选择音频引擎的 Python 解释器',filetypes=[('Python','python.exe'),('所有文件','*.exe')])
        if path:self.executable.set(path)

    def open_license(self):
        model=self.model.get() if self.model.get() in ('small','medium','large') else 'medium'
        webbrowser.open('https://huggingface.co/MuScriptor/muscriptor-'+model)

    def help(self):self.app.show_help(filename='AUDIO_TRANSCRIPTION.md')

    def save(self):
        self.config.write_text(json.dumps({'executable':self.executable.get(),'model':self.model.get(),
            'device':selected(DEVICES,self.device.get()),'workflow':selected(FLOWS,self.flow.get()),
            'source_kind':selected(KINDS,self.source_kind.get()),'language':selected(LANGUAGES,self.language.get())},ensure_ascii=False,indent=2),encoding='utf-8')

    def begin(self,operation,caption):
        if self.job or self.app.active:return
        self.app.stop_preview()
        self.job=AudioPipeline();job=self.job
        for widget,_ in self.controls:widget.configure(state='disabled')
        for button in (self.import_button,self.original_button,self.folder_button):button.configure(state='disabled')
        self.result_selector.configure(state='disabled')
        self.cancel_button.configure(state='normal')
        self.state.set(caption);self.progress.start(12);self.app.refresh_controls()
        def worker():
            try:self.messages.put(('done',operation(job,lambda text:self.messages.put(('log',text)))))
            except Exception as error:self.messages.put(('error',str(error)))
        threading.Thread(target=worker,daemon=False).start()

    def install(self):
        if self.job:return
        path=filedialog.askopenfilename(parent=self.window,title='选择完整 Python 3.10–3.13（推荐 3.12），将创建独立环境',filetypes=[('Python','python.exe')])
        if path:
            device=selected(DEVICES,self.device.get())
            only=selected(FLOWS,self.flow.get())=='melody'
            self.begin(lambda job,log:('installed',job.install(path,self.app.directory,log,device=device,melody_only=only)),
                       '正在安装独立引擎；伴奏及 GPU 组件下载较大，可取消后重试…' if not only else '正在安装旋律 Beta 的轻量依赖…')

    def check_environment(self):
        try:executable=python_engine(self.executable.get())
        except ValueError as error:self.state.set(str(error));return
        model=self.model.get()
        self.begin(lambda job,log:('checked',job.diagnose(executable,self.app.directory,model,log)),'正在检查依赖、解码器、设备和模型准备状态…')

    def transcribe(self):
        if self.job or self.app.active:return
        try:
            executable=python_engine(self.executable.get())
            if not self.source.get().strip():raise ValueError('请先选择音频文件。')
            flow=selected(FLOWS,self.flow.get())
            request=AudioRequest(Path(self.source.get()),selected(KINDS,self.source_kind.get()),self.model.get(),
                selected(DEVICES,self.device.get()),parse_time(self.start.get()),parse_time(self.end.get()) if self.end.get().strip() else None,
                flow!='accompaniment',selected(LANGUAGES,self.language.get()),
                rights_basis=next((k for k,v in SOURCE_BASES.items() if v==self.rights_basis.get()),''),
                rights_reference=self.rights_reference.get(),
                accepted_models=tuple(m for m,accepted in [(MUSCRIPTOR_TERMS,self.muscriptor_terms.get()),(GAME_TERMS,self.game_terms.get())] if accepted)).validate()
            request.use_record(melody_only=flow=='melody')
            self.save()
        except (ValueError,OSError) as error:self.state.set(str(error));return
        operation='melody_only' if flow=='melody' else 'accompaniment'
        self.begin(lambda job,log:('processed',getattr(job,operation)(executable,request,self.app.directory,log)),
                   '正在准备音频；完成后可对照原音频、导入曲谱并试听。')

    def cancel(self):
        if self.job:self.job.cancel();self.state.set('正在停止当前任务，请稍候…')

    def set_results(self,result):
        self.result=result
        self.result_paths={label:path for label,path in [('伴奏（默认）',result.accompaniment),('主旋律（Beta）',result.melody),('伴奏＋主旋律（Beta）',result.combined)] if path}
        self.result_selector.configure(values=list(self.result_paths),state='readonly')
        self.result_choice.set(next(iter(self.result_paths)))
        self.import_result()

    def import_result(self):
        path=self.result_paths.get(self.result_choice.get())
        if path and not self.job and not self.app.active:
            if self.app.open_path(path):
                caption=self.result_choice.get()
                warning=' '.join(self.result.warnings) if self.result else ''
                self.state.set(f'已导入{caption}。请在多轨工作区试听，再进入游戏试奏。'+(' '+warning if warning else ''))

    def preview_audio(self):
        if self.job or self.app.active or not self.result:return
        path=self.result.source_audio
        try:
            import winsound
            self.app.stop_preview()
            winsound.PlaySound(str(path),winsound.SND_FILENAME|winsound.SND_ASYNC|winsound.SND_NODEFAULT)
            self.state.set('正在试听选中的音频片段。')
        except (OSError,RuntimeError) as error:self.state.set('试听失败：'+str(error))

    def open_results(self):
        if self.result:os.startfile(self.result.directory)

    def write_log(self,text):
        self.log.configure(state='normal');self.log.delete('1.0','end');self.log.insert('end',clean_log(text));self.log.configure(state='disabled')

    def poll(self):
        while not self.messages.empty():
            kind,value=self.messages.get_nowait()
            if kind=='log':
                self.write_log(value)
                line=clean_log(value).splitlines()
                if line:self.state.set(line[-1][:180])
                continue
            cancelled=self.job is not None and self.job.cancelled.is_set()
            self.job=None;self.progress.stop()
            for widget,state in self.controls:widget.configure(state=state)
            self.cancel_button.configure(state='disabled');self.flow_changed();self.app.refresh_controls()
            if cancelled:self.state.set('任务已取消；未自动导入结果。')
            elif kind=='error':
                detail=clean_log(value);self.state.set(detail.splitlines()[0][:220]);self.write_log(detail)
            elif value[0]=='installed':
                self.executable.set(str(value[1]));self.save()
                self.state.set('引擎已安装。使用前请确认输入素材与模型条款；MuScriptor 还需官方授权与登录。')
            elif value[0]=='checked':
                data=value[1];self.write_log(json.dumps(data,ensure_ascii=False,indent=2))
                missing=[name for name in ('soundfile','imageio-ffmpeg','onnxruntime') if not data.get(name)]
                if missing:self.state.set('请安装 / 更新独立引擎。缺少：'+', '.join(missing))
                elif not data.get('model_login_configured') and not data.get('muscriptor_weights_cached'):
                    self.state.set('确认 GAME 条款后可试用旋律 Beta；伴奏需先完成 MuScriptor 授权与登录。设备：'+('NVIDIA GPU' if data.get('cuda_available') else 'CPU'))
                else:self.state.set('引擎环境检查完成；请选短片段核对实际识别效果。')
            else:self.set_results(value[1])
            ready=bool(self.result_paths)
            self.import_button.configure(state='normal' if ready else 'disabled')
            self.folder_button.configure(state='normal' if ready else 'disabled')
            self.original_button.configure(state='normal' if ready else 'disabled')
            self.result_selector.configure(state='readonly' if ready else 'disabled')
        if not self.closed:self.poll_id=self.window.after(120,self.poll)

    def close(self):
        if self.closed:return
        self.closed=True;self.cancel();self.app.stop_preview()
        self.window.after_cancel(self.poll_id);self.window.destroy();self.app.audio_dialog=None
        if not self.app.closed:self.app.refresh_controls()
