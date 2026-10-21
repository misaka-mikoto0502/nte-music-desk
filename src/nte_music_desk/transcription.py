"""Optional local MuScriptor CLI adapter. The desktop bundle has no ML runtime.

Only a separate process handles audio/weights. Originals are never overwritten;
an output is published only after successful exit and our MIDI parser accepts it.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import threading
import time
import uuid

from .midi import parse_midi

ENGINE_VERSION = '0.3.0'
AUDIO_SUFFIXES = {'.wav', '.mp3', '.flac', '.ogg', '.m4a', '.aiff', '.aif'}


class TranscriptionCancelled(Exception):
    pass


def clean_log(text):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
    return re.sub(r'hf_[A-Za-z0-9]{8,}', '[token hidden]', text)[-4000:]


def managed_python(directory):
    return Path(directory) / 'audio-engine' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def engine_command(executable):
    path = Path(executable).expanduser().resolve()
    if not path.is_file():
        raise ValueError('请先安装转谱引擎，或选择已安装 MuScriptor 的 Python / muscriptor.exe。')
    if path.name.lower().startswith(('python', 'pypy')):
        return [str(path), '-m', 'muscriptor.main']
    if path.stem.lower() == 'muscriptor':
        return [str(path)]
    raise ValueError('请选择 Python 解释器或 muscriptor.exe，不能填写命令或脚本。')


def transcription_command(executable, source, output, model='small', device='cpu'):
    if model not in ('small', 'medium', 'large') or device not in ('cpu', 'auto', 'cuda'):
        raise ValueError('模型或设备选项无效。')
    # Keep genuine onset timing. Do not force a piano-only recognition model,
    # quantize, fill rests, or trim leading silence before the user reviews it.
    return engine_command(executable) + ['transcribe', str(source), '--output', str(output),
        '--format', 'midi', '--model', model, '--device', device, '--batch-size', '1',
        '--detect-tempo', 'false']


class ProcessJob:
    def __init__(self):
        self.cancelled = threading.Event()

    def cancel(self):
        self.cancelled.set()

    @staticmethod
    def sanitize_log(path):
        path = Path(path)
        if path.exists():
            with path.open('rb') as reader:
                reader.seek(max(0,path.stat().st_size-4000))
                tail=clean_log(reader.read().decode('utf-8',errors='replace'))
            path.write_text(tail,encoding='utf-8')

    @staticmethod
    def kill(process):
        if process.poll() is not None:
            return
        if os.name == 'nt':
            # This PID was created by this job; kill its descendants as well
            # (pip / model workers), without matching unrelated process names.
            command = Path(os.environ.get('SYSTEMROOT', 'C:/Windows')) / 'System32/taskkill.exe'
            try:
                subprocess.run([str(command), '/PID', str(process.pid), '/T', '/F'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW, timeout=15)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
        else:
            process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def run(self, command, log, notify=None, timeout=7200, *, failure=None, environment=None):
        if self.cancelled.is_set():
            raise TranscriptionCancelled('任务已取消。')
        started, position = time.monotonic(), 0
        env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1', HF_HUB_DISABLE_PROGRESS_BARS='1')
        if environment:
            env.update(environment)
        with Path(log).open('ab') as stream:
            process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream, stderr=subprocess.STDOUT,
                shell=False, env=env, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            try:
                while process.poll() is None:
                    if self.cancelled.wait(.15):
                        raise TranscriptionCancelled('任务已取消；未导入未完成的结果。')
                    if time.monotonic() - started > timeout:
                        raise ValueError('引擎运行超时，请缩短音频或检查模型下载。')
                    size = Path(log).stat().st_size
                    if notify and size != position:
                        with Path(log).open('rb') as reader:
                            reader.seek(max(0, size - 4000))
                            notify(clean_log(reader.read().decode('utf-8', errors='replace')))
                        position = size
            finally:
                if process.poll() is None:
                    self.kill(process)
        if self.cancelled.is_set():
            raise TranscriptionCancelled('任务已取消。')
        if process.returncode:
            with Path(log).open('rb') as reader:
                reader.seek(max(0, Path(log).stat().st_size - 4000))
                detail = clean_log(reader.read().decode('utf-8', errors='replace'))
            raise ValueError((failure or '引擎运行失败。首次使用请确认模型授权与 Hugging Face 登录；详细配置见音频转谱说明。') + '\n' + detail)

    def install(self, python, directory, notify=None):
        python = Path(python).resolve()
        if not python.is_file() or not python.name.lower().startswith('python'):
            raise ValueError('请选择已安装的完整 Python 3.10+ 解释器。')
        environment = Path(directory) / 'audio-engine'
        log = Path(directory) / 'audio-engine-install.log'
        self.run([str(python), '-m', 'venv', str(environment)], log, notify, timeout=120)
        target = managed_python(directory)
        self.run([str(target), '-m', 'pip', 'install', '--disable-pip-version-check', f'muscriptor=={ENGINE_VERSION}'], log, notify)
        self.run(engine_command(target) + ['transcribe', '--help'], log, notify, timeout=120)
        return target

    def transcribe(self, executable, source, directory, model='small', device='cpu', notify=None):
        source = Path(source).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in AUDIO_SUFFIXES:
            raise ValueError('请选择 WAV、MP3、FLAC、OGG、M4A 或 AIFF 音频；具体解码支持取决于引擎。')
        if not 0 < source.stat().st_size <= 512 * 1024 * 1024:
            raise ValueError('音频需大于 0 且不超过 512 MB。建议先用 15–30 秒片段试听识别效果。')
        job = Path(directory) / 'transcriptions' / uuid.uuid4().hex
        job.mkdir(parents=True, exist_ok=False)
        staging, result, log = job / 'partial.mid', job / 'original.mid', job / 'engine.log'
        try:
            self.run(transcription_command(executable, source, staging, model, device), log, notify)
            if not staging.is_file() or not 0 < staging.stat().st_size <= 32 * 1024 * 1024:
                raise ValueError('引擎没有输出有效大小的 MIDI。')
            song = parse_midi(staging.read_bytes(), title=source.stem)
            if not song.notes or not song.track_info():
                raise ValueError('识别结果中没有可演奏的有音高声部，请换用清晰的音乐片段。')
            if self.cancelled.is_set():
                raise TranscriptionCancelled('任务已取消。')
            # Only hash the source; do not duplicate audio or send it to our servers.
            digest = hashlib.sha256()
            with source.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    digest.update(block)
            data = {'schema': 'nte-transcription-v1', 'engine': 'MuScriptor',
                'engine_contract': ENGINE_VERSION, 'model': model, 'device': device,
                'source_name': source.name, 'source_sha256': digest.hexdigest(),
                'midi_sha256': hashlib.sha256(staging.read_bytes()).hexdigest(),
                'notes': len(song.notes), 'parts': len(song.track_info()),
                'seconds': song.seconds, 'timing': 'unquantized',
                'note': 'AI 识别结果，需要试听核对；原始 MIDI 未做游戏音域适配。'}
            (job / 'provenance.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            if self.cancelled.is_set():
                raise TranscriptionCancelled('任务已取消。')
            staging.replace(result)
            return result
        finally:
            staging.unlink(missing_ok=True)
            self.sanitize_log(log)
