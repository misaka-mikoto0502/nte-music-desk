"""A running preview must be rejected before PyInstaller removes any files."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from tools import build_windows


class BuildOutputGuardChecks(unittest.TestCase):
    def test_running_app_and_native_child_block_but_sibling_directory_does_not(self):
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder);application=output/'异环演奏工作台'
            application.mkdir();marker=application/'keep.txt';marker.write_text('unchanged')
            for image in (application/'app.exe',application/'_internal/bin/nte-audio.exe'):
                with patch.object(build_windows.sys,'platform','win32'),patch.object(build_windows,'running_windows_images',return_value=iter([image])):
                    with self.assertRaisesRegex(RuntimeError,'运行'):build_windows.require_inactive_output(output)
                self.assertEqual(marker.read_text(),'unchanged')
            sibling=output/'异环演奏工作台-backup/app.exe'
            with patch.object(build_windows.sys,'platform','win32'),patch.object(build_windows,'running_windows_images',return_value=iter([sibling])):
                build_windows.require_inactive_output(output)

    def test_preflight_failure_precedes_staging_and_build_even_with_overwrite(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(build_windows.sys,'platform','win32'), \
                 patch.object(build_windows.sys,'argv',['build_windows.py','--output',folder,'--overwrite']), \
                 patch.object(build_windows,'require_inactive_output',side_effect=RuntimeError('running')), \
                 patch.object(build_windows,'check_release') as release, \
                 patch.object(build_windows.subprocess,'run') as run:
                with self.assertRaisesRegex(RuntimeError,'running'):build_windows.main()
                release.assert_not_called();run.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()),[])
