import json,tempfile,unittest
from pathlib import Path
from unittest.mock import MagicMock,patch
from nte_music_desk.audio_window import verify_host
from nte_music_desk.paths import asset_dir
from nte_music_desk.ui import App

class AudioWindowChecks(unittest.TestCase):
    def test_host_assets_are_complete_and_tampering_is_rejected(self):
        self.assertTrue(verify_host(asset_dir()/'audio_window').is_file())
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            (folder/'manifest.json').write_text(json.dumps({'files':{'../bad.exe':'a'*64}}))
            with self.assertRaises(ValueError):verify_host(folder)

    def test_import_uses_desktop_reuses_window_and_keeps_browser_opt_in(self):
        app=App.__new__(App);app.active=app.audio_dialog=app.light_audio=app.light_window=None
        app.closed=False;app.messages=MagicMock();app.assets=Path('assets');app.directory=Path('data')
        app.set_status=MagicMock();app.show_error=MagicMock()
        session=MagicMock();host=MagicMock();host.show.return_value=True
        with patch('nte_music_desk.light_audio.LightAudioSession',return_value=session),patch('nte_music_desk.audio_window.DesktopAudioWindow',return_value=host) as factory,patch('webbrowser.open',return_value=True) as browser:
            path=Path('自己的录音.mp3');app.open_light_audio(path)
            session.select_desktop_audio.assert_called_once_with(path)
            factory.assert_called_once();browser.assert_not_called()
            app.open_light_audio();host.show.assert_called_once();self.assertEqual(factory.call_count,1)
            host.show.return_value=False
            app.open_light_audio();session.cancel_current.assert_called_once();self.assertEqual(factory.call_count,2)
            app.open_light_audio(browser=True);browser.assert_called_once_with(session.url,new=2)
            app.show_error.assert_not_called()

    def test_only_current_window_close_cancels_current_task(self):
        app=App.__new__(App);app.light_window=object();app.light_audio=MagicMock();app.refresh_controls=MagicMock()
        app.handle_message({'kind':'light_window_closed','window':object()})
        app.light_audio.cancel_current.assert_not_called()
        app.handle_message({'kind':'light_window_closed','window':app.light_window})
        self.assertIsNone(app.light_window);app.light_audio.cancel_current.assert_called_once()
