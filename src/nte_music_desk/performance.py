"""Compile one performance plan for keyboard execution, audition and reports."""
from __future__ import annotations

from dataclasses import dataclass
from .midi import validate_score, note_name
from .keyboard import KEYS, PianoKey
from .instruments import SHIFT, score_instrument


@dataclass(frozen=True)
class PlannedNote:
    at: float
    duration: float
    midi: int
    source_midi: int
    source_at: float
    source_track: int
    velocity: int = 80


@dataclass(frozen=True)
class PerformancePlan:
    key_events: tuple
    notes: tuple[PlannedNote, ...]
    duration: float
    mixed_groups: int


def _record(notes, event, at, release):
    if notes is not None:
        notes.append(PlannedNote(at, release - at, event["midi"], event.get("source_midi", event["midi"]),
                                 event.get("source_at", event["at"]), event.get("source_track", -1), event.get('velocity', 80)))


def _compile_keys(score, hold_ms=300, notes=None):
    validate_score(score)
    if not 20 <= hold_ms <= 400:
        raise ValueError("按键时长应为 20–400 毫秒。")
    profile = score_instrument(score)
    if profile.id == "piano":
        return piano_schedule(score, hold_ms, notes)
    events, next_key = [], {}
    # Reverse scan finds the next occurrence of the same physical key, so a
    # repeated pitch always gets a release gap, including octave-fold collisions.
    for note in reversed(score["events"]):
        key = KEYS[note_name(note["midi"])]
        at = note["at"]
        duration = min(hold_ms / 1000, note["duration"] * 0.8)
        if key in next_key:
            duration = min(duration, max(0, next_key[key] - at) * 0.8)
        if duration <= 0:
            continue  # Duplicated simultaneous pitch: strike just once.
        next_key[key] = at
        events.extend([(at, 1, key), (at + duration, 0, key)])
        _record(notes, note, at, at + duration)
    events.sort(key=lambda e: (e[0], e[1], e[2].virtual_key))  # release before down
    return events


def piano_schedule(score, hold_ms, notes=None):
    """Reserve a modifier-settle gap; no note remains down across a Shift change."""
    if score["mode"] != "melody":
        return piano_chord_schedule(score, hold_ms, notes)
    events, shifted, last_release = [], False, 0
    source_notes = score["events"]
    for index, note in enumerate(source_notes):
        mapped = score_instrument(score).keys[note_name(note["midi"])]
        key = PianoKey(mapped.label.replace("Shift + ", ""), mapped.virtual_key, mapped.scan_code)
        at = note["at"] + 0.02
        release = at + min(hold_ms / 1000, note["duration"] * 0.8)
        if index + 1 < len(source_notes):
            following = source_notes[index + 1]
            next_shift = score_instrument(score).keys[note_name(following["midi"])].shifted
            gap = 0.025 if mapped.shifted != next_shift else 0.008
            release = min(release, following["at"] + 0.02 - gap)
        if release - at < 0.005:
            raise ValueError("钢琴音符过密，无法留出 Shift 切换时间，请降低速度倍率。")
        if mapped.shifted != shifted:
            events.append((at - 0.015, int(mapped.shifted), SHIFT))
            shifted = mapped.shifted
        events.extend([(at, 1, key), (release, 0, key)])
        _record(notes, note, at, release)
        last_release = release
    if shifted:
        events.append((last_release + 0.001, 0, SHIFT))
    events.sort(key=lambda e: (e[0], e[1], e[2].virtual_key))
    return events


def piano_chord_schedule(score, hold_ms, notes=None):
    """White/black subgroups use short successive attacks, never mixed Shift states.

    Within each subgroup the physical keys are pressed together. Release all
    keys before changing Shift, including C/C# which share one letter. This is
    a fast rolled chord for mixed colors; it does not claim exact simultaneity.
    """
    profile = score_instrument(score)
    groups = []
    for note in score["events"]:
        if not groups or note["at"] - groups[-1][0]["at"] > max(.000001, score.get('settings', {}).get('onset_group_ms', 25) / 1000):
            groups.append([note])
        else:
            groups[-1].append(note)
    batches = []
    for group in groups:
        # Folding and multiple tracks may create the same pitch near one onset.
        unique = {}
        for note in group:
            existing = unique.get(note["midi"])
            if existing is None or existing["duration"] < note["duration"]:
                unique[note["midi"]] = note
        if len(unique) > score.get('settings', {}).get('max_polyphony', 6):
            raise ValueError("钢琴同组音符超过配置上限，请调整和弦音数。")
        parts = []
        for shifted in (False, True):
            part = [(note, profile.keys[note_name(note["midi"])]) for note in unique.values()
                    if profile.keys[note_name(note["midi"])].shifted == shifted]
            if part:
                parts.append((shifted, part))
        for offset, (shifted, part) in enumerate(parts):
            batches.append((group[0]["at"] + 0.02 + offset * 0.055, shifted, part))
    events, owns_shift, last_release = [], False, 0
    preserving = score['mode'] in ('faithful', 'balanced')
    switch_at, next_switch = float('inf'), {}
    for i in range(len(batches) - 1, -1, -1):
        if i + 1 < len(batches) and batches[i][1] != batches[i + 1][1]:
            switch_at = batches[i + 1][0]
        next_switch[i] = switch_at
    future, same_key_at = {}, {}
    for i in range(len(batches) - 1, -1, -1):
        at, _, part = batches[i]
        for note, mapped in part:
            same_key_at[i, mapped.virtual_key] = future.get(mapped.virtual_key, float('inf'))
            future[mapped.virtual_key] = at
    for index, (at, shifted, part) in enumerate(batches):
        release_cap = float("inf")
        if preserving:
            release_cap = next_switch[index] - .025
        elif index + 1 < len(batches):
            next_at, next_shift, _ = batches[index + 1]
            release_cap = next_at - (0.025 if shifted != next_shift else 0.008)
        if release_cap - at < 0.005:
            raise ValueError("钢琴和弦过密，无法留出分组与松键时间，请降低速度倍率或减少音轨。")
        if shifted != owns_shift:
            events.append((at - 0.015, int(shifted), SHIFT))
            owns_shift = shifted
        last_release = at
        for note, mapped in part:
            key = PianoKey(mapped.label.replace("Shift + ", ""), mapped.virtual_key, mapped.scan_code)
            release = min(at + min(hold_ms / 1000, note["duration"] * 0.8), release_cap)
            if preserving:
                release = min(release, same_key_at[index, mapped.virtual_key] - .008)
                if release - at < .005:
                    raise ValueError('钢琴声部在 Shift 切换或重复键处过密，请降低速度或使用吉他钢琴模式。')
            events.extend([(at, 1, key), (release, 0, key)])
            _record(notes, note, at, release)
            last_release = max(last_release, release)
    if owns_shift:
        events.append((last_release + 0.001, 0, SHIFT))
    events.sort(key=lambda e: (e[0], e[1], e[2].virtual_key))
    return events


def performance_plan(score, hold_ms=300):
    notes = []
    keys = _compile_keys(score, hold_ms, notes)
    if not notes:
        raise ValueError("曲谱没有可执行的音符。")
    notes.sort(key=lambda n: (n.at, n.midi))
    groups = []
    for event in score["events"]:
        if not groups or event["at"] - groups[-1][0]["at"] > max(.000001, score.get('settings', {}).get('onset_group_ms', 25) / 1000):
            groups.append([event])
        else:
            groups[-1].append(event)
    profile = score_instrument(score)
    mixed = sum(len({profile.keys[note_name(e["midi"])].shifted for e in group}) > 1 for group in groups) if profile.id == "piano" else 0
    duration = max(score.get("summary", {}).get("seconds", 0), keys[-1][0],
                   max(n.at + n.duration for n in notes))
    return PerformancePlan(tuple(keys), tuple(notes), duration, mixed)


def key_schedule(score, hold_ms=300):
    """Compatibility API backed by the same plan used for previews."""
    return list(performance_plan(score, hold_ms).key_events)

