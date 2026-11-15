"""Bundled GAME small singing-note recognizer; no separation or downloads.

Uses the official five-module ONNX API.
The encoder includes its own frontend. NumPy + the bundled CPU ORT suffice.
"""
import json
import math
import os
from pathlib import Path

from .piano_transcription import load_runtime


class VocalTranscriber:
    sample_rate = 44100

    def __init__(self, directory):
        ort = load_runtime()
        # D3PM's exported segmenter has RandomUniform nodes. Seed before
        # constructing sessions so each fresh job repeats the same decoding.
        ort.set_seed(0)
        directory = Path(directory)
        self.settings = json.loads((directory / 'config.json').read_text(encoding='utf-8'))
        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, min(8, (os.cpu_count() or 2) // 2))
        options.inter_op_num_threads = 1
        # Five modules run sequentially. Retained per-session arenas otherwise
        # accumulate large, unused temporary buffers between modules/chunks.
        options.enable_cpu_mem_arena = False
        options.add_session_config_entry('session.intra_op.allow_spinning', '0')
        options.add_session_config_entry('session.inter_op.allow_spinning', '0')
        self.sessions = {name: ort.InferenceSession(str(directory / (name + '.onnx')), sess_options=options, providers=['CPUExecutionProvider'])
                         for name in ('encoder', 'segmenter', 'estimator', 'dur2bd', 'bd2dur')}

    def run(self, name, **values):
        session = self.sessions[name]
        return dict(zip([o.name for o in session.get_outputs()], session.run(None, {i.name: values[i.name] for i in session.get_inputs()})))

    def transcribe(self, audio, progress=lambda value: None):
        import numpy as np
        sr = self.sample_rate
        seconds = len(audio) / sr
        notes = []
        # Universal language id 0. Model randomness is seeded at session
        # creation; keep the same eight upstream segmentation steps.
        language = np.array([0], np.int64)
        for core in range(0, len(audio), 20 * sr):
            end = min(len(audio), core + 20 * sr)
            left, right = max(0, core - sr), min(len(audio), end + sr)
            waveform = np.ascontiguousarray(audio[left:right][None, :], dtype=np.float32)
            duration = np.array([(right - left) / sr], np.float32)
            enc = self.run('encoder', waveform=waveform, duration=duration)
            known = self.run('dur2bd', durations=duration[:, None], maskN=np.ones((1, 1), bool), maskT=enc['maskT'])
            boundaries = known['boundaries']
            for step in range(8 if self.settings.get('loop') else 1):
                boundaries = self.run('segmenter', x_seg=enc['x_seg'], maskT=enc['maskT'], known_boundaries=known['boundaries'],
                    prev_boundaries=boundaries, language=language, threshold=np.array(.2, np.float32), radius=np.array(2, np.int64), t=np.array([step / 8], np.float32))['boundaries']
            durations = self.run('bd2dur', boundaries=boundaries, maskT=enc['maskT'], duration=duration)
            est = self.run('estimator', x_est=enc['x_est'], boundaries=boundaries, maskT=enc['maskT'], maskN=durations['maskN'], threshold=np.array(.2, np.float32))
            cursor = left / sr
            for length, valid, present, pitch in zip(durations['durations'][0], durations['maskN'][0], est['presence'][0], est['scores'][0]):
                if not valid: continue
                finish = cursor + float(length)
                start, stop = max(cursor, core / sr), min(finish, end / sr, seconds)
                if present and math.isfinite(float(pitch)) and 0 <= pitch <= 127 and stop - start >= .04:
                    item = dict(start=start, end=stop, pitch=int(np.rint(pitch)), velocity=90, program=0, drum=False, role='vocal')
                    if notes and core > 0 and abs(start - core / sr) < .015 and abs(notes[-1]['end'] - start) < .015 and notes[-1]['pitch'] == item['pitch']:
                        notes[-1]['end'] = stop
                    else: notes.append(item)
                cursor = finish
            progress(end / len(audio))
        return notes


def merge_vocal(accompaniment, vocal):
    """Prefer the specialized melody where both engines heard the same note.

    Remove only duplicate same-pitch, substantially overlapping predictions.
    Other pitches, chords and bass notes are retained without quantization.
    """
    from bisect import bisect_left
    by_pitch = {}
    for note in vocal: by_pitch.setdefault(note['pitch'], []).append(note)
    ends = {pitch: [n['end'] for n in group] for pitch, group in by_pitch.items()}
    output = []
    for note in accompaniment:
        group = by_pitch.get(note['pitch'], [])
        cursor = bisect_left(ends.get(note['pitch'], []), note['start'])
        duplicate = False
        for other in group[cursor:]:
            if other['start'] >= note['end']: break
            overlap = min(note['end'], other['end']) - max(note['start'], other['start'])
            shorter = min(note['end'] - note['start'], other['end'] - other['start'])
            if shorter > 0 and overlap / shorter >= .6:
                duplicate = True; break
        if not duplicate: output.append(note)
    return sorted(output + list(vocal), key=lambda n: (n['start'], n['pitch'], n['end']))
