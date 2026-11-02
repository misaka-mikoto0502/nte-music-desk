"""Windows file drops for one small import widget, including elevated apps."""
import ctypes as C
from ctypes import wintypes as W
from pathlib import Path

SCORE_EXTENSIONS = {'.mid', '.midi', '.kar', '.rmi', '.musicxml', '.xml', '.mxl'}


class FileDropTarget:
    def __init__(self, widget, notify):
        self.user32 = u = C.WinDLL('user32', use_last_error=True)
        self.shell32 = s = C.WinDLL('shell32', use_last_error=True)
        self.hwnd, self.notify = widget.winfo_id(), notify
        u.GetWindowLongPtrW.argtypes=[W.HWND,C.c_int];u.GetWindowLongPtrW.restype=C.c_ssize_t
        u.SetWindowLongPtrW.argtypes=[W.HWND,C.c_int,C.c_ssize_t];u.SetWindowLongPtrW.restype=C.c_ssize_t
        u.CallWindowProcW.argtypes=[C.c_void_p,W.HWND,W.UINT,W.WPARAM,W.LPARAM];u.CallWindowProcW.restype=C.c_ssize_t
        u.IsWindow.argtypes=[W.HWND];u.IsWindow.restype=W.BOOL
        u.ChangeWindowMessageFilterEx.argtypes=[W.HWND,W.UINT,W.DWORD,C.c_void_p]
        u.ChangeWindowMessageFilterEx.restype=W.BOOL
        s.DragAcceptFiles.argtypes=[W.HWND,W.BOOL]
        s.DragQueryFileW.argtypes=[W.HANDLE,W.UINT,W.LPWSTR,W.UINT];s.DragQueryFileW.restype=W.UINT
        s.DragFinish.argtypes=[W.HANDLE]
        self.original=u.GetWindowLongPtrW(self.hwnd,-4)
        self.callback=C.WINFUNCTYPE(C.c_ssize_t,W.HWND,W.UINT,W.WPARAM,W.LPARAM)(self.dispatch)
        C.set_last_error(0)
        result=u.SetWindowLongPtrW(self.hwnd,-4,C.cast(self.callback,C.c_void_p).value)
        if not result and C.get_last_error():raise C.WinError(C.get_last_error())
        try:
            # Only this import widget accepts the Shell's file-drop messages.
            # No process-wide filter, privilege, or game input setting changes.
            for message in (0x233, 0x49):  # WM_DROPFILES, WM_COPYGLOBALDATA
                if not u.ChangeWindowMessageFilterEx(self.hwnd,message,1,None):raise C.WinError(C.get_last_error())
            s.DragAcceptFiles(self.hwnd,True)
        except BaseException:
            self.close()
            raise

    def dispatch(self,hwnd,message,wparam,lparam):
        if message != 0x233:
            return self.user32.CallWindowProcW(self.original,hwnd,message,wparam,lparam)
        try:
            count=self.shell32.DragQueryFileW(wparam,0xFFFFFFFF,None,0)
            if count != 1:
                self.notify({'kind':'drop_error','text':'一次请只拖入一个音频或曲谱文件。'})
                return 0
            length=self.shell32.DragQueryFileW(wparam,0,None,0)
            if not 0 < length < 32768:
                self.notify({'kind':'drop_error','text':'文件路径无效或过长。'})
                return 0
            path=C.create_unicode_buffer(length+1)
            self.shell32.DragQueryFileW(wparam,0,path,len(path))
            self.notify({'kind':'dropped_file','path':Path(path.value)})
        except Exception:
            self.notify({'kind':'drop_error','text':'无法读取拖入文件，请点击导入后选择。'})
        finally:
            self.shell32.DragFinish(wparam)
        return 0

    def close(self):
        if self.user32.IsWindow(self.hwnd):
            self.shell32.DragAcceptFiles(self.hwnd,False)
            self.user32.SetWindowLongPtrW(self.hwnd,-4,self.original)
            for message in (0x233,0x49):self.user32.ChangeWindowMessageFilterEx(self.hwnd,message,0,None)
