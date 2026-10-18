"""Bounded MusicXML/MXL import into the same timed-note model as MIDI.

No network, external executables, XML entities or archive extraction. Uses the
encoded durations for tuplets and supports ordinary repeats and numbered endings.
"""
from bisect import bisect_right
from fractions import Fraction
import io
from pathlib import Path, PurePosixPath
import re
import struct
import xml.etree.ElementTree as ET
import zipfile

from .midi import MidiSong, MidiNote, read_midi, parse_midi

MAX_XML = 8 * 1024 * 1024
MAX_FILE = 16 * 1024 * 1024


def xml_root(data):
    if len(data) > MAX_XML:
        raise ValueError("MusicXML 超过 8 MB，请先精简曲谱。")
    try:
        encoding = "utf-16" if data[:2] in (b"\xff\xfe", b"\xfe\xff") or data[:4] in (b"<\x00?\x00", b"\x00<\x00?") else "utf-8-sig"
        text = data.decode(encoding)
    except UnicodeError as error:
        raise ValueError("请将 MusicXML 另存为 UTF-8 或 UTF-16 编码。") from error
    if "<!ENTITY" in text.upper() or re.search(r"<!DOCTYPE[^>]*\[", text, re.I):
        raise ValueError("不支持包含实体或内部 DTD 的 XML。")
    # Standard MusicXML exports often declare an external DTD. Do not fetch it.
    text = re.sub(r"<!DOCTYPE[^>]*>", "", text, flags=re.I)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as error:
        raise ValueError(f"MusicXML 格式不完整：{error}") from error
    for element in root.iter():
        if isinstance(element.tag, str):
            element.tag = element.tag.rsplit("}", 1)[-1]
    return root


def unpack_mxl(data):
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > 256 or len(set(names)) != len(names) or sum(e.file_size for e in entries) > 32*1024*1024:
                raise ValueError("MXL 包含过多文件、重复文件名或展开数据过大。")
            def read(name):
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name or ":" in name:
                    raise ValueError("MXL 内部路径无效。")
                info = archive.getinfo(name)
                if info.file_size > MAX_XML or info.flag_bits & 1:
                    raise ValueError("不支持过大或加密的 MXL 文件。")
                with archive.open(info) as stream:
                    value = stream.read(MAX_XML+1)
                if len(value) > MAX_XML:
                    raise ValueError("MXL 展开文件超过大小限制。")
                return value
            container = xml_root(read("META-INF/container.xml"))
            roots = container.findall("./rootfiles/rootfile")
            choices = [r.get("full-path", "") for r in roots if r.get("media-type", "") in ("application/vnd.recordare.musicxml+xml", "application/vnd.recordare.musicxml", "")]
            if not choices:
                raise ValueError("MXL 没有可读取的 MusicXML 主文件。")
            return read(choices[0])
    except (zipfile.BadZipFile, KeyError, RuntimeError, OSError) as error:
        raise ValueError("MXL 压缩包不完整或缺少主文件。") from error


def integer(value, label, minimum=0, maximum=1000000):
    try:
        result = int(value)
        if not minimum <= result <= maximum:
            raise ValueError()
        return result
    except (ValueError, TypeError):
        raise ValueError(f"MusicXML 的{label}无效。") from None


def repeats(measures):
    """Return a finite plan for simple forward/back repeats and 1st/2nd endings."""
    starts, blocks, open_start = {}, {}, None
    for index, measure in enumerate(measures):
        if measure.find('./barline[@location="middle"]/repeat') is not None:
            raise ValueError("暂不支持小节内反复，请先在制谱软件中展开后导出。")
        for repeat in measure.findall("./barline/repeat"):
            direction = repeat.get("direction")
            if direction == "forward":
                if open_start is not None:
                    raise ValueError("暂不支持嵌套反复，请先在制谱软件中展开后导出。")
                open_start = index
            elif direction == "backward":
                start = open_start if open_start is not None else 0
                times = integer(repeat.get("times", "2"), "反复次数", 1, 8)
                if start in starts:
                    raise ValueError("反复结构较复杂，请先展开反复后导出。")
                starts[start] = index
                blocks[index] = (start, times)
                open_start = None
    if open_start is not None:
        raise ValueError("反复起点缺少终点，请检查 MusicXML。")
    plan, counts, index, pass_number, ending = [], {}, 0, 1, None
    while index < len(measures):
        if len(plan) > 20000:
            raise ValueError("展开反复后的小节数量过多。")
        if index in starts:
            pass_number = counts.get(starts[index], 0) + 1
        measure = measures[index]
        marks = measure.findall("./barline/ending")
        for mark in marks:
            if mark.get("type") == "start":
                ending = set()
                for first, last in re.findall(r"(\d+)(?:\s*-\s*(\d+))?", mark.get("number", "")):
                    a, b = int(first), int(last or first)
                    if not 1 <= a <= b <= 8:
                        raise ValueError("反复房子的编号无效。")
                    ending.update(range(a, b+1))
                if not ending:
                    raise ValueError("反复房子缺少编号。")
        if ending is None or pass_number in ending:
            plan.append(index)
        if any(mark.get("type") in ("stop", "discontinue") for mark in marks):
            ending = None
        if index in blocks:
            start, times = blocks[index]
            completed = counts.get(index, 0) + 1
            pass_number = completed
            if completed < times:
                counts[index] = completed
                index, ending = start, None
                continue
        index += 1
    return plan


def parse_musicxml(data, title="MusicXML"):
    root = xml_root(data)
    if root.tag != "score-partwise":
        raise ValueError("请选择 score-partwise MusicXML；其他 XML 或 timewise 格式请先在制谱软件中重新导出。")
    parts = root.findall("part")
    if not 1 <= len(parts) <= 128:
        raise ValueError("MusicXML 声部数量无效。")
    title = root.findtext("work/work-title") or root.findtext("movement-title") or title
    info = {p.get("id"): p for p in root.findall("part-list/score-part")}
    raw, names, tempos, warnings = [], [], [(Fraction(0), -1, 0, 120.0)], []
    skipped_grace, skipped_unpitched, navigation, final_beat = 0, 0, False, Fraction(0)
    anchor = next((p for p in parts if p.find("./measure/barline/repeat") is not None),parts[0])
    anchor_measures = anchor.findall("measure")
    repeat_plan = repeats(anchor_measures)
    for track, part in enumerate(parts):
        description = info.get(part.get("id"))
        names.append(description.findtext("part-name", f"声部 {track}") if description is not None else f"声部 {track}")
        channel_text = description.findtext("midi-instrument/midi-channel", "1") if description is not None else "1"
        channel = integer(channel_text, "MIDI 通道", 1, 16)-1
        measures = part.findall("measure")
        if len(measures) > 20000:
            raise ValueError("MusicXML 小节过多。")
        divisions, nominal, transpose, global_beat = 1, Fraction(4), 0, Fraction(0)
        if len(measures)!=len(anchor_measures) and len(repeat_plan)!=len(anchor_measures):
            raise ValueError("声部小节与反复结构不一致，请先在制谱软件中展开反复。")
        if part.find("./measure/barline/repeat") is not None and repeats(measures)!=repeat_plan:
            raise ValueError("各声部的反复结构不一致，请先展开反复。")
        plan = repeat_plan if len(measures)==len(anchor_measures) else list(range(len(measures)))
        ties, serial, states, local_bpm = {}, 0, {}, (120.0 if track==0 else None)
        for measure_index in plan:
            if measure_index in states:
                divisions, nominal, transpose, local_bpm = states[measure_index]
                if local_bpm is not None:
                    serial += 1
                    tempos.append((global_beat,track,serial,local_bpm))
            else:
                states[measure_index] = (divisions,nominal,transpose,local_bpm)
            measure = measures[measure_index]
            cursor, furthest, last_onset = Fraction(0), Fraction(0), None
            for element in measure:
                if element.tag == "attributes":
                    if element.find("divisions") is not None:
                        divisions = integer(element.findtext("divisions"), "divisions", 1)
                    time = element.find("time")
                    if time is not None and time.find("beats") is not None:
                        beats_text = time.findtext("beats", "").strip()
                        if not beats_text:
                            raise ValueError("MusicXML 的拍号无效。")
                        beats = sum(integer(b, "拍号", 1, 64) for b in beats_text.split("+"))
                        unit = integer(time.findtext("beat-type"), "拍号分母", 1, 64)
                        nominal = Fraction(beats*4, unit)
                    trans = element.find("transpose")
                    if trans is not None:
                        transpose = integer(trans.findtext("chromatic", "0"), "移调", -48, 48) + 12*integer(trans.findtext("octave-change", "0"), "八度移调", -4, 4)
                elif element.tag in ("backup", "forward"):
                    duration = Fraction(integer(element.findtext("duration"), "声部时值", 0), divisions)
                    cursor += -duration if element.tag == "backup" else duration
                    if cursor < 0:
                        raise ValueError("MusicXML 声部回退超出了小节起点。")
                    furthest = max(furthest, cursor)
                    last_onset = None
                elif element.tag in ("direction", "sound"):
                    sounds = [element] if element.tag == "sound" else element.findall("sound")
                    for sound in sounds:
                        if any(k in sound.attrib for k in ("dacapo", "dalsegno", "tocoda", "fine")):
                            navigation = True
                    tempo = next((s.get("tempo") for s in sounds if s.get("tempo")), None)
                    if tempo is None and element.tag == "direction":
                        metro = element.find("direction-type/metronome")
                        if metro is not None and metro.findtext("per-minute"):
                            units = {"whole": 4, "half": 2, "quarter": 1, "eighth": .5, "16th": .25}
                            if metro.findtext("beat-unit") in units:
                                dots = len(metro.findall("beat-unit-dot"))
                                value = re.search(r"\d+(?:\.\d+)?",metro.findtext("per-minute"))
                                if value:
                                    tempo = float(value[0]) * units[metro.findtext("beat-unit")] * sum(.5**n for n in range(dots+1))
                    if tempo is not None:
                        try:
                            bpm = float(tempo)
                            if not 10 <= bpm <= 1000:
                                raise ValueError()
                        except (ValueError, TypeError):
                            raise ValueError("MusicXML 速度需为 10–1000 BPM。") from None
                        offset = Fraction(integer(element.findtext("offset", "0"), "速度偏移", -1000000), divisions)
                        serial += 1
                        tempos.append((max(Fraction(0), global_beat+cursor+offset), track, serial, bpm))
                        local_bpm = bpm
                elif element.tag == "note":
                    if element.find("grace") is not None:
                        skipped_grace += 1
                        continue
                    duration = Fraction(integer(element.findtext("duration"), "音符时值", 1), divisions)
                    chord = element.find("chord") is not None
                    if chord and last_onset is None:
                        raise ValueError("MusicXML 和弦缺少前置音符。")
                    onset = last_onset if chord else cursor
                    if not chord:
                        last_onset, cursor = cursor, cursor+duration
                    end = onset+duration
                    furthest = max(furthest, cursor, end)
                    pitch_element = element.find("pitch")
                    if element.find("rest") is not None:
                        continue
                    if pitch_element is None:
                        skipped_unpitched += 1
                        continue
                    step = pitch_element.findtext("step")
                    if not step or len(step) != 1 or step not in "CDEFGAB":
                        raise ValueError("MusicXML 音名无效。")
                    alteration = pitch_element.findtext("alter", "0")
                    try:
                        if not re.fullmatch(r"[+-]?\d{1,2}(?:\.\d{1,6})?",alteration):
                            raise ValueError()
                        alter = Fraction(alteration)
                        if alter.denominator != 1 or not -2 <= alter <= 2:
                            raise ValueError()
                    except (ValueError, ZeroDivisionError):
                        raise ValueError("只支持十二平均律的升降音，微分音请先重新导出。") from None
                    pitch = (integer(pitch_element.findtext("octave"), "音高八度", -1, 9)+1)*12 + {"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}[step] + int(alter)+transpose
                    if not 0 <= pitch <= 127:
                        raise ValueError("MusicXML 音高超出标准 MIDI 范围。")
                    begin, finish = global_beat+onset, global_beat+end
                    tie_types = {t.get("type") for t in [*element.findall("tie"), *element.findall("notations/tied")]}
                    key = (element.findtext("staff", "1"), element.findtext("voice", "1"), pitch)
                    previous = ties.get(key)
                    if "stop" in tie_types and previous is not None and previous["end"] == begin:
                        previous["end"] = finish
                        note = previous
                    else:
                        note = {"track":track,"channel":channel,"pitch":pitch,"start":begin,"end":finish}
                        raw.append(note)
                    if "start" in tie_types:
                        ties[key] = note
                    else:
                        ties.pop(key, None)
                    if len(raw) > 100000:
                        raise ValueError("MusicXML 音符超过十万，请先精简文件。")
            global_beat += furthest if furthest > 0 else nominal
            if global_beat > 1000000:
                raise ValueError("MusicXML 时间跨度过长。")
        final_beat = max(final_beat, global_beat)
    tempo_map = {}
    for beat, track, serial, bpm in sorted(tempos):
        tempo_map[beat] = bpm
    beats, seconds, rates = [], [], []
    previous, elapsed, rate = Fraction(0), 0.0, 120.0
    for beat, bpm in sorted(tempo_map.items()):
        elapsed += float(beat-previous)*60/rate
        beats.append(beat); seconds.append(elapsed); rates.append(bpm)
        previous, rate = beat, bpm
    def at_seconds(beat):
        index = bisect_right(beats, beat)-1
        return seconds[index]+float(beat-beats[index])*60/rates[index]
    def program(track):
        description = info.get(parts[track].get('id'))
        value = description.findtext('midi-instrument/midi-program', '1') if description is not None else '1'
        return integer(value, 'MIDI 乐器编号', 1, 128) - 1
    programs = [program(track) for track in range(len(parts))]
    notes = [MidiNote(n["track"],n["channel"],n["pitch"],80,at_seconds(n["start"]),at_seconds(n["end"]),programs[n['track']]) for n in raw]
    notes.sort(key=lambda n:(n.start,n.track,n.pitch))
    if skipped_grace:
        warnings.append(f"MusicXML 的 {skipped_grace} 个无时值装饰音未展开。")
    if skipped_unpitched:
        warnings.append(f"已跳过 {skipped_unpitched} 个无固定音高的音。")
    if navigation:
        warnings.append("D.C./D.S./Coda/Fine 跳转未展开；请在制谱软件中展开跳转后导出，或改用 MIDI。")
    if root.find(".//ornaments") is not None:
        warnings.append("颤音等装饰记号未展开；如需完整装饰音，请在制谱软件中导出 MIDI。")
    if not notes:
        raise ValueError("MusicXML 没有可用音符。")
    duration = max(at_seconds(final_beat), max(n.end for n in notes))
    if duration > 7200:
        raise ValueError("曲谱超过两小时，请先分段导出。")
    from .parts import normalize_parts
    return normalize_parts(MidiSong(str(title)[:180],1,480,notes,names,[(round(float(b)*480),round(60000000/r)) for b,r in zip(beats,rates)],duration,warnings))


def read_score(path):
    path = Path(path)
    if path.suffix.lower() in (".mid", ".midi", ".kar"):
        return read_midi(path)
    if path.stat().st_size > MAX_FILE:
        raise ValueError("曲谱超过 16 MB，请先精简文件。")
    data = path.read_bytes()
    if data.startswith(b"MThd"):
        return parse_midi(data,path.stem)
    if path.suffix.lower() == ".mxl":
        return parse_musicxml(unpack_mxl(data),path.stem)
    if path.suffix.lower() in (".xml", ".musicxml"):
        return parse_musicxml(data,path.stem)
    if path.suffix.lower() == ".rmi" and data[:4] == b"RIFF" and data[8:12] == b"RMID":
        end = struct.unpack("<I",data[4:8])[0]+8
        if end > len(data):
            raise ValueError("RMI 数据不完整。")
        position = 12
        while position+8 <= end:
            kind, size = data[position:position+4],struct.unpack("<I",data[position+4:position+8])[0]
            position += 8
            if position+size > end:
                raise ValueError("RMI 数据块长度无效。")
            if kind == b"data":
                return parse_midi(data[position:position+size],path.stem)
            position += size+(size%2)
        raise ValueError("RMI 中没有 MIDI 数据块。")
    raise ValueError("支持 MIDI/KAR/RMI、MusicXML/XML 和 MXL。音频、PDF、图片需先做音符识别，再导出 MIDI 或 MusicXML。")
