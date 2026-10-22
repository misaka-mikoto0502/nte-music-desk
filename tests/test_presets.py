import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from nte_music_desk.presets import PresetStore, fingerprint, DEFAULTS


class PresetChecks(unittest.TestCase):
    def test_content_identity_instrument_isolation_and_invalid_edits(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "song.mid"
            p.write_bytes(b"first content")
            digest = fingerprint(p)
            store = PresetStore(d)
            settings = {**DEFAULTS, "tracks": [2], "speed": .8, "mode": "chords"}
            store.save(digest, "piano", settings)
            p.rename(Path(d) / "renamed.mid")
            self.assertEqual(fingerprint(Path(d) / "renamed.mid"), digest)
            self.assertEqual(store.load(digest, "piano", [2]), settings)
            self.assertIsNone(store.load(digest, "guitar", [2]))
            self.assertIsNone(store.load("a" * 64, "piano", [2]))
            for bad in (float("nan"), 0, 4):
                with self.assertRaises(ValueError):
                    store.save(digest, "piano", {**settings, "speed": bad})
            self.assertEqual(store.load(digest, "piano", [2]), settings)
            with self.assertRaises(ValueError):
                store.load(digest, "piano", [1])
            data = json.loads(store.path(digest, "piano").read_text(encoding="utf-8"))
            data["schema"] = "future-version"
            store.path(digest, "piano").write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(ValueError):
                store.load(digest, "piano", [2])
