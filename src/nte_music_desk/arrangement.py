"""Non-destructive, source-time segment edits compiled through the existing converter."""
from copy import deepcopy
import math

from .midi import convert, validate_score


def validate_segments(value, *, duration=7200, tracks=None):
    if not isinstance(value, list) or len(value) > 128:
        raise ValueError('分段数量需在 0–128 之间。')
    result = []
    for item in value:
        if not isinstance(item, dict):
            raise ValueError('分段数据无效。')
        start, end = item.get('start'), item.get('end')
        if any(type(t) not in (int, float) or not math.isfinite(t) for t in (start, end)):
            raise ValueError('分段时间无效。')
        if not 0 <= start < end <= duration + .000001:
            raise ValueError('分段终点需在曲目范围内，且大于起点。')
        if item.get('mode') not in ('faithful', 'balanced', 'melody', 'chords'):
            raise ValueError('分段演奏方案无效。')
        transpose = item.get('transpose')
        if type(transpose) is not int or not -36 <= transpose <= 36:
            raise ValueError('分段移调需为 −36 至 +36 半音。')
        selected = item.get('tracks')
        if (not isinstance(selected, list) or not selected or len(selected) > 2048
                or any(type(t) is not int or not 0 <= t < 2048 for t in selected)):
            raise ValueError('分段需选择至少一个有效声部。')
        if tracks is not None and not set(selected).issubset(tracks):
            raise ValueError('分段包含当前曲谱中不存在的声部。')
        name = item.get('name', '片段')
        if not isinstance(name, str) or len(name) > 80:
            raise ValueError('分段名称过长。')
        result.append(dict(start=float(start), end=float(end), name=name,
                           mode=item['mode'], transpose=transpose, tracks=sorted(set(selected))))
    result.sort(key=lambda item: item['start'])
    if any(a['end'] > b['start'] + .000001 for a, b in zip(result, result[1:])):
        raise ValueError('已保存的分段不能重叠。')
    return result


def apply_region(segments, candidate):
    """Replace a range while retaining the unaffected portions of existing edits."""
    candidate = validate_segments([candidate])[0]
    result = []
    for segment in validate_segments(segments):
        if segment['end'] <= candidate['start'] or segment['start'] >= candidate['end']:
            result.append(segment)
            continue
        if segment['start'] < candidate['start']:
            result.append({**segment, 'end': candidate['start']})
        if segment['end'] > candidate['end']:
            result.append({**segment, 'start': candidate['end']})
    return validate_segments([*result, candidate])


def compile_arrangement(song, settings, instrument):
    edits = validate_segments(settings.get('segments', []), duration=song.seconds,
                              tracks={p['index'] for p in song.track_info()})
    options = dict(tracks=settings['tracks'], mode=settings['mode'], speed=settings['speed'],
                   transpose=settings['transpose'], range_policy=settings['range_policy'],
                   start=settings['start'], end=settings['end'], instrument=instrument,
                   max_polyphony=settings['max_polyphony'], roles=settings['roles'])
    if not edits:
        score = convert(song, **options)
        score['settings']['chord_alignment_ms'] = settings['chord_alignment_ms']
        return score

    start = settings['start']
    end = song.seconds if settings['end'] is None else settings['end']
    if not 0 <= start < end <= song.seconds:
        raise ValueError('演奏范围超出原曲。')
    points = sorted({start, end, *(t for e in edits for t in (e['start'], e['end']) if start < t < end)})
    parts, cache = [], {}
    for left, right in zip(points, points[1:]):
        selected = next((e for e in edits if e['start'] <= left < e['end']), None)
        local = dict(options)
        if selected:
            local.update({key: selected[key] for key in ('mode', 'transpose', 'tracks')})
        # Each note belongs to the region containing its onset. A sustained
        # note may cross a boundary and remains a single note in the whole plan.
        source_notes = [n for n in song.notes if left <= max(start, n.start) < right
                        and n.end > start and n.track in local['tracks'] and n.channel != 9]
        if not source_notes:
            continue
        local.update(start=start, end=end)
        key = (tuple(local['tracks']), local['mode'], local['transpose'])
        if key not in cache:
            # Derive each variant against the same complete source. Adding an
            # edit must not change octave choices in the unaffected regions.
            cache[key] = convert(song, **local, change_limit=400000)
        variant = cache[key]
        # Copy only data owned by this region. Copying the complete cached
        # song for every interval wastes work before discarding most events.
        part = dict(variant)
        part['events'] = [deepcopy(e) for e in variant['events'] if left <= e['source_at'] < right]
        part['summary'] = dict(variant['summary'])
        part['adaptation'] = dict(variant['adaptation'])
        changes = [deepcopy(c) for c in variant['adaptation']['changes'] if left <= c['source_at'] < right]
        part['adaptation'].update(changes=changes, total_changes=len(changes))
        part['summary'].update(source_notes=len(source_notes), notes=len(part['events']),
                               folded=sum(c['action'] == 'folded' for c in changes),
                               dropped=sum(c['action'] == 'dropped' for c in changes),
                               merged=sum(c['action'] == 'merged' for c in changes),
                               chord_notes_removed=sum(c['action'] == 'simplified' for c in changes))
        parts.append(part)
    if not parts or not any(part['events'] for part in parts):
        raise ValueError('当前分段和声部没有可演奏的音符。')
    score = deepcopy(parts[0])
    score['mode'] = 'faithful'
    score['settings'].update(mode=settings['mode'], tracks=list(settings['tracks']),
                             transpose=settings['transpose'], max_polyphony=36,
                             segments=edits, chord_alignment_ms=settings['chord_alignment_ms'])
    score['events'] = sorted((event for part in parts for event in part['events']),
                             key=lambda event: (event['at'], event['midi']))
    for field in ('source_notes', 'notes', 'folded', 'dropped', 'merged', 'chord_notes_removed'):
        score['summary'][field] = sum(part['summary'][field] for part in parts)
    score['summary']['seconds'] = (end - start) / settings['speed']
    score['summary']['source_origin_seconds'] = start
    changes = sorted((change for part in parts for change in part['adaptation']['changes']),
                     key=lambda change: (change['source_at'], change['track']))
    count = sum(part['adaptation']['total_changes'] for part in parts)
    score['adaptation'] = dict(changes=changes[:2000], total_changes=count,
                               truncated=count > 2000, voice_octaves={})
    score['warnings'] = list(dict.fromkeys(warning for part in parts for warning in part['warnings']))
    return validate_score(score)
