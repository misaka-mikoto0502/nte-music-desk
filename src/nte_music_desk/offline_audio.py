"""Complete on-device transcription: bundled resources and isolated jobs.

This module deliberately has no network client, package installer or model
download fallback. Source builders prepare assets; users just open the app.
"""
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
import uuid

from .midi import MidiNote, MidiSong, write_midi
from .paths import asset_dir

PROFILES = {'piano': '钢琴曲', 'song': '歌曲／含人声'}
AUDIO_EXTENSIONS = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus', '.webm', '.aif', '.aiff'}
CREATE_NO_WINDOW = 0x08000000 if sys.platform == 'win32' else 0
BACKGROUND_FLAGS = CREATE_NO_WINDOW | (0x00004000 if sys.platform == 'win32' else 0)


def background_priority():
    """Yield CPU time to the foreground player without changing model arithmetic."""
    if sys.platform != 'win32': return 'default'
    import ctypes
    from ctypes import wintypes
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.GetCurrentProcess.restype = wintypes.HANDLE
    api.SetPriorityClass.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.SetPriorityClass.restype = wintypes.BOOL
    if not api.SetPriorityClass(api.GetCurrentProcess(), 0x00004000):
        raise ctypes.WinError(ctypes.get_last_error())
    return 'below_normal'


def peak_memory_bytes():
    if sys.platform != 'win32':
        return None
    import ctypes
    from ctypes import wintypes
    class Counters(ctypes.Structure):
        _fields_ = [('cb', wintypes.DWORD), ('faults', wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in ('peak', 'current', 'pool_peak', 'pool',
                                               'nonpaged_peak', 'nonpaged', 'pagefile', 'pagefile_peak')]
    counters = Counters()
    api = ctypes.WinDLL('psapi', use_last_error=True).GetProcessMemoryInfo
    api.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    api.restype = wintypes.BOOL
    return counters.peak if api(wintypes.HANDLE(-1), ctypes.byref(counters), ctypes.sizeof(counters)) else None


def remove_temporary_audio(directory):
    # The parent calls this after the complete process tree has stopped,
    # including cancellation. Keep MIDI, original predictions and audit logs.
    for name in ('input.f32', 'vocal.f32', 'result.partial'):
        try:
            (Path(directory) / name).unlink(missing_ok=True)
        except OSError:
            pass


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def bundle_dir():
    return asset_dir() / 'offline_audio'


def verify_bundle(directory=None, *, hashes=False):
    directory = Path(directory or bundle_dir())
    try:
        manifest = json.loads((directory / 'manifest.json').read_text(encoding='utf-8'))
        if manifest['schema'] != 1:
            raise ValueError('离线资源版本不匹配。')
        required = {'bin/ffmpeg.exe', 'bin/nte-audio.exe', 'models/muscriptor/muscriptor-small-f16.gguf',
                    'models/transkun/transkun.onnx', 'models/transkun/transkun-heads.onnx',
                    'models/transkun/freq2mels.f32', 'models/transkun/windows.f32',
                    'models/transkun/symbols.i32', 'models/transkun/params.json'}
        required.update('models/game/' + name for name in ('config.json', 'encoder.onnx', 'segmenter.onnx', 'estimator.onnx', 'dur2bd.onnx', 'bd2dur.onnx'))
        records = {item['file']: item for item in manifest['files']}
        if not required.issubset(records):
            raise ValueError('离线资源清单缺少必要组件。')
        for relative, record in records.items():
            path = (directory / relative).resolve()
            if not path.is_relative_to(directory.resolve()) or path.stat().st_size != record['bytes']:
                raise ValueError(f'离线组件不完整：{relative}')
            if hashes and file_hash(path) != record['sha256']:
                raise ValueError(f'离线组件校验失败：{relative}')
        return manifest
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise ValueError('离线转谱组件不完整。请重新完整解压包含模型的 Windows 包；无需安装 Python。') from error


@dataclass(frozen=True)
class OfflineRequest:
    source: Path
    profile: str = 'piano'
    start: float = 0
    end: float | None = None

    def validate(self):
        if self.profile not in PROFILES:
            raise ValueError('请选择钢琴曲或歌曲／含人声。')
        if not self.source.is_file() or self.source.suffix.lower() not in AUDIO_EXTENSIONS:
            raise ValueError('请选择支持的本地音频文件。')
        if not math.isfinite(self.start) or not 0 <= self.start < 7200:
            raise ValueError('起点需在 0–120 分钟之间。')
        if self.end is not None and (not math.isfinite(self.end) or not self.start < self.end <= self.start + 3600):
            raise ValueError('终点必须晚于起点，每次最长处理 60 分钟。')


class ProcessOwner:
    """Kill only this job and its descendants; never leave inference running."""
    def __init__(self, process):
        self.process, self.handle = process, None
        if sys.platform == 'win32':
            import ctypes as c
            from ctypes import wintypes as w
            class IO(c.Structure):
                _fields_ = [(name, c.c_ulonglong) for name in ('ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount', 'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]
            class BASIC(c.Structure):
                _fields_ = [('PerProcessUserTimeLimit', c.c_longlong), ('PerJobUserTimeLimit', c.c_longlong), ('LimitFlags', w.DWORD), ('MinimumWorkingSetSize', c.c_size_t), ('MaximumWorkingSetSize', c.c_size_t), ('ActiveProcessLimit', w.DWORD), ('Affinity', c.c_size_t), ('PriorityClass', w.DWORD), ('SchedulingClass', w.DWORD)]
            class EXTENDED(c.Structure):
                _fields_ = [('BasicLimitInformation', BASIC), ('IoInfo', IO), ('ProcessMemoryLimit', c.c_size_t), ('JobMemoryLimit', c.c_size_t), ('PeakProcessMemoryUsed', c.c_size_t), ('PeakJobMemoryUsed', c.c_size_t)]
            api = c.WinDLL('kernel32', use_last_error=True)
            api.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]; api.CreateJobObjectW.restype = w.HANDLE
            api.SetInformationJobObject.argtypes = [w.HANDLE, c.c_int, c.c_void_p, w.DWORD]
            api.AssignProcessToJobObject.argtypes = [w.HANDLE, w.HANDLE]
            api.CloseHandle.argtypes = [w.HANDLE]
            handle = api.CreateJobObjectW(None, None)
            info = EXTENDED(); info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
            if not handle or not api.SetInformationJobObject(handle, 9, c.byref(info), c.sizeof(info)) or not api.AssignProcessToJobObject(handle, int(process._handle)):
                error = c.get_last_error()
                if handle: api.CloseHandle(handle)
                process.kill()
                process.wait()
                raise OSError(error, '无法隔离音频处理进程。')
            self.api, self.handle = api, handle

    def close(self):
        if self.handle:
            self.api.CloseHandle(self.handle)
            self.handle = None
        elif self.process.poll() is None:
            self.process.kill()


class OfflineJob:
    def __init__(self, directory, request, notify):
        request.validate()
        verify_bundle()
        self.directory = Path(directory) / 'offline-transcriptions' / uuid.uuid4().hex
        self.directory.mkdir(parents=True)
        self.request, self.notify = request, notify
        self.cancelled = threading.Event()
        self.lock, self.owner = threading.Lock(), None
        self.thread = threading.Thread(target=self.run, name='offline-audio', daemon=True)

    def start(self):
        self.thread.start()
        return self

    def cancel(self):
        self.cancelled.set()
        with self.lock:
            if self.owner:
                self.owner.close()

    def run(self):
        request_path = self.directory / 'request.json'
        progress_path = self.directory / 'progress.jsonl'
        report_path = self.directory / 'result.json'
        process = None
        try:
            request_path.write_text(json.dumps({'source': str(self.request.source.resolve()), 'profile': self.request.profile,
                'start': self.request.start, 'end': self.request.end}, ensure_ascii=False), encoding='utf-8')
            args = [sys.executable]
            if not getattr(sys, 'frozen', False):
                args.append(str(Path(__file__).with_name('_bootstrap.py')))
            args += ['--offline-audio-worker', str(request_path)]
            with (self.directory / 'worker.log').open('w', encoding='utf-8') as log:
                process = subprocess.Popen(args, stdout=log, stderr=log, creationflags=BACKGROUND_FLAGS)
                with self.lock:
                    self.owner = ProcessOwner(process)
                    if self.cancelled.is_set(): self.owner.close()
                offset, pending = 0, ''
                while process.poll() is None:
                    if self.cancelled.wait(.12):
                        self.cancel()
                        break
                    if progress_path.exists():
                        with progress_path.open('r', encoding='utf-8') as stream:
                            stream.seek(offset); pending += stream.read(); offset = stream.tell()
                        lines = pending.split('\n'); pending = lines.pop()
                        for line in lines:
                            if line:
                                self.notify(json.loads(line))
                process.wait()
            if self.cancelled.is_set():
                # Even a completion that raced with Cancel must stay out of
                # the automatic shelf scan. Preserve its files for recovery.
                saved = {}
                if report_path.exists():
                    try: saved = json.loads(report_path.read_text(encoding='utf-8'))
                    except (OSError, ValueError): pass
                saved['status'] = 'cancelled'
                report_path.write_text(json.dumps(saved, ensure_ascii=False), encoding='utf-8')
                self.notify({'kind': 'cancelled'})
                return
            if not report_path.exists():
                raise ValueError('本地引擎未能完成处理。可在结果目录查看 worker.log。')
            result = json.loads(report_path.read_text(encoding='utf-8'))
            if result.get('status') != 'ok':
                raise ValueError(result.get('error', '转谱失败。'))
            path = Path(result['midi']).resolve()
            if path.parent != self.directory.resolve() or not path.is_file() or process.returncode:
                raise ValueError('转谱结果不完整，未导入曲库。')
            self.notify({'kind': 'done', **result})
        except Exception as error:
            self.notify({'kind': 'cancelled'} if self.cancelled.is_set() else {'kind': 'error', 'error': str(error)})
        finally:
            with self.lock:
                if self.owner: self.owner.close()
            if process and process.poll() is None:
                process.kill(); process.wait()
            remove_temporary_audio(self.directory)


def decode_audio(source, destination, rate, start=0, end=None, *, preview=False):
    """Decode only local files. No HTTP/HTTPS protocols compiled into this call."""
    limit = min(3600, end - start if end is not None else 3600)
    command = [str(bundle_dir() / 'bin/ffmpeg.exe'), '-nostdin', '-v', 'error', '-protocol_whitelist', 'file,pipe',
               '-ss', str(start), '-i', str(source), '-t', str(limit), '-vn', '-ac', '1', '-ar', str(rate)]
    command += ['-c:a', 'pcm_s16le'] if preview else ['-f', 'f32le', '-c:a', 'pcm_f32le']
    command += ['-y', str(destination)]
    completed = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=BACKGROUND_FLAGS)
    if completed.returncode:
        detail = completed.stderr.decode('utf-8', errors='replace')[-1200:]
        raise ValueError(f'无法读取该音频或选段：{detail}')


def notes_to_song(events, title, duration):
    """Keep all pitched notes and instruments. Drums stay in the raw result."""
    clean = []
    for n in events:
        pitch, program = int(n['pitch']), int(n.get('program', 0))
        start, end = float(n['start']), float(n['end'])
        if n.get('drum') or pitch < 0: continue
        if not (0 <= pitch <= 127 and 0 <= program <= 127 and math.isfinite(start) and math.isfinite(end)):
            raise ValueError('模型返回了无效的音符。')
        start, end = max(0, start), min(duration, end)
        if end > start:
            clean.append((pitch, program, start, end, max(1, min(127, int(n.get('velocity', 90)))), n.get('role') == 'vocal'))
    if not clean:
        raise ValueError('该选段没有识别出有音高的音符。可切换音频类型或选取更清晰的片段。')
    programs = sorted({n[1] for n in clean})
    # SMF single port has 15 melodic patches. Preserve pitches/time even when
    # a noisy prediction introduces more patches; consolidate the rarest ones.
    if len(programs) > 15:
        counts = {p: sum(n[1] == p for n in clean) for p in programs}
        keep = sorted(programs, key=lambda p: (-counts[p], p))[:15]
        clean = [(p, pr if pr in keep else keep[0], s, e, v, role) for p, pr, s, e, v, role in clean]
        programs = sorted(keep)
    groups = sorted({(role, pr) for _, pr, _, _, _, role in clean}, key=lambda key: (not key[0], key[1]))
    tracks = {key: i for i, key in enumerate(groups)}
    from .parts import instrument_name
    notes = [MidiNote(tracks[role, pr], 0, p, v, s, e, pr) for p, pr, s, e, v, role in clean]
    notes.sort(key=lambda n: (n.start, n.track, n.pitch, n.end))
    return MidiSong(title, 1, 480, notes, ['演唱主旋律' if role else instrument_name(p, 0) for role, p in groups], [(0, 500000)], duration, [])


def run_song_engine(pcm, directory, duration, emit):
    """Collect actual backend/timing without treating metadata as progress."""
    command = [str(bundle_dir() / 'bin/nte-audio.exe'),
               str(bundle_dir() / 'models/muscriptor/muscriptor-small-f16.gguf'),
               str(pcm), str(directory / 'native-notes.json')]
    stats = {}
    with (directory / 'native.log').open('w', encoding='utf-8') as log:
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log, text=True,
                              encoding='utf-8', creationflags=BACKGROUND_FLAGS) as process:
            for line in process.stdout:
                update = json.loads(line)
                if 'progress' in update:
                    emit('recognize', .34 + .60 * update['progress'], duration=duration)
                else:
                    stats.update(update)
            if process.wait():
                raise ValueError('歌曲引擎运行失败，请查看 native.log。')
    return stats


def worker(request_path):
    """Private CLI used identically by source and frozen Windows builds."""
    request_path = Path(request_path).resolve()
    directory = request_path.parent
    def emit(stage, progress, **extra):
        with (directory / 'progress.jsonl').open('a', encoding='utf-8') as stream:
            stream.write(json.dumps({'kind': 'progress', 'stage': stage, 'progress': progress, **extra}, ensure_ascii=False) + '\n')
    started = time.perf_counter()
    last_mark = started
    timings = {}
    def mark(name):
        nonlocal last_mark
        now = time.perf_counter()
        timings[name] = round(now - last_mark, 4)
        last_mark = now
    try:
        data = json.loads(request_path.read_text(encoding='utf-8'))
        request = OfflineRequest(Path(data['source']), data['profile'], float(data['start']), data['end'])
        request.validate()
        scheduling = background_priority()
        verify_bundle(hashes=True)
        mark('verify')
        import numpy as np
        rate = 44100 if request.profile == 'piano' else 16000
        emit('decode', 0)
        pcm = directory / 'input.f32'
        decode_audio(request.source, pcm, rate, request.start, request.end)
        if pcm.stat().st_size % 4: raise ValueError('音频解码结果不完整。')
        audio = np.memmap(pcm, dtype='<f4', mode='r') if pcm.stat().st_size else np.empty(0, np.float32)
        duration = len(audio) / rate
        if duration < .1: raise ValueError('选段没有足够的音频，请检查起点和终点。')
        if any(not np.isfinite(audio[start:start + rate * 20]).all() for start in range(0, len(audio), rate * 20)):
            raise ValueError('音频包含无效采样。')
        emit('load', .02, duration=duration)
        mark('decode')
        native_stats = {}
        if request.profile == 'piano':
            from .piano_transcription import PianoTranscriber
            engine = PianoTranscriber(bundle_dir() / 'models/transkun')
            emit('recognize', .04, duration=duration)
            events = engine.transcribe(audio, lambda p: emit('recognize', .04 + .90 * p, duration=duration))
            del engine, audio
            audio = None
            mark('piano')
        else:
            # Only the native child needs 16 kHz PCM from this point on.
            # Release the parent's mapping before loading the singing model.
            del audio
            audio = None
            from .vocal_transcription import VocalTranscriber, merge_vocal
            vocal_pcm = directory / 'vocal.f32'
            decode_audio(request.source, vocal_pcm, 44100, request.start, request.end)
            vocal_audio = np.memmap(vocal_pcm, dtype='<f4', mode='r')
            engine = VocalTranscriber(bundle_dir() / 'models/game')
            emit('vocal', .04, duration=duration)
            vocal = engine.transcribe(vocal_audio, lambda p: emit('vocal', .04 + .30 * p, duration=duration))
            (directory / 'vocal-notes.json').write_text(json.dumps(vocal), encoding='utf-8')
            del engine, vocal_audio
            vocal_pcm.unlink(missing_ok=True)
            mark('vocal')
            emit('recognize', .34, duration=duration)
            native_stats = run_song_engine(pcm, directory, duration, emit)
            mark('accompaniment')
            events = json.loads((directory / 'native-notes.json').read_text(encoding='utf-8'))
            events = merge_vocal(events, vocal)
        emit('organize', .96, duration=duration)
        song = notes_to_song(events, request.source.stem, duration)
        (directory / 'raw-notes.json').write_text(json.dumps(events), encoding='utf-8')
        # A non-MIDI extension prevents the shelf from finding partial writes.
        partial = directory / 'result.partial'
        write_midi(song, partial)
        midi = directory / ((''.join(c if c not in '<>:"/\\|?*' and ord(c) >= 32 else '_' for c in request.source.stem)[:100] or '曲谱') + '_本地转谱.mid')
        emit('save', .99, duration=duration)
        from .cli import render_song_preview
        render_song_preview(song, directory / 'score-preview.wav', seconds=min(30, duration))
        decode_audio(request.source, directory / 'audio-preview.wav', 44100, request.start, min(request.start + 30, request.end) if request.end is not None else request.start + 30, preview=True)
        digest = file_hash(request.source)
        mark('write_and_preview')
        result = {'status': 'ok', 'midi': str(midi), 'profile': request.profile, 'seconds': duration,
                  'notes': len(song.notes), 'source': str(request.source), 'source_sha256': digest,
                  'start': request.start, 'end': request.end, 'engine': 'Transkun2-ONNX' if request.profile == 'piano' else 'GAME-small-ONNX + MuScriptor-small-F16',
                  'seed': 0 if request.profile == 'song' else None, 'resources_sha256': file_hash(bundle_dir() / 'manifest.json'),
                  'runtime': native_stats.get('backend', 'CPU'), 'native': native_stats,
                  'timings': timings, 'elapsed_seconds': round(time.perf_counter() - started, 3),
                  'worker_peak_working_set_bytes': peak_memory_bytes(),
                  'scheduling': scheduling,
                  'network': False, 'postprocessing': 'no-transpose/no-rhythm-quantization/no-confidence-pruning'}
        partial.replace(midi)
        status = 0
        del audio
        pcm.unlink(missing_ok=True)  # Temporary decoded PCM only; never touch the user's file.
    except Exception as error:
        result, status = {'status': 'error', 'error': str(error)}, 1
    temporary = directory / 'result.json.partial'
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(directory / 'result.json')
    return status
