from pathlib import Path
import tempfile,unittest
from tools.package_source import collect_files,TOP_FILES

class SourcePackageChecks(unittest.TestCase):
    def test_complete_assets_but_no_dependency_cache_or_personal_state(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for name in TOP_FILES:(root/name).write_text('fixture')
            paths=['src/nte_music_desk/assets/audio_window/NteAudioWindow.exe',
                   'tools/audio_window/AudioWindow.cs','tools/light_audio_web/pipeline.js',
                   'tools/light_audio_web/node_modules/vendor/index.js',
                   'src/nte_music_desk/assets/midi_ui_settings.json','tools/.env.local','releases/README.md']
            for name in paths:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'fixture')
            names={p.relative_to(root).as_posix() for p in collect_files(root)}
            self.assertIn('.gitattributes',names)
            self.assertTrue(set(paths[:3]).issubset(names))
            self.assertTrue(set(paths[3:6]).isdisjoint(names))
            (root/'tools/personal.exe').write_bytes(b'not a bundled component')
            with self.assertRaises(ValueError):collect_files(root)
