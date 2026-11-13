from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock,patch
from nte_music_desk.file_drop import FileDropTarget
from nte_music_desk.ui import App


class ImportRoutingChecks(unittest.TestCase):
    def test_audio_scores_busy_and_unsupported_drops(self):
        app=App.__new__(App)
        app.active=app.preview_token=None
        app.set_status=MagicMock();app.open_path=MagicMock(return_value=True);app.open_offline_audio=MagicMock()
        with tempfile.TemporaryDirectory() as d:
            score=Path(d)/'自己的 乐谱.MID';score.touch()
            audio=Path(d)/'自己的 音频.FLAC';audio.touch()
            other=Path(d)/'readme.txt';other.touch()
            self.assertTrue(app.import_local_file(score));app.open_path.assert_called_once_with(score)
            self.assertTrue(app.import_local_file(audio));app.open_offline_audio.assert_called_once_with(audio)
            self.assertFalse(app.import_local_file(other));self.assertFalse(app.import_local_file(Path(d)))
            app.active={'phase':'playing'}
            self.assertFalse(app.import_local_file(score));self.assertEqual(app.open_path.call_count,1)


@unittest.skipUnless(sys.platform=='win32','Windows Shell file-drop API')
class NativeDropChecks(unittest.TestCase):
    def test_registration_is_scoped_to_import_widget_and_restored(self):
        user,shell=MagicMock(),MagicMock()
        user.GetWindowLongPtrW.return_value=77;user.SetWindowLongPtrW.return_value=77
        user.ChangeWindowMessageFilterEx.return_value=True;user.IsWindow.return_value=True
        with patch('nte_music_desk.file_drop.C.WinDLL',side_effect=[user,shell]):
            receiver=FileDropTarget(SimpleNamespace(winfo_id=lambda:101),lambda m:None)
            shell.DragAcceptFiles.assert_called_once_with(101,True)
            self.assertEqual([call.args[:3] for call in user.ChangeWindowMessageFilterEx.call_args_list],[(101,0x233,1),(101,0x49,1)])
            receiver.close()
            shell.DragAcceptFiles.assert_called_with(101,False)
            user.SetWindowLongPtrW.assert_called_with(101,-4,77)

    def test_drop_is_bounded_and_always_releases_shell_handle(self):
        messages=[];receiver=FileDropTarget.__new__(FileDropTarget)
        receiver.notify=messages.append;receiver.shell32=MagicMock()
        def query(handle,index,buffer,size):
            if index==0xFFFFFFFF:return 1
            path='C:\\曲谱 文件.mid'
            if buffer is not None:buffer.value=path
            return len(path)
        receiver.shell32.DragQueryFileW.side_effect=query
        self.assertEqual(receiver.dispatch(101,0x233,555,0),0)
        self.assertEqual(messages[0]['path'],Path('C:\\曲谱 文件.mid'))
        receiver.shell32.DragFinish.assert_called_once_with(555)
        receiver.shell32.DragQueryFileW.side_effect=lambda *args:2
        receiver.dispatch(101,0x233,556,0)
        self.assertEqual(messages[-1]['kind'],'drop_error')
        receiver.shell32.DragFinish.assert_called_with(556)
