"""Local Standard MIDI File reader and NTE guitar score conversion.

No third-party dependencies, network access, or Windows input in this module.
Supports SMF 0/1 with PPQN timing; tempo changes are integrated across tracks.
Reference: https://mido.github.io/mido/files/midi.html
"""
from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict, deque
from dataclasses import dataclass, replace, field
import json
import math
from pathlib import Path
import struct
from .instruments import get_instrument, score_instrument


LOW, HIGH = 52, 87  # E3 through D#6, the verified 36-key guitar layout.


def note_name(pitch):
    return ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")[pitch % 12] + str(pitch // 12 - 1)


@dataclass(frozen=True)
class MidiNote:
    track: int
    channel: int
    pitch: int
    velocity: int
    start: float
    end: float
    program: int = 0


@dataclass
class MidiSong:
    title: str
    format: int
    ppqn: int
    notes: list[MidiNote]
    track_names: list[str]
    tempos: list[tuple[int, int]]
    seconds: float
    warnings: list[str]
    part_sources: dict[int, int] = field(default_factory=dict)

    def track_info(self, include_drums=False):
        from .parts import instrument_name, role_hint
        result = []
        grouped = defaultdict(list)
        for note in self.notes:
            if include_drums or note.channel != 9:
                grouped[note.track].append(note)
        for index, name in enumerate(self.track_names):
            notes = grouped[index]
            if notes:
                average = sum(n.pitch for n in notes) / len(notes)
                channel, program = notes[0].channel, notes[0].program
                result.append({"index": index, "name": name or f"音轨 {index}", "notes": len(notes),
                               "low": min(n.pitch for n in notes), "high": max(n.pitch for n in notes),
                               "average": average, "channel": channel, "program": program,
                               "instrument": instrument_name(program, channel), "drums": channel == 9,
                               "source_track": self.part_sources.get(index, index),
                               "role": role_hint(name, program, average)})
        return result

    def suggested_track(self):
        tracks = self.track_info()
        if not tracks:
            raise ValueError("MIDI 没有可用的旋律音符（已排除打击乐通道）。")
        minimum = min(8, max(t["notes"] for t in tracks))
        eligible = [t for t in tracks if t["notes"] >= minimum]
        return max(eligible, key=lambda t: (t["average"], t["notes"]))["index"]


class Reader:
    def __init__(self, data):
        self.data, self.pos = data, 0

    def take(self, count):
        if count < 0 or self.pos + count > len(self.data):
            raise ValueError("MIDI 数据不完整或事件长度有误。")
        value = self.data[self.pos:self.pos + count]
        self.pos += count
        return value

    def byte(self):
        return self.take(1)[0]

    def vlq(self):
        value = 0
        for _ in range(4):
            byte = self.byte()
            value = (value << 7) | (byte & 127)
            if not byte & 128:
                return value
        raise ValueError("MIDI 变长整数超过 4 字节。")


def decode_text(data):
    for encoding in ("utf-8", "cp932", "gb18030"):
        try:
            return data.decode(encoding).strip("\x00 \r\n")
        except UnicodeDecodeError:
            pass
    return data.decode("latin1").strip("\x00 \r\n")


def read_midi(path):
    path = Path(path)
    if path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("MIDI 文件超过 16 MB，请先精简文件。")
    return parse_midi(path.read_bytes(), path.stem)


def parse_midi(data, title="MIDI"):
    reader = Reader(data)
    if reader.take(4) != b"MThd":
        raise ValueError("这不是标准 MIDI 文件。请选择 .mid/.midi；MP3、PDF 不能直接转换。")
    header_size = struct.unpack(">I", reader.take(4))[0]
    if header_size < 6:
        raise ValueError("MIDI 头部长度无效。")
    fmt, track_count, division = struct.unpack(">HHH", reader.take(header_size)[:6])
    if fmt not in (0, 1):
        raise ValueError("只支持同步 MIDI TYPE 0/1；TYPE 2 请先在制谱软件中另存为 TYPE 1。")
    if not 1 <= track_count <= 1024 or (fmt == 0 and track_count != 1):
        raise ValueError("MIDI 音轨数量无效。")
    if division == 0 or division & 0x8000:
        raise ValueError("只支持 PPQN 拍时钟；SMPTE 时间码请先另存为 PPQN MIDI。")
    raw_notes, tempo_events, names, warnings = [], [(0, -1, 0, 500000)], [], []
    program_events = defaultdict(list)
    end_ticks, event_count = [], 0
    for track in range(track_count):
        if reader.take(4) != b"MTrk":
            raise ValueError(f"第 {track} 轨缺少 MTrk 数据块。")
        chunk_size = struct.unpack(">I", reader.take(4))[0]
        chunk = Reader(reader.take(chunk_size))
        tick, running, name, serial = 0, None, "", 0
        active = defaultdict(deque)

        def finish(channel, pitch):
            queue = active[channel, pitch]
            if queue:
                start, velocity, onset_serial = queue.popleft()
                if tick > start:
                    raw_notes.append((track, channel, pitch, velocity, start, tick, onset_serial))

        while chunk.pos < len(chunk.data):
            tick += chunk.vlq()
            status = chunk.byte()
            if status < 128:
                if running is None:
                    raise ValueError(f"音轨 {track} 中有缺少状态字节的 MIDI 事件。")
                chunk.pos -= 1
                status = running
            elif status < 0xF0:
                running = status
            else:
                running = None
            serial += 1
            event_count += 1
            if event_count > 1000000:
                raise ValueError("MIDI 事件超过一百万，请先精简文件。")
            if status == 0xFF:
                kind, size = chunk.byte(), chunk.vlq()
                payload = chunk.take(size)
                if kind == 3:
                    name = decode_text(payload)
                elif kind == 0x51:
                    if size != 3 or int.from_bytes(payload, "big") == 0:
                        raise ValueError("MIDI 速度事件无效。")
                    tempo_events.append((tick, track, serial, int.from_bytes(payload, "big")))
                elif kind == 0x2F:
                    break
            elif status in (0xF0, 0xF7):
                chunk.take(chunk.vlq())
            elif 0x80 <= status <= 0xEF:
                kind, channel = status >> 4, status & 15
                payload = chunk.take(1 if kind in (0xC, 0xD) else 2)
                if any(byte >= 128 for byte in payload):
                    raise ValueError("MIDI 通道事件含有非法数据字节。")
                if kind == 9 and payload[1] > 0:
                    active[channel, payload[0]].append((tick, payload[1], serial))
                elif kind == 8 or (kind == 9 and payload[1] == 0):
                    finish(channel, payload[0])
                elif kind == 0xC:
                    program_events[channel].append((tick, track, serial, payload[0]))
                elif kind == 0xB and payload[0] in (120, 123):
                    for chan, pitch in list(active):
                        if chan == channel:
                            while active[chan, pitch]:
                                finish(chan, pitch)
            else:
                raise ValueError(f"暂不支持 MIDI 状态 0x{status:02X}，请先在制谱软件中重新导出。")
        unfinished = sum(len(queue) for queue in active.values())
        if unfinished:
            warnings.append(f"音轨 {track} 有 {unfinished} 个音没有松键事件，已在轨道末尾结束。")
            for (channel, pitch), queue in active.items():
                while queue:
                    start, velocity, onset_serial = queue.popleft()
                    raw_notes.append((track, channel, pitch, velocity, start, max(tick, start + division // 4), onset_serial))
        end_ticks.append(tick)
        names.append(name)

    # Tempo at each tick applies to every synchronous track. Last event wins
    # at a shared tick, with deterministic track/event ordering.
    tempo_map = {}
    for tick, track, serial, tempo in sorted(tempo_events):
        tempo_map[tick] = tempo
    ticks, seconds, tempos = [], [], []
    previous_tick, elapsed, previous_tempo = 0, 0.0, 500000
    for tick, tempo in sorted(tempo_map.items()):
        elapsed += (tick - previous_tick) * previous_tempo / division / 1000000
        ticks.append(tick)
        seconds.append(elapsed)
        tempos.append(tempo)
        previous_tick, previous_tempo = tick, tempo

    def in_seconds(tick):
        index = bisect_right(ticks, tick) - 1
        return seconds[index] + (tick - ticks[index]) * tempos[index] / division / 1000000

    programs = {channel: sorted(values) for channel, values in program_events.items()}
    def program_at(channel, tick, track, serial):
        values = programs.get(channel, [])
        index = bisect_right(values, (tick, track, serial, 127)) - 1
        return values[index][3] if index >= 0 else 0
    notes = [MidiNote(t, c, p, v, in_seconds(a), in_seconds(b), program_at(c, a, t, serial))
             for t, c, p, v, a, b, serial in raw_notes]
    notes.sort(key=lambda n: (n.start, n.track, n.pitch))
    duration = max([in_seconds(max(end_ticks)), *[n.end for n in notes]])
    from .parts import normalize_parts
    return normalize_parts(MidiSong(title, fmt, division, notes, names, list(zip(ticks, tempos)), duration, warnings))


def convert(song, tracks=None, mode="melody", speed=1.0, transpose=0, range_policy="fold", start=0.0, instrument="guitar", end=None, max_polyphony=12, roles=None):
    profile = get_instrument(instrument)
    low, high = profile.low, profile.high
    if mode not in ("melody", "chords", "faithful", "balanced") or range_policy not in ("fold", "drop", "strict"):
        raise ValueError("转换模式无效。")
    if type(max_polyphony) is not int or not 2 <= max_polyphony <= 36:
        raise ValueError('并行音符上限需为 2–36。')
    if not math.isfinite(speed) or not 0.25 <= speed <= 2 or not -36 <= transpose <= 36:
        raise ValueError("速度倍率需为 0.25–2；移调需为 -36–36 半音。")
    if not math.isfinite(start) or not 0 <= start <= 7200:
        raise ValueError("起始位置需为 0–7200 秒。")
    segmented = start > 0 or end is not None
    stop = song.seconds if end is None else end
    if not math.isfinite(stop) or not start < stop <= song.seconds:
        raise ValueError("片段终点需大于起点，且不超过原曲时长。")
    tracks = ([p['index'] for p in song.track_info()] if mode in ('faithful', 'balanced') else [song.suggested_track()]) if tracks is None else sorted(set(tracks))
    if not tracks or any(t < 0 or t >= len(song.track_names) for t in tracks):
        raise ValueError("请至少选择一个有效音轨。")
    notes = [replace(n, start=max(start, n.start), end=min(stop, n.end))
             for n in song.notes if n.track in tracks and n.channel != 9 and n.start < stop and n.end > start]
    notes.sort(key=lambda n: (n.start, n.track, n.pitch))
    if not notes:
        raise ValueError("所选轨道和起点之后没有可用音符。")
    from .arranging import voice_octaves, choose_voices
    role_map = {str(p['index']): p['role'] for p in song.track_info()}
    if roles:
        role_map.update(roles)
    preserve = mode in ('faithful', 'balanced')
    offsets = voice_octaves(notes, low, high, transpose) if preserve and range_policy == 'fold' else {}
    budget = 1 if mode == 'melody' else 6 if mode == 'chords' else min(6, max_polyphony) if mode == 'balanced' else max_polyphony
    changes, change_count = [], 0
    def record(action, note, adapted=None):
        nonlocal change_count
        change_count += 1
        if len(changes) < 2000:
            changes.append({"action": action, "source_at": round(note.start, 6), "track": note.track,
                            "source_midi": note.pitch, "requested_midi": note.pitch + transpose, "midi": adapted})
    groups = []
    for note in notes:
        if not groups or note.start - groups[-1][0].start > (0.000001 if preserve else 0.025):
            groups.append([note])
        else:
            groups[-1].append(note)
    retained, reduced, premerged = [], 0, 0
    for group in groups:
        pool, duplicates = group, []
        if preserve:
            unique = {}
            for note in sorted(group, key=lambda n: (n.end - n.start, role_map.get(str(n.track)) == 'melody', n.velocity), reverse=True):
                pitch = note.pitch + offsets.get(note.track, 0)
                if pitch in unique:
                    duplicates.append(note)
                    record('merged', note, pitch + transpose)
                else:
                    unique[pitch] = note
            pool = list(unique.values())
            premerged += len(duplicates)
        chosen = choose_voices(pool, budget, role_map) if preserve else sorted(pool, key=lambda n: (n.pitch, n.velocity), reverse=True)[:budget]
        reduced += len(pool) - len(chosen)
        kept_ids = {id(note) for note in chosen}
        for note in pool:
            if id(note) not in kept_ids:
                record("simplified", note)
        retained.extend(chosen)
    retained.sort(key=lambda n: (n.start, n.pitch))
    origin = start if segmented else min(n.start for n in retained)
    events, folded, dropped, merged = [], 0, 0, premerged
    seen = set()
    for note in retained:
        pitch = note.pitch + transpose + offsets.get(note.track, 0)
        adjusted = offsets.get(note.track, 0) != 0
        if not low <= pitch <= high:
            if range_policy == "strict":
                raise ValueError(f"{note_name(pitch)} 超出 {profile.range_label}。请选择八度折回或调整移调。")
            if range_policy == "drop":
                dropped += 1
                record("dropped", note)
                continue
            adjusted = True
            while pitch < low:
                pitch += 12
            while pitch > high:
                pitch -= 12
        if adjusted:
            folded += 1
            record("folded", note, pitch)
        at = round((note.start - origin) / speed, 6)
        signature = (at, pitch)
        if signature in seen:
            merged += 1
            record("merged", note, pitch)
            continue
        seen.add(signature)
        events.append({"at": at, "duration": round(max(0.01, (note.end - note.start) / speed), 6),
                       "midi": pitch, "source_midi": note.pitch,
                       "source_at": round(note.start, 6), "source_track": note.track, "velocity": note.velocity})
    if not events:
        raise ValueError("全部音符均被音域过滤，请使用八度折回或调整音轨。")
    # Trim any leading silence introduced by range filtering, retain later rests.
    first = 0 if segmented else events[0]["at"]
    for event in events:
        event["at"] = round(event["at"] - first, 6)
    if mode == "melody":
        for current, following in zip(events, events[1:]):
            current["duration"] = min(current["duration"], following["at"] - current["at"])
    warnings = list(song.warnings)
    if instrument == "piano" and mode != "melody":
        warnings.append(f"钢琴每组最多 {budget} 音；混合黑白键分组约错开 55 毫秒，无法严格同时按住两种 Shift 状态。")
    if preserve:
        warnings.append('保留原声部起音；并行上限是软件设置，游戏实际多音能力需试奏确认。力度保留于曲谱/试听，键盘不能表达原曲力度与踏板。')
    if any(0 < b["at"] - a["at"] < 0.06 for a, b in zip(events, events[1:])):
        warnings.append("含间距小于 60 毫秒的音，游戏可能吞音，可降低速度倍率。")
    return {"schema": "nte-guitar-score-v1" if instrument == "guitar" else "nte-piano-score-v1",
            "instrument": instrument, "title": song.title, "mode": mode,
            "settings": {"tracks": tracks, "speed": speed, "transpose": transpose,
                         "range_policy": range_policy, "start": start, "end": end,
                         "max_polyphony": budget, "roles": role_map, "onset_group_ms": 0 if preserve else 25},
            "summary": {"source_notes": len(notes), "notes": len(events), "folded": folded,
                        "dropped": dropped, "merged": merged, "chord_notes_removed": reduced,
                        "seconds": round((stop - start) / speed if segmented else max(e["at"] + e["duration"] for e in events), 6),
                        "source_origin_seconds": round(origin + first * speed, 6)},
            "warnings": warnings, "events": events,
            "adaptation": {"changes": sorted(changes, key=lambda c: (c["source_at"], c["track"])),
                           "total_changes": change_count, "truncated": change_count > len(changes),
                           "voice_octaves": {str(k): v for k, v in offsets.items() if v}}}


def validate_score(score):
    if not isinstance(score, dict) or score.get("schema") not in ("nte-guitar-score-v1", "nte-piano-score-v1"):
        raise ValueError("不支持的游戏曲谱格式。")
    profile = score_instrument(score)
    if (score["schema"] == "nte-piano-score-v1") != (profile.id == "piano"):
        raise ValueError("曲谱格式与乐器类型不一致。")
    events = score.get("events")
    if not isinstance(events, list) or not 1 <= len(events) <= 100000:
        raise ValueError("曲谱音符数量无效。")
    previous, at_count = -1, 0
    settings = score.get('settings', {})
    if not isinstance(settings, dict):
        raise ValueError('曲谱设置无效。')
    limit = settings.get('max_polyphony', 6)
    if type(limit) is not int or not 1 <= limit <= 36:
        raise ValueError('曲谱和弦音数上限无效。')
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("曲谱事件无效。")
        at, duration, pitch = event.get("at"), event.get("duration"), event.get("midi")
        if (type(at) not in (int, float) or type(duration) not in (int, float)
                or not math.isfinite(at) or not math.isfinite(duration)
                or not 0 <= at <= 7200 or not 0 < duration <= 120
                or at < previous or type(pitch) is not int or not profile.low <= pitch <= profile.high):
            raise ValueError("曲谱的时间顺序、音高或时值无效。")
        at_count = at_count + 1 if at == previous else 1
        if type(event.get('velocity', 80)) is not int or not 1 <= event.get('velocity', 80) <= 127:
            raise ValueError('曲谱力度需为 1–127。')
        if at_count > limit:
            raise ValueError("同一时刻的音符数超过配置上限（最多 36）。")
        previous = at
    if score.get("mode") not in ("melody", "chords", "faithful", "balanced"):
        raise ValueError("曲谱演奏模式无效。")
    if profile.id == "piano" and score["mode"] == "melody" and any(a["at"] == b["at"] for a, b in zip(events, events[1:])):
        raise ValueError("旋律版同一时刻只能有一个音，请选择和弦版。")
    return score


def save_score(score, path):
    validate_score(score)
    Path(path).write_text(json.dumps(score, ensure_ascii=False, indent=2), encoding="utf-8")


def load_score(path):
    path = Path(path)
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("游戏曲谱文件过大。")
    return validate_score(json.loads(path.read_text(encoding="utf-8-sig")))


def write_midi(song, path):
    """Export all imported parts as SMF1 with a fixed tempo and preserved seconds.

    This carries timed notes, not printed notation, pedal, lyrics or ornaments.
    480 PPQN at 120 BPM gives a timing grid of about 1.04 milliseconds.
    """
    def vlq(value):
        if not 0<=value<0x10000000:raise ValueError("导出 MIDI 的时间跨度过长。")
        parts = [value&127]
        while value>>7:
            value >>= 7
            parts.insert(0,(value&127)|128)
        return bytes(parts)
    def chunk(track):return b"MTrk"+struct.pack(">I",len(track))+track
    tracks = []
    # SMF1 shares 16 channels across tracks. Allocate one channel per patch so
    # MusicXML parts that all defaulted to channel 1 do not change each other.
    programs = sorted({n.program for n in song.notes if n.channel != 9})
    if len(programs) > 15:
        raise ValueError('标准 MIDI 单端口最多同时保留 15 种有音高乐器；请在制谱软件中合并音色后导出。')
    channels = dict(zip(programs, [c for c in range(16) if c != 9]))
    for index,name in enumerate(song.track_names):
        events = []
        for note in song.notes:
            if note.track!=index:continue
            if not (math.isfinite(note.start) and math.isfinite(note.end) and 0<=note.start<note.end<=7200 and 0<=note.pitch<=127 and 0<=note.channel<=15 and type(note.program) is int and 0<=note.program<=127):
                raise ValueError("导出 MIDI 的音高或时间无效。")
            start,end = round(note.start*960),max(round(note.start*960)+1,round(note.end*960))
            channel = 9 if note.channel == 9 else channels[note.program]
            events.extend([(start,1,channel,note.pitch,max(1,min(127,note.velocity))), (end,0,channel,note.pitch,0)])
        if not events:continue
        text = str(name).encode("utf-8")[:1024]
        track = bytearray(b"\x00\xff\x03"+vlq(len(text))+text)
        used = {n.program for n in song.notes if n.track == index and n.channel != 9}
        for program in sorted(used):
            track.extend(bytes([0, 0xC0 | channels[program], program]))
        previous = 0
        for tick,on,channel,pitch,velocity in sorted(events):
            track.extend(vlq(tick-previous)+bytes([(0x90 if on else 0x80)|channel,pitch,velocity]))
            previous = tick
        tracks.append(chunk(bytes(track)+b"\x00\xff\x2f\x00"))
    if not tracks:raise ValueError("没有可导出的音符。")
    if len(tracks)>1023:raise ValueError("音轨过多，请先精简到 1023 轨以内。")
    tempo = chunk(b"\x00\xff\x51\x03\x07\xa1\x20\x00\xff\x2f\x00")
    Path(path).write_bytes(b"MThd"+struct.pack(">IHHH",6,1,len(tracks)+1,480)+tempo+b"".join(tracks))
