import json
import sys
import tempfile
import threading
import time
from pathlib import Path
import unittest
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nte_music_desk.transcription import ProcessJob, TranscriptionCancelled, transcription_command, clean_log
from nte_music_desk.midi import MidiSong, MidiNote, write_midi, parse_midi


class TranscriptionChecks(unittest.TestCase):
    def test_contract_keeps_unquantized_multitrack_and_validates_options(self):
        command = transcription_command(sys.executable, '音频 有空格.wav', 'output.mid')
        self.assertEqual(command[1:4], ['-m', 'muscriptor.main', 'transcribe'])
        self.assertNotIn('--quantize', command)
        self.assertEqual(command[command.index('--detect-tempo') + 1], 'false')
        self.assertEqual(command[command.index('--batch-size') + 1], '1')
        self.assertNotIn('--instruments', command)
        with self.assertRaises(ValueError): transcription_command(sys.executable, 'a.wav', 'a.mid', model='evil')
        self.assertNotIn('hf_abcdefgh123456', clean_log('\x1b[31mhf_abcdefgh123456'))

    def test_real_subprocess_output_validation_and_provenance(self):
        # Transport fixture, NOT a model quality test: the child copies known MIDI.
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, fixture = root / '片段 有空格.wav', root / 'fixture.mid'
            source.write_bytes(b'fixture audio')
            write_midi(MidiSong('fixture', 1, 480, [MidiNote(0,0,60,90,0,.5), MidiNote(1,1,48,70,0,.6)], ['lead','bass'], [(0,500000)], .6, []), fixture)
            script = root / 'engine.py'
            script.write_text('import pathlib,sys\npathlib.Path(sys.argv[sys.argv.index("--output")+1]).write_bytes(pathlib.Path(' + repr(str(fixture)) + ').read_bytes())\nprint("hf_abcdefgh123456")\n', encoding='utf-8')
            with patch('nte_music_desk.transcription.engine_command', return_value=[sys.executable, str(script)]):
                result = ProcessJob().transcribe(sys.executable, source, root)
            self.assertEqual(len(parse_midi(result.read_bytes()).notes), 2)
            provenance = json.loads((result.parent / 'provenance.json').read_text(encoding='utf-8'))
            self.assertEqual(provenance['parts'], 2)
            self.assertEqual(provenance['source_name'], source.name)
            self.assertNotIn('hf_abcdefgh123456', (result.parent / 'engine.log').read_text(encoding='utf-8'))
            self.assertFalse((result.parent / 'partial.mid').exists())
            script.write_text('import pathlib,sys\npathlib.Path(sys.argv[sys.argv.index("--output")+1]).write_bytes(b"not MIDI")\n', encoding='utf-8')
            with patch('nte_music_desk.transcription.engine_command', return_value=[sys.executable, str(script)]):
                with self.assertRaises(ValueError): ProcessJob().transcribe(sys.executable, source, root)
            self.assertEqual(len(list((root / 'transcriptions').rglob('original.mid'))), 1)

    def test_cancellation_terminates_child_and_discards_partial(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); script = root / 'wait.py'; source = root / 'a.wav'
            source.write_bytes(b'fixture')
            marker = root / 'started'
            script.write_text('import time,pathlib,sys\npathlib.Path(' + repr(str(marker)) + ').touch()\npathlib.Path(sys.argv[sys.argv.index("--output")+1]).write_bytes(b"partial")\ntime.sleep(30)\n', encoding='utf-8')
            job, errors = ProcessJob(), []
            def run():
                try: job.transcribe(sys.executable, source, root)
                except Exception as e: errors.append(e)
            with patch('nte_music_desk.transcription.engine_command', return_value=[sys.executable, str(script)]):
                thread = threading.Thread(target=run); thread.start()
                deadline = time.monotonic() + 5
                while not marker.exists() and time.monotonic() < deadline: time.sleep(.02)
                job.cancel(); thread.join(timeout=15)
            self.assertFalse(thread.is_alive())
            self.assertIsInstance(errors[0], TranscriptionCancelled)
            self.assertFalse(list((root / 'transcriptions').rglob('*.mid')))
