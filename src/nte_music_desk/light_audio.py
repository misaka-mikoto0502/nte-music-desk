"""Local browser transcription; stdlib desktop, CPU JS worker, no audio upload."""
from __future__ import annotations

import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path, PureWindowsPath
import re
import secrets
import threading
import time
import uuid

from .midi import MidiNote, MidiSong, write_midi
from .paths import asset_dir

MAX_SECONDS = 180
MAX_FILE_BYTES = 64 * 1024 * 1024
MAX_RESPONSE = 4 * 1024 * 1024
PROFILES = {'polyphonic', 'melody'}


def validate_source(data):
    if not isinstance(data, dict):
        raise ValueError('转谱请求无效。')
    # Local imports need no declaration form. Record the input route without
    # claiming that a license or permission has been independently verified.
    use = {'basis': 'local-file', 'status': 'local_file_provided',
           'publication_rights': 'not_verified; use audio and output lawfully'}
    name = data.get('name')
    if not isinstance(name, str) or not 1 <= len(name) <= 255:
        raise ValueError('音频文件名无效。')
    size = data.get('bytes')
    if type(size) is not int or not 0 < size <= MAX_FILE_BYTES:
        raise ValueError('轻量转谱单个文件最多 64 MB。')
    start, end, duration = (data.get(k) for k in ('start', 'end', 'duration'))
    if any(type(n) not in (int, float) or not math.isfinite(n) for n in (start, end, duration)):
        raise ValueError('音频时间无效。')
    if not 0 < duration <= 7200 or not 0 <= start < end <= duration + .02 or end - start > MAX_SECONDS + .02:
        raise ValueError('轻量转谱每次最多 3 分钟，请选择有效片段。')
    digest = data.get('sha256')
    if not isinstance(digest, str) or len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
        raise ValueError('音频散列无效。')
    if data.get('profile') not in PROFILES:
        raise ValueError('请选择保留和弦或突出旋律。')
    title = PureWindowsPath(name).stem[:100] or '本地音频'
    return {**{key: data[key] for key in ('bytes','duration','start','end','sha256','profile')},
            'name': PureWindowsPath(name).name, 'title': title, 'rights': use}


def notes_to_song(events, seconds, title):
    if not isinstance(events, list) or not 0 < len(events) <= 50000:
        raise ValueError('没有可用音符，请换用清晰的单乐器片段。')
    notes = []
    for event in events:
        if not isinstance(event, dict):
            raise ValueError('音符格式无效。')
        pitch, start, duration, amplitude = (event.get(k) for k in ('pitchMidi', 'startTimeSeconds', 'durationSeconds', 'amplitude'))
        if type(pitch) is not int or not 21 <= pitch <= 108 or any(
            type(n) not in (int, float) or not math.isfinite(n) for n in (start, duration, amplitude)):
            raise ValueError('音符音高或数值无效。')
        if not -.06 <= start < seconds or not 0 < duration <= seconds + .1 or not 0 <= amplitude <= 1:
            raise ValueError('音符超出片段范围。')
        end = min(seconds, start + duration)
        start = max(0, start)
        if end > start:
            notes.append(MidiNote(0, 0, pitch, max(1, min(127, round(amplitude * 127))), start, end, 0))
    if not notes:
        raise ValueError('片段内没有可用音符。')
    notes.sort(key=lambda n: (n.start, n.pitch))
    return MidiSong(title + ' · 轻量转谱 Beta', 1, 480, notes, ['Basic Pitch'], [], seconds, [])


class LightAudioSession:
    """One capability URL per app; callbacks only enqueue work for the Tk thread."""
    def __init__(self, directory, notify, *, assets=None, can_start=lambda: True):
        self.directory, self.notify = Path(directory), notify
        self.assets = Path(assets) if assets is not None else asset_dir() / 'light_audio'
        self.token = secrets.token_urlsafe(24)
        self.lock = threading.Lock()
        self.run_id, self.source, self.last_seen = None, None, 0
        self.result = None
        self.closed = False
        manifest = json.loads((self.assets / 'manifest.json').read_text(encoding='utf-8'))
        self.files = manifest['files']
        if not isinstance(self.files, dict) or not self.files:
            raise ValueError('轻量转谱资源清单无效。')
        total = 0
        for name, digest in self.files.items():
            if Path(name).name != name or name in ('.', '..'):
                raise ValueError('轻量转谱资源路径无效。')
            path = self.assets / name
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                raise ValueError('轻量转谱资源校验失败，请重新完整解压软件。')
            total += path.stat().st_size
        if total > 4_500_000:
            raise ValueError('轻量转谱组件超过体积预算。')
        self.asset_bytes = total
        session = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def setup(self):
                super().setup()
                self.connection.settimeout(15)

            def reply(self, code, data, content='application/json; charset=utf-8'):
                raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                self.send_header('Content-Type', content)
                self.send_header('Content-Length', str(len(raw)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; worker-src 'self'; connect-src 'self'; img-src 'self' data:; media-src 'self' blob:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'")
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except (OSError, TimeoutError):
                    pass

            def route(self):
                if self.headers.get('Host') != session.host or session.closed:
                    return None
                prefix = '/' + session.token + '/'
                return self.path[len(prefix):] if self.path.startswith(prefix) else None

            def do_GET(self):
                name = self.route()
                if name == 'state':
                    self.reply(200, {'open': True})
                elif name == 'result.mid' and session.result:
                    self.reply(200, session.result.read_bytes(), 'audio/midi')
                else:
                    name = 'index.html' if name == '' else name
                    if name not in session.files:
                        self.reply(404, {'error': '资源不存在。'}); return
                    content = {'html': 'text/html; charset=utf-8', 'js': 'text/javascript; charset=utf-8',
                               'css': 'text/css; charset=utf-8', 'json': 'application/json', 'bin': 'application/octet-stream',
                               'txt': 'text/plain; charset=utf-8'}.get(name.rsplit('.', 1)[-1], 'application/octet-stream')
                    self.reply(200, (session.assets / name).read_bytes(), content)

            def do_POST(self):
                route = self.route()
                if route not in ('begin', 'complete', 'cancel', 'pulse') or self.headers.get('Origin') != session.origin:
                    self.reply(403, {'error': '本地会话来源无效。'}); return
                try:
                    if self.headers.get('Content-Type') != 'application/json' or self.headers.get('Transfer-Encoding'):
                        raise ValueError('请求格式无效。')
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= MAX_RESPONSE:
                        raise ValueError('请求大小无效。')
                    data = json.loads(self.rfile.read(length))
                    if not isinstance(data, dict):
                        raise ValueError('请求格式无效。')
                    if route == 'begin':
                        if not can_start():
                            raise ValueError('请先停止游戏演奏或其他音频任务。')
                        source = validate_source(data)
                        with session.lock:
                            if session.busy:
                                raise ValueError('已有转谱任务正在运行，请先取消。')
                            session.run_id, session.source = uuid.uuid4().hex, source
                            session.last_seen = time.monotonic()
                        session.notify({'kind': 'light_status', 'text': '轻量转谱正在浏览器本机运行…'})
                        response = {'job_id': session.run_id}
                    else:
                        with session.lock:
                            if not session.run_id or data.get('job_id') != session.run_id:
                                raise ValueError('任务已取消或会话过期。')
                            if route == 'pulse':
                                session.last_seen = time.monotonic(); response = {'running': True}
                            elif route == 'cancel':
                                session.run_id = None; response = {'cancelled': True}
                                session.notify({'kind': 'light_status', 'text': '轻量转谱已取消，未导入未完成的曲谱。'})
                            else:
                                song = notes_to_song(data.get('notes'), session.source['end'] - session.source['start'], session.source['title'])
                                job = session.directory / 'light-transcriptions' / session.run_id
                                job.mkdir(parents=True, exist_ok=False)
                                title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', session.source['title']).strip(' .') or '本地音频'
                                staging, output = job / 'partial.mid', job / (title + '_轻量Beta.mid')
                                raw_song = notes_to_song(data.get('raw_notes', data.get('notes')),
                                                         session.source['end'] - session.source['start'], session.source['title'])
                                write_midi(raw_song, job / 'model_raw.mid')
                                write_midi(song, staging)
                                record = {'schema': 'nte-light-audio-v1', 'engine': 'Spotify Basic Pitch 1.0.1 / TensorFlow.js CPU',
                                          'license': 'Apache-2.0', 'source': session.source,
                                          'source_hash_status': 'browser_reported; audio_not_sent_to_desktop',
                                          'note_count': len(song.notes), 'raw_note_count': len(raw_song.notes),
                                          'midi_sha256': hashlib.sha256(staging.read_bytes()).hexdigest(),
                                          'quality': 'experimental; not a verified 90-95 percent accuracy guarantee'}
                                (job / 'provenance.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
                                staging.replace(output)
                                session.result = output
                                session.run_id = None
                                session.notify({'kind': 'light_done', 'path': output})
                                response = {'notes': len(song.notes), 'result': 'result.mid'}
                    self.reply(200, response)
                except (ValueError, OSError, TypeError, KeyError) as error:
                    self.reply(400, {'error': str(error)[:300]})

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.host = '127.0.0.1:' + str(self.server.server_port)
        self.origin = 'http://' + self.host
        self.url = self.origin + '/' + self.token + '/'
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={'poll_interval': .1}, daemon=True)
        self.thread.start()

    @property
    def busy(self):
        return self.run_id is not None and time.monotonic() - self.last_seen < 8

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.run_id = None
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
