"""Read legacy local titles without contacting the former online catalogs."""
import json
from pathlib import Path


def local_title(path, directory):
    path, directory = Path(path).resolve(), Path(directory).resolve()
    if path.parent != directory / 'downloaded_midis':
        return None
    try:
        sidecar = path.with_suffix('.source.json')
        if sidecar.stat().st_size > 32768:
            return None
        data = json.loads(sidecar.read_text(encoding='utf-8'))
        if not isinstance(data, dict) or data.get('filename') != path.name:
            return None
        title = data.get('title')
        return title[:180] if isinstance(title, str) and title else None
    except (OSError, ValueError, TypeError):
        return None
