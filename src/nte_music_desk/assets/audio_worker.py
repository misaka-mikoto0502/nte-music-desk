"""Run only with the optional audio-engine Python, never the desktop runtime.

JSON request/response files keep paths out of shell strings. All audio remains
local. The parent owns cancellation and terminates this process and its children.
"""
from __future__ import annotations

import importlib.metadata
import json
import logging
import math
import os
from pathlib import Path
import subprocess
import sys


def audio_info(path):
    import soundfile as sf
    info = sf.info(str(path))
    if info.frames <= 0 or info.samplerate <= 0 or info.channels not in (1, 2):
        raise ValueError('音频没有可用的单声道或立体声采样。')
    return {'seconds': info.frames / info.samplerate, 'samplerate': info.samplerate,
            'channels': info.channels, 'frames': info.frames}


def prepare(config):
    import imageio_ffmpeg
    start, end = config.get('start', 0), config.get('end')
    requested = (end - start) if end is not None else 1800.05
    command = [imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-hide_banner', '-loglevel', 'error',
               '-i', config['source'], '-ss', str(start), '-t', str(requested), '-vn',
               '-ac', '2', '-ar', '44100', '-c:a', 'pcm_s16le', '-y', config['output']]
    result = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise ValueError('音频解码失败：' + result.stderr.decode('utf-8', errors='replace')[-1600:])
    info = audio_info(config['output'])
    if info['seconds'] > 1800:
        raise ValueError('音频超过 30 分钟，请先选取更短的片段。')
    if end is not None and info['seconds'] + .05 < end - start:
        raise ValueError('片段终点超过音频末尾，请缩短终点或留空。')
    return {**info, 'source_start_seconds': start, 'source_end_seconds': start + info['seconds']}


def separate(config):
    from audio_separator.separator import Separator
    import imageio_ffmpeg
    # Some separator backends use the executable name rather than an API. Its
    # own soundfile path is used here; the packaged decoder is also on PATH.
    os.environ['PATH'] = str(Path(imageio_ffmpeg.get_ffmpeg_exe()).parent) + os.pathsep + os.environ.get('PATH', '')
    separator = Separator(log_level=logging.INFO, model_file_dir=config['models'],
                          output_dir=config['directory'], output_format='WAV',
                          use_soundfile=True, normalization_threshold=1.0,
                          amplification_threshold=0.0,
                          mdxc_params={'segment_size':256, 'override_model_segment_size':False,
                                       'batch_size':1, 'overlap':8, 'pitch_shift':0})
    separator.load_model(config['model'])
    separator.separate(config['source'], custom_output_names={'Instrumental':'accompaniment', 'Vocals':'vocals'})
    directory = Path(config['directory'])
    paths = {'accompaniment': directory / 'accompaniment.wav', 'vocals': directory / 'vocals.wav'}
    original = audio_info(config['source'])
    result = {}
    for key, path in paths.items():
        if not path.is_file():
            raise ValueError(f'分离引擎没有产生 {key} 音轨，请检查模型版本。')
        info = audio_info(path)
        if abs(info['seconds'] - original['seconds']) > .1:
            raise ValueError('分离结果时长变化过大，不能保证人声与伴奏对齐。')
        result[key] = {'path':str(path), **info}
    return result


def diagnose(config):
    checks = {}
    for package in ('muscriptor', 'audio-separator', 'soundfile', 'imageio-ffmpeg', 'onnxruntime'):
        try:
            checks[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            checks[package] = None
    import torch
    checks['torch'] = torch.__version__
    checks['cuda_available'] = torch.cuda.is_available()
    checks['cuda_devices'] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    try:
        import imageio_ffmpeg
        checks['decoder'] = Path(imageio_ffmpeg.get_ffmpeg_exe()).is_file()
    except (ImportError, RuntimeError):
        checks['decoder'] = False
    try:
        from huggingface_hub import get_token, constants
        checks['model_login_configured'] = bool(get_token())
        cache = Path(constants.HF_HUB_CACHE) / ('models--MuScriptor--muscriptor-' + config.get('model','medium'))
        checks['muscriptor_weights_cached'] = cache.is_dir() and any(cache.rglob('*.safetensors'))
    except ImportError:
        checks['model_login_configured'] = False
        checks['muscriptor_weights_cached'] = False
    return checks


def main():
    request = Path(sys.argv[1])
    config = json.loads(request.read_text(encoding='utf-8'))
    operations = {'prepare':prepare, 'separate':separate, 'diagnose':diagnose}
    result = operations[config['operation']](config)
    Path(config['response']).write_text(json.dumps(result, ensure_ascii=False, indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
