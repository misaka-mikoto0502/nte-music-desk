"""UMX-HQ only: official MIT weights, verified before safe state-dict loading.

Runs inside the optional engine, never imports ML libraries in the desktop app.
Source/license: https://zenodo.org/records/3370489 (metadata: mit-license).
"""
import hashlib
from pathlib import Path
import urllib.request

WEIGHTS = {
    'vocals': ('vocals-b62c91ce.pth', 'd918985fad0fedf6d9ce89e279aa7218'),
    'drums': ('drums-9619578f.pth', 'cebf76e196e73e85d247f462c31e36fc'),
    'bass': ('bass-8d85a5bd.pth', '8cc37d31903fe48306468ee968f4b1b6'),
    'other': ('other-b52fbbf7.pth', '8637606623ed7c74986789c3b1f94bc6'),
}
MODEL_URL = 'https://zenodo.org/records/3370489'


def valid_weight(path, checksum):
    if not path.is_file() or path.stat().st_size != 35637796:
        return False
    # The publisher's checksum identifies the official file. torch.load also
    # uses weights_only=True; we never execute a user-supplied pickle/model.
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'md5').hexdigest() == checksum


def weight_files(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    files = {}
    for target, (name, checksum) in WEIGHTS.items():
        path = directory / name
        if not valid_weight(path, checksum):
            temporary = path.with_suffix('.partial')
            try:
                print('获取官方 UMX-HQ 权重：' + target, flush=True)
                request = urllib.request.Request(MODEL_URL + '/files/' + name, headers={'User-Agent': 'NTE-Music-Desk'})
                with urllib.request.urlopen(request, timeout=60) as response, temporary.open('wb') as stream:
                    total = 0
                    while block := response.read(256 * 1024):
                        total += len(block)
                        if total > 35637796:
                            raise ValueError('UMX-HQ 权重大小异常。')
                        stream.write(block)
                if not valid_weight(temporary, checksum):
                    raise ValueError('UMX-HQ 官方权重校验失败，请重试。')
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        files[target] = path
    return files


def separate(config):
    if config.get('separator') != 'umxhq':
        raise ValueError('仅支持官方 UMX-HQ；ViperX 权重许可未核实，仍不下载或调用。')
    import numpy as np
    import soundfile as sf
    import torch
    import openunmix

    source, rate = sf.read(config['source'], dtype='float32', always_2d=True)
    if rate != 44100 or source.shape[1] != 2 or not 0 < len(source) <= 1800 * rate:
        raise ValueError('请先解码为 44.1 kHz 双声道选段。')
    device = config.get('device', 'auto')
    if device == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    if device not in ('cpu', 'cuda') or device == 'cuda' and not torch.cuda.is_available():
        raise ValueError('分离设备不可用，请选择 CPU 或安装匹配的 NVIDIA 引擎。')
    torch.set_num_threads(min(4, torch.get_num_threads()))
    files = weight_files(config['models'])
    separator = openunmix.umxhq(pretrained=False, device=device, niter=1)
    for target, path in files.items():
        state = torch.load(path, map_location='cpu', weights_only=True)
        # Official 2019 files include three obsolete analysis buffers. New
        # Open-Unmix removes those too (upstream uses strict=False). Keep
        # strict checking for the actual learned parameters.
        for obsolete in ('sample_rate','stft.window','transform.0.window'):
            state.pop(obsolete,None)
        separator.target_models[target].load_state_dict(state)
    separator.eval()
    # Keep the common sample clock. Overlap/crossfade bounds memory for long
    # clips without trimming leading silence or independently retiming stems.
    chunk, overlap = 20 * rate, rate
    outputs = {name: np.zeros_like(source) for name in ('vocals', 'accompaniment')}
    normalizer = np.zeros(len(source), dtype=np.float32)
    with torch.inference_mode():
        for start in range(0, len(source), chunk - overlap):
            stop = min(len(source), start + chunk)
            audio = torch.from_numpy(source[start:stop].T.copy()).unsqueeze(0).to(device)
            estimates = separator.to_dict(separator(audio), aggregate_dict={
                'vocals': ['vocals'], 'accompaniment': ['drums', 'bass', 'other']})
            window = np.ones(stop - start, dtype=np.float32)
            fade = min(overlap, len(window))
            if start: window[:fade] *= np.linspace(0, 1, fade, dtype=np.float32)
            if stop < len(source): window[-fade:] *= np.linspace(1, 0, fade, dtype=np.float32)
            for name in outputs:
                value = estimates[name][0].detach().cpu().numpy().T
                if value.shape != source[start:stop].shape or not np.isfinite(value).all():
                    raise ValueError('分离结果的采样长度或数值异常。')
                outputs[name][start:stop] += value * window[:, None]
            normalizer[start:stop] += window
            print(f'分离音频：{stop / rate:.1f} / {len(source) / rate:.1f} 秒', flush=True)
            if stop == len(source): break
    for name in outputs:
        outputs[name] /= np.maximum(normalizer[:, None], 1e-8)
    # One shared gain prevents clipping and keeps A/B relative stem levels.
    peak = max(float(np.max(np.abs(value))) for value in outputs.values())
    gain = min(1.0, .98 / peak) if peak else 1.0
    for name, value in outputs.items():
        path = Path(config['output']) / (name + '.wav')
        sf.write(str(path), value * gain, rate, subtype='PCM_16')
    return {'seconds': len(source) / rate, 'frames': len(source), 'samplerate': rate,
            'separator': 'umxhq', 'license': 'MIT', 'source': MODEL_URL,
            'gain': gain, 'device': device}
