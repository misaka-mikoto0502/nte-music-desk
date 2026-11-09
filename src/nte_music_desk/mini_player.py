"""Topmost, non-activating desktop controls; no game injection or focus bypass."""
import ctypes as C
from ctypes import wintypes as W
import sys
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, font as tkfont
from .appearance import RoundedPanel, RoundedButton, COLORS as THEME
from .controls import CharacterProgress


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
        u.ShowWindow.argtypes=[W.HWND,C.c_int];u.ShowWindow.restype=W.BOOL
        u.GetForegroundWindow.restype=W.HWND
        u.GetCursorPos.argtypes=[C.POINTER(W.POINT)];u.GetCursorPos.restype=W.BOOL
        u.GetAsyncKeyState.argtypes=[C.c_int];u.GetAsyncKeyState.restype=C.c_short
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

    def show(self,x,y):
        self.user32.ShowWindow(self.hwnd,4)
        self.user32.SetWindowPos(self.hwnd,W.HWND(-1),x,y,0,0,0x1|0x10|0x40)


class SongDropdown:
    """Mouse-operated song list that leaves the game's foreground unchanged."""
    def __init__(self,mini,entries):
        self.mini,self.native=mini,None
        self.window=tk.Toplevel(mini.window);self.window.withdraw()
        self.window.title('异环演奏工作台 · 选择曲目')
        self.window.overrideredirect(True);self.window.attributes('-topmost',True)
        self.window.configure(bg='#010203')
        if sys.platform=='win32':self.window.attributes('-transparentcolor','#010203')
        panel=RoundedPanel(self.window,padx=8,pady=8,radius=12);panel.pack(fill='both',expand=True)
        self.canvas=tk.Canvas(panel,bg=THEME['paper'],highlightthickness=0,borderwidth=0,
                              height=min(5,len(entries))*38,takefocus=False)
        bar=ttk.Scrollbar(panel,orient='vertical',command=self.canvas.yview,takefocus=False,style='Desk.Vertical.TScrollbar')
        self.canvas.configure(yscrollcommand=bar.set)
        if len(entries)>5:bar.pack(side='right',fill='y')
        self.canvas.pack(side='left',fill='both',expand=True)
        rows=tk.Frame(self.canvas,bg=THEME['paper'])
        item=self.canvas.create_window(0,0,window=rows,anchor='nw')
        rows.bind('<Configure>',lambda _:self.canvas.configure(scrollregion=self.canvas.bbox('all')))
        self.canvas.bind('<Configure>',lambda e:self.canvas.itemconfigure(item,width=e.width))
        self.buttons=[]
        selected=mini.pending_song[0] if mini.pending_song else mini.app.current_path
        for title,path,_ in entries:
            label=mini.short_title(title,mini.WIDTH-85)
            button=RoundedButton(rows,text=('✓  ' if path==selected else '    ')+label,
                command=lambda p=path:mini.choose_song(p),bg=THEME['bg'] if path==selected else THEME['paper'],
                fg=THEME['teal'] if path==selected else THEME['ink'],activebackground=THEME['bg'],
                font=('Microsoft YaHei UI',10),padx=8,pady=6,anchor='w',takefocus=False)
            button.pack(fill='x',pady=1);self.buttons.append((button,path))
        for widget in (self.canvas,rows,*[b for b,_ in self.buttons]):
            widget.bind('<MouseWheel>',lambda e:self.scroll(e))
        self.window.update_idletasks()
        row_height=max(38,max(button.winfo_reqheight()+2 for button,_ in self.buttons))
        self.canvas.configure(height=min(5,len(entries))*row_height)
        width=mini.WIDTH-24;height=min(5,len(entries))*row_height+16
        mini.window.update_idletasks()
        x=mini.title_row.winfo_rootx();y=mini.window.winfo_rooty()+mini.window.winfo_height()+4
        left,top,screen_width,screen_height=mini.screen_bounds()
        x=max(left,min(x,left+screen_width-width))
        if y+height>top+screen_height:y=mini.window.winfo_rooty()-height-4
        y=max(top,min(y,top+screen_height-height))
        self.window.geometry(f'{width}x{height}{x:+d}{y:+d}')
        self.window.update_idletasks()
        if sys.platform=='win32':self.native=NonActivatingWindow(self.window)
        if self.native:
            self.foreground=self.native.user32.GetForegroundWindow()
            self.native.show(x,y)
        else:self.window.deiconify()
        self.mouse_down=True  # Ignore the title click that opened this list.

    def scroll(self,event):
        self.canvas.yview_scroll(-int(event.delta/120),'units');return 'break'

    def dismiss_outside(self):
        if not self.native:return
        u=self.native.user32
        if u.GetForegroundWindow()!=self.foreground or u.GetAsyncKeyState(0x1B)&0x8000:
            self.mini.close_songs();return
        down=bool(u.GetAsyncKeyState(1)&0x8000)
        if down and not self.mouse_down:
            point=W.POINT()
            if u.GetCursorPos(C.byref(point)):
                def contains(widget):
                    return (widget.winfo_rootx()<=point.x<widget.winfo_rootx()+widget.winfo_width() and
                            widget.winfo_rooty()<=point.y<widget.winfo_rooty()+widget.winfo_height())
                if not contains(self.window) and not contains(self.mini.title_row):self.mini.close_songs()
        self.mouse_down=down

    def close(self):
        if self.native:self.native.close()
        self.window.destroy()


class MiniPlayer:
    WIDTH,HEIGHT=360,176
    def __init__(self,app):
        self.app,self.native,self.drag=app,None,None
        self.songs=None;self.pending_song=None;self.notice='';self.notice_until=0
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
        self.title_row=RoundedPanel(panel,fill=THEME['bg'],padx=9,pady=4,radius=9)
        self.title_row.pack(fill='x',pady=(3,5))
        self.title=tk.Label(self.title_row,text='',bg=THEME['bg'],fg=THEME['ink'],font=('Microsoft YaHei UI',11,'bold'),anchor='w',cursor='hand2')
        arrow=tk.Label(self.title_row,text='▾',bg=THEME['bg'],fg=THEME['ink'],font=('Microsoft YaHei UI',10),cursor='hand2')
        arrow.pack(side='right',padx=(6,0));self.title.pack(side='left',fill='x',expand=True)
        self.title_font=tkfont.Font(root=self.title,font=self.title.cget('font'))
        for widget in (self.title,self.title_row,arrow):widget.bind('<ButtonRelease-1>',lambda _:self.toggle_songs())
        line=tk.Frame(panel,bg=THEME['paper']);line.pack(fill='x')
        self.status=tk.Label(line,text='',bg=THEME['paper'],fg=THEME['ink'],font=('Microsoft YaHei UI',8))
        self.status.pack(side='left')
        tk.Label(line,textvariable=app.time_text,bg=THEME['paper'],fg=THEME['ink'],font=('Microsoft YaHei UI',8)).pack(side='right')
        self.progress=CharacterProgress(panel,app.assets/'mingyin-icon.webp')
        self.progress.pack(fill='x',pady=(2,4))
        app.bind_seek(self.progress)
        controls=tk.Frame(panel,bg=THEME['paper']);controls.pack(fill='x')
        self.play=self.button(controls,'▶ 演奏',self.toggle,THEME['teal'],THEME['paper']);self.play.pack(side='left',fill='x',expand=True)
        self.stop=self.button(controls,'■ 停止',app.stop,THEME['paper'],THEME['ink']);self.stop.pack(side='left',padx=6)
        self.main=self.button(controls,'主窗',self.open_main,THEME['paper'],THEME['ink']);self.main.pack(side='left')
        for widget in (branding,header):
            widget.bind('<ButtonPress-1>',self.begin_drag)
            widget.bind('<B1-Motion>',self.move)
            widget.bind('<ButtonRelease-1>',self.finish_drag)
        self.window.protocol('WM_DELETE_WINDOW',self.hide)
        self.window.update_idletasks()
        self.HEIGHT=max(self.HEIGHT,self.window.winfo_reqheight())
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
        left,top,width,height=self.screen_bounds()
        return max(left,min(x,left+width-self.WIDTH)),max(top,min(y,top+height-self.HEIGHT))

    def screen_bounds(self):
        left,top,width,height=0,0,self.app.root.winfo_screenwidth(),self.app.root.winfo_screenheight()
        if sys.platform=='win32':
            u=C.windll.user32
            left,top,width,height=(u.GetSystemMetrics(i) for i in (76,77,78,79))
        return left,top,width,height

    def button(self,parent,text,command,fill,ink):
        return RoundedButton(parent,text=text,command=command,bg=fill,fg=ink,activebackground=fill,
                             font=('Microsoft YaHei UI',9),padx=12,pady=5,takefocus=False,
                             outline=None if fill==THEME['teal'] else THEME['ink'])

    def show(self):
        self.app.mini_visible.set(True)
        if self.native:
            # Tk deiconify can activate a window; use the explicit Win32
            # no-activation show path after the game has received focus.
            self.native.show(*self.position)
        else:self.window.deiconify()
        self.refresh();self.app.save_preferences()

    def hide(self):
        self.close_songs()
        self.app.mini_visible.set(False);self.window.withdraw()
        if self.native:self.native.user32.ShowWindow(self.native.hwnd,0)
        self.app.save_preferences()

    def toggle(self):
        self.close_songs()
        if self.app.active:self.app.toggle_pause()
        else:self.app.play(None)

    def open_main(self):
        self.close_songs()
        if self.app.active:self.app.stop()
        self.app.root.deiconify();self.app.root.lift()

    def begin_drag(self,event):
        self.close_songs()
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
        if self.songs:self.songs.dismiss_outside()
        active=self.app.active
        phase=active.get('phase','waiting') if active else ''
        paused=active.get('pause_requested',False) if active else False
        caption='▶ 继续' if paused else ('Ⅱ 暂停' if active else ('▶ 续播' if self.app.score and self.app.playback_offset()>.05 else '▶ 演奏'))
        ready=bool(self.app.score) and not self.app.preview_token and not self.app.exclusive_audio_busy()
        enabled=(phase in ('playing','paused') and not self.app.stop_requested) if active else ready
        state='normal' if enabled else 'disabled'
        if self.play.cget('text')!=caption or str(self.play.cget('state'))!=state:self.play.configure(text=caption,state=state)
        stop_state='normal' if active or self.app.preview_token else 'disabled'
        if str(self.stop.cget('state'))!=stop_state:self.stop.configure(state=stop_state)
        title=self.short_title(self.app.title.get(),self.WIDTH-70)
        self.title.configure(text=title)
        self.status.configure(text=('已暂停 · F7 继续 · F8 停止' if phase=='paused' else 'F7 暂停 · F8 停止')
                              if active and phase in ('playing','paused') else ('准备演奏…' if active else
                              ('就绪 · 本地转谱在后台进行' if getattr(getattr(self.app,'offline_dialog',None),'job',None)
                               else ('音频处理中' if self.app.exclusive_audio_busy() else '就绪 · 拖动顶部可移动'))))
        if self.pending_song:self.status.configure(text='正在停止旧曲并切换…')
        elif time.monotonic()<self.notice_until:self.status.configure(text=self.notice)
        self.progress.draw(self.app.progress.get()/100)

    def short_title(self,title,width):
        title=' '.join(title.split())
        if self.title_font.measure(title)>width:
            while title and self.title_font.measure(title+'…')>width:title=title[:-1]
            title+='…'
        return title

    def close_songs(self):
        if self.songs:
            popup,self.songs=self.songs,None;popup.close()

    def toggle_songs(self):
        if self.songs:self.close_songs();return
        if self.app.exclusive_audio_busy():
            self.show_notice('音频处理中，暂不能换曲');return
        entries=self.app.library_entries()
        if not entries:self.show_notice('曲目列表为空，请先导入曲谱');return
        self.songs=SongDropdown(self,entries)

    def show_notice(self,text):
        self.notice,self.notice_until=text,time.monotonic()+4
        self.refresh()

    def choose_song(self,path):
        path=Path(path).resolve()
        if not path.is_file():
            self.close_songs();self.show_notice('文件已移动，请在主窗重新导入');return
        if path==self.app.current_path and self.pending_song is None:
            self.close_songs();return
        if self.app.exclusive_audio_busy():
            self.close_songs();self.show_notice('音频处理中，暂不能换曲');return
        self.close_songs()
        if self.app.active:
            autoplay=self.pending_song[1] if self.pending_song else not self.app.active.get('pause_requested',False)
            self.pending_song=(path,autoplay)
            self.app.pending_import=None
            self.app.stop(switching_song=True)
        else:
            self.app.open_path(path)
        self.refresh()

    def cancel_song_change(self):
        self.pending_song=None
        self.close_songs()

    def finish_song_change(self,message):
        selected,self.pending_song=self.pending_song,None
        path,autoplay=selected
        result=message.get('result',{})
        reason=result.get('reason','')
        interrupted=any(word in reason for word in ('F8','Esc','前台','窗口'))
        if self.native:
            interrupted=interrupted or any(self.native.user32.GetAsyncKeyState(key)&0x8000 for key in (0x1B,0x77))
        # Only our requested handoff may restart after a stop. Modifier-key,
        # focus and unknown interruptions must remain stopped.
        completed = message.get('code') == 0 and result.get('status') == 'completed'
        requested = message.get('code') == 2 and (result.get('stop_origin') == 'workbench' or
                    (result.get('stop_origin') is None and reason == '收到工作台停止指令，已停止。'))
        if self.app.open_path(path) and autoplay and (completed or requested) and not interrupted:
            self.app.play(None)

    def close(self):
        self.close_songs()
        if self.native:self.native.close()
        self.window.destroy()
