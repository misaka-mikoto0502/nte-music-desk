"""Explainable arrangement candidates, using existing conversion rules."""
from __future__ import annotations

from .midi import convert, note_name
from .instruments import get_instrument


def adaptation_metrics(score):
    events, summary = score["events"], score["summary"]
    collisions = summary.get("merged", max(0, summary["source_notes"] - summary["chord_notes_removed"] - summary["dropped"] - len(events)))
    skyline = []
    groups = []
    for event in events:
        if not groups or event["at"] - groups[-1][0]["at"] > max(.000001, score.get('settings', {}).get('onset_group_ms', 25) / 1000):
            groups.append([event])
        else:
            groups[-1].append(event)
    for group in groups:
        skyline.append(max(group, key=lambda e: e["source_midi"]))
    reversals, distortion = 0, 0
    for a, b in zip(skyline, skyline[1:]):
        original = b["source_midi"] - a["source_midi"]
        adapted = b["midi"] - a["midi"]
        reversals += original * adapted < 0
        distortion += abs(original - adapted)
    profile = get_instrument(score.get("instrument", "guitar"))
    mixed = sum(len({profile.keys[note_name(e["midi"])].shifted for e in group}) > 1 for group in groups) if profile.id == "piano" else 0
    return {"folded": summary["folded"], "dropped": summary["dropped"], "collisions": collisions,
            "contour_reversals": reversals, "interval_distortion": distortion, "mixed_groups": mixed}


def recommend_transpositions(song, *, tracks=None, mode="melody", speed=1, transpose=0,
                             range_policy="fold", start=0, end=None, instrument="guitar", hold_ms=300,
                             planner=None, limit=3, cancel=None, roles=None, max_polyphony=12):
    candidates = []
    for shift in sorted(set(range(-12, 13)) | {-36, -24, 24, 36, transpose}):
        if cancel is not None and cancel():
            raise ValueError("移调分析已取消。")
        try:
            score = convert(song, tracks, mode, speed, shift, range_policy, start, instrument, end, max_polyphony, roles)
            if planner is not None:
                planner(score, hold_ms)
            metrics = adaptation_metrics(score)
            cost = (metrics["dropped"] * 100 + metrics["collisions"] * 20 + metrics["folded"] * 4
                    + metrics["contour_reversals"] * 8 + metrics["interval_distortion"] / 12
                    + metrics["mixed_groups"] * .15)
            candidates.append({"transpose": shift, **metrics, "cost": cost})
        except ValueError:
            continue
    if not candidates:
        raise ValueError("没有可演奏的移调候选，请先降低速度、减少音轨或调整音域策略。")
    candidates.sort(key=lambda c: (c["cost"], abs(c["transpose"]), c["transpose"]))
    return candidates[:limit]


def adaptation_report(score, plan=None):
    result = {"schema": "nte-adaptation-report-v1", "title": score.get("title", "曲谱"),
            "instrument": score.get("instrument", "guitar"), "mode": score["mode"],
            "settings": dict(score.get("settings", {})), "summary": dict(score["summary"]),
            "metrics": adaptation_metrics(score), "warnings": list(score.get("warnings", [])),
            "changes": score.get("adaptation", {}).get("changes", []),
            "total_changes": score.get("adaptation", {}).get("total_changes", 0),
            "truncated": score.get("adaptation", {}).get("truncated", False),
            "voice_octaves": score.get('adaptation', {}).get('voice_octaves', {}),
            "note": "规则适配结果，不代表听感还原度或游戏实际发声；变更明细最多保存 2000 条，统计为完整计数。"}
    if plan is not None:
        from dataclasses import asdict
        result["performance"] = {"seconds": plan.duration, "planned_notes": len(plan.notes),
                                 "mixed_groups": plan.mixed_groups,
                                 "notes": [asdict(n) for n in plan.notes[:2000]], "truncated": len(plan.notes) > 2000}
        held, peak = set(), 0
        from .instruments import SHIFT
        for _, down, key in plan.key_events:
            if key == SHIFT:
                continue
            if down:
                held.add(key.virtual_key)
            else:
                held.discard(key.virtual_key)
            peak = max(peak, len(held))
        origin = score['summary'].get('source_origin_seconds', 0)
        speed = score.get('settings', {}).get('speed', 1)
        deviations = [abs(n.at - (n.source_at - origin) / speed) * 1000 for n in plan.notes]
        result['performance'].update({'peak_held_keys': peak, 'max_onset_deviation_ms': max(deviations, default=0),
                                      'mean_onset_deviation_ms': sum(deviations) / max(1, len(deviations))})
    return result
