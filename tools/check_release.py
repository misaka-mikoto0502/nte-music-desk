"""Check version metadata and bundled help before creating release archives."""
import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def check_release(root=ROOT):
    tree = ast.parse((root / 'src/nte_music_desk/__init__.py').read_text(encoding='utf-8'))
    version = next(ast.literal_eval(node.value) for node in tree.body
                   if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '__version__' for t in node.targets))
    if not re.fullmatch(r'\d+\.\d+\.\d+', version):
        raise ValueError('Release version must be major.minor.patch')
    project = (root / 'pyproject.toml').read_text(encoding='utf-8').split('[project]', 1)[1].split('\n[', 1)[0]
    if re.search(r'^version\s*=\s*"([^"]+)"', project, re.M).group(1) != version:
        raise ValueError('pyproject.toml version differs from application version')
    windows = (root / 'tools/version_info.txt').read_text(encoding='utf-8')
    for field in ('FileVersion', 'ProductVersion'):
        if re.search(r"StringStruct\('" + field + r"',\s*'([^']+)'\)", windows).group(1) != version:
            raise ValueError(f'Windows {field} differs from application version')
    expected = tuple(map(int, version.split('.'))) + (0,)
    for field in ('filevers', 'prodvers'):
        actual = tuple(map(int, re.search(field + r'=\(([^)]+)\)', windows).group(1).split(',')))
        if actual != expected:
            raise ValueError(f'Windows {field} differs from application version')
    if not (root / f'docs/RELEASE_NOTES_{version}.md').is_file():
        raise ValueError('Current release notes are missing')
    for bundled in (root / 'src/nte_music_desk/assets').glob('*.md'):
        original = root / 'docs' / bundled.name
        if not original.is_file() or bundled.read_text(encoding='utf-8') != original.read_text(encoding='utf-8'):
            raise ValueError(f'Bundled help is out of date: {bundled.name}')
    return version


if __name__ == '__main__':
    print(f'Release metadata and bundled help: {check_release()} passed')
