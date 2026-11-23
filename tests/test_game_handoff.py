"""Focus handoff and progress confirmation; all game/key operations are mocked."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from nte_music_desk import cli
from nte_music_desk.keyboard import WindowsKeyboard, PlaybackStopped


@unittest.skipUnless(sys.platform == 'win32', 'Windows window enumeration')
class GameWindowDetectionChecks(unittest.TestCase):
    def find_game(self, windows):
        windows_by_handle = dict(enumerate(windows, start=1))
        keyboard = WindowsKeyboard.__new__(WindowsKeyboard)
        keyboard.user32 = MagicMock()
        keyboard.user32.EnumWindows.side_effect = lambda callback, param: all(
            callback(hwnd, param) for hwnd in windows_by_handle)
        keyboard.user32.IsWindowVisible.side_effect = lambda hwnd: windows_by_handle[hwnd].get('visible', True)
        keyboard.user32.GetWindow.side_effect = lambda hwnd, _: windows_by_handle[hwnd].get('owner')

        def copy_text(field):
            def read(hwnd, buffer, size):
                buffer.value = windows_by_handle[hwnd].get(field, '')[:size - 1]
                return len(buffer.value)
            return read

        keyboard.user32.GetWindowTextW.side_effect = copy_text('title')
        keyboard.user32.GetClassNameW.side_effect = copy_text('window_class')
        keyboard.window_pid = lambda hwnd: 100 + hwnd
        keyboard.process_path = lambda pid: windows_by_handle[pid - 100]['path']
        try:
            return keyboard.find_game()
        finally:
            keyboard.user32.SetForegroundWindow.assert_not_called()
            keyboard.user32.keybd_event.assert_not_called()

    def test_find_game_across_window_titles(self):
        for title, window_class in (('异环', ''), ('Neverness to Everness', 'UnrealWindow'),
                                    ('異環', 'UnrealWindow'), ('', 'UnrealWindow')):
            with self.subTest(title=title, window_class=window_class):
                self.assertEqual(self.find_game([
                    {'title': title, 'window_class': window_class, 'path': r'D:\Games\NTE\HTGame.EXE'},
                ]), (1, 101))

    def test_skips_launchers_other_games_secondary_and_unverifiable_windows(self):
        with self.assertRaisesRegex(RuntimeError, '未找到'):
            self.find_game([
                {'title': '异环', 'path': r'D:\Games\NTE\NTEGlobalLauncher.exe'},
                {'window_class': 'UnrealWindow', 'path': r'D:\Games\NTE\NTEGlobalGame.exe'},
                {'window_class': 'UnrealWindow', 'path': r'D:\Games\OtherGame.exe'},
                {'title': '异环', 'path': r'D:\Games\NTE\OtherHTGame.exe'},
                {'window_class': 'UnrealWindow', 'path': ''},
                {'window_class': 'UnrealWindow', 'path': r'D:\Games\NTE\HTGame.exe', 'visible': False},
                {'window_class': 'UnrealWindow', 'path': r'D:\Games\NTE\HTGame.exe', 'owner': 9},
                {'title': 'Error', 'window_class': '#32770', 'path': r'D:\Games\NTE\HTGame.exe'},
            ])

    def test_multiple_game_windows_require_user_to_leave_only_one(self):
        with self.assertRaisesRegex(RuntimeError, '找到 2 个'):
            self.find_game([
                {'title': '异环', 'window_class': 'UnrealWindow', 'path': r'D:\Games\CN\HTGame.exe'},
                {'title': 'Neverness to Everness', 'window_class': 'UnrealWindow',
                 'path': r'D:\Games\Global\HTGame.exe'},
            ])


@unittest.skipUnless(sys.platform=='win32','Windows foreground handoff')
class GameHandoffChecks(unittest.TestCase):
    def keyboard(self):
        keyboard=WindowsKeyboard.__new__(WindowsKeyboard)
        keyboard.hwnd=123;keyboard.pid=456;keyboard.user32=MagicMock()
        keyboard.held=set();keyboard.allow_shift=False
        keyboard.window_pid=MagicMock(return_value=456)
        keyboard.cancelled=MagicMock(return_value=False)
        keyboard.user32.IsWindow.return_value=True
        keyboard.user32.IsIconic.return_value=False
        keyboard.user32.GetAsyncKeyState.return_value=0
        return keyboard

    def test_restore_and_focus_are_confirmed_before_success(self):
        keyboard=self.keyboard()
        keyboard.user32.IsIconic.return_value=True
        keyboard.user32.GetForegroundWindow.return_value=123
        keyboard.focus_game()
        keyboard.user32.ShowWindow.assert_called_once_with(123,9)
        keyboard.user32.SetForegroundWindow.assert_called_once_with(123)
        keyboard.user32.keybd_event.assert_not_called()

    def test_focus_refusal_cancel_or_replaced_window_never_sends_input(self):
        for failure in ('refused','cancelled','replaced'):
            with self.subTest(failure=failure):
                keyboard=self.keyboard();keyboard.user32.GetForegroundWindow.return_value=999
                if failure=='cancelled':keyboard.cancelled.return_value=True
                if failure=='replaced':keyboard.window_pid.return_value=777
                with self.assertRaises((RuntimeError,PlaybackStopped)):keyboard.focus_game(timeout=0)
                keyboard.user32.keybd_event.assert_not_called()

    def test_cli_confirms_focus_for_zero_and_nonzero_countdown(self):
        for countdown in (0,1):
            with self.subTest(countdown=countdown),tempfile.TemporaryDirectory() as d:
                folder=Path(d);score=folder/'score.json';score.write_text('{}')
                args=argparse.Namespace(play=score,hold_ms=300,position=0,report=folder/'result.json',
                    cancel_file=None,control_file=None,countdown=countdown,elevated_child=False)
                backend=self.keyboard();backend.cancelled.return_value=False
                backend.user32.GetForegroundWindow.return_value=123
                order=[];backend.focus_game=MagicMock(side_effect=lambda:order.append('focus'))
                def progress(path,phase,**values):order.append((phase,values))
                def play(*args,**kwargs):
                    order.append('play');kwargs['on_progress']('playing',0,0);return 0
                tick=iter(i*.25 for i in range(50))
                with patch.object(cli,'load_score',return_value={'title':'test','settings':{},'events':[]}), \
                     patch.object(cli,'performance_plan',return_value=MagicMock(duration=10)), \
                     patch.object(cli.ctypes.windll.shell32,'IsUserAnAdmin',return_value=True), \
                     patch.object(cli,'CancellableKeyboard',return_value=backend), \
                     patch.object(cli,'write_progress',side_effect=progress), \
                     patch.object(cli,'play_timed',side_effect=play), \
                     patch.object(cli.time,'perf_counter',side_effect=lambda:next(tick)), \
                     patch.object(cli.time,'sleep'):
                    self.assertEqual(cli.play_file(args),0)
                self.assertEqual(order[0],'focus')
                self.assertEqual(order[1], ('focused', {'game_focused': True, 'game_hwnd': 123}))
                for event in order:
                    if isinstance(event,tuple) and event[0] in ('countdown','playing'):
                        self.assertTrue(event[1]['game_focused'])
                        self.assertEqual(event[1]['game_hwnd'], 123)
                backend.user32.keybd_event.assert_not_called()

    def test_workbench_stop_is_distinguished_from_safety_interruptions(self):
        for reason,origin in (('收到工作台停止指令，已停止。','workbench'),
                              ('倒计时期间取消。','workbench'),('演奏已取消。','workbench'),
                              ('检测到 Alt 按下，已停止；请松开修饰键后重试。','safety'),
                              ('游戏失去前台焦点或已关闭，已停止。','safety'),
                              ('检测到 Esc 或 F8，已停止。','safety')):
            with self.subTest(reason=reason),tempfile.TemporaryDirectory() as d:
                folder=Path(d);cancel=folder/'stop';cancel.touch()
                args=argparse.Namespace(play=folder/'score.json',hold_ms=300,position=0,
                    report=folder/'result.json',cancel_file=cancel,control_file=None,countdown=0,elevated_child=False)
                backend=self.keyboard();backend.focus_game=MagicMock()
                backend.user32.GetForegroundWindow.return_value=123
                with patch.object(cli,'load_score',return_value={'settings':{},'events':[]}), \
                     patch.object(cli,'performance_plan',return_value=MagicMock(duration=10)), \
                     patch.object(cli.ctypes.windll.shell32,'IsUserAnAdmin',return_value=True), \
                     patch.object(cli,'CancellableKeyboard',return_value=backend), \
                     patch.object(cli,'play_timed',side_effect=PlaybackStopped(reason)):
                    self.assertEqual(cli.play_file(args),2)
                result=json.loads(args.report.read_text(encoding='utf-8'))
                self.assertEqual(result['stop_origin'],origin)
                backend.user32.keybd_event.assert_not_called()
