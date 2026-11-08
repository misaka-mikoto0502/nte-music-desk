"""Exercise reproducible sample workflows in fresh data folders, without game input."""
import argparse
from contextlib import contextmanager
import json
import math
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid
import wave
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from nte_music_desk import cli
from nte_music_desk.analysis import adaptation_report, recommend_transpositions
from nte_music_desk.midi import MidiNote, MidiSong, convert, save_score, validate_score, write_midi
from nte_music_desk.notation import read_score
from nte_music_desk.paths import asset_dir
from nte_music_desk.performance import performance_plan
from nte_music_desk.presets import DEFAULTS, PresetStore, fingerprint


@contextmanager
def desk(directory):
    import tkinter as tk
    from nte_music_desk.ui import App
    directory.mkdir(parents=True, exist_ok=True)
    preferences = directory / 'midi_ui_settings.json'
    if not preferences.exists():
        preferences.write_text('{"mini_player_visible":false}', encoding='utf-8')
    def forbidden(*args, **kwargs):
        raise AssertionError('Workflow checks must never start the game backend')
    engine = SimpleNamespace(ROOT=directory, ASSETS=asset_dir(), key_schedule=cli.key_schedule,
        render_preview=cli.render_preview, render_song_preview=cli.render_song_preview,
        run_playback_and_wait=forbidden)
    root = tk.Tk()
    root.withdraw()
    app = App(root, engine)
    errors = []
    app.show_error = lambda error: errors.append(str(error))
    root.report_callback_exception = lambda kind, error, trace: errors.append(str(error))
    try:
        yield app
        assert not errors, errors
        assert app.active is None
    finally:
        app.close()


def raw_position(app):
    origin, speed, _ = app.position_frame()
    return origin + app.playback_offset() * speed


def wav_seconds(path):
    with wave.open(str(path)) as audio:
        assert audio.getnframes() > 0
        return audio.getnframes() / audio.getframerate()


def samples(output):
    folder = output / 'samples'
    folder.mkdir()
    paths = {'midi': asset_dir() / 'scores/twinkle.mid',
             'musicxml': asset_dir() / 'scores/twinkle.musicxml'}
    paths['mxl'] = folder / 'twinkle.mxl'
    with zipfile.ZipFile(paths['mxl'], 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('META-INF/container.xml', '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>')
        archive.writestr('score.xml', paths['musicxml'].read_bytes())
    notes = [MidiNote(0, 0, p, 90, i, i + .4) for i, p in enumerate((72, 74, 76, 77))]
    notes += [MidiNote(1, 1, p, 70, i * 2, i * 2 + .6, 32) for i, p in enumerate((40, 43))]
    notes += [MidiNote(2, 2, p, 65, i * 2, i * 2 + .5) for i in range(2) for p in (48, 52, 55)]
    notes += [MidiNote(3, 9, 36, 100, 0, .1)]
    paths['multitrack'] = folder / 'lead-bass-chords-drums.mid'
    write_midi(MidiSong('sample', 1, 480, notes, ['lead', 'bass', 'chords', 'drums'], [], 4, []), paths['multitrack'])
    return paths


def conversion_matrix(paths, output):
    folder = output / 'scores'
    folder.mkdir()
    rows = []
    for name, path in paths.items():
        song = read_score(path)
        tracks = [part['index'] for part in song.track_info() if not part['drums']]
        for instrument in ('guitar', 'piano'):
            for mode in ('faithful', 'balanced', 'melody', 'chords'):
                reference = convert(song, tracks=tracks, instrument=instrument, mode=mode)
                for speed in (.5, 1, 1.5):
                    score = convert(song, tracks=tracks, instrument=instrument, mode=mode, speed=speed)
                    plan = performance_plan(score)
                    assert math.isclose(score['summary']['seconds'], reference['summary']['seconds'] / speed, abs_tol=1e-5)
                    summary = score['summary']
                    assert summary['source_notes'] == sum(summary[key] for key in ('notes', 'chord_notes_removed', 'dropped', 'merged'))
                    assert len(plan.notes) == summary['notes']
                    assert all(event['source_track'] in tracks for event in score['events'])
                    target = folder / f'{name}-{instrument}-{mode}-{speed:g}.json'
                    save_score(score, target)
                    validate_score(json.loads(target.read_text(encoding='utf-8')))
                    rows.append({'sample': name, 'instrument': instrument, 'mode': mode,
                        'speed': speed, 'notes': summary['notes'], 'seconds': summary['seconds']})
    return {'configurations': len(rows), 'results': rows}


def import_seek_and_audition(paths, output):
    folder = output / 'desk'
    with desk(folder) as app:
        for path in paths.values():
            assert app.import_local_file(path)
            assert app.score is not None
        assert app.file_drop.hwnd == app.import_button.winfo_id()
        assert app.drop_zone is app.import_button
        assert app.import_local_file(paths['midi'])
        app.seek_fraction(.5)
        original = raw_position(app)
        app.speed.set('.5')
        app.update_score()
        assert math.isclose(raw_position(app), original, abs_tol=1e-5)
        app.source_preview_button.invoke()
        message = app.messages.get(timeout=15)
        assert message['kind'] == 'preview_ready', message
        source_wav = output / 'source-comparison.wav'
        source_wav.write_bytes(message['path'].read_bytes())
        source_seconds = wav_seconds(source_wav)
        assert math.isclose(app.preview_origin, original, abs_tol=1e-5)
        app.stop_button.invoke()
        app.preview_button.invoke()
        message = app.messages.get(timeout=15)
        assert message['kind'] == 'preview_ready', message
        adapted_wav = output / 'adapted-comparison.wav'
        adapted_wav.write_bytes(message['path'].read_bytes())
        adapted_seconds = wav_seconds(adapted_wav)
        assert source_wav.read_bytes() != adapted_wav.read_bytes()
        app.stop_button.invoke()
    with desk(folder) as app:
        assert math.isclose(raw_position(app), original, abs_tol=1e-5)
        assert float(app.speed.get()) == .5
    return {'imported_formats': list(paths), 'resume_source_seconds': original,
            'speed_after_restart': .5, 'source_wav_seconds': source_seconds,
            'adapted_wav_seconds': adapted_seconds, 'audition_outputs': 'distinct_source_and_adapted_wavs',
            'native_drop_widget': 'shared_with_import_button'}


def legacy_and_invalid_settings(paths, output):
    folder = output / 'legacy'
    store = PresetStore(folder)
    digest = fingerprint(paths['midi'])
    settings = {**DEFAULTS, 'tracks': [0], 'mode': 'faithful', 'start': 2, 'end': 9, 'speed': .75}
    store.save(digest, 'guitar', settings)
    original = store.path(digest, 'guitar').read_bytes()
    with desk(folder) as app:
        assert app.start.get() in ('0', '0.0') and app.end.get() == ''
        assert float(app.speed.get()) == .75
        assert math.isclose(raw_position(app), 2, abs_tol=1e-5)
        backup = store.path(digest, 'guitar').with_suffix('.excerpt.backup.json')
        assert backup.read_bytes() == original
        usable = store.path(digest, 'guitar').read_bytes()
        for value in ('', '-', 'abc', 'nan', 'inf', '0', '2.01', '.24'):
            app.speed.set(value)
            assert app.update_score(quiet=True) is None, value
            assert store.path(digest, 'guitar').read_bytes() == usable
        app.speed.set('.75')
        assert app.update_score() is not None
        assert backup.read_bytes() == original
    return {'legacy_range': [2, 9], 'new_range': 'full_song', 'resume_source_seconds': 2,
            'backup': 'byte_identical', 'invalid_speed_inputs_rejected': 8, 'valid_preset': 'preserved'}


def recommendations(output):
    song = MidiSong('only +17 fits', 0, 480,
        [MidiNote(0, 0, 35, 80, 0, .5), MidiNote(0, 0, 70, 80, 1, 1.5)], ['lead'], [], 2, [])
    wide = recommend_transpositions(song, mode='faithful', range_policy='strict')
    assert [candidate['transpose'] for candidate in wide] == [17]
    close = MidiSong('shift transition', 0, 480,
        [MidiNote(0, 0, 60, 80, 0, 1), MidiNote(0, 0, 61, 80, .02, 1.02)], ['lead'], [], 2, [])
    candidates = recommend_transpositions(close, mode='faithful', instrument='piano', limit=73)
    current = next(candidate for candidate in candidates if candidate['transpose'] == 0)
    assert candidates[0]['max_timing_adjustment_ms'] < current['max_timing_adjustment_ms']
    return {'strict_range_candidate': wide[0]['transpose'], 'piano_preferred_shift': candidates[0]['transpose'],
            'current_delay_ms': current['max_timing_adjustment_ms'], 'preferred_delay_ms': candidates[0]['max_timing_adjustment_ms']}


def timeline_report(output):
    from nte_music_desk.ui import position_label
    song = MidiSong('late notes', 0, 480,
        [MidiNote(0, 0, 30, 80, 180, 181), MidiNote(0, 0, 60, 80, 199, 200)], ['lead'], [], 200, [])
    score = convert(song, mode='faithful')
    report = adaptation_report(score, performance_plan(score))
    assert report['timeline']['source_seconds'] == 200
    assert report['timeline']['performance_seconds'] == 20
    assert report['changes'][0]['source_at'] == 180
    assert position_label(report['changes'][0]['source_at']) == '03:00.000'
    (output / 'timeline-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'source_total': '03:20', 'performance_total': '00:20', 'first_change': '03:00.000', 'json_source_seconds': 180}


def real_audio_handoff(audio, expected, output, reference=None):
    from nte_music_desk.audio_window import verify_host
    from nte_music_desk.light_audio import LightAudioSession
    folder = output / 'real-audio'
    with desk(folder) as app:
        session = app.light_audio = LightAudioSession(folder, app.messages.put)
        session.select_desktop_audio(audio)
        report = folder / 'host.json'
        process = subprocess.Popen([str(verify_host(asset_dir() / 'audio_window')), session.url,
            str(folder / 'profile'), str(report), '--diagnostic', 'polyphonic', '0'], stdin=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 60
            while process.poll() is None and time.monotonic() < deadline:
                app.root.update()
                time.sleep(.02)
            if process.poll() is None:
                raise TimeoutError('Native audio sample exceeded 60 seconds')
            result = json.loads(report.read_text(encoding='utf-8-sig'))
            assert result['state'] == 'diagnostic', result
            deadline = time.monotonic() + 3
            while (app.current_path != session.result or not app.messages.empty()) and time.monotonic() < deadline:
                app.root.update()
                time.sleep(.02)
            assert app.current_path == session.result
            assert app.song.notes
            if expected is not None:
                assert len(app.song.notes) == expected
            assert session.latest_result['workbench']['state'] == 'loaded'
            assert session.result.read_bytes() == Path(result['download']).read_bytes()
            evidence = {'notes': len(app.song.notes), 'saved_midi_matches_download': True,
                'workbench': 'loaded_without_manual_import', 'layout_cases': len(result['layout'])}
            if reference is not None:
                from nte_music_desk.audio_quality import compare_notes
                evidence['reference_comparison'] = compare_notes(read_score(reference), app.song, tolerance=.1)
            return evidence
        finally:
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            process.stdin.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / '.build' / ('workflow-check-' + uuid.uuid4().hex[:8]))
    parser.add_argument('--audio', type=Path, help='Optional local synthetic WAV for real WebView2 inference and workbench handoff')
    parser.add_argument('--expected-notes', type=int, help='Optional model regression count, not an accuracy score')
    parser.add_argument('--reference-midi', type=Path, help='Known matching reference; report pitch/onset quality separately')
    args = parser.parse_args()
    if args.reference_midi and not args.audio:
        parser.error('--reference-midi requires --audio')
    if sys.platform != 'win32':
        parser.error('Native workflow checks require Windows with Tcl/Tk')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    paths = samples(output)
    cases = [('conversion_matrix', lambda: conversion_matrix(paths, output)),
             ('import_seek_and_audition', lambda: import_seek_and_audition(paths, output)),
             ('legacy_and_invalid_settings', lambda: legacy_and_invalid_settings(paths, output)),
             ('recommendations', lambda: recommendations(output)), ('timeline_report', lambda: timeline_report(output))]
    if args.audio:
        cases.append(('real_audio_handoff', lambda: real_audio_handoff(args.audio.resolve(), args.expected_notes,
            output, args.reference_midi.resolve() if args.reference_midi else None)))
    report = {'schema': 'nte-workflow-check-v1', 'game_input_sent': False, 'cases': {}}
    for name, check in cases:
        try:
            report['cases'][name] = {'status': 'passed', **check()}
        except Exception as error:
            import traceback
            report['cases'][name] = {'status': 'failed', 'error': str(error), 'traceback': traceback.format_exc()}
        print(name + ': ' + report['cases'][name]['status'], flush=True)
    report['status'] = 'passed' if all(case['status'] == 'passed' for case in report['cases'].values()) else 'failed'
    destination = output / 'report.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(str(destination), flush=True)
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    sys.exit(main())
