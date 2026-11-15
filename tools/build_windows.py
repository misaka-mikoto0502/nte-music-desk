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
import tempfile
import re

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from nte_music_desk import __version__
from tools.check_release import check_release


def running_windows_images():
    """Read image paths with limited query rights, including elevated workers."""
    import ctypes as c
    from ctypes import wintypes as w
    kernel = c.WinDLL('kernel32', use_last_error=True)
    psapi = c.WinDLL('psapi', use_last_error=True)
    psapi.EnumProcesses.argtypes = [c.POINTER(w.DWORD), w.DWORD, c.POINTER(w.DWORD)]
    psapi.EnumProcesses.restype = w.BOOL
    kernel.OpenProcess.argtypes = [w.DWORD, w.BOOL, w.DWORD]; kernel.OpenProcess.restype = w.HANDLE
    kernel.QueryFullProcessImageNameW.argtypes = [w.HANDLE, w.DWORD, w.LPWSTR, c.POINTER(w.DWORD)]
    kernel.QueryFullProcessImageNameW.restype = w.BOOL
    kernel.CloseHandle.argtypes = [w.HANDLE]
    count = 1024
    while True:
        processes = (w.DWORD * count)(); used = w.DWORD()
        if not psapi.EnumProcesses(processes, c.sizeof(processes), c.byref(used)):
            raise c.WinError(c.get_last_error())
        if used.value < c.sizeof(processes): break
        count *= 2
    for pid in processes[:used.value // c.sizeof(w.DWORD)]:
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle: continue
        try:
            name = c.create_unicode_buffer(32768); size = w.DWORD(len(name))
            if kernel.QueryFullProcessImageNameW(handle, 0, name, c.byref(size)):
                yield Path(name.value).resolve()
        finally:
            kernel.CloseHandle(handle)


def require_inactive_output(output):
    if sys.platform != 'win32': return
    application = (output / '异环演奏工作台').resolve()
    running = [path for path in running_windows_images() if path.is_relative_to(application)]
    if running:
        raise RuntimeError('输出目录仍有工作台或转谱进程运行，请先正常关闭，或使用临时 --output。'
                           '\n' + '\n'.join(map(str, sorted(set(running)))))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / f"releases/v{__version__}")
    parser.add_argument("--work", type=Path, default=ROOT / ".build/cache/package")
    parser.add_argument("--overwrite", action="store_true", help="Explicitly replace an existing same-version archive")
    parser.add_argument('--label', default='', help='Optional preview label; never overwrites a published version')
    args = parser.parse_args()
    if args.label and not re.fullmatch('[a-z0-9][a-z0-9-]{0,40}', args.label):parser.error('Use a short lowercase ASCII preview label.')
    if sys.platform != "win32":
        parser.error("Windows packages must be built on Windows.")
    output, work = args.output.resolve(), args.work.resolve()
    # Must precede PyInstaller --noconfirm: rmtree can partly remove resources
    # before it encounters the running EXE/DLL and fails on Windows.
    require_inactive_output(output)
    check_release(ROOT)
    from nte_music_desk.offline_audio import verify_bundle
    offline = ROOT / 'src/nte_music_desk/assets/offline_audio'
    manifest = verify_bundle(offline, hashes=True)
    for key, relative in [('native_source_sha256','tools/offline_audio/main.cpp'),('native_build_sha256','tools/offline_audio/CMakeLists.txt'),
                          ('resource_spec_sha256','tools/offline_audio/resources.json'),('recipe_sha256','tools/prepare_offline_audio.py')]:
        if manifest.get(key) != hashlib.sha256((ROOT/relative).read_bytes()).hexdigest():
            parser.error('Offline runtime is stale. Run python tools/prepare_offline_audio.py before building.')
    spec = json.loads((ROOT / 'tools/offline_audio/resources.json').read_text(encoding='utf-8'))
    approved_models = {model['file'] for model in spec['models']}
    approved_models.update('models/game/' + model['file'] for model in spec['vocal_model']['files'])
    approved_models.add('models/game/verified.json')
    actual_models = {path.relative_to(offline).as_posix() for path in (offline / 'models').rglob('*') if path.is_file()}
    if actual_models != approved_models:
        parser.error('Bundled model files differ from the fixed resource list: ' +
                     ', '.join(sorted(actual_models ^ approved_models)))
    label = '-' + args.label if args.label else ''
    archive = output / f"NTE-Music-Desk-v{__version__}{label}-Windows-x64.zip"
    if archive.exists() and not args.overwrite:
        parser.error("Archive already exists; choose a new --output or explicitly use --overwrite.")
    output.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    # Never copy bytecode caches from local audio-engine checks into the app.
    # Use a fresh staging folder so removed resources cannot survive a rebuild.
    with tempfile.TemporaryDirectory(prefix='resources-', dir=work) as stage:
        resources = Path(stage) / 'assets'
        shutil.copytree(ROOT / 'src/nte_music_desk/assets', resources,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo'))
        subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onedir", "--windowed",
                        "--noupx", "--name", "异环演奏工作台", "--distpath", str(output), "--workpath", str(work / "pyinstaller"),
                        "--specpath", str(work), "--paths", str(ROOT / "src"),
                        "--add-data", f"{resources}:nte_music_desk/assets",
                        "--icon", str(ROOT / "src/nte_music_desk/assets/icon.ico"),
                        "--manifest", str(ROOT / "tools/windows.manifest"),
                        "--version-file", str(ROOT / "tools/version_info.txt"),
                        str(ROOT / "src/nte_music_desk/_bootstrap.py")], check=True, cwd=ROOT)
    app = output / "异环演奏工作台"
    if args.label:
        (app/'build-info.json').write_text(json.dumps({'version':__version__, 'label':args.label, 'preview':True}),encoding='utf-8')
    # App-local CRT satisfies NumPy/ONNX without asking users to install a
    # redistributable or depending on an older Conda DLL beside Python.
    for library in (offline / 'vc-runtime').glob('*.dll'):
        shutil.copy2(library, app / '_internal' / library.name)
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
    pillow = importlib.metadata.distribution('Pillow')
    for file in pillow.files or []:
        if '/licenses/' in str(file).replace('\\', '/'):
            source = pillow.locate_file(file)
            if source.is_file():
                shutil.copyfile(source, licenses / ('Pillow_' + str(file).replace('\\', '_').replace('/', '_')))
    for package in ('numpy', 'onnxruntime'):
        distribution = importlib.metadata.distribution(package)
        for file in distribution.files or []:
            if '/licenses/' in str(file).replace('\\', '/') or Path(str(file)).name.lower().startswith(('license', 'thirdpartynotice', 'copying')):
                source = distribution.locate_file(file)
                if source.is_file():shutil.copy2(source, licenses / (package + '_' + Path(str(file)).name))
    for filename in ("LICENSE", "THIRD_PARTY_NOTICES.md"):
        shutil.copyfile(ROOT / filename, app / filename)
    shutil.copyfile(ROOT / "docs/USAGE.md", app / "使用说明.md")
    (app / "开始使用.txt").write_text(
        f"异环演奏工作台 v{__version__}\n\n双击“异环演奏工作台.exe”打开，无需安装 Python。\n"
        "请完整解压并保留 _internal 文件夹。\n导入音乐（点击或拖入）→ 选择游戏乐器与方案 → 试听／原谱对照 → 进度定位 → 开始演奏。\n"
        "本地音频转谱已包含钢琴／歌曲模型、CPU 运行库与解码器；首次使用也无需联网、安装 Python、CUDA 或 WebView2。\n"
        "本地转谱可点击“后台运行”，继续用主窗或演奏小窗；从“导入音乐”下方查看转谱进度或结果。后台完成只加入曲目列表；关闭转谱窗口会取消任务。\n"
        "为什么需要管理员权限：自动演奏通过 Windows 接口模拟按键；游戏以管理员权限运行时，普通权限工具的输入可能被系统权限隔离限制。\n"
        "当前版本在打开主界面前统一请求一次 UAC，由用户手动确认；取消则不启动主界面。授权作用于整个程序，演奏、音频处理等子进程也会继承权限。\n"
        "读谱、音频转谱和本地试听本身不需要管理员权限；命令行分析、转换与离线自检可普通权限运行。详细说明见“使用说明.md”的“管理员权限说明”。\n"
        "顶部“迷你播放器”或 F6 隐藏/显示演奏小窗，F7 暂停/继续，F8 停止。\n"
        "点击“开始演奏”后自动聚焦游戏并显示迷你播放器，无需手动打开；小窗不抢游戏焦点。录制时按 F6 隐藏小窗，再按一次恢复。切出游戏自动停止。\n"
        "小窗可拖动明音头像定位进度，点击曲名展开列表换曲；演奏中换曲先停止旧曲再播放，暂停或空闲时只载入。拖动顶部标识栏移动小窗。\n"
        "个人数据在 %LOCALAPPDATA%\\NteMusicDesk；可从“帮助 → 打开数据目录”查看。\n", encoding="utf-8")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for path in sorted(app.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output).as_posix())
    with archive.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    archive.with_suffix(".zip.sha256").write_text(f"{digest}  {archive.name}\n", encoding="ascii")
    print(f"Built {archive} ({archive.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
