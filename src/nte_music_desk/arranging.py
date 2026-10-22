"""Voice-preserving reduction. No generated accompaniment or timing quantization."""
from collections import defaultdict


def voice_octaves(notes, low, high, transpose):
    grouped = defaultdict(list)
    for n in notes:
        grouped[n.track].append(n.pitch + transpose)
    result = {}
    for track, pitches in grouped.items():
        def cost(shift):
            moved = [p + shift for p in pitches]
            return (sum(p < low or p > high for p in moved),
                    sum(max(low - p, 0, p - high) for p in moved), abs(shift), shift)
        result[track] = min(range(-48, 49, 12), key=cost)
    return result


def choose_voices(group, budget, roles):
    """Reserve melody and bass before filling harmony; keep distinct pitches."""
    rank = lambda n: (n.velocity, n.end - n.start, n.pitch)
    selected = []
    for role in ('melody', 'bass'):
        candidates = [n for n in group if roles.get(str(n.track)) == role]
        if candidates:
            selected.append(max(candidates, key=rank) if role == 'melody' else min(candidates, key=lambda n: (n.pitch, -n.velocity)))
    if not selected and group:
        selected.append(max(group, key=rank))
    if len(selected) < budget:
        # Keep the lowest anchor even when source instrument metadata is absent.
        bass = min(group, key=lambda n: (n.pitch, -n.velocity))
        if bass not in selected:
            selected.append(bass)
    for note in sorted(group, key=lambda n: (roles.get(str(n.track)) == 'melody', *rank(n)), reverse=True):
        if len(selected) >= budget:
            break
        if note not in selected:
            selected.append(note)
    return selected[:budget]
