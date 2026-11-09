"""Build the small .NET Framework/WebView2 host; never bundle a browser engine."""
from pathlib import Path
import argparse,hashlib,json,subprocess,urllib.request,zipfile
ROOT=Path(__file__).resolve().parents[1]
VERSION='1.0.2903.40'
SDK_SHA256='ef128016dd1e51c59178c827ed5b8aa3322c57afa8675d930f8109505542ad74'

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--sdk',type=Path);args=parser.parse_args()
    cache=ROOT/'.build/cache/webview-sdk';cache.mkdir(parents=True,exist_ok=True)
    sdk=args.sdk or cache/'sdk.nupkg'
    if not sdk.is_file():
        urllib.request.urlretrieve(f'https://api.nuget.org/v3-flatcontainer/microsoft.web.webview2/{VERSION}/microsoft.web.webview2.{VERSION}.nupkg',sdk)
    if hashlib.sha256(sdk.read_bytes()).hexdigest()!=SDK_SHA256:raise ValueError('WebView2 SDK hash mismatch')
    target=ROOT/'src/nte_music_desk/assets/audio_window';target.mkdir(exist_ok=True)
    with zipfile.ZipFile(sdk) as package:
        for source in ['lib/net462/Microsoft.Web.WebView2.Core.dll','lib/net462/Microsoft.Web.WebView2.WinForms.dll','build/native/x64/WebView2Loader.dll','LICENSE.txt','NOTICE.txt']:
            (target/Path(source).name).write_bytes(package.read(source))
    compiler=Path('C:/Windows/Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    subprocess.run([str(compiler),'/nologo','/target:winexe','/platform:x64','/optimize+',
        '/out:'+str(target/'NteAudioWindow.exe'),'/win32icon:'+str(ROOT/'src/nte_music_desk/assets/icon.ico'),
        '/reference:System.dll','/reference:System.Core.dll','/reference:System.Drawing.dll',
        '/reference:System.Windows.Forms.dll','/reference:System.Web.Extensions.dll',
        '/reference:'+str(target/'Microsoft.Web.WebView2.Core.dll'),
        '/reference:'+str(target/'Microsoft.Web.WebView2.WinForms.dll'),str(ROOT/'tools/audio_window/AudioWindow.cs')],check=True)
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in target.iterdir() if p.is_file() and p.name!='manifest.json'}
    source_hash=hashlib.sha256((ROOT/'tools/audio_window/AudioWindow.cs').read_text(encoding='utf-8').encode('utf-8')).hexdigest()
    (target/'manifest.json').write_text(json.dumps({'sdk':VERSION,'sdk_sha256':SDK_SHA256,'source_sha256':source_hash,'files':files},indent=2)+'\n',encoding='utf-8')
    print('Audio window bytes:',sum(p.stat().st_size for p in target.iterdir() if p.is_file()))
if __name__=='__main__':main()
