"""Versioned, content-addressed arrangements. No game input or third-party code."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

from .instruments import INSTRUMENTS

DEFAULTS = {"tracks": [], "mode": "melody", "speed": 1.0, "transpose": 0,
            "range_policy": "fold", "start": 0.0, "end": None, "countdown": 7, "hold_ms": 300, "roles": {}, "max_polyphony": 12}


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_settings(value):
    if not isinstance(value, dict):
        raise ValueError("演奏方案设置无效。")
    result = {**DEFAULTS, **{k: v for k, v in value.items() if k in DEFAULTS}}
    tracks = result["tracks"]
    if not isinstance(tracks, list) or not tracks or len(tracks) > 2048 or any(type(t) is not int or not 0 <= t < 2048 for t in tracks):
        raise ValueError("演奏方案的音轨无效。")
    result["tracks"] = sorted(set(tracks))
    roles = result['roles']
    if not isinstance(roles, dict) or len(roles) > 2048 or any(not isinstance(k, str) or not k.isdigit() or int(k) >= 2048 or v not in ('melody', 'bass', 'harmony') for k, v in roles.items()):
        raise ValueError('演奏方案的声部角色无效。')
    result['roles'] = dict(roles)
    if result["mode"] not in ("melody", "chords", "faithful", "balanced") or result["range_policy"] not in ("fold", "drop", "strict"):
        raise ValueError("演奏方案的模式无效。")
    for name, low, high in (("speed", .25, 2), ("start", 0, 7200)):
        v = result[name]
        if type(v) not in (int, float) or not math.isfinite(v) or not low <= v <= high:
            raise ValueError(f"演奏方案的 {name} 无效。")
    for name, low, high in (("transpose", -36, 36), ("countdown", 0, 60), ("hold_ms", 20, 400), ("max_polyphony", 2, 36)):
        if type(result[name]) is not int or not low <= result[name] <= high:
            raise ValueError(f"演奏方案的 {name} 无效。")
    end = result["end"]
    if end is not None and (type(end) not in (int, float) or not math.isfinite(end) or not result["start"] < end <= 7200):
        raise ValueError("演奏方案的片段终点无效。")
    return result


class PresetStore:
    def __init__(self, directory):
        self.directory = Path(directory) / "arrangements"

    def path(self, digest, instrument):
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest) or instrument not in INSTRUMENTS:
            raise ValueError("演奏方案标识无效。")
        return self.directory / f"{digest}.{instrument}.json"

    def load(self, digest, instrument, tracks, source_tracks=None):
        path = self.path(digest, instrument)
        if not path.exists():
            return None
        if path.stat().st_size > 65536:
            raise ValueError("演奏方案文件过大。")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("schema") not in ("nte-arrangement-v1", "nte-arrangement-v2") or data.get("sha256") != digest or data.get("instrument") != instrument:
            raise ValueError("演奏方案版本或曲谱标识不匹配。")
        settings = validate_settings(data.get("settings"))
        if data['schema'] == 'nte-arrangement-v1' and source_tracks:
            settings['tracks'] = [part for part, original in source_tracks.items() if original in settings['tracks'] and part in tracks]
            if not settings['tracks']:
                raise ValueError('旧方案的音轨已不存在。')
        if not set(settings["tracks"]).issubset(tracks):
            raise ValueError("演奏方案包含不存在的音轨。")
        return settings

    def save(self, digest, instrument, settings):
        settings = validate_settings(settings)
        path = self.path(digest, instrument)
        self.directory.mkdir(parents=True, exist_ok=True)
        if path.exists():
            old = path.read_text(encoding='utf-8')
            if 'nte-arrangement-v1' in old:
                backup = path.with_suffix('.v1.backup.json')
                if not backup.exists():
                    backup.write_text(old, encoding='utf-8')
        data = {"schema": "nte-arrangement-v2", "sha256": digest, "instrument": instrument,
                "arranger_version": 1, "settings": settings}
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
        temporary.replace(path)
