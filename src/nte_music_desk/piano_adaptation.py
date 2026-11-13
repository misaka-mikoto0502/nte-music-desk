"""Bounded, deterministic game-key adaptation; never edits the source score.

Only used when the exact piano planner cannot satisfy key/Shift safety gaps.
Each attack remains at or after its requested time, with at most 50 ms extra
delay beyond the existing black-key roll. Unresolvable local conflicts are
reduced using source roles, register, velocity and duration.
"""
from collections import deque
from dataclasses import dataclass

from .midi import note_name
from .instruments import score_instrument

MAX_DELAY = .050
REGROUP_WINDOW = .024
LOOKBACK = 8
CHANGE_LIMIT = 2000


@dataclass
class AdaptivePiano:
    batches: list
    merged: int
    pruned: int
    adjusted: int
    max_delay_ms: float
    regrouped: int
    changes: tuple
    total_changes: int


def adapt_piano_batches(score):
    profile = score_instrument(score)
    melody = score['mode'] == 'melody'
    sequential = score['mode'] in ('melody', 'chords')
    limit = 1 if melody else score.get('settings', {}).get('max_polyphony', 6)
    events = [dict(event) for event in score['events']]
    changes = []
    total_changes = merged = pruned = regrouped = 0

    def record(action, event, **detail):
        nonlocal total_changes
        total_changes += 1
        if len(changes) < CHANGE_LIMIT:
            changes.append(dict(action=action, source_at=event.get('source_at', event['at']),
                track=event.get('source_track', -1), source_midi=event.get('source_midi', event['midi']),
                requested_midi=event.get('source_midi', event['midi']) + score.get('settings', {}).get('transpose', 0),
                midi=None if action == 'density_pruned' else event['midi'], **detail))

    # A different original octave may fold onto the same game key. Merge only
    # overlapping attacks too close to retrigger; preserve real repeated notes.
    retained, previous = [], {}
    for event in events:
        prior = previous.get(event['midi'])
        if prior is not None and event.get('source_midi', event['midi']) != prior.get('source_midi', prior['midi']) and \
                0 <= event['at'] - prior['at'] < .013 and prior['at'] + prior['duration'] > event['at']:
            prior['duration'] = max(prior['duration'], event['at'] + event['duration'] - prior['at'])
            prior['velocity'] = max(prior.get('velocity', 80), event.get('velocity', 80))
            merged += 1
            record('key_merged', event, reason='octave_fold_collision', kept_source_at=prior.get('source_at', prior['at']))
        else:
            retained.append(event)
            previous[event['midi']] = event

    # Register anchors are local estimates, supplemented by explicit track roles.
    # Fixed windows do not chain a dense run into one long "chord".
    priorities, group = {}, []
    roles = score.get('settings', {}).get('roles', {})
    def rank_group(items):
        low = min(e.get('source_midi', e['midi']) for e in items)
        high = max(e.get('source_midi', e['midi']) for e in items)
        for e in items:
            pitch = e.get('source_midi', e['midi'])
            role = roles.get(str(e.get('source_track', -1)), '')
            priorities[id(e)] = (100 if role == 'melody' else 30 if role == 'bass' else 0) + \
                30 * (pitch == high) + 20 * (pitch == low) + e.get('velocity', 80) / 127 * 3 + min(e['duration'], 1) * 2
    for event in retained:
        if group and event['at'] - group[0]['at'] > .025:
            rank_group(group); group = []
        group.append(event)
    if group: rank_group(group)

    groups, group = [], []
    window = max(.000001, score.get('settings', {}).get('onset_group_ms', 25) / 1000)
    for event in retained:
        duplicate = any(e['midi'] == event['midi'] for e in group)
        if group and (melody or event['at'] - group[0]['at'] > window or duplicate):
            groups.append(group); group = []
        group.append(event)
    if group: groups.append(group)
    batches, requested = [], {}
    for group in groups:
        parts = []
        for shifted in (False, True):
            part = [(e, profile.keys[note_name(e['midi'])]) for e in group
                    if profile.keys[note_name(e['midi'])].shifted == shifted]
            if part: parts.append((shifted, part))
        for offset, (shifted, part) in enumerate(parts):
            at = group[0]['at'] + .020 + offset * .055
            # Regrouping must never exceed the original per-onset voice budget.
            for start in range(0, len(part), limit):
                chunk = part[start:start + limit]
                batches.append((at, shifted, chunk))
                for e, _ in chunk: requested[id(e)] = at

    if not melody:
        packed, pending = [], {}
        for desired, shifted, part in sorted(batches, key=lambda b: b[0]):
            current = pending.get(shifted)
            keys = {k.virtual_key for _, k in part}
            if current is not None and desired - current['first'] <= REGROUP_WINDOW + 1e-9 and \
                    not (keys & current['keys']) and len(current['part']) + len(part) <= limit:
                current['at'] = desired
                current['part'].extend(part); current['keys'].update(keys)
                regrouped += len(part)
            else:
                current = dict(at=desired, first=desired, shifted=shifted, part=list(part), keys=keys)
                pending[shifted] = current; packed.append(current)
        batches = [(g['at'], g['shifted'], g['part']) for g in packed]
    batches.sort(key=lambda b: b[0])

    def schedule(batch, state):
        desired, shifted, part = batch
        previous_at, previous_shift, last_keys = state
        at = max(desired, previous_at)
        if previous_shift is not None:
            if shifted != previous_shift: at = max(at, previous_at + .030)
            elif sequential: at = max(at, previous_at + .013)
        for _, key in part:
            at = max(at, last_keys.get(key.virtual_key, -float('inf')) + .013)
        if any(at - requested[id(e)] > MAX_DELAY + 1e-9 for e, _ in part): return None
        keys = dict(last_keys)
        for _, key in part: keys[key.virtual_key] = at
        return (at, shifted, part), (at, shifted, keys)

    # Keep a small rollback window. At a conflict, compare local note/group
    # removals and replay only that window; no repeated whole-song conversion.
    history = deque()
    prefix = []
    state = (-float('inf'), None, {})
    for batch in batches:
        result = schedule(batch, state)
        if result is not None:
            placed, after = result
            history.append((batch, state, placed)); state = after
        else:
            recent = [item[0] for item in history] + [batch]
            initial = history[0][1] if history else state
            candidates = []
            singles = sorted(((priorities[id(e)], bi, ni) for bi, (_, _, part) in enumerate(recent)
                              for ni, (e, _) in enumerate(part)), key=lambda x: (x[0], x[1], x[2]))[:16]
            for cost, bi, ni in singles: candidates.append((cost, 1, bi, (ni,)))
            for bi, (_, _, part) in enumerate(recent):
                candidates.append((sum(priorities[id(e)] for e, _ in part), len(part), bi, tuple(range(len(part)))))
            winner = None
            for cost, count, bi, indexes in sorted(candidates, key=lambda c: (c[0], c[1], -c[2], c[3])):
                replay, replay_state = [], initial
                for ri, (desired, shifted, part) in enumerate(recent):
                    keep = [item for i, item in enumerate(part) if ri != bi or i not in indexes]
                    if not keep: continue
                    candidate = (desired, shifted, keep)
                    placed = schedule(candidate, replay_state)
                    if placed is None: break
                    value, after = placed
                    replay.append((candidate, replay_state, value)); replay_state = after
                else:
                    winner = (bi, indexes, replay, replay_state)
                    break
            # Removing the incoming group always leaves the already-valid prefix.
            assert winner is not None, 'Local piano adaptation did not converge'
            bi, indexes, replay, state = winner
            for ni in indexes:
                event = recent[bi][2][ni][0]
                pruned += 1
                record('density_pruned', event, reason='key_timing_conflict')
            history = deque(replay)
        while len(history) > LOOKBACK:
            prefix.append(history.popleft()[2])
    scheduled = prefix + [item[2] for item in history]
    adjusted = 0; maximum = 0
    for at, _, part in scheduled:
        for event, _ in part:
            delay = max(0, at - requested[id(event)])
            if delay > 1e-9:
                adjusted += 1; maximum = max(maximum, delay * 1000)
                record('timing_adjusted', event, delay_ms=round(delay * 1000, 3))
    assert sum(len(part) for _, _, part in scheduled) + merged + pruned == len(events)
    return AdaptivePiano(scheduled, merged, pruned, adjusted, round(maximum, 3), regrouped,
                         tuple(changes), total_changes)
