"""Topmost, non-activating desktop controls; no game injection or focus bypass."""
import ctypes as C
from ctypes import wintypes as W
import sys
import tkinter as tk
from .appearance import RoundedPanel, RoundedButton, COLORS as THEME


class NonActivatingWindow:
    def __init__(self,window):
        self.user32=C.WinDLL('user32',use_last_error=True)
        u=self.user32
        u.GetAncestor.argtypes=[W.HWND,W.UINT];u.GetAncestor.restype=W.HWND
        self.hwnd=u.GetAncestor(window.winfo_id(),2)
        u.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int];u.GetWindowLongPtrW.restype=C.c_ssize_t
        u.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_ssize_t];u.SetWindowLongPtrW.restype=C.c_ssize_t
        u.CallWindowProcW.argtypes=[C.c_void_p,W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.CallWindowProcW.restype=C.c_ssize_t
        u.SetWindowPos.argtypes=[W.HWND,W.HWND,C.c_int,C.c_int,C.c_int,C.c_int,W.UINT]
        u.IsWindow.argtypes=[W.HWND];u.IsWindow.restype=W.BOOL
        u.IsWindowVisible.argtypes=[W.HWND];u.IsWindowVisible.restype=W.BOOL
        self.original=u.GetWindowLongPtrW(self.hwnd,-4)
        self.callback=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)(self.dispatch)
        C.set_last_error(0)
        result=u.SetWindowLongPtrW(self.hwnd,-4,C.cast(self.callback,C.c_void_p).value)
        if not result and C.get_last_error():raise C.WinError(C.get_last_error())
        style=u.GetWindowLongPtrW(self.hwnd,-20)
        u.SetWindowLongPtrW(self.hwnd,-20,(style|0x08000000|0x80)&~0x40000)
        u.SetWindowLongPtrW(self.hwnd,-8,0)  # Independent tool window survives main-window minimization.
        u.SetWindowPos(self.hwnd,W.HWND(-1),0,0,0,0,0x1|0x2|0x10|0x20)

    def dispatch(self,hwnd,message,wparam,lparam):
        if message==0x21:return 3  # WM_MOUSEACTIVATE -> MA_NOACTIVATE (keep the click).
        return self.user32.CallWindowProcW(self.original,hwnd,message,wparam,lparam)

    def close(self):
        if self.user32.IsWindow(self.hwnd):
            self.user32.SetWindowLongPtrW(self.hwnd,-4,self.original)


class MiniPlayer:
    WIDTH,HEIGHT=360,150
    def __init__(self,app):
        self.app,self.native,self.drag=app,None,None
        self.window=tk.Toplevel(app.root)
        self.window.withdraw()
        self.window.title('异环演奏工作台 · 迷你播放器')
        self.window.overrideredirect(True)
        self.window.attributes('-topmost',True)
        self.window.configure(bg='#010203')
        if sys.platform=='win32':self.window.attributes('-transparentcolor','#010203')
        panel=RoundedPanel(self.window,fill=THEME['paper'],padx=13,pady=10,radius=18)
        panel.pack(fill='both',expand=True)
        header=tk.Frame(panel,bg=THEME['paper']);header.pack(fill='x')
        branding=tk.Label(header,text='NTE  MUSIC DESK',bg=THEME['paper'],fg=THEME['teal'],font=('Microsoft YaHei UI',8))
        branding.pack(side='left')
        tk.Button(header,text='×',command=self.hide,bg=THEME['paper'],fg=THEME['ink'],relief='flat',borderwidth=0,takefocus=0,padx=5,pady=0).pack(side='right')
        self.title=tk.Label(panel,text='',bg=THEME['paper'],fg=THEME['ink'],font=('Microsoft YaHei UI',11,'bold'),anchor='w')
        self.title.pack(fill='x',pady=(2,5))
        line=tk.Frame(panel,bg=THEME['paper']);line.pack(fill='x')
        self.status=tk.Label(line,text='',bg=THEME['paper'],fg=THEME['ink'],font=('Microsoft YaHei UI',8))
        self.status.pack(side='left')
        tk.Label(line,textvariable=app.time_text,bg=THEME['paper'],fg=THEME['ink'],font=('Microsoft YaHei UI',8)).pack(side='right')
        self.progress=tk.Canvas(panel,height=12,bg=THEME['paper'],borderwidth=0,highlightthickness=0,cursor='hand2')
        self.progress.pack(fill='x',pady=(5,7))
        app.bind_seek(self.progress)
        controls=tk.Frame(panel,bg=THEME['paper']);controls.pack(fill='x')
        self.play=self.button(controls,'▶ 演奏',self.toggle,THEME['teal'],THEME['paper']);self.play.pack(side='left',fill='x',expand=True)
        self.stop=self.button(controls,'■ 停止',app.stop,THEME['paper'],THEME['ink']);self.stop.pack(side='left',padx=6)
        self.main=self.button(controls,'主窗',self.open_main,THEME['paper'],THEME['ink']);self.main.pack(side='left')
        for widget in (branding,self.title,header):
            widget.bind('<ButtonPress-1>',self.begin_drag)
            widget.bind('<B1-Motion>',self.move)
            widget.bind('<ButtonRelease-1>',self.finish_drag)
        self.window.protocol('WM_DELETE_WINDOW',self.hide)
        self.window.update_idletasks()
        position=app.preferences.get('mini_player_position')
        x,y=app.root.winfo_screenwidth()-self.WIDTH-24,100
        if isinstance(position,list) and len(position)==2 and all(type(v) is int and abs(v)<100000 for v in position):x,y=position
        self.position=self.clamp(x,y)
        x,y=self.position
        self.window.geometry(f'{self.WIDTH}x{self.HEIGHT}{x:+d}{y:+d}')
        self.window.update_idletasks()
        if sys.platform=='win32':self.native=NonActivatingWindow(self.window)
        self.refresh()

    def clamp(self,x,y):
        left,top,width,height=0,0,self.app.root.winfo_screenwidth(),self.app.root.winfo_screenheight()
        if sys.platform=='win32':
            u=C.windll.user32
            left,top,width,height=(u.GetSystemMetrics(i) for i in (76,77,78,79))
        return max(left,min(x,left+width-self.WIDTH)),max(top,min(y,top+height-self.HEIGHT))

    def button(self,parent,text,command,fill,ink):
        return RoundedButton(parent,text=text,command=command,bg=fill,fg=ink,activebackground=fill,
                             font=('Microsoft YaHei UI',9),padx=12,pady=5,takefocus=False,
                             outline=None if fill==THEME['teal'] else THEME['ink'])

    def show(self):
        self.app.mini_visible.set(True)
        self.window.deiconify()
        if self.native:self.native.user32.SetWindowPos(self.native.hwnd,W.HWND(-1),*self.position,0,0,0x1|0x10|0x40)
        self.refresh();self.app.save_preferences()

    def hide(self):
        self.app.mini_visible.set(False);self.window.withdraw();self.app.save_preferences()

    def toggle(self):
        if self.app.active:self.app.toggle_pause()
        else:self.app.play(None)

    def open_main(self):
        if self.app.active:self.app.stop()
        self.app.root.deiconify();self.app.root.lift()

    def begin_drag(self,event):
        self.drag=(event.x_root-self.window.winfo_rootx(),event.y_root-self.window.winfo_rooty())

    def move(self,event):
        if self.drag:
            self.position=self.clamp(event.x_root-self.drag[0],event.y_root-self.drag[1])
            x,y=self.position
            if self.native:self.native.user32.SetWindowPos(self.native.hwnd,W.HWND(-1),x,y,0,0,0x1|0x10)
            else:self.window.geometry(f'{x:+d}{y:+d}')

    def finish_drag(self,event=None):
        self.drag=None;self.app.save_preferences()

    def refresh(self):
        active=self.app.active
        phase=active.get('phase','waiting') if active else ''
        paused=active.get('pause_requested',False) if active else False
        caption='▶ 继续' if paused else ('Ⅱ 暂停' if active else ('▶ 续播' if self.app.score and self.app.playback_offset()>.05 else '▶ 演奏'))
        ready=bool(self.app.score) and not self.app.preview_token and not (self.app.audio_dialog and self.app.audio_dialog.job)
        if getattr(self.app,'light_audio',None) and self.app.light_audio.busy:ready=False
        enabled=(phase in ('playing','paused') and not self.app.stop_requested) if active else ready
        state='normal' if enabled else 'disabled'
        if self.play.cget('text')!=caption or str(self.play.cget('state'))!=state:self.play.configure(text=caption,state=state)
        stop_state='normal' if active or self.app.preview_token else 'disabled'
        if str(self.stop.cget('state'))!=stop_state:self.stop.configure(state=stop_state)
        title=self.app.title.get();title=title if len(title)<=25 else title[:24]+'…'
        self.title.configure(text=title)
        self.status.configure(text=('已暂停 · F7 继续 · F8 停止' if phase=='paused' else 'F7 暂停 · F8 停止')
                              if active and phase in ('playing','paused') else ('准备演奏…' if active else '就绪 · 拖动标题可移动'))
        self.app.paint_progress(self.progress,THEME['teal'],THEME['bg'])

    def close(self):
        if self.native:self.native.close()
        self.window.destroy()
