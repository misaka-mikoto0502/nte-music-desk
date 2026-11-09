"""Local titles and saved transcription shelf; no online catalogs."""
import json
from pathlib import Path


def shelf_customizations(preferences):
    """Read display-only names and hidden entries without touching score files."""
    names, hidden = {}, set()
    saved_names = preferences.get('shelf_names', {})
    if isinstance(saved_names, dict):
        for value, title in saved_names.items():
            if not isinstance(value, str) or not value or not isinstance(title, str):continue
            title = ' '.join(title.split())
            if not title or len(title) > 180:continue
            try:names[Path(value).resolve()] = title
            except (OSError, ValueError):continue
    saved_hidden = preferences.get('shelf_hidden', [])
    for value in saved_hidden if isinstance(saved_hidden, list) else []:
        if not isinstance(value, str) or not value:continue
        try:hidden.add(Path(value).resolve())
        except (OSError, ValueError):continue
    return names, hidden


def generated_scores(directory):
    """Saved final MIDI files are the shelf; downloads and diagnostics stay out."""
    directory=Path(directory)
    paths=[]
    for folder,pattern in [('light-transcriptions','*/*_轻量Beta.mid'),('transcriptions','*/*.mid'),('offline-transcriptions','*/*_本地转谱.mid')]:
        for path in (directory/folder).glob(pattern):
            if '.partial.' in path.name or path.name in ('partial.mid','model_raw.mid','model_selected.mid'):
                continue
            try:
                if folder == 'offline-transcriptions':
                    report = json.loads((path.parent / 'result.json').read_text(encoding='utf-8'))
                    if report.get('status') != 'ok' or Path(report.get('midi', '')).resolve() != path.resolve():continue
                if path.is_file():paths.append((path.stat().st_mtime_ns,path.resolve()))
            except (OSError, ValueError, TypeError):continue
    return [path for _,path in sorted(paths,key=lambda item:(item[0],str(item[1])),reverse=True)]


def shelf_entries(directory, imported):
    entries={}
    for item in imported if isinstance(imported,list) else []:
        if not isinstance(item,dict) or not isinstance(item.get('path'),str):continue
        try:
            path=Path(item['path']).resolve()
            if path.is_file():
                title=item.get('title')
                entries[path]=(title[:180] if isinstance(title,str) and title else path.stem,'本地曲谱')
        except (OSError,ValueError):continue
    for path in generated_scores(directory):entries[path]=(entries.get(path,(path.stem,''))[0],'音频识别 · 已保存')
    return [(title,path,caption) for path,(title,caption) in entries.items()]


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
