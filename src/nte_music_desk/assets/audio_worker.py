"""Run only with the optional audio-engine Python, never the desktop runtime.

JSON request/response files keep paths out of shell strings. All audio remains
local. The parent owns cancellation and terminates this process and its children.
"""
from __future__ import annotations

import importlib.metadata
import json
import math
import os
from pathlib import Path
import subprocess
import sys
from audio_runtime import prefer_system_runtime

prefer_system_runtime()


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
    if end is not None and not config.get('allow_short',False) and info['seconds'] + .05 < end - start:
        raise ValueError('片段终点超过音频末尾，请缩短终点或留空。')
    return {**info, 'source_start_seconds': start, 'source_end_seconds': start + info['seconds']}


def separate(config):
    from separation_runtime import separate as run
    return run(config)


def diagnose(config):
    checks = {}
    for package in ('muscriptor', 'openunmix', 'soundfile', 'imageio-ffmpeg', 'onnxruntime'):
        try:
            checks[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            checks[package] = None
    checks.update(torch=None,cuda_available=False,cuda_devices=[])
    try:
        import torch
        checks['torch'] = torch.__version__
        checks['cuda_available'] = torch.cuda.is_available()
        checks['cuda_devices'] = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
    except (ImportError,OSError) as error:
        checks['torch_error'] = str(error)
    try:
        import onnxruntime
        checks['onnxruntime_ready'] = True
    except (ImportError,OSError) as error:
        checks['onnxruntime_ready'] = False
        checks['onnxruntime_error'] = str(error)
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


def model_access(config):
    """Explicit online HEAD check, without downloading weights or exposing tokens."""
    if config.get('model') not in ('small','medium'):raise ValueError('仅支持 1B 参数以内的 small / medium 模型。')
    from huggingface_hub import get_hf_file_metadata,hf_hub_url
    from huggingface_hub.errors import HfHubHTTPError
    try:
        metadata=get_hf_file_metadata(hf_hub_url('MuScriptor/muscriptor-'+config['model'],'model.safetensors'),timeout=20)
    except HfHubHTTPError as error:
        status=error.response.status_code if error.response is not None else None
        if status in (401,403):raise ValueError('模型访问未获准：请在所选模型页面接受条款，并在当前引擎登录 Hugging Face。') from None
        raise ValueError('模型访问检查失败，请检查网络或稍后重试。') from None
    return {'model':'muscriptor-'+config['model'],'access':'verified_by_authorized_file_metadata',
            'bytes':metadata.size,'weights_downloaded':False,'inference_tested':False}


def main():
    request = Path(sys.argv[1])
    config = json.loads(request.read_text(encoding='utf-8'))
    operations = {'prepare':prepare, 'separate':separate, 'diagnose':diagnose,'model_access':model_access}
    result = operations[config['operation']](config)
    Path(config['response']).write_text(json.dumps(result, ensure_ascii=False, indent=2),encoding='utf-8')


if __name__ == '__main__':
    main()
