"""Build a windowed Windows portable application; no global Python changes."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
import importlib.metadata
import json

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from nte_music_desk import __version__


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "releases")
    parser.add_argument("--work", type=Path, default=ROOT / ".build")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("Windows packages must be built on Windows.")
    output, work = args.output.resolve(), args.work.resolve()
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
                    "--noupx", "--name", "异环演奏工作台", "--distpath", str(output), "--workpath", str(work / "pyinstaller"),
                    "--specpath", str(work), "--paths", str(ROOT / "src"),
                    "--add-data", f"{ROOT / 'src/nte_music_desk/assets'}:nte_music_desk/assets",
                    "--icon", str(ROOT / "src/nte_music_desk/assets/icon.ico"),
                    "--version-file", str(ROOT / "tools/version_info.txt"),
                    str(ROOT / "src/nte_music_desk/_bootstrap.py")], check=True, cwd=ROOT)
    app = output / "异环演奏工作台"
    licenses = app / "licenses"
    licenses.mkdir(exist_ok=True)
    base = Path(sys.base_prefix)
    candidates = [(base / "LICENSE_PYTHON.txt", "Python.txt"), (base / "LICENSE.txt", "Python-distribution.txt")]
    for root in (base / "tcl", base / "Library/lib"):
        for component in ("tcl8.6", "tk8.6", "tcl8.7", "tk8.7", "tcl9.0", "tk9.0"):
            candidates.append((root / component / "license.terms", component + ".txt"))
    for source, name in candidates:
        if source.is_file():
            shutil.copyfile(source, licenses / name)
    # Conda-based local builds keep component notices in their package cache.
    # Standard python.org builds simply skip this branch.
    components = {"openssl", "tk", "libffi", "bzip2", "xz", "zlib", "expat", "vc", "vs2015_runtime", "ucrt"}
    for metadata in (base / "conda-meta").glob("*.json"):
        record = json.loads(metadata.read_text(encoding="utf-8"))
        if record.get("name") not in components:
            continue
        info = base / "pkgs" / metadata.stem / "info"
        for notice in info.rglob("*"):
            if notice.is_file() and ("license" in notice.name.lower() or "copying" in notice.name.lower()):
                relative = str(notice.relative_to(info)).replace("\\", "_").replace("/", "_")
                shutil.copyfile(notice, licenses / (record["name"] + "_" + relative))
    distribution = importlib.metadata.distribution("pyinstaller")
    for file in distribution.files or []:
        if str(file).replace("\\", "/").endswith("licenses/COPYING.txt"):
            shutil.copyfile(distribution.locate_file(file), licenses / "PyInstaller.txt")
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(ROOT / filename, app / filename)
    shutil.copyfile(ROOT / "docs/USAGE.md", app / "使用说明.md")
    (app / "开始使用.txt").write_text(
        f"异环演奏工作台 v{__version__}\n\n双击“异环演奏工作台.exe”打开，无需安装 Python。\n"
        "请完整解压并保留 _internal 文件夹。\n选曲 → 选择乐器 → 电脑试听 → 游戏试奏 → 完整演奏。\n"
        "F8 停止；切出游戏自动停止。只有游戏演奏需要手动确认 UAC。\n"
        "个人数据在 %LOCALAPPDATA%\\NteMusicDesk；可从“文件 → 打开数据目录”查看。\n", encoding="utf-8")
    archive = output / f"NTE-Music-Desk-v{__version__}-Windows-x64.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Built {archive} ({archive.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
