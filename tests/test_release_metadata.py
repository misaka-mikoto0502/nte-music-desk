from pathlib import Path
import shutil
import tempfile
import unittest

from tools.check_release import check_release, ROOT


class ReleaseMetadataChecks(unittest.TestCase):
    def test_repository_release_metadata_and_bundled_help_are_consistent(self):
        self.assertTrue(check_release())

    def test_release_guard_rejects_stale_windows_version_and_help(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            for name in ('src/nte_music_desk/__init__.py', 'pyproject.toml', 'tools/version_info.txt'):
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
            (root / 'docs').mkdir()
            for source in (ROOT / 'docs').glob('RELEASE_NOTES_*.md'):
                shutil.copyfile(source, root / 'docs' / source.name)
            version_file = root / 'tools/version_info.txt'
            original = version_file.read_text(encoding='utf-8')
            version_file.write_text(original.replace("StringStruct('FileVersion', '", "StringStruct('FileVersion', '99."), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'FileVersion'):
                check_release(root)
            version_file.write_text(original, encoding='utf-8')
            (root / 'docs/USAGE.md').write_text('current help', encoding='utf-8')
            (root / 'src/nte_music_desk/assets').mkdir()
            (root / 'src/nte_music_desk/assets/USAGE.md').write_text('old help', encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'USAGE.md'):
                check_release(root)
