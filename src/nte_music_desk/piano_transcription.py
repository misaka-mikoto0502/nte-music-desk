"""Transkun 2 ONNX inference, without PyTorch or a network connection.

Frontend/decoder adapted from TuesdayCrowd/audio-claudio (Unlicense), pinned
in tools/offline_audio/resources.json; original Transkun by Yujia Yan (MIT).
Keep physical note intervals and velocity; never quantize, transpose or prune
chords during recognition. Pedal intervals are retained in the raw job result.
"""
from dataclasses import dataclass
from pathlib import Path
import math
import os
import sys


def load_runtime():
    # Conda Python may have an older msvcp140 beside python.exe. Prefer the
    # app-local redist in frozen builds, without modifying the user's system.
    if sys.platform == 'win32':
        import ctypes
        bundled = Path(getattr(sys, '_MEIPASS', ''))
        for name in ('msvcp140.dll', 'vcruntime140_1.dll'):
            candidate = bundled / name if getattr(sys, 'frozen', False) else Path(os.environ['SystemRoot']) / 'System32' / name
            if candidate.is_file():
                ctypes.WinDLL(str(candidate))
    import onnxruntime
    onnxruntime.disable_telemetry_events()
    return onnxruntime


def decode_intervals(score, forced):
    """Backward semi-CRF Viterbi; strict > tie handling matches upstream."""
    import numpy as np
    t, _, tracks = score.shape
    q = np.zeros((t, tracks), dtype=np.float32)
    ptr = np.full((t, tracks), -1, dtype=np.int32)
    q[-1] = np.maximum(score[-1, -1], 0)
    columns = np.arange(tracks)
    for begin in range(t - 2, -1, -1):
        candidates = q[begin + 1:] + score[begin + 1:, begin, :]
        selected = candidates.argmax(axis=0)
        best = candidates[selected, columns]
        use = best > q[begin + 1]
        ptr[begin] = np.where(use, selected + begin + 1, -1)
        q[begin] = np.where(use, best, q[begin + 1]) + np.maximum(score[begin, begin], 0)
    intervals = []
    for k in range(tracks):
        j = int(forced[k])
        found = []
        while j < t - 1:
            if score[j, j, k] > 0:
                found.append((j, j))
            end = ptr[j, k]
            if end < 0:
                j += 1
            else:
                found.append((j, int(end)))
                j = int(end)
        if score[-1, -1, k] > 0:
            found.append((t - 1, t - 1))
        intervals.append(found)
    return intervals


def subframe(logit):
    # ContinuousBernoulli mean, expressed in logits to avoid exp overflow.
    if abs(logit) < .004:
        value = logit / 12 - logit ** 3 / 720
    elif logit > 40:
        value = .5 - 1 / logit
    elif logit < -40:
        value = -.5 - 1 / logit
    else:
        value = .5 / math.tanh(logit / 2) - 1 / logit
    return max(-.5, min(.5, value / .99))


@dataclass
class Event:
    pitch: int
    start: float
    end: float
    onset: bool
    offset: bool
    velocity: int


class PianoTranscriber:
    sample_rate = 44100

    def __init__(self, directory):
        import numpy as np
        ort = load_runtime()
        directory = Path(directory)
        self.windows = np.fromfile(directory / 'windows.f32', '<f4').reshape(6, 4096)
        filters = np.fromfile(directory / 'freq2mels.f32', '<f4').reshape(2049, 229)
        self.filters = [(np.flatnonzero(filters[:, m]), filters[filters[:, m] != 0, m]) for m in range(229)]
        self.symbols = np.fromfile(directory / 'symbols.i32', '<i4')
        options = ort.SessionOptions()
        options.intra_op_num_threads = min(8, max(1, (os.cpu_count() or 2) // 2))
        options.inter_op_num_threads = 1
        self.model = ort.InferenceSession(str(directory / 'transkun.onnx'), sess_options=options, providers=['CPUExecutionProvider'])
        self.heads = ort.InferenceSession(str(directory / 'transkun-heads.onnx'), sess_options=options, providers=['CPUExecutionProvider'])

    def features(self, segment):
        import numpy as np
        n = len(segment)
        count = math.ceil(n / 1024) + 1
        x = np.pad(segment.astype(np.float64), (2048, (count - 1) * 1024 + 2048 - n))
        frames = np.lib.stride_tricks.sliding_window_view(x, 4096)[::1024]
        frames = (frames - frames.mean()) / (frames.std(ddof=1) + 1e-8)
        features = np.empty((1, count, 229, 6), np.float32)
        for w, window in enumerate(self.windows):
            spectrum = np.fft.rfft(frames * window, axis=-1, norm='ortho')
            power = spectrum.real ** 2 + spectrum.imag ** 2
            for m, (indices, weights) in enumerate(self.filters):
                mel = (power[:, indices] * weights).sum(axis=1)
                features[0, :, m, w] = (np.log(mel + 1e-5) - math.log(1e-5)) / -math.log(1e-5)
        return features

    def transcribe(self, audio, progress=lambda value: None):
        import numpy as np
        if not len(audio):
            return []
        fs, hop = 44100, 1024
        pad, step, length = 352800, 353280, 705600
        frame_duration = hop / fs
        duration = len(audio) / fs
        forced = np.full(90, 344, np.int32)
        by_pitch = {}
        starts = range(0, len(audio) + 2 * pad, step)
        for part, pos in enumerate(starts):
            segment = np.zeros(length, np.float32)
            left, right = max(0, pos - pad), min(len(audio), pos - pad + length)
            if right > left:
                offset = max(0, pad - pos)
                segment[offset:offset + right - left] = audio[left:right]
            # A silence-only tail cannot introduce a note or close a real note
            # more accurately. Keep the regular segment carry for non-silence.
            score, ctx = self.model.run(['S', 'ctx'], {'featuresBatch': self.features(segment)})
            intervals = decode_intervals(score, forced)
            indices = [(k, a, b) for k, group in enumerate(intervals) for a, b in group]
            if indices:
                k, a, b = np.asarray(indices).T
                left, right = ctx[k, a], ctx[k, b]
                velocity, raw = self.heads.run(['velLogits', 'ofRaw'], {'attr': np.concatenate((left, right, left * right), axis=1)})
            cursor, current = 0, []
            for k, group in enumerate(intervals):
                last_end = 0
                last_closed = 0
                for a, b in group:
                    values = raw[cursor]
                    start = max((a + subframe(float(values[0]))) * frame_duration, last_end)
                    end = max((b + subframe(float(values[1]))) * frame_duration, start + 1e-8)
                    last_end = end
                    offset = b < round(length / hop) or values[3] > 0
                    if offset:
                        last_closed = b
                    shift = pos / fs - 8
                    begin = max(start + shift, 0)
                    current.append(Event(int(self.symbols[k]), begin, max(end + shift, begin), a > 0 or values[2] > 0, bool(offset), max(1, int(velocity[cursor].argmax()))))
                    cursor += 1
                forced[k] = max(last_closed - step // hop, 0)
            for event in sorted(current, key=lambda e: (e.start, e.end, e.pitch)):
                group = by_pitch.setdefault(event.pitch, [])
                if group and event.start < group[-1].end:
                    if event.onset:
                        group[-1] = event
                    else:
                        group[-1].end = max(event.end, group[-1].end)
                        group[-1].offset = event.offset
                elif event.onset:
                    group.append(event)
            progress((part + 1) / len(starts))
            # Release the quadratic score matrix before allocating the next.
            del score, ctx
        events = []
        for group in by_pitch.values():
            if group:
                group[-1].offset = True
            group = [e for e in group if e.offset]
            for previous, following in zip(group, group[1:]):
                previous.end = min(previous.end, following.start)
            events.extend(e for e in group if e.start < min(e.end, duration))
        return [dict(pitch=e.pitch, start=e.start, end=min(e.end, duration), velocity=e.velocity, program=0, drum=False)
                for e in sorted(events, key=lambda e: (e.start, e.pitch, e.end))]
