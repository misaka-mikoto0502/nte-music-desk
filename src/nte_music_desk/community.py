"""Portable performance projects and an HTTP community demo with durable storage."""
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
from pathlib import Path
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from . import __version__
from .arrangement import compile_arrangement, validate_segments
from .instruments import get_instrument
from .midi import MidiNote, MidiSong
from .performance import performance_plan
from .presets import validate_settings

MAX_BYTES = 12 * 1024 * 1024


def encode(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')


def project_document(song, settings, instrument, *, title, author, description='', parent=''):
    return validate_project(dict(schema='nte-performance-project-v1', title=title, author=author,
                                 description=description, parent=parent, instrument=instrument,
                                 engine_version=__version__, settings=settings,
                                 source=dict(title=song.title, ppqn=song.ppqn, seconds=song.seconds,
                                             track_names=song.track_names, tempos=song.tempos,
                                             part_sources={str(k): v for k, v in song.part_sources.items()},
                                             notes=[asdict(note) for note in song.notes])))


def project_song(source):
    return MidiSong(source['title'], 1, source['ppqn'], [MidiNote(**note) for note in source['notes']],
                    source['track_names'], [tuple(tempo) for tempo in source['tempos']], source['seconds'], [],
                    {int(k): v for k, v in source['part_sources'].items()})


def validate_project(value):
    if not isinstance(value, dict) or value.get('schema') != 'nte-performance-project-v1':
        raise ValueError('请选择工作台导出的演奏工程。')
    result = {'schema': 'nte-performance-project-v1'}
    for key, maximum in (('title', 120), ('author', 80), ('description', 1500), ('parent', 64), ('engine_version', 40)):
        text = value.get(key, '')
        if not isinstance(text, str) or len(text) > maximum or any(ord(char) < 32 and char != '\n' for char in text):
            raise ValueError('作品标题、作者或说明无效。')
        if key in ('title', 'author') and not text.strip():
            raise ValueError('请填写作品名称与作者。')
        result[key] = text.strip()
    result['instrument'] = get_instrument(value.get('instrument')).id
    source = value.get('source')
    if not isinstance(source, dict):
        raise ValueError('工程缺少原始音符。')
    notes, names = source.get('notes'), source.get('track_names')
    duration, ppqn = source.get('seconds'), source.get('ppqn')
    if (type(duration) not in (int, float) or not math.isfinite(duration) or not 0 < duration <= 7200
            or type(ppqn) is not int or not 1 <= ppqn <= 32767):
        raise ValueError('工程时长或节奏无效。')
    if (not isinstance(names, list) or not 1 <= len(names) <= 2048
            or any(not isinstance(name, str) or len(name) > 200 for name in names)):
        raise ValueError('工程声部无效。')
    if not isinstance(notes, list) or not 1 <= len(notes) <= 100000:
        raise ValueError('工程音符数量无效。')
    clean_notes = []
    for note in notes:
        if not isinstance(note, dict):
            raise ValueError('工程音符无效。')
        for key, low, high in (('track', 0, len(names) - 1), ('channel', 0, 15),
                               ('pitch', 0, 127), ('velocity', 1, 127), ('program', 0, 127)):
            if type(note.get(key)) is not int or not low <= note[key] <= high:
                raise ValueError('工程音符声部、音高或力度无效。')
        start, end = note.get('start'), note.get('end')
        if (any(type(t) not in (int, float) or not math.isfinite(t) for t in (start, end))
                or not 0 <= start < end <= duration + .01 or end - start > 120):
            raise ValueError('工程音符时间无效。')
        clean_notes.append({key: note[key] for key in ('track', 'channel', 'pitch', 'velocity', 'start', 'end', 'program')})
    tempos = source.get('tempos', [[0, 500000]])
    if (not isinstance(tempos, list) or not 1 <= len(tempos) <= 10000
            or any(not isinstance(t, (list, tuple)) or len(t) != 2
                   or type(t[0]) is not int or t[0] < 0 or type(t[1]) is not int or not 1 <= t[1] <= 16777215 for t in tempos)):
        raise ValueError('工程速度标记无效。')
    parts = source.get('part_sources', {})
    if (not isinstance(parts, dict) or len(parts) > 2048
            or any(not isinstance(k, str) or not k.isdigit() or int(k) >= len(names)
                   or type(v) is not int or not 0 <= v < 2048 for k, v in parts.items())):
        raise ValueError('工程声部来源无效。')
    title = source.get('title', result['title'])
    if not isinstance(title, str) or len(title) > 200:
        raise ValueError('原曲名称无效。')
    result['source'] = dict(title=title, ppqn=ppqn, seconds=duration, notes=clean_notes,
                            track_names=names, tempos=tempos, part_sources=parts)
    song = project_song(result['source'])
    result['settings'] = validate_settings(value.get('settings'))
    available = {track['index'] for track in song.track_info()}
    if not set(result['settings']['tracks']).issubset(available):
        raise ValueError('工程选中了不存在的声部。')
    result['settings']['segments'] = validate_segments(result['settings']['segments'], duration=duration, tracks=available)
    if len(encode(result)) > MAX_BYTES:
        raise ValueError('工程超过 12 MB，请缩短曲目或减少音符。')
    return result


def read_project(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('演奏工程超过 12 MB。')
    return validate_project(json.loads(path.read_text(encoding='utf-8-sig')))


def write_project(path, project):
    project = validate_project(project)
    path = Path(path)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_bytes(encode(project))
    temporary.replace(path)


def request_json(endpoint, path='/projects', project=None):
    endpoint = endpoint.strip().rstrip('/')
    parts = urlsplit(endpoint)
    if (parts.scheme not in ('http', 'https') or not parts.hostname or parts.username or parts.password
            or parts.query or parts.fragment):
        raise ValueError('请输入有效的社区服务地址。')
    if parts.scheme == 'http' and parts.hostname not in ('localhost', '127.0.0.1', '::1'):
        raise ValueError('联网社区请使用 HTTPS；本机 Demo 可使用 HTTP。')
    payload = encode(validate_project(project)) if project is not None else None
    request = Request(endpoint + path, data=payload, headers={'Content-Type': 'application/json',
                                                             'User-Agent': 'NTE-Music-Desk/' + __version__})
    try:
        with urlopen(request, timeout=12) as response:
            data = response.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError('社区返回的数据过大。')
        return json.loads(data)
    except HTTPError as error:
        raise ValueError('社区请求未完成（HTTP ' + str(error.code) + '）。') from error
    except (URLError, TimeoutError, OSError) as error:
        raise ValueError('暂时无法连接社区，请检查服务地址或启动本机 Demo。') from error


class CommunityDemo:
    """A loopback service for exercising real upload/list/download requests."""
    def __init__(self, directory, *, port=0):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def respond(self, status, value):
                body = encode(value)
                self.send_response(status)
                self.send_header('Content-Type', 'application/json; charset=utf-8')
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlsplit(self.path).path
                if path == '/projects':
                    self.respond(200, {'projects': owner.list_projects(), 'demo': True})
                    return
                key = path.removeprefix('/projects/')
                if path.startswith('/projects/') and len(key) == 64 and all(c in '0123456789abcdef' for c in key):
                    file = owner.directory / (key + '.json')
                    if file.exists():
                        self.respond(200, json.loads(file.read_text(encoding='utf-8')))
                        return
                self.respond(404, {'error': '作品不存在。'})

            def do_POST(self):
                if self.path != '/projects':
                    self.respond(404, {'error': '入口不存在。'})
                    return
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if not 0 < length <= MAX_BYTES:
                        self.respond(413, {'error': '作品大小无效。'})
                        return
                    self.connection.settimeout(15)
                    value = json.loads(self.rfile.read(length))
                    key = owner.publish(value)
                    self.respond(201, {'id': key, 'demo': True})
                except (ValueError, KeyError, TypeError, OSError) as error:
                    self.respond(400, {'error': str(error)})

        self.server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
        self.server.daemon_threads = True
        self.endpoint = 'http://127.0.0.1:' + str(self.server.server_port)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def publish(self, project):
        project = validate_project(project)
        # Reject unusable arrangements before admitting them to the demo index.
        performance_plan(compile_arrangement(project_song(project['source']), project['settings'], project['instrument']),
                         project['settings']['hold_ms'])
        key = hashlib.sha256(encode(project)).hexdigest()
        with self.lock:
            path = self.directory / (key + '.json')
            if not path.exists():
                value = {'id': key, 'created_at': datetime.now(timezone.utc).isoformat(), 'project': project}
                temporary = path.with_suffix('.tmp')
                temporary.write_bytes(encode(value))
                temporary.replace(path)
        return key

    def list_projects(self):
        result = []
        with self.lock:
            for file in self.directory.glob('*.json'):
                try:
                    value = json.loads(file.read_text(encoding='utf-8'))
                    project = value['project']
                    result.append(dict(id=value['id'], created_at=value['created_at'], title=project['title'],
                                       author=project['author'], instrument=project['instrument'],
                                       segments=len(project['settings']['segments']), description=project['description'],
                                       parent=project['parent']))
                except (ValueError, KeyError, OSError):
                    continue
        return sorted(result, key=lambda item: item['created_at'], reverse=True)[:200]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
