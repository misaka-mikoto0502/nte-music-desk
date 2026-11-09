"""Prepare the *complete* Windows runtime; only developers run this tool.

Pinned public models, a small CPU host, an audio-only LGPL decoder, sources,
notices and app-local VC runtime. Never download anything from the application.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = json.loads((ROOT / 'tools/offline_audio/resources.json').read_text(encoding='utf-8'))
RES = ROOT / 'src/nte_music_desk/assets/offline_audio'


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for data in iter(lambda: stream.read(1048576), b''): value.update(data)
    return value.hexdigest()


def download(url, path, sha=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file() and (sha is None or digest(path) == sha): return path
    temporary = path.with_name(path.name + '.partial')
    print('Fetch:', path.name, flush=True)
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'NTE-Music-Desk-build'}), timeout=90) as response, temporary.open('wb') as stream:
        while data := response.read(1048576): stream.write(data)
    if sha is not None and digest(temporary) != sha: raise ValueError('Checksum mismatch: ' + path.name)
    temporary.replace(path)
    return path


def checkout(record, destination, archives):
    revision = record['revision']
    if (destination / 'SOURCE_REVISION').is_file():
        if (destination / 'SOURCE_REVISION').read_text().strip() == revision: return destination
        raise ValueError('Source cache has another revision; choose another --work: ' + str(destination))
    archive = download(f"https://codeload.github.com/{record['repo']}/zip/{revision}", archives / (revision + '.zip'))
    with zipfile.ZipFile(archive) as package:
        for entry in package.infolist():
            target = destination.joinpath(*Path(entry.filename).parts[1:]).resolve()
            if not target.is_relative_to(destination.resolve()): raise ValueError('Invalid source archive')
            if entry.is_dir(): target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(package.read(entry))
    (destination / 'SOURCE_REVISION').write_text(revision)
    return destination


def visual_studio(explicit=None):
    if explicit: return explicit.resolve()
    env = os.environ.get('VSINSTALLDIR')
    if env: return Path(env)
    where = Path(os.environ.get('ProgramFiles(x86)', 'C:/Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    if where.is_file():
        value = subprocess.check_output([str(where), '-latest', '-products', '*', '-requires', 'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath'], text=True).strip()
        if value: return Path(value)
    raise RuntimeError('Build machine needs Visual Studio C++ tools (end users do not).')


def build_native(work, vs, source, ggml):
    cmake = vs / 'Common7/IDE/CommonExtensions/Microsoft/CMake/CMake/bin/cmake.exe'
    ninja = vs / 'Common7/IDE/CommonExtensions/Microsoft/CMake/Ninja/ninja.exe'
    if not cmake.is_file() or not ninja.is_file(): raise RuntimeError('Install the Visual Studio CMake component on the build machine.')
    script = work / 'native-audio-build.cmd'
    target = work / 'native-audio'
    script.write_text(f'''@echo off
call "{vs}/VC/Auxiliary/Build/vcvars64.bat" >nul
if errorlevel 1 exit /b 1
"{cmake}" -S "{ROOT}/tools/offline_audio" -B "{target}" -G Ninja -DCMAKE_MAKE_PROGRAM="{ninja}" -DCMAKE_BUILD_TYPE=Release -DMUSCRIPTOR_SOURCE="{source}" -DFETCHCONTENT_SOURCE_DIR_GGML="{ggml}"
if errorlevel 1 exit /b 1
"{cmake}" --build "{target}" --parallel 8
''', encoding='utf-8')
    with (work / 'native-audio-build.log').open('w', encoding='utf-8') as log:
        subprocess.run(['cmd.exe', '/c', str(script)], stdout=log, stderr=subprocess.STDOUT, check=True)
    shutil.copy2(target / 'nte-audio.exe', RES / 'bin/nte-audio.exe')


def decoder_options():
    return ['--target-os=mingw32', '--arch=x86_64', '--disable-x86asm', '--disable-doc', '--disable-debug',
        '--disable-network', '--disable-autodetect', '--disable-everything', '--enable-ffmpeg', '--enable-avcodec',
        '--enable-avformat', '--enable-avutil', '--enable-swresample', '--enable-avfilter', '--enable-protocol=file,pipe',
        '--enable-demuxer=wav,mp3,flac,ogg,mov,aac,asf,matroska,aiff', '--enable-parser=aac,mpegaudio,flac,opus,vorbis',
        '--enable-decoder=aac,aac_fixed,mp3,mp3float,flac,vorbis,opus,wmalossless,wmapro,wmav1,wmav2,alac,pcm_f32le,pcm_f64le,pcm_s16le,pcm_s24le,pcm_s32le,pcm_u8,pcm_s16be,pcm_s24be,pcm_s32be,pcm_f32be,pcm_f64be',
        '--enable-encoder=pcm_f32le,pcm_s16le', '--enable-muxer=pcm_f32le,wav',
        '--enable-filter=aresample,aformat,anull,atrim,asetpts,abuffer,abuffersink', '--extra-ldflags=-static']


def build_decoder(work):
    kit = download(SPEC['decoder_toolchain']['url'], work / 'w64devkit.exe', SPEC['decoder_toolchain']['sha256'])
    if not (work / 'w64devkit/bin/sh.exe').is_file():
        # The vendor SFX extracts next to its executable. No installation or
        # global PATH changes; it is a compiler cache, excluded from all ZIPs.
        subprocess.run([str(kit)], cwd=work, check=True)
    archive = download(SPEC['decoder_source']['url'], work / 'ffmpeg-7.1-source.tar.gz', SPEC['decoder_source']['sha256'])
    source = work / 'ffmpeg-source/FFmpeg-n7.1'
    if not source.is_dir():
        with tarfile.open(archive) as package: package.extractall(source.parent, filter='data')
    target = work / 'minimal-ffmpeg'; target.mkdir(exist_ok=True)
    env = dict(os.environ)
    env.update(PATH=str(work / 'w64devkit/bin') + ';' + env['PATH'], LC_ALL='C', TMPDIR=target.as_posix())
    options = decoder_options()
    recipe = json.dumps(options)
    stamp = target / 'nte-options.json'
    with (work / 'minimal-ffmpeg-build.log').open('a', encoding='utf-8') as log:
        if not stamp.is_file() or stamp.read_text() != recipe:
            subprocess.run([str(work / 'w64devkit/bin/sh.exe'), (source / 'configure').as_posix(), *options], cwd=target, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            stamp.write_text(recipe)
        subprocess.run([str(work / 'w64devkit/bin/make.exe'), '-j8'], cwd=target, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    shutil.copy2(target / 'ffmpeg.exe', RES / 'bin/ffmpeg.exe')
    # Corresponding source and exact configure recipe accompany the decoder;
    # no GPL codecs or external codec libraries are linked into this build.
    shutil.copy2(archive, RES / 'licenses/ffmpeg-7.1-source.tar.gz')
    shutil.copy2(source / 'COPYING.LGPLv2.1', RES / 'licenses/FFmpeg-LGPL-2.1.txt')
    shutil.copy2(work / 'w64devkit/COPYING.MinGW-w64-runtime.txt', RES / 'licenses/MinGW-w64-runtime.txt')
    (RES / 'licenses/FFmpeg-build.json').write_text(json.dumps({'source': SPEC['decoder_source'], 'compiler': SPEC['decoder_toolchain'], 'configure': options, 'make': '-j8', 'linking': 'static; users may modify and relink the LGPL component'}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, default=ROOT / '.build/cache')
    parser.add_argument('--vs-root', type=Path)
    parser.add_argument('--reuse-decoder', action='store_true', help='Reuse the previously verified identical decoder and its corresponding source')
    args = parser.parse_args()
    if sys.platform != 'win32': parser.error('Prepare the portable runtime on Windows.')
    work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    for folder in ('bin', 'licenses', 'vc-runtime'): (RES / folder).mkdir(parents=True, exist_ok=True)
    for model in SPEC['models']: download(model['url'], RES / model['file'], model['sha256'])
    vocal = SPEC['vocal_model']
    archive = download(vocal['url'], work / 'GAME-1.0.3-small-onnx.zip', vocal['sha256'])
    with zipfile.ZipFile(archive) as package:
        for item in vocal['files']:
            target = RES / 'models/game' / item['file']; target.parent.mkdir(parents=True, exist_ok=True)
            if not target.is_file() or digest(target) != item['sha256']:
                data = package.read('GAME-1.0.3-small-onnx/' + item['file'])
                if hashlib.sha256(data).hexdigest() != item['sha256']: raise ValueError('GAME component mismatch')
                target.write_bytes(data)
    native = checkout(SPEC['sources']['muscriptor'], work / 'vendor-muscriptor.cpp-http', work / 'offline-source-archives')
    ggml = checkout(SPEC['sources']['ggml'], work / 'vendor-ggml-http', work / 'offline-source-archives')
    vs = visual_studio(args.vs_root)
    build_native(work, vs, native, ggml)
    if args.reuse_decoder:
        old = json.loads((RES / 'manifest.json').read_text(encoding='utf-8'))
        for record in old['files']:
            if record['file'].startswith('licenses/FFmpeg') or record['file'] in ('bin/ffmpeg.exe', 'licenses/ffmpeg-7.1-source.tar.gz', 'licenses/MinGW-w64-runtime.txt'):
                path = RES / record['file']
                if not path.is_file() or digest(path) != record['sha256']:
                    raise ValueError('Existing decoder changed: ' + record['file'])
        recipe = json.loads((RES / 'licenses/FFmpeg-build.json').read_text())
        if recipe['source'] != SPEC['decoder_source'] or recipe['compiler'] != SPEC['decoder_toolchain'] or recipe['configure'] != decoder_options():
            raise ValueError('Decoder recipe changed; rebuild without --reuse-decoder')
    else:
        build_decoder(work)
    notices = RES / 'licenses'
    shutil.copy2(native / 'LICENSE', notices / 'muscriptor.cpp-MIT.txt')
    shutil.copy2(ggml / 'LICENSE', notices / 'ggml-MIT.txt')
    pffft = (native / 'cpp/third_party/pffft/pffft.c').read_text()
    (notices / 'pffft.txt').write_text(pffft.split('*/', 1)[0] + '*/\n')
    adapter = SPEC['sources']['transkun_adapter']
    base = f"https://raw.githubusercontent.com/{adapter['repo']}/{adapter['revision']}/"
    download(base + 'UNLICENSE', notices / 'audio-claudio-Unlicense.txt')
    download(base + 'fixtures/models/transkun/LICENSE.transkun', notices / 'Transkun-MIT.txt')
    modelbase = 'https://huggingface.co/DamRsn/muscriptor-gguf/resolve/d7045f94e8b19427f4ff9542975035e66596e51c/'
    download(modelbase + 'LICENSE', notices / 'MuScriptor-CC-BY-NC-4.0.txt')
    download(modelbase + 'NOTICE.md', notices / 'MuScriptor-NOTICE.md')
    download(modelbase + 'README.md', notices / 'MuScriptor-model-card.md')
    download('https://huggingface.co/TuesdayCrowd/transkun-onnx/resolve/b44598166715a50d863973a8ecbbdbbb392f08d6/README.md', notices / 'Transkun-model-card.md')
    download('https://creativecommons.org/licenses/by-nc-sa/4.0/legalcode.txt', notices / 'GAME-CC-BY-NC-SA-4.0.txt')
    download('https://raw.githubusercontent.com/openvpi/GAME/v1.0.3/LICENSE', notices / 'GAME-code-MIT.txt')
    (notices / 'GAME-NOTICE.txt').write_text('GAME 1.0.3 small ONNX, OpenVPI contributors. Weights unmodified, CC BY-NC-SA 4.0.\nhttps://github.com/openvpi/GAME/releases/tag/v1.0.0\nhttps://github.com/openvpi/GAME/releases/tag/v1.0.3\nAdapter uses the documented ONNX module workflow.\n')
    redists = sorted((vs / 'VC/Redist/MSVC').glob('14.*/x64/Microsoft.VC143.CRT'), reverse=True)
    if not redists: raise RuntimeError('App-local Visual C++ runtime not found.')
    for library in redists[0].glob('*.dll'): shutil.copy2(library, RES / 'vc-runtime' / library.name)
    (notices / 'Microsoft-VC-runtime.txt').write_text('Microsoft Visual C++ Redistributable, supplied under the Microsoft Visual Studio distributable-code terms.\nhttps://learn.microsoft.com/visualstudio/releases/2022/redistribution\n')
    (notices / 'README.txt').write_text('Offline CPU engines: Transkun 2 ONNX (MIT; export by TuesdayCrowd), MuScriptor small (Mirelo/Kyutai; GGUF by Damien Ronssin; CC BY-NC 4.0 with upstream conditions).\nMuScriptor weights are non-commercial; the application MIT licence does not replace model terms.\nNo model weights are modified or retrained. FFmpeg 7.1 is an audio-only, network-disabled LGPL build; source and relinking recipe are included.\n')
    files = [{'file': p.relative_to(RES).as_posix(), 'bytes': p.stat().st_size, 'sha256': digest(p)} for p in sorted(RES.rglob('*')) if p.is_file() and p.name != 'manifest.json']
    manifest = {'schema': 1, 'sources': SPEC, 'files': files, 'recipe_sha256': digest(Path(__file__)),
                'native_source_sha256': digest(ROOT / 'tools/offline_audio/main.cpp'),
                'native_build_sha256': digest(ROOT / 'tools/offline_audio/CMakeLists.txt'),
                'resource_spec_sha256': digest(ROOT / 'tools/offline_audio/resources.json'), 'network': False,
                'cpu': 'Windows x64, AVX and F16C; hardware F16 conversion; CPU only; no CUDA or WebView2 required'}
    (RES / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(f'Complete offline resources: {sum(f["bytes"] for f in files):,} bytes', flush=True)


if __name__ == '__main__': main()
