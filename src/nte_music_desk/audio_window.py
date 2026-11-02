"""Small native WebView2 window around the existing local transcription session."""
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import uuid
from urllib.parse import urlsplit


def verify_host(folder):
    folder=Path(folder)
    manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
    required={'NteAudioWindow.exe','Microsoft.Web.WebView2.Core.dll','Microsoft.Web.WebView2.WinForms.dll','WebView2Loader.dll','LICENSE.txt','NOTICE.txt'}
    files=manifest.get('files',{})
    if set(files)!=required:raise ValueError('桌面转谱组件清单无效，请重新完整解压。')
    for name,digest in files.items():
        if hashlib.sha256((folder/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('桌面转谱组件校验失败，请重新完整解压。')
    return folder/'NteAudioWindow.exe'


class DesktopAudioWindow:
    def __init__(self,session,assets,directory,notify):
        parsed=urlsplit(session.url)
        if parsed.scheme!='http' or parsed.hostname!='127.0.0.1' or not parsed.port or parsed.query or parsed.fragment:
            raise ValueError('桌面转谱会话地址无效。')
        self.session,self.notify=session,notify
        folder=Path(directory)/'light-window';folder.mkdir(exist_ok=True)
        self.report=folder/(uuid.uuid4().hex+'.json')
        self.process=subprocess.Popen([str(verify_host(Path(assets)/'audio_window')),session.url,
            str(folder/'profile'),str(self.report)],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
            text=True,creationflags=subprocess.CREATE_NO_WINDOW)
        threading.Thread(target=self._wait,daemon=True).start()

    def _wait(self):
        code=self.process.wait()
        if self.process.stdin:self.process.stdin.close()
        self.notify({'kind':'light_window_closed','window':self,'code':code})

    def show(self):
        if self.process.poll() is not None:return False
        try:self.process.stdin.write('show\n');self.process.stdin.flush();return True
        except (OSError,ValueError):return False

    def close(self):
        if self.process.poll() is not None:return
        try:
            self.process.stdin.write('close\n');self.process.stdin.flush()
            self.process.wait(timeout=2)
        except (OSError,ValueError,subprocess.TimeoutExpired):
            if self.process.poll() is None:self.process.terminate()
