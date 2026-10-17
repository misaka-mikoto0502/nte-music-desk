"""Foreground-checked Windows input and instrument key primitives."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
from dataclasses import dataclass
from pathlib import Path
import subprocess
import sys
import time


def elevation_command(arguments):
    """Frozen apps relaunch the EXE, source installs use their trusted bootstrap."""
    arguments = list(arguments)
    if "--elevated-child" not in arguments:
        arguments.append("--elevated-child")
    if getattr(sys, "frozen", False):
        return sys.executable, arguments, str(Path(sys.executable).resolve().parent)
    bootstrap = Path(__file__).resolve().with_name("_bootstrap.py")
    return sys.executable, ["-X", "utf8", "-I", "-S", str(bootstrap), *arguments], str(bootstrap.parent)


@dataclass(frozen=True)
class PianoKey:
    label: str
    virtual_key: int
    scan_code: int
    shifted: bool = False


# The three rows observed in this game's guitar interface each start at E.
# Entries are physical US-QWERTY keys: (label, Windows virtual key, scan code).
LOW_ROW = [
    ("A", 0x41, 0x1E), ("S", 0x53, 0x1F), ("D", 0x44, 0x20),
    ("F", 0x46, 0x21), ("G", 0x47, 0x22), ("H", 0x48, 0x23),
    ("J", 0x4A, 0x24), ("K", 0x4B, 0x25), ("L", 0x4C, 0x26),
    (";", 0xBA, 0x27), ("'", 0xDE, 0x28), ("Enter", 0x0D, 0x1C),
]
MID_ROW = [
    ("Q", 0x51, 0x10), ("W", 0x57, 0x11), ("E", 0x45, 0x12),
    ("R", 0x52, 0x13), ("T", 0x54, 0x14), ("Y", 0x59, 0x15),
    ("U", 0x55, 0x16), ("I", 0x49, 0x17), ("O", 0x4F, 0x18),
    ("P", 0x50, 0x19), ("[", 0xDB, 0x1A), ("]", 0xDD, 0x1B),
]
HIGH_ROW = [
    ("1", 0x31, 0x02), ("2", 0x32, 0x03), ("3", 0x33, 0x04),
    ("4", 0x34, 0x05), ("5", 0x35, 0x06), ("6", 0x36, 0x07),
    ("7", 0x37, 0x08), ("8", 0x38, 0x09), ("9", 0x39, 0x0A),
    ("0", 0x30, 0x0B), ("-", 0xBD, 0x0C), ("=", 0xBB, 0x0D),
]


def note_name(midi_number: int) -> str:
    return ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")[midi_number % 12] + str(midi_number // 12 - 1)


KEYS = {
    note_name(start + index): PianoKey(*entry)
    for start, row in [(52, LOW_ROW), (64, MID_ROW), (76, HIGH_ROW)]
    for index, entry in enumerate(row)
}

class PlaybackStopped(Exception):
    pass


class WindowsKeyboard:
    def __init__(self, allow_shift=False):
        self.user32 = C.WinDLL("user32", use_last_error=True)
        self.kernel32 = C.WinDLL("kernel32", use_last_error=True)
        self.held = set()
        self.allow_shift = allow_shift
        self.user32.GetForegroundWindow.restype = W.HWND
        self.user32.IsWindow.argtypes = [W.HWND]
        self.user32.IsWindow.restype = W.BOOL
        self.user32.IsWindowVisible.argtypes = [W.HWND]
        self.user32.IsWindowVisible.restype = W.BOOL
        self.user32.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
        self.user32.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
        self.user32.SetForegroundWindow.argtypes = [W.HWND]
        self.user32.GetAsyncKeyState.argtypes = [C.c_int]
        self.user32.GetAsyncKeyState.restype = C.c_short
        self.user32.keybd_event.argtypes = [W.BYTE, W.BYTE, W.DWORD, C.c_size_t]
        self.user32.keybd_event.restype = None
        self.kernel32.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.kernel32.OpenProcess.restype = W.HANDLE
        self.kernel32.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, C.POINTER(W.DWORD)]
        self.kernel32.CloseHandle.argtypes = [W.HANDLE]
        self.hwnd, self.pid = self.find_game()

    def window_pid(self, hwnd):
        pid = W.DWORD()
        self.user32.GetWindowThreadProcessId(hwnd, C.byref(pid))
        return pid.value

    def process_path(self, pid):
        process = self.kernel32.OpenProcess(0x1000, False, pid)
        if not process:
            return ""
        try:
            path, size = C.create_unicode_buffer(32768), W.DWORD(32768)
            if self.kernel32.QueryFullProcessImageNameW(process, 0, path, C.byref(size)):
                return path.value
            return ""
        finally:
            self.kernel32.CloseHandle(process)

    def find_game(self):
        matches = []
        callback_type = C.WINFUNCTYPE(W.BOOL, W.HWND, C.c_ssize_t)

        @callback_type
        def collect(hwnd, _):
            if self.user32.IsWindowVisible(hwnd):
                title = C.create_unicode_buffer(1024)
                self.user32.GetWindowTextW(hwnd, title, len(title))
                if title.value.strip() == "异环":
                    pid = self.window_pid(hwnd)
                    if self.process_path(pid).lower().endswith("\\htgame.exe"):
                        matches.append((hwnd, pid))
            return True

        self.user32.EnumWindows.argtypes = [callback_type, C.c_ssize_t]
        if not self.user32.EnumWindows(collect, 0):
            raise OSError("无法枚举游戏窗口。")
        if len(matches) != 1:
            raise RuntimeError(f"需要一个打开的《异环》游戏窗口，当前找到 {len(matches)} 个。")
        return matches[0]

    def cancelled(self):
        return any(self.user32.GetAsyncKeyState(vk) & 0x8000 for vk in (0x1B, 0x77))  # Esc / F8

    def check(self):
        if self.cancelled():
            raise PlaybackStopped("检测到 Esc 或 F8，已停止。")
        if (not self.user32.IsWindow(self.hwnd)
                or self.window_pid(self.hwnd) != self.pid
                or self.user32.GetForegroundWindow() != self.hwnd):
            raise PlaybackStopped("游戏失去前台焦点或已关闭，已停止。")
        owns_shift = self.allow_shift and any(k.virtual_key == 0xA0 for k in self.held)
        forbidden = (0xA1, 0x11, 0x12, 0x5B, 0x5C) if owns_shift else (0x10, 0x11, 0x12, 0x5B, 0x5C)
        pressed = next((vk for vk in forbidden if self.user32.GetAsyncKeyState(vk) & 0x8000), None)
        if pressed is not None:
            label = {0x10: "Shift", 0xA1: "右 Shift", 0x11: "Ctrl", 0x12: "Alt", 0x5B: "左 Win", 0x5C: "右 Win"}[pressed]
            raise PlaybackStopped(f"检测到 {label} 按下，已停止；请松开修饰键后重试。")

    def down(self, key):
        self.check()
        if key.virtual_key == 0xA0 and not self.allow_shift:
            raise PlaybackStopped("当前乐器不允许发送 Shift。")
        self.held.add(key)
        self.user32.keybd_event(key.virtual_key, key.scan_code, 0, 0)

    def up(self, key):
        if key in self.held:
            self.user32.keybd_event(key.virtual_key, key.scan_code, 2, 0)
            self.held.remove(key)

    def release_all(self):
        # Release all note keys before releasing our modifier, even on failure.
        for key in sorted(self.held, key=lambda k: k.virtual_key == 0xA0):
            self.up(key)


def run_elevated_and_wait(script_path=None, arguments=None):
    """Request normal Windows UAC consent; wait for this one playback process."""
    shell32 = C.WinDLL("shell32", use_last_error=True)
    kernel32 = C.WinDLL("kernel32", use_last_error=True)

    class SHELLEXECUTEINFO(C.Structure):
        _fields_ = [("cbSize", W.DWORD), ("fMask", W.ULONG), ("hwnd", W.HWND),
                    ("lpVerb", W.LPCWSTR), ("lpFile", W.LPCWSTR), ("lpParameters", W.LPCWSTR),
                    ("lpDirectory", W.LPCWSTR), ("nShow", C.c_int), ("hInstApp", W.HINSTANCE),
                    ("lpIDList", W.LPVOID), ("lpClass", W.LPCWSTR), ("hkeyClass", W.HKEY),
                    ("dwHotKey", W.DWORD), ("hIcon", W.HANDLE), ("hProcess", W.HANDLE)]

    shell32.ShellExecuteExW.argtypes = [C.POINTER(SHELLEXECUTEINFO)]
    shell32.ShellExecuteExW.restype = W.BOOL
    kernel32.WaitForSingleObject.argtypes = [W.HANDLE, W.DWORD]
    kernel32.GetExitCodeProcess.argtypes = [W.HANDLE, C.POINTER(W.DWORD)]
    kernel32.CloseHandle.argtypes = [W.HANDLE]
    arguments = sys.argv[1:] if arguments is None else list(arguments)
    executable, command_args, working_directory = elevation_command(arguments)
    parameters = subprocess.list2cmdline(command_args)
    info = SHELLEXECUTEINFO()
    info.cbSize, info.fMask = C.sizeof(info), 0x40
    info.lpVerb, info.lpFile, info.lpParameters = "runas", executable, parameters
    info.lpDirectory, info.nShow = working_directory, 0
    if not shell32.ShellExecuteExW(C.byref(info)):
        error = C.get_last_error()
        if error == 1223:
            print("UAC 已取消，未演奏。")
            return 2
        raise C.WinError(error)
    try:
        kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)
        result = W.DWORD()
        if not kernel32.GetExitCodeProcess(info.hProcess, C.byref(result)):
            raise C.WinError(C.get_last_error())
        return result.value
    finally:
        kernel32.CloseHandle(info.hProcess)

