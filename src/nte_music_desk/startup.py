"""Elevate the interactive application before creating any Tk windows."""
from pathlib import Path
import sys
from .keyboard import is_administrator, run_elevated_and_wait

TASK_FLAGS = {'--play', '--inspect', '--convert', '--to-midi', '--self-test', '--offline-audio-worker', '--version', '--help', '-h'}


def is_task(arguments):
    return any(argument.split('=',1)[0] in TASK_FLAGS for argument in arguments)


def ensure_gui_elevation(arguments):
    if sys.platform != 'win32' or is_task(arguments) or is_administrator():
        return None
    if '--elevated-child' in arguments:
        raise RuntimeError('启动未获得管理员权限，请重新打开软件并确认 Windows 权限提示。')
    arguments=list(arguments)
    for index,value in enumerate(arguments):
        if value=='--data-dir' and index+1<len(arguments):
            arguments[index+1]=str(Path(arguments[index+1]).expanduser().resolve())
        elif value.startswith('--data-dir='):
            arguments[index]='--data-dir='+str(Path(value.split('=',1)[1]).expanduser().resolve())
    return run_elevated_and_wait(arguments=arguments, visible=True, wait=False)
