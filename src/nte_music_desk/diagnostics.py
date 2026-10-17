"""Offline release health check. Never calls any keyboard or elevation API."""
import json
from pathlib import Path
import sys
from . import __version__


def run_self_test(engine, destination):
    from .catalog import CatalogClient
    from .midi import read_midi, convert
    from .ui import App
    import tkinter as tk

    catalog = CatalogClient(engine.ROOT, resources=engine.ASSETS)
    counts = {source: len(catalog.load(source)[0]) for source in ("bitmidi", "murashin","mutopia")}
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
        for mode in ("melody", "chords"):
            score = convert(song, instrument=instrument, mode=mode)
            plan = engine.key_schedule(score)
            converted[instrument + "/" + mode] = {"notes": len(score["events"]), "key_events": len(plan)}
    preview = engine.ROOT / "self-test-preview.wav"
    engine.render_preview(convert(song), preview, seconds=1)
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
        app.instrument.set("钢琴 · Shift 黑键")
        app.mode.set("和弦版（最多 6 音）")
        assert app.update_score()["mode"] == "chords"
        assert app.assets != app.directory
        assert app.open_path(engine.ASSETS / "scores/twinkle.musicxml")
    finally:
        App.show_error = original_error
        if app is not None:
            app.close()
        else:
            root.destroy()
    result = {"status": "passed", "version": __version__, "frozen": bool(getattr(sys, "frozen", False)),
              "catalogs": counts, "conversion": converted, "musicxml_import_export":"passed", "tk_gui": "passed", "game_input_sent": False}
    destination = Path(destination).resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0
