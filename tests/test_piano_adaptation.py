"""Game-key constraints using synthetic music; no game input or model inference."""
import copy
from dataclasses import replace
import random
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from nte_music_desk.analysis import adaptation_report, recommend_transpositions
from nte_music_desk.instruments import SHIFT, get_instrument
from nte_music_desk.midi import MidiNote, MidiSong, convert, note_name
from nte_music_desk.performance import PianoDensityError, performance_plan


def score_for(attacks, mode='faithful', speed=1):
    notes = [MidiNote(0, 0, pitch, 80, at, at + .3) for at, pitch in attacks]
    song = MidiSong('synthetic', 1, 480, notes, ['piano'], [(0, 500000)],
                   max(n.end for n in notes), [])
    return convert(song, mode=mode, instrument='piano', speed=speed)


class PianoAdaptationChecks(unittest.TestCase):
    def assert_safe(self, plan):
        held, released, shifted, changed = {}, {}, False, -float('inf')
        expected = iter(plan.notes)
        # Independent checks of modifier, note pitch, hold and retrigger gaps.
        for at, down, key in plan.key_events:
            if key == SHIFT:
                self.assertFalse(held)
                shifted, changed = bool(down), at
            elif down:
                self.assertNotIn(key.virtual_key, held)
                self.assertGreaterEqual(at - released.get(key.virtual_key, -100), .008 - 1e-9)
                self.assertGreaterEqual(at - changed, .015 - 1e-9)
                held[key.virtual_key] = at
            else:
                self.assertIn(key.virtual_key, held)
                self.assertGreaterEqual(at - held.pop(key.virtual_key), .005 - 1e-9)
                released[key.virtual_key] = at
        self.assertFalse(held)
        self.assertFalse(shifted)
        profile = get_instrument('piano')
        for note in expected:
            key = profile.keys[note_name(note.midi)]
            state = False
            for at, down, event_key in plan.key_events:
                if at > note.at + 1e-9: break
                if event_key == SHIFT: state = bool(down)
            self.assertEqual(state, key.shifted)

    def test_previously_playable_plans_are_identical(self):
        for mode in ('faithful', 'balanced', 'melody', 'chords'):
            score = score_for([(0, 60), (.4, 64), (.8, 61), (1.2, 65)], mode)
            self.assertEqual(performance_plan(score), performance_plan(score, strict=True))
            self.assertFalse(performance_plan(score).auto_adapted)

    def test_dense_alternation_is_local_deterministic_and_does_not_drift(self):
        score = score_for([(i * .001, 60 + i % 2) for i in range(80)] + [(1, 67)])
        before = copy.deepcopy(score)
        with self.assertRaises(PianoDensityError): performance_plan(score, strict=True)
        plan = performance_plan(score)
        self.assertEqual(plan, performance_plan(score))
        self.assertEqual(score, before)
        self.assertTrue(plan.auto_adapted)
        self.assertGreater(plan.pruned_notes, 0)
        self.assertEqual(len(plan.notes) + plan.merged_notes + plan.pruned_notes, len(score['events']))
        self.assertLessEqual(plan.max_timing_adjustment_ms, 50)
        self.assertAlmostEqual(plan.notes[-1].at, 1.02)
        self.assert_safe(plan)

    def test_fold_collisions_merge_but_original_repeated_notes_remain(self):
        score = score_for([(0, 60), (.001, 60), (.2, 64)])
        score['events'][1]['source_midi'] = 48
        # Force fallback with a separate dense run, then inspect the collision.
        tail = score_for([(i * .001, 60 + i % 2) for i in range(20)])
        score['events'] += [{**e, 'at': e['at'] + 1, 'source_at': e['source_at'] + 1} for e in tail['events']]
        plan = performance_plan(score)
        self.assertEqual(plan.merged_notes, 1)
        self.assertEqual(sum(n.source_at < .01 for n in plan.notes), 1)
        score['events'][1]['source_midi'] = 60
        plan = performance_plan(score)
        self.assertEqual(plan.merged_notes, 0)
        self.assertEqual(sum(n.source_at < .01 for n in plan.notes), 2)
        self.assert_safe(plan)

    def test_short_duration_and_all_modes_keep_key_safety(self):
        for mode in ('faithful', 'balanced', 'melody', 'chords'):
            for speed in (.25, 1, 2):
                score = score_for([(i * .001, 60 + i % 12) for i in range(70)], mode, speed)
                score['events'][-1]['duration'] = .0001
                plan = performance_plan(score)
                self.assert_safe(plan)
                self.assertLessEqual(plan.max_timing_adjustment_ms, 50)

    def test_invalid_input_is_not_silently_pruned(self):
        score = score_for([(0, 60), (.01, 61)])
        for field, value in (('midi', 128), ('at', -1), ('duration', float('nan'))):
            invalid = copy.deepcopy(score); invalid['events'][0][field] = value
            with self.assertRaises(ValueError): performance_plan(invalid)
        with self.assertRaises(ValueError): performance_plan(score, hold_ms=1)
        invalid = copy.deepcopy(score); invalid['settings']['max_polyphony'] = 0
        with self.assertRaises(ValueError): performance_plan(invalid)

    def test_report_uses_source_time_and_preserves_score_and_full_counts(self):
        score = score_for([(i * .001, 60 + i % 2) for i in range(100)], speed=2)
        score['settings']['transpose'] = 2
        for e in score['events']: e['source_at'] += 20
        score['summary']['source_origin_seconds'] += 20
        before = copy.deepcopy(score)
        plan = performance_plan(score)
        report = adaptation_report(score, plan)
        self.assertEqual(score, before)
        self.assertEqual(report['playability']['planned_notes'], len(plan.notes))
        self.assertEqual(report['playability']['density_pruned'], plan.pruned_notes)
        actions = [c for c in report['changes'] if c['action'] == 'density_pruned']
        self.assertEqual(len(actions), plan.pruned_notes)
        self.assertTrue(all(c['source_at'] >= 20 and c['midi'] is None for c in actions))
        self.assertTrue(all(c['requested_midi'] == c['source_midi'] + 2 for c in actions))
        self.assertEqual(report['total_changes'], score['adaptation']['total_changes'] + plan.adaptation_total_changes)
        large = replace(plan, adaptation_changes=tuple([plan.adaptation_changes[0]] * 2000), adaptation_total_changes=2500)
        report = adaptation_report(score, large)
        self.assertEqual(len(report['changes']), 2000)
        self.assertTrue(report['truncated'])
        self.assertEqual(report['total_changes'], score['adaptation']['total_changes'] + 2500)

    def test_recommendation_accounts_for_notes_lost_to_density(self):
        song = MidiSong('one', 1, 480, [MidiNote(0, 0, 60, 80, 0, 1)], ['piano'], [(0, 500000)], 1, [])
        base = performance_plan(convert(song))
        def planner(score, hold_ms):
            return replace(base, pruned_notes=1 if score['settings']['transpose'] == 0 else 0)
        metrics = dict(folded=0, dropped=0, collisions=0, contour_reversals=0, interval_distortion=0)
        with patch('nte_music_desk.analysis.performance_plan', side_effect=planner), \
                patch('nte_music_desk.analysis.adaptation_metrics', return_value=metrics):
            candidates = recommend_transpositions(song, limit=73)
        self.assertNotEqual(candidates[0]['transpose'], 0)
        self.assertEqual(candidates[-1]['transpose'], 0)

    def test_seeded_dense_scores_remain_valid(self):
        rng = random.Random(20261109)
        for index in range(16):
            attacks, at = [], 0
            for _ in range(150):
                at += rng.choice((.0002, .001, .004, .02, .07))
                attacks.append((at, rng.randrange(48, 83)))
            score = score_for(attacks, ('faithful', 'balanced', 'melody', 'chords')[index % 4])
            if index == 0: score['settings'].pop('max_polyphony')  # Legacy JSON defaults to six voices.
            plan = performance_plan(score)
            self.assert_safe(plan)
            self.assertLessEqual(plan.max_timing_adjustment_ms, 50)
            if index == 0:
                from collections import Counter
                self.assertLessEqual(max(Counter(n.at for n in plan.notes).values()), 6)


if __name__ == '__main__': unittest.main()
