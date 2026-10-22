from pathlib import Path
import tempfile
import unittest
import sys
import wave
from nte_music_desk.audio_audition import WaveComparison


class ComparisonChecks(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='win32','Windows MCI API')
    def test_real_mci_opens_and_seeks_own_silent_wav_without_playback(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)/('中文 长路径测试'*12)
            folder.mkdir()
            path=folder/'静音 test.wav'
            with wave.open(str(path),'wb') as stream:
                stream.setparams((1,2,22050,0,'NONE','none'))
                stream.writeframes(b'\0\0'*22050)
            player=WaveComparison()
            try:
                player.switch(path);player.seek(500,playing=False)
                self.assertAlmostEqual(player.position(),500,delta=1)
                self.assertFalse(player.playing)
            finally:player.close()

    def test_switch_retains_position_and_play_state_and_close_is_idempotent(self):
        commands=[]
        def send(command):
            commands.append(command)
            if command.endswith(' length'):return '8500'
            if command.endswith(' position'):return '2250'
            return ''
        with tempfile.TemporaryDirectory() as d:
            first,second=Path(d)/'原录音.wav',Path(d)/'MIDI.wav'
            first.touch();second.touch()
            player=WaveComparison(send=send)
            player.switch(first);player.toggle();commands.clear()
            player.switch(second)
            self.assertTrue(player.playing)
            self.assertIn(f'seek {player.alias} to 2250 wait',commands)
            self.assertIn(f'play {player.alias} from 2250 to 8500',commands)
            player.toggle();self.assertFalse(player.playing)
            commands.clear();player.switch(first)
            self.assertFalse(any(c.startswith('play ') for c in commands))
            player.close();count=len(commands);player.close()
            self.assertEqual(len(commands),count)

    def test_seek_stays_inside_common_length_and_failed_open_does_not_play(self):
        commands=[]
        def send(command):
            commands.append(command)
            return '45000' if command.endswith(' length') else '0'
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'a.wav';path.touch()
            player=WaveComparison(send=send)
            player.switch(path);self.assertEqual(player.length,30000)
            player.seek(60000,playing=False)
            self.assertIn(f'seek {player.alias} to 29999 wait',commands)
            with self.assertRaises(ValueError):player.switch(Path(d)/'missing.wav')
            self.assertFalse(player.opened)
