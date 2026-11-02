"""Local Windows WAV comparison with a shared position; no game input."""
import ctypes as C
from pathlib import Path
import tkinter as tk
from tkinter import ttk
import uuid


class WaveComparison:
    def __init__(self,send=None,limit=30):
        self.alias='nte'+uuid.uuid4().hex
        self.opened=self.playing=False
        self.limit=int(limit*1000);self.length=self.limit
        if send is None:
            self.winmm=C.WinDLL('winmm')
            self.winmm.mciSendStringW.argtypes=[C.c_wchar_p,C.c_wchar_p,C.c_uint,C.c_void_p]
            self.winmm.mciSendStringW.restype=C.c_uint
            self.winmm.mciGetErrorStringW.argtypes=[C.c_uint,C.c_wchar_p,C.c_uint]
            self.winmm.mciGetErrorStringW.restype=C.c_bool
            send=self.native_send
        self.send=send

    def native_send(self,command):
        result=C.create_unicode_buffer(1024)
        code=self.winmm.mciSendStringW(command,result,len(result),None)
        if code:
            self.winmm.mciGetErrorStringW(code,result,len(result))
            raise ValueError('本地试听失败：'+result.value)
        return result.value

    def position(self):
        return min(self.length,max(0,int(self.send(f'status {self.alias} position')))) if self.opened else 0

    def switch(self,path):
        position=self.position();playing=self.playing
        self.close()
        path=Path(path).resolve()
        if not path.is_file() or path.suffix.lower()!='.wav':raise ValueError('请选择有效 WAV 试听文件。')
        if hasattr(self,'winmm'):
            # The legacy waveaudio driver can reject long element names even
            # through the Unicode API. Use Windows' existing short path only;
            # no file renaming, cwd changes or system setting changes.
            kernel=C.WinDLL('kernel32',use_last_error=True)
            kernel.GetShortPathNameW.argtypes=[C.c_wchar_p,C.c_wchar_p,C.c_uint]
            kernel.GetShortPathNameW.restype=C.c_uint
            short=C.create_unicode_buffer(32768)
            size=kernel.GetShortPathNameW(str(path),short,len(short))
            if 0<size<len(short):path=short.value
        self.send(f'open "{path}" type waveaudio alias {self.alias}')
        self.opened=True
        try:
            self.send(f'set {self.alias} time format milliseconds')
            self.length=min(self.limit,int(self.send(f'status {self.alias} length')))
            self.seek(position,playing=playing)
        except Exception:
            self.close();raise

    def seek(self,position,*,playing=None):
        if not self.opened:return
        play=self.playing if playing is None else playing
        position=min(max(0,int(position)),max(0,self.length-1))
        self.send(f'seek {self.alias} to {position} wait')
        self.playing=False
        if play:
            self.send(f'play {self.alias} from {position} to {self.length}')
            self.playing=True

    def toggle(self):
        if self.playing:
            self.send(f'pause {self.alias}');self.playing=False
        else:
            position=self.position()
            self.seek(0 if position>=self.length-10 else position,playing=True)

    def close(self):
        if self.opened:
            try:self.send(f'close {self.alias}')
            finally:self.opened=self.playing=False


class AuditionWindow:
    def __init__(self,app,paths,origin=0):
        app.stop_preview()
        self.app,self.paths,self.origin=app,paths,origin
        self.closed=self.dragging=False
        self.player=WaveComparison()
        self.player.switch(next(iter(paths.values())))
        self.window=tk.Toplevel(app.root)
        self.window.title('音频与曲谱对照试听')
        try:self.window.iconbitmap(str(app.assets/'icon.ico'))
        except tk.TclError:pass
        self.window.geometry('650x300');self.window.minsize(600,290)
        self.window.configure(bg='#FCFBF7')
        self.window.protocol('WM_DELETE_WINDOW',self.close)
        body=tk.Frame(self.window,bg='#FCFBF7',padx=22,pady=18);body.pack(fill='both',expand=True)
        app.label(body,'在同一位置比较',16,bold=True).pack(anchor='w')
        app.label(body,'原录音 / 分离音频 / 曲谱合成音；合成音只用于核对音高与节奏。\n最多试听选段前 30 秒，切换音源保持位置。',9,'#738078',justify='left').pack(anchor='w',pady=(5,12))
        self.choice=tk.StringVar(value=next(iter(paths)))
        choice=ttk.Combobox(body,textvariable=self.choice,values=list(paths),state='readonly')
        choice.pack(fill='x');choice.bind('<<ComboboxSelected>>',self.switch)
        self.position=tk.DoubleVar(value=0)
        self.slider=ttk.Scale(body,from_=0,to=self.player.length,variable=self.position)
        self.slider.pack(fill='x',pady=(12,0))
        self.slider.bind('<ButtonPress-1>',lambda e:setattr(self,'dragging',True))
        self.slider.bind('<ButtonRelease-1>',self.seek)
        self.time=tk.StringVar()
        app.label(body,textvariable=self.time,size=9).pack(anchor='w',pady=(3,8))
        row=tk.Frame(body,bg='#FCFBF7');row.pack(fill='x')
        self.button=app.button(row,'▶ 播放',self.toggle,'preview',9);self.button.pack(side='left')
        self.loop=tk.BooleanVar(value=False)
        ttk.Checkbutton(row,text='循环当前片段',variable=self.loop).pack(side='left',padx=14)
        app.button(row,'关闭',self.close,size=9).pack(side='right')
        app.audio_audition=self
        self.poll_id=self.window.after(80,self.poll)

    def switch(self,event=None):
        try:
            self.player.switch(self.paths[self.choice.get()]);self.slider.configure(to=self.player.length)
        except (OSError,ValueError) as error:self.app.show_error(error)

    def toggle(self):
        try:self.player.toggle()
        except ValueError as error:self.app.show_error(error)

    def seek(self,event=None):
        self.dragging=False
        try:self.player.seek(self.position.get())
        except ValueError as error:self.app.show_error(error)

    def poll(self):
        if self.closed:return
        try:
            position=self.player.position()
            if self.player.playing and position>=self.player.length-10:
                if self.loop.get():self.player.seek(0,playing=True)
                else:self.player.playing=False
            if not self.dragging:self.position.set(position)
            self.button.configure(text='Ⅱ 暂停' if self.player.playing else '▶ 播放')
            self.time.set(f'片段 {position/1000:.1f} / {self.player.length/1000:.1f} 秒   ·   原音频 {self.origin+position/1000:.1f} 秒')
        except ValueError as error:
            self.close();self.app.show_error(error);return
        self.poll_id=self.window.after(80,self.poll)

    def close(self):
        if self.closed:return
        self.closed=True
        self.window.after_cancel(self.poll_id)
        try:self.player.close()
        finally:
            self.window.destroy()
            if self.app.audio_audition is self:self.app.audio_audition=None
