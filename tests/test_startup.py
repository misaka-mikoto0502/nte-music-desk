from pathlib import Path
import sys
import unittest
from unittest.mock import patch, MagicMock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from nte_music_desk.startup import ensure_gui_elevation
from nte_music_desk.keyboard import run_playback_and_wait, elevation_command, run_elevated_and_wait


class StartupChecks(unittest.TestCase):
    def test_bootstrap_completes_shell_dispatch_without_waiting_for_gui_exit(self):
        shell, kernel = MagicMock(), MagicMock()
        captured = {}
        def launch(pointer):
            info = pointer._obj
            captured.update(mask=info.fMask, verb=info.lpVerb)
            info.hProcess = 1234
            return True
        shell.ShellExecuteExW.side_effect = launch
        with patch('nte_music_desk.keyboard.C.WinDLL',side_effect=[shell,kernel]), patch('nte_music_desk.keyboard.elevation_command',return_value=('test.exe',[],'.')):
            self.assertEqual(run_elevated_and_wait(arguments=[],visible=True,wait=False),0)
        self.assertTrue(captured['mask'] & 0x100)  # Required when the bootstrap has no message pump.
        self.assertTrue(captured['mask'] & 0x40)
        self.assertEqual(captured['verb'],'runas')
        kernel.WaitForSingleObject.assert_not_called()
        kernel.CloseHandle.assert_called_once_with(1234)

    def test_missing_child_process_handle_is_not_reported_as_success(self):
        shell, kernel = MagicMock(), MagicMock()
        shell.ShellExecuteExW.return_value = True
        with patch('nte_music_desk.keyboard.C.WinDLL',side_effect=[shell,kernel]), patch('nte_music_desk.keyboard.elevation_command',return_value=('test.exe',[],'.')):
            with self.assertRaisesRegex(RuntimeError,'未返回提权进程'):
                run_elevated_and_wait(arguments=[],visible=True,wait=False)
        kernel.CloseHandle.assert_not_called()

    def test_gui_elevates_once_before_window_and_preserves_data_path(self):
        with patch('nte_music_desk.startup.is_administrator',return_value=False), patch('nte_music_desk.startup.run_elevated_and_wait',return_value=0) as launch:
            self.assertEqual(ensure_gui_elevation(['--data-dir','relative data']),0)
            self.assertEqual(launch.call_args.kwargs,{'arguments':['--data-dir',str(Path('relative data').resolve())],'visible':True,'wait':False})
        with patch('nte_music_desk.startup.is_administrator',return_value=True), patch('nte_music_desk.startup.run_elevated_and_wait') as launch:
            self.assertIsNone(ensure_gui_elevation([]));launch.assert_not_called()

    def test_offline_commands_and_relaunch_failure_never_prompt_again(self):
        with patch('nte_music_desk.startup.is_administrator',return_value=False), patch('nte_music_desk.startup.run_elevated_and_wait') as launch:
            for args in (['--self-test','report.json'],['--inspect=a.mid'],['--version'],['--help'],['--convert','a.mid']):
                self.assertIsNone(ensure_gui_elevation(args))
            with self.assertRaisesRegex(RuntimeError,'管理员权限'):ensure_gui_elevation(['--elevated-child'])
            launch.assert_not_called()

    def test_playback_inherits_admin_and_cannot_request_uac(self):
        with patch('nte_music_desk.keyboard.is_administrator',return_value=True), patch('nte_music_desk.keyboard.subprocess.run') as run, patch('nte_music_desk.keyboard.run_elevated_and_wait') as elevate:
            run.return_value.returncode=2
            self.assertEqual(run_playback_and_wait(arguments=['--play','own score.json']),2)
            self.assertIn('--elevated-child',run.call_args.args[0])
            elevate.assert_not_called()
        with patch('nte_music_desk.keyboard.is_administrator',return_value=False), patch('nte_music_desk.keyboard.subprocess.run') as run:
            with self.assertRaises(RuntimeError):run_playback_and_wait(arguments=[])
            run.assert_not_called()

    def test_source_gui_keeps_installed_pillow_while_playback_remains_isolated(self):
        with patch('sys.frozen',False,create=True):
            desktop=elevation_command([],desktop=True)[1]
            worker=elevation_command(['--play','score.json'])[1]
        self.assertIn('-I',desktop)
        self.assertNotIn('-S',desktop)
        self.assertIn('-S',worker)
