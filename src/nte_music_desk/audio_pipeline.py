"""Accompaniment-first audio workflow. ML dependencies stay in a child Python."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import uuid

from .midi import read_midi, write_midi
from .paths import asset_dir
from .transcription import ProcessJob, TranscriptionCancelled, AUDIO_SUFFIXES, ENGINE_VERSION, managed_python, transcription_command

SEPARATOR_VERSION = '0.47.1'
SEPARATOR_MODEL = 'model_bs_roformer_ep_317_sdr_12.9755.ckpt'
DECODER_VERSION = '0.6.0'
# A tested Windows/Python 3.12 baseline. Newest binary wheels may have different
# DLL requirements; keep the three PyTorch components mutually compatible.
AUDIO_DEPENDENCIES = [f'muscriptor=={ENGINE_VERSION}',f'audio-separator[cpu]=={SEPARATOR_VERSION}',
    f'imageio-ffmpeg=={DECODER_VERSION}','numpy==2.2.6','scipy==1.15.3','librosa==0.11.0',
    'numba==0.61.2','onnxruntime==1.22.1']
TORCH_DEPENDENCIES = ['torch==2.8.0','torchaudio==2.8.0','torchvision==0.23.0']


@dataclass(frozen=True)
class AudioRequest:
    source: Path
    source_kind: str = 'original'
    model: str = 'medium'
    device: str = 'auto'
    start: float = 0
    end: float | None = None
    melody_beta: bool = False

    def validate(self):
        path = Path(self.source).expanduser().resolve()
        if not path.is_file() or path.suffix.lower() not in AUDIO_SUFFIXES:
            raise ValueError('请选择 MP3、WAV、FLAC、OGG、M4A 或 AIFF 音频。')
        if not 0 < path.stat().st_size <= 512 * 1024 * 1024:
            raise ValueError('音频需大于 0 且不超过 512 MB。')
        if self.source_kind not in ('original', 'instrumental'):
            raise ValueError('请选择原唱或伴奏 / 纯音乐。')
        if self.model not in ('small','medium','large') or self.device not in ('cpu','auto','cuda'):
            raise ValueError('模型或设备无效。')
        if type(self.melody_beta) is not bool:
            raise ValueError('旋律 Beta 选项无效。')
        if type(self.start) not in (int,float) or not math.isfinite(self.start) or not 0 <= self.start < 7200:
            raise ValueError('片段起点需为 0–7200 秒。')
        if self.end is not None and (type(self.end) not in (int,float) or not math.isfinite(self.end) or not self.start < self.end <= 7200 or self.end-self.start > 1800):
            raise ValueError('片段终点需大于起点，单次最多 30 分钟。')
        if self.melody_beta and self.source_kind != 'original':
            raise ValueError('旋律 Beta 需要包含歌声的原唱音频，请选择“原唱 / 含人声”。')
        return replace(self,source=path)


@dataclass(frozen=True)
class AudioResult:
    directory: Path
    accompaniment: Path
    source_audio: Path
    accompaniment_audio: Path
    melody: Path | None = None
    combined: Path | None = None
    warnings: tuple[str,...] = ()


def python_engine(executable):
    path = Path(executable).expanduser().resolve()
    if not path.is_file() or not path.name.lower().startswith(('python','pypy')):
        raise ValueError('请先安装独立音频引擎，或选择已配置的 Python 解释器；此流程需要 Python，不能选择 muscriptor.exe。')
    return path


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''):
            digest.update(block)
    return digest.hexdigest()


class AudioPipeline(ProcessJob):
    def worker(self, executable, operation, directory, config, notify=None):
        directory = Path(directory)
        request, response = directory/f'{operation}-request.json', directory/f'{operation}-response.json'
        request.write_text(json.dumps({**config,'operation':operation,'response':str(response)},ensure_ascii=False),encoding='utf-8')
        self.run([str(python_engine(executable)),str(asset_dir()/'audio_worker.py'),str(request)],
                 directory/'engine.log',notify,timeout=7200 if operation=='separate' else 120,
                 failure={'prepare':'音频解码或选段失败。','separate':'伴奏分离失败，请检查依赖、模型下载与设备。','diagnose':'环境检查失败，请检查 Python 与依赖。'}[operation],
                 environment={'CUDA_VISIBLE_DEVICES':'-1'} if config.get('device')=='cpu' else None)
        if not response.is_file() or response.stat().st_size > 128*1024:
            raise ValueError('音频引擎未返回有效结果。')
        data = json.loads(response.read_text(encoding='utf-8'))
        if not isinstance(data,dict):
            raise ValueError('音频引擎结果格式无效。')
        return data

    def diagnose(self, executable, directory, model='medium', notify=None):
        target = Path(directory)/'audio-checks'/uuid.uuid4().hex
        target.mkdir(parents=True)
        return self.worker(executable,'diagnose',target,{'model':model},notify)

    def install(self, python, directory, notify=None, device='cpu'):
        python = python_engine(python)
        directory = Path(directory)
        directory.mkdir(parents=True,exist_ok=True)
        log = directory/'audio-engine-install.log'
        self.run([str(python),'-m','venv',str(directory/'audio-engine')],log,notify,timeout=180,failure='独立 Python 环境创建失败。')
        target = managed_python(directory)
        torch_command=[str(target),'-m','pip','install','--disable-pip-version-check',*TORCH_DEPENDENCIES]
        if device=='cuda':torch_command+=['--index-url','https://download.pytorch.org/whl/cu128']
        self.run(torch_command,log,notify,failure='PyTorch 安装失败，请检查下载连接；NVIDIA 组件需要较大空间与兼容驱动。')
        self.run([str(target),'-m','pip','install','--disable-pip-version-check',
                  *TORCH_DEPENDENCIES,*AUDIO_DEPENDENCIES],log,notify,
                 failure='音频引擎依赖安装失败，可重试；原 Python 环境未改动。')
        self.run(transcription_command(target,'unused.wav','unused.mid')[:3]+['transcribe','--help'],log,notify,timeout=120,failure='MuScriptor 启动检查失败。')
        self.diagnose(target,directory,notify=notify)
        return target

    def preflight(self, executable, request, job, notify=None, require_transcription=True):
        checks=self.worker(executable,'diagnose',job,{'model':request.model,'device':request.device},notify)
        required=['soundfile','imageio-ffmpeg']+(['audio-separator'] if request.source_kind=='original' else [])+(['muscriptor'] if require_transcription else ['onnxruntime'])
        missing=[name for name in required if not checks.get(name)]
        if missing or not checks.get('decoder'):
            raise ValueError('独立引擎缺少依赖：'+', '.join(missing or ['音频解码器'])+'。请安装 / 更新独立引擎。')
        if request.device=='cuda' and not checks.get('cuda_available'):
            raise ValueError('当前引擎未启用 NVIDIA GPU，请安装 GPU 组件或选择 CPU。')
        if require_transcription and not checks.get('muscriptor_weights_cached') and not checks.get('model_login_configured'):
            raise ValueError('伴奏转谱需要先完成 MuScriptor 模型授权与 Hugging Face 登录。请打开“配置说明”；旋律 Beta 可独立试用。')
        return checks

    def accompaniment(self, executable, request, directory, notify=None):
        executable, request = python_engine(executable), request.validate()
        root = Path(directory)
        job = root/'transcriptions'/uuid.uuid4().hex
        job.mkdir(parents=True,exist_ok=False)
        staging, result = job/'accompaniment.partial.mid', job/'accompaniment.mid'
        def stage(message):
            if self.cancelled.is_set(): raise TranscriptionCancelled('任务已取消。')
            if notify: notify(message)
        try:
            self.preflight(executable,request,job,notify)
            stage('1/3 解码并准备选中的音频片段…')
            prepared = job/'source.wav'
            info = self.worker(executable,'prepare',job,{'source':str(request.source),'output':str(prepared),'start':request.start,'end':request.end},notify)
            backing = prepared
            if request.source_kind == 'original':
                stage('2/3 分离人声与伴奏；首次使用会下载分离模型…')
                self.worker(executable,'separate',job,{'source':str(prepared),'directory':str(job),'models':str(root/'audio-models'/'separator'), 'model':SEPARATOR_MODEL,'device':request.device},notify)
                backing = job/'accompaniment.wav'
            stage('3/3 识别伴奏中的乐器声部，保留原始起音与和声…')
            self.run(transcription_command(executable,backing,staging,request.model,request.device),job/'engine.log',notify,
                     failure='伴奏转谱失败。请检查 MuScriptor 模型授权、登录、设备和日志。')
            if not staging.is_file() or not 0 < staging.stat().st_size <= 32*1024*1024:
                raise ValueError('伴奏识别没有输出有效大小的 MIDI。')
            song = read_midi(staging)
            if not song.track_info():
                raise ValueError('没有识别到可演奏的伴奏音符，请换用更清晰的片段。')
            if song.seconds > info['seconds'] + 2:
                raise ValueError('识别结果时间超出音频片段，未导入。')
            stage('正在校验伴奏结果…')
            metadata = {'schema':'nte-audio-pipeline-v1','workflow':'accompaniment','source_kind':request.source_kind,
                'source_name':request.source.name,'source_sha256':sha256(request.source), 'source_start_seconds':request.start,
                'source_end_seconds':info['source_end_seconds'],'seconds':info['seconds'],
                'engines':{'muscriptor':ENGINE_VERSION,'separator':SEPARATOR_VERSION if request.source_kind=='original' else None},
                'separation_model':SEPARATOR_MODEL if request.source_kind=='original' else None,
                'model':request.model,'device':request.device, 'midi_sha256':sha256(staging),'notes':len(song.notes),
                'parts':len(song.track_info()),'timing':'relative to selected audio start; leading silence retained in MIDI',
                'quality':'model output, requires audition; not a measured fidelity score', 'melody_beta_requested':request.melody_beta}
            (job/'provenance.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
            stage('伴奏已完成，可试听并导入工作台。')
            staging.replace(result)
            return AudioResult(job,result,prepared,backing)
        finally:
            staging.unlink(missing_ok=True)
            self.sanitize_log(job/'engine.log')
