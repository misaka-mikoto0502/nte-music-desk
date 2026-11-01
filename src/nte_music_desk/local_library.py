"""Local titles and saved transcription shelf; no online catalogs."""
import json
from pathlib import Path


def generated_scores(directory):
    """Saved final MIDI files are the shelf; downloads and diagnostics stay out."""
    directory=Path(directory)
    paths=[]
    for folder,pattern in [('light-transcriptions','*/*_轻量Beta.mid'),('transcriptions','*/*.mid')]:
        for path in (directory/folder).glob(pattern):
            if '.partial.' in path.name or path.name in ('partial.mid','model_raw.mid','model_selected.mid'):
                continue
            try:
                if path.is_file():paths.append((path.stat().st_mtime_ns,path.resolve()))
            except OSError:continue
    return [path for _,path in sorted(paths,key=lambda item:(item[0],str(item[1])),reverse=True)]


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
