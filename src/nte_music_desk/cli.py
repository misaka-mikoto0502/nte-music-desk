"""Standalone MIDI -> verified NTE guitar keyboard player (standard library)."""
from __future__ import annotations

import argparse
from array import array
import ctypes
import json
import math
from pathlib import Path
import sys
import time
import wave
import logging
import os

from .paths import default_data_dir, asset_dir, ensure_data_dir
from . import __version__, APP_NAME
from .notation import read_score
from .midi import write_midi
ROOT = default_data_dir()
ASSETS = asset_dir()
from .midi import convert, load_score, note_name, read_midi, save_score, validate_score
from .keyboard import KEYS, PlaybackStopped, WindowsKeyboard, run_elevated_and_wait
from .keyboard import PianoKey
from .instruments import INSTRUMENTS, SHIFT, score_instrument


def limit_score(score, seconds):
    result = {**score, "events": [dict(e) for e in score["events"] if e["at"] < seconds]}
    if not result["events"]:
        raise ValueError("试听范围内没有音符，请调整片段起点。")
    for event in result["events"]:
        event["duration"] = min(event["duration"], seconds - event["at"])
    result["summary"] = {**score.get("summary", {}), "notes": len(result["events"]),
                         "seconds": min(seconds, score.get("summary", {}).get("seconds", max(e["at"] + e["duration"] for e in result["events"])))}
    return validate_score(result)


from .performance import key_schedule, piano_schedule, piano_chord_schedule, performance_plan


def play_timed(score, backend, hold_ms=300, clock=time.perf_counter, sleep=time.sleep):
    plan = performance_plan(score, hold_ms)
    schedule = plan.key_events
    started, sent = clock(), 0

    def wait_until(deadline):
        while True:
            backend.check()
            remaining = deadline - clock()
            if remaining <= 0:
                return
            sleep(min(0.01, remaining))

    try:
        for at, is_down, key in schedule:
            wait_until(started + at)
            if clock() - started - at > 0.3:
                raise PlaybackStopped("系统调度延迟超过 300 毫秒，已停止，避免音符挤在一起。")
            if is_down:
                backend.down(key)
                sent += key.virtual_key != SHIFT.virtual_key
            else:
                backend.up(key)
        wait_until(started + plan.duration)
        return sent
    finally:
        backend.release_all()


class CancellableKeyboard(WindowsKeyboard):
    def __init__(self, cancel_path=None, allow_shift=False):
        self.cancel_path = Path(cancel_path) if cancel_path else None
        super().__init__(allow_shift=allow_shift)

    def cancelled(self):
        return (self.cancel_path is not None and self.cancel_path.exists()) or super().cancelled()


def write_progress(report_path, phase, **values):
    """Optional UI telemetry; atomic replacement keeps readers off partial JSON."""
    try:
        path = Path(report_path).with_suffix(".progress.json")
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"phase": phase, **values}), encoding="utf-8")
        temporary.replace(path)
    except OSError:
        pass  # The timing/input path must not depend on optional UI reporting.


def play_file(args):
    score = load_score(args.play)
    plan = performance_plan(score, args.hold_ms)  # Reject unsupported timing before UAC or focus changes.
    if sys.platform != "win32":
        raise RuntimeError("游戏演奏仅支持 Windows。")
    if not ctypes.windll.shell32.IsUserAnAdmin():
        if args.elevated_child:
            raise RuntimeError("演奏进程未获得管理员权限。")
        arguments = ["--play", str(Path(args.play).resolve()), "--countdown", str(args.countdown), "--hold-ms", str(args.hold_ms)]
        arguments.extend(["--data-dir", str(ROOT)])
        if args.report:
            arguments.extend(["--report", str(Path(args.report).resolve())])
        if args.cancel_file:
            arguments.extend(["--cancel-file", str(Path(args.cancel_file).resolve())])
        return run_elevated_and_wait(__file__, arguments)
    backend, code = None, 0
    destination = Path(args.report) if args.report else ROOT / "nte_midi_last_run.json"
    duration = plan.duration
    report = {"title": score.get("title", "MIDI"), "status": "starting", "elevated": True,
              "planned_notes": len(score["events"]), "planned_seconds": duration, "settings": score.get("settings", {})}
    try:
        backend = CancellableKeyboard(args.cancel_file, allow_shift=score_instrument(score).id == "piano")
        report.update({"game_hwnd": backend.hwnd, "game_pid": backend.pid})
        if backend.cancelled():
            raise PlaybackStopped("演奏已取消。")
        print(f"请进入 {score_instrument(score).title} 的 36 键界面。F8 / Esc 停止；切出游戏也会停止。", flush=True)
        backend.user32.SetForegroundWindow(backend.hwnd)
        for remaining in range(args.countdown, 0, -1):
            write_progress(destination, "countdown", remaining=remaining)
            print(f"{remaining} 秒后开始……", flush=True)
            deadline = time.perf_counter() + 1
            while time.perf_counter() < deadline:
                if backend.cancelled():
                    raise PlaybackStopped("倒计时期间取消。")
                time.sleep(0.01)
        backend.check()
        write_progress(destination, "playing", started_at=time.time(), seconds=duration)
        report["sent_notes"] = play_timed(score, backend, args.hold_ms)
        report["status"] = "completed"
        print("演奏按键已发送完毕。实际发声请在游戏中确认。", flush=True)
    except (PlaybackStopped, KeyboardInterrupt) as error:
        code = 2
        report.update({"status": "stopped", "reason": str(error) or "键盘中断"})
        print(report["reason"], flush=True)
    except Exception as error:
        code = 1
        report.update({"status": "error", "reason": str(error)})
        print(f"演奏失败：{error}", flush=True)
    finally:
        if backend:
            backend.release_all()
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        write_progress(destination, report["status"])
    return code


def render_preview(score, path, seconds=20, hold_ms=300):
    """Synthesize actual planned note attacks/releases, including Shift groups."""
    if not math.isfinite(seconds) or not 0 < seconds <= 60:
        raise ValueError("试听时长需为 0–60 秒。")
    plan = performance_plan(score, hold_ms)
    stop = min(seconds, plan.duration)
    events = [{"at": n.at, "duration": min(n.duration, stop - n.at), "midi": n.midi}
              for n in plan.notes if n.at < stop]
    if not events:
        raise ValueError("试听范围内没有音符，请调整片段起点。")
    return render_audio(events, path, stop)


def render_song_preview(song, path, tracks=None, start=0, end=None, speed=1, transpose=0, seconds=20):
    """Audition original voices without game range folding or chord reduction."""
    if not all(math.isfinite(v) for v in (start, speed, seconds)) or not 0 <= start < song.seconds or not .25 <= speed <= 2 or not 0 < seconds <= 60:
        raise ValueError("试听起点、速度或时长无效。")
    if type(transpose) is not int or not -36 <= transpose <= 36:
        raise ValueError("试听移调需为 -36–36 半音。")
    end = song.seconds if end is None else end
    if not math.isfinite(end) or not start < end <= song.seconds:
        raise ValueError("试听片段终点需大于起点，且不超过原曲时长。")
    tracks = {t["index"] for t in song.track_info()} if tracks is None else set(tracks)
    stop = min(end, start + seconds * speed)
    events = [{"at": (max(start, n.start) - start) / speed,
               "duration": (min(stop, n.end) - max(start, n.start)) / speed,
               "midi": n.pitch + transpose}
              for n in song.notes if n.track in tracks and n.channel != 9 and n.start < stop and n.end > start]
    if not events:
        raise ValueError("这条音轨在所选片段内没有可试听音符。")
    return render_audio(events, path, (stop - start) / speed)


def render_audio(events, path, length=None):
    """Quiet sine preview shared by source and adapted score audition."""
    rate = 22050
    length = max(e["at"] + e["duration"] for e in events) if length is None else length
    samples = array("i", [0]) * int((length + .25) * rate + 1)
    for event in events:
        begin = int(event["at"] * rate)
        duration = min(3.0, event["duration"])
        size = min(int(duration * rate), len(samples) - begin)
        frequency = 440 * 2 ** ((event["midi"] - 69) / 12)
        for index in range(size):
            t = index / rate
            envelope = min(1, t / 0.008) * min(1, (size - index) / (rate * 0.03)) * math.exp(-1.8 * t)
            samples[begin + index] += int(3500 * envelope * math.sin(2 * math.pi * frequency * t))
    gain = min(1, 24000 / max(1, max(abs(v) for v in samples)))
    pcm = array("h", (int(value * gain) for value in samples))
    if sys.byteorder != "little":
        pcm.byteswap()
    with wave.open(str(path), "wb") as audio:
        audio.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        audio.writeframes(pcm.tobytes())
    return length


def main(argv=None):
    global ROOT
    parser = argparse.ArgumentParser(description=f"{APP_NAME}：MIDI 转吉他 / 钢琴键位")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("--data-dir", type=Path, default=ROOT, help="个人设置、曲库与运行记录目录")
    parser.add_argument("--self-test", type=Path, help="离线自检并写入 JSON；不会发送游戏按键")
    parser.add_argument("--inspect", metavar="SCORE", help="只读分析 MIDI/MusicXML，不激活窗口、不发键")
    parser.add_argument("--convert", metavar="SCORE", help="转换 MIDI/MusicXML 为游戏曲谱，不激活窗口、不发键")
    parser.add_argument("--to-midi", metavar="SCORE", help="将原曲全部声部另存为标准 MIDI")
    parser.add_argument("--output", help="转换后的 JSON 文件")
    parser.add_argument("--tracks", default="auto", help="auto、all 或逗号分隔的 0 起始音轨编号")
    parser.add_argument("--mode", choices=["melody", "chords"], default="melody")
    parser.add_argument("--instrument", choices=list(INSTRUMENTS), default="guitar", help="guitar：吉他钢琴模式；piano：钢琴 Shift 黑键")
    parser.add_argument("--speed", type=float, default=1.0)
    parser.add_argument("--transpose", type=int, default=0)
    parser.add_argument("--range-policy", choices=["fold", "drop", "strict"], default="fold")
    parser.add_argument("--start", type=float, default=0)
    parser.add_argument("--end", type=float, help="片段终点（原曲秒数），留空演奏至曲末")
    parser.add_argument("--play", metavar="JSON", help="将已转换曲谱发送到游戏（请求 UAC）")
    parser.add_argument("--countdown", type=int, default=7)
    parser.add_argument("--hold-ms", type=int, default=300)
    parser.add_argument("--cancel-file", help=argparse.SUPPRESS)
    parser.add_argument("--report", help=argparse.SUPPRESS)
    parser.add_argument("--elevated-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    ROOT = ensure_data_dir(args.data_dir)
    if sum(bool(value) for value in (args.inspect, args.convert, args.play,args.to_midi)) > 1:
        parser.error("--inspect、--convert、--to-midi、--play 只能选择一个。")
    if not 0 <= args.countdown <= 60 or not 20 <= args.hold_ms <= 400:
        parser.error("倒计时需为 0–60 秒；按键时长需为 20–400 毫秒。")
    if args.self_test:
        if any((args.play, args.inspect, args.convert,args.to_midi)):
            parser.error("--self-test 不能与其他任务同时使用。")
        from .diagnostics import run_self_test
        return run_self_test(sys.modules[__name__], args.self_test)
    if args.to_midi:
        if not args.output:parser.error("--to-midi 需要 --output 指定新的 .mid 文件。")
        if Path(args.to_midi).resolve()==Path(args.output).resolve():parser.error("请另存到新文件，避免覆盖原曲。")
        write_midi(read_score(args.to_midi),args.output)
        return 0
    if args.inspect or args.convert:
        song = read_score(args.inspect or args.convert)
        if args.inspect:
            print(json.dumps({"title": song.title, "format": song.format, "seconds": song.seconds,
                              "notes": len(song.notes), "tempos": len(song.tempos),
                              "suggested_track": song.suggested_track(), "tracks": song.track_info(),
                              "warnings": song.warnings}, ensure_ascii=False, indent=2))
        else:
            tracks = None if args.tracks == "auto" else ([t["index"] for t in song.track_info()] if args.tracks == "all" else [int(t) for t in args.tracks.split(",")])
            score = convert(song, tracks, args.mode, args.speed, args.transpose, args.range_policy, args.start, args.instrument, args.end)
            destination = Path(args.output) if args.output else Path(args.convert).with_suffix(f".{args.instrument}.json")
            save_score(score, destination)
            print(json.dumps({"output": str(destination.resolve()), **score["summary"], "warnings": score["warnings"]}, ensure_ascii=False, indent=2))
        return 0
    if args.play:
        return play_file(args)
    import tkinter as tk
    from .ui import App
    App(tk.Tk(), engine=sys.modules[__name__]).root.mainloop()
    return 0


def entrypoint():
    """A windowed EXE has no console; errors are reported to UI and local logs."""
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    raw = sys.argv[1:]
    is_task = any(flag in raw for flag in ("--play", "--convert", "--inspect", "--self-test","--to-midi"))
    try:
        if sys.platform == "win32":
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("NteMusicDesk.Desktop.1")
        return main()
    except Exception as error:
        try:
            folder = ensure_data_dir(ROOT) / "logs"
            folder.mkdir(exist_ok=True)
            logging.basicConfig(filename=folder / "app.log", encoding="utf-8", level=logging.INFO)
            logging.exception("Application operation failed")
            for flag in ("--report", "--self-test"):
                if flag in raw:
                    report = Path(raw[raw.index(flag)+1]).resolve()
                    report.parent.mkdir(parents=True, exist_ok=True)
                    report.write_text(json.dumps({"status": "error", "reason": str(error)}, ensure_ascii=False), encoding="utf-8")
        except (OSError, ValueError, IndexError):
            pass
        if not is_task:
            import tkinter.messagebox
            tkinter.messagebox.showerror(APP_NAME, f"启动失败：{error}")
        print(f"无法完成：{error}", file=sys.stderr)
        return 1
