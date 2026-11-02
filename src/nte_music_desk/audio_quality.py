"""One-to-one pitch/onset comparison for known MIDI references, not listening scores."""
from collections import defaultdict
import math
import statistics


def compare_notes(reference, prediction, tolerance=.1):
    if type(tolerance) not in (int,float) or not math.isfinite(tolerance) or not 0<tolerance<=1:
        raise ValueError('起音容差需大于 0 且不超过 1 秒。')
    groups=[]
    for song in (reference,prediction):
        grouped=defaultdict(list)
        for note in song.notes:
            if note.channel!=9:grouped[note.pitch].append(note)
        for notes in grouped.values():notes.sort(key=lambda n:n.start)
        groups.append(grouped)
    truth,detected=groups
    matched=0;onsets=[];offsets=[]
    for pitch,notes in truth.items():
        guesses=detected[pitch];i=j=0
        # Sorted equal-width time windows admit monotone one-to-one matching.
        # A predicted duplicate cannot match the same reference note twice.
        while i<len(notes) and j<len(guesses):
            delta=guesses[j].start-notes[i].start
            if delta < -tolerance-1e-9:j+=1
            elif delta > tolerance+1e-9:i+=1
            else:
                matched+=1;onsets.append(abs(delta));offsets.append(abs(guesses[j].end-notes[i].end))
                i+=1;j+=1
    count_truth=sum(map(len,truth.values()));count_detected=sum(map(len,detected.values()))
    precision=matched/count_detected if count_detected else 0
    recall=matched/count_truth if count_truth else 0
    return {'metric':'exact MIDI pitch and onset, one-to-one; drums excluded',
        'onset_tolerance_seconds':tolerance,'reference_notes':count_truth,'predicted_notes':count_detected,
        'matched_notes':matched,'missed_notes':count_truth-matched,'extra_notes':count_detected-matched,
        'precision':precision,'recall':recall,'onset_pitch_f1':2*precision*recall/(precision+recall) if precision+recall else 0,
        'median_absolute_onset_error_seconds':statistics.median(onsets) if onsets else None,
        'median_absolute_offset_error_seconds':statistics.median(offsets) if offsets else None,
        'limitations':'Known-reference note matching only; does not measure timbre, separation, game sound or subjective fidelity.'}
