"""Use the existing system C++ runtime before optional native ML imports.

Conda may place an older MSVCP140 beside python.exe. Explicitly loading the
already-installed Windows copy avoids that DLL shadowing. No files or global
environment are changed; non-Windows interpreters use their normal loader.
"""
import os

_HANDLES = []


def prefer_system_runtime():
    if os.name != 'nt':return
    import ctypes
    from pathlib import Path
    buffer=ctypes.create_unicode_buffer(32768)
    if not ctypes.windll.kernel32.GetSystemDirectoryW(buffer,len(buffer)):return
    for name in ('MSVCP140.dll','MSVCP140_1.dll'):
        path=Path(buffer.value)/name
        if path.is_file():
            try:_HANDLES.append(ctypes.WinDLL(str(path)))
            except OSError:pass
