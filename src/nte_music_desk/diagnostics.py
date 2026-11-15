"""Offline release health check. Never calls any keyboard or elevation API."""
import json
from pathlib import Path
import sys
from . import __version__


def wave_output_available():
    """Hosted Windows runners may have no wave device; report that explicitly."""
    if sys.platform != 'win32':return False
    import ctypes
    winmm=ctypes.WinDLL('winmm')
    winmm.waveOutGetNumDevs.restype=ctypes.c_uint
    return winmm.waveOutGetNumDevs()>0


def run_self_test(engine, destination):
    from .midi import read_midi, convert
    from .ui import App
    import tkinter as tk

    song = read_midi(engine.ASSETS / "scores/twinkle.mid")
    from .notation import read_score
    from .midi import write_midi
    xml_song = read_score(engine.ASSETS / "scores/twinkle.musicxml")
    assert len(xml_song.notes)==len(song.notes)
    roundtrip = engine.ROOT / "self-test-roundtrip.mid"
    write_midi(xml_song,roundtrip)
    assert len(read_midi(roundtrip).notes)==len(song.notes)
    roundtrip.unlink()
    converted = {}
    for instrument in ("guitar", "piano"):
        for mode in ("melody", "chords", "faithful", "balanced"):
            score = convert(song, instrument=instrument, mode=mode)
            plan = engine.key_schedule(score)
            converted[instrument + "/" + mode] = {"notes": len(score["events"]), "key_events": len(plan)}
    preview = engine.ROOT / "self-test-preview.wav"
    engine.render_preview(convert(song), preview, seconds=1)
    assert preview.stat().st_size > 1000
    preview.unlink()
    from .analysis import recommend_transpositions, adaptation_report
    from .performance import performance_plan
    clip = convert(song, start=1, end=3)
    assert clip["summary"]["seconds"] == 2
    assert len(recommend_transpositions(song, planner=engine.key_schedule)) == 3
    assert adaptation_report(clip, performance_plan(clip))["performance"]["planned_notes"] > 0
    engine.render_song_preview(song, preview, start=1, end=3, seconds=1)
    assert preview.stat().st_size > 1000
    preview.unlink()
    original_error = App.show_error
    def fail(self, error):
        raise RuntimeError(str(error))
    App.show_error = fail
    root, app = tk.Tk(), None
    root.withdraw()
    try:
        app = App(root, engine)
        root.update_idletasks()
        assert app.score is not None
        assert app.file_drop is not None, 'Native file-drop target was not registered'
        assert app.file_drop.user32.GetWindowLongPtrW(app.file_drop.hwnd,-20)&0x10
        dpi_aware = bool(app.file_drop.user32.IsProcessDPIAware())
        if getattr(sys, 'frozen', False):
            assert dpi_aware, 'The portable app must declare DPI awareness'
        assert app.mini is not None and app.mini.window.attributes('-topmost')
        assert app.mini.native.user32.GetWindowLongPtrW(app.mini.native.hwnd,-20)&0x08000000
        assert not hasattr(app, 'open_online')
        assert app.heading_canvas.type(app.heading_label.item) == 'text'
        from .appearance import COLORS
        assert len(set(COLORS.values())) == 4
        from .offline_audio import verify_bundle
        offline_resources = None
        if getattr(sys, 'frozen', False) or (engine.ASSETS/'offline_audio/manifest.json').is_file():
            offline_resources = verify_bundle(engine.ASSETS/'offline_audio', hashes=True)
            app.open_offline_audio()
            root.update_idletasks()
            assert app.offline_dialog.profile in ('piano', 'song')
            app.offline_dialog.close()
        app.instrument.set("钢琴 · Shift 黑键")
        app.mode.set("和弦版（最多 6 音）")
        assert app.update_score()["mode"] == "chords"
        app.start.set("1")
        app.end.set("3")
        app.speed.set("0.8")
        assert app.update_score()["summary"]["seconds"] == 2.5
        app.instrument.set("吉他 · 钢琴模式")
        assert float(app.speed.get()) == 1
        app.instrument.set("钢琴 · Shift 黑键")
        assert float(app.speed.get()) == .8 and app.end.get() == '' and float(app.start.get()) == 0
        backup = app.preset_store.path(app.song_fingerprint, 'piano').with_suffix('.excerpt.backup.json')
        assert json.loads(backup.read_text(encoding='utf-8'))['settings']['end'] == 3
        assert app.assets != app.directory
        assert app.open_path(engine.ASSETS / "scores/twinkle.musicxml")
        app.tracks.show_workspace()
        root.update_idletasks()
        assert len(app.tracks.views) == 2 and len(app.tracks.timeline.find_all()) > 0
        from .audio_audition import WaveComparison
        engine.render_song_preview(song,preview,seconds=1)
        comparison=None
        audio_comparison='not_run_no_wave_output_device'
        try:
            if wave_output_available():
                comparison=WaveComparison()
                comparison.switch(preview);comparison.seek(500,playing=False)
                assert abs(comparison.position()-500)<=1 and not comparison.playing
                audio_comparison='passed_silent_open_and_seek'
        finally:
            if comparison:comparison.close()
            preview.unlink(missing_ok=True)
        app.chord_align.set(True);app.update_score(quiet=True)
        assert app.score['settings']['chord_alignment_ms']==24
        assert app.progress_bar.bind('<ButtonPress-1>') and app.mini.progress.bind('<ButtonPress-1>')
        app.seek_fraction(.4)
        position=app.playback_offset()
        assert position>0 and app.preferences['playback_positions'][app.song_fingerprint]>0
        engine.render_preview(app.score,preview,start_at=position,seconds=.1)
        assert preview.stat().st_size>1000
        preview.unlink()
    finally:
        App.show_error = original_error
        if app is not None:
            app.close()
        else:
            root.destroy()
    result = {"status": "passed", "version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
              "music_sources": "local_files_only", "conversion": converted, "musicxml_import_export":"passed", "tk_gui": "passed",
              "arrangement_memory": "passed", "excerpt": "passed", "recommendations": "passed",
              "multitrack_gui": "passed", "audio_comparison": audio_comparison,
              "seek_resume":"passed_saved_position_bindings_and_mid_score_preview; no_game_input",
              "chord_onset_alignment":"passed_setting_and_shared_planner",
              "desktop_file_drop":"passed_native_widget_registration; physical_drag_not_run",
              "mini_player": "passed", "interactive_uac_and_game_overlay": "not_run_requires_user_desktop_test",
              "rounded_controls": "passed", "workspace_palette": "passed_four_colors",
              "dpi_aware": dpi_aware,
              "bundled_offline_audio": 'passed_model_runtime_hashes_and_native_gui' if offline_resources else 'not_staged_source_build',
              "offline_model_inference": 'checked_separately_by_verify_offline_audio',
              "performance_preview": "passed", "game_input_sent": False}
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0
