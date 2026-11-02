# 异环演奏工作台 / NTE Music Desk

Windows 桌面曲谱演奏工具：导入本地曲谱，一键操控《异环》的吉他钢琴模式或钢琴 Shift 黑键模式。支持多轨声部适配、试听，以及可选的本地音频转谱。

<img src="src/nte_music_desk/assets/icon.png" alt="异环演奏工作台应用图标" width="160" height="160">

2.0 整合了本地音频转谱桌面窗口、CPU 加速与剩余时间、拖入导入、自动保存和载入 MIDI，以及启动时提权和置顶迷你播放器。支持拖动进度、断点续播，同一次识别可免重算切换均衡版与弱音版。日常曲谱导入与轻量转谱无需配置 Python 或 GPU。考虑音乐版权风险，不提供搜曲与下载，请使用自己的本地文件，并合法合理使用输入和转换结果。音频识别继续标为 Beta；高级分离与转谱需独立配置。

## 下载与使用

从 Releases 获取 Windows x64 便携包，完整解压后双击 **异环演奏工作台.exe**。曲谱导入与演奏不需要安装 Python。请保留同目录的 `_internal` 文件夹。轻量音频 Beta 在独立桌面窗口中用本机 CPU 运行，依赖系统已有的 WebView2 Runtime 与 .NET Framework 4.6.2+；缺少组件时可手动使用文件菜单中的浏览器兼容入口。高级分离与转谱仍需独立引擎和授权模型。

选曲 → 选择乐器与片段 → 时序试听 → 游戏试奏 → 开始演奏。首次可用内置《小星星》检查功能。打开图形应用时手动确认一次 UAC，后续演奏继承权限；F7 暂停/继续，F8 停止，切出游戏自动停止。

[完整使用说明](docs/USAGE.md) · [构建与发布](docs/RELEASING.md) · [项目结构](docs/ARCHITECTURE.md) · [发布检查](docs/VALIDATION.md)

[音频转谱配置](docs/AUDIO_TRANSCRIPTION.md) · [本轮复查与下一轮计划](docs/NEXT_STEPS.md)

[轻量音频转谱 Beta](docs/LIGHT_AUDIO.md)：新增资源约 2.34 MB，本机 CPU 加速、动态剩余时间，支持拖入音频、MIDI 自动下载和导入；可选弱音识别与和弦起音对齐；清晰单乐器优先，不承诺任意歌曲达到 90–95% 准确率。

[音乐与模型许可边界](docs/COPYRIGHT_AND_MODELS.md)：本地文件不自动代表具备转谱或发布授权，代码与模型权重采用各自许可。

[2.0 更新说明](docs/RELEASE_NOTES_2.0.0.md) · [2.0 发布验证与待验收项](docs/VALIDATION_2.0.md) · [音频实测记录](docs/AUDIO_BENCHMARK.md)

1.3.1 提供暖灰/墨绿界面、圆角面板与按钮，城市吉他背景可在“外观”菜单关闭或调节浓度。[界面设计记录](docs/APPEARANCE.md)

## 功能

- 吉他钢琴模式 E3–D#6 与钢琴 Shift 黑键模式（暂按 C3–B5）。
- 多轨工作区：乐器、原轨/通道、音域、声部角色、独奏/静音与音符总览，游标随播放移动。
- 原曲声部模式默认每组保留 12 音，可调 2–36；另有旋律＋低音、旧旋律与 6 音和弦模式。
- 保留声部独立起音，优先整体八度移动；支持变速、移调与片段起止（支持分:秒）。
- 可选 MuScriptor 将已获授权的伴奏 / 纯音乐转成多轨 MIDI；GAME 歌声旋律为独立 Beta，需分别确认模型条款。提供独立安装、音频选段、取消和结果导入，原始转谱与游戏适配分开保留。
- UMX-HQ 分离原唱的人声与伴奏，保留共同时间轴；可独立导出 WAV，或继续转谱。双路识别可分别保留伴奏、旋律 Beta 与合并 MIDI，旋律失败时保留伴奏。
- 转谱前试听最多 30 秒音频；生成后在原音频、分离音频与曲谱合成音之间同位置切换，支持定位、暂停和片段循环。环境检查与在线模型访问验证分别提供。
- 按曲谱内容与乐器自动记忆方案，文件改名后仍可恢复；音轨可单独试听。
- 主窗和迷你播放器支持点击/拖动进度，从选定位置演奏；暂停、停止及退出后记住原曲位置，变速后仍可续播。默认开始倒计时 3 秒。
- 轻量转谱一次推理保存两档结果，免重算切换并自动载入；新识别 MIDI 使用统一力度 96，已有 MIDI 保留原力度。
- 推荐最多 3 个移调候选，说明折回、丢音、重合等差异，手动应用后试听。
- 钢琴全白/全黑键和弦成组触发；混合黑白键约错开 55 毫秒快速分组。
- 导入 .mid / .midi / .kar / .rmi / .musicxml / .xml / .mxl，可将原曲全部声部另存为标准 MIDI。
- 原谱对照与按键时序合成试听、20 秒游戏试奏、键位明细与 JSON 导出。
- 可导出的适配报告，定位简化、折回、丢弃或合并的音符，显示并行键峰值与计划起音偏差。
- 个人设置、转谱结果和运行记录放在 `%LOCALAPPDATA%\NteMusicDesk`，与软件和源码分开。

## 从源码运行

需要 Windows 和带 Tcl/Tk 的 Python 3.10 或更高版本。先安装项目依赖（界面使用 Pillow），可选音频引擎独立安装：

```powershell
python -m pip install -e .
python src/nte_music_desk/_bootstrap.py
```

安装后也可使用桌面启动命令：

```powershell
nte-music-desk
```

只转换文件不会请求管理员权限或发送游戏按键：

```powershell
python src/nte_music_desk/_bootstrap.py --inspect my-song.mid
python src/nte_music_desk/_bootstrap.py --convert my-song.mid --instrument piano --mode chords --output my-score.json
python src/nte_music_desk/_bootstrap.py --convert my-song.mid --start 35 --end 50 --output excerpt.json
python src/nte_music_desk/_bootstrap.py --to-midi my-score.mxl --output converted.mid
```

## 开发检查与构建

```powershell
python -m unittest discover -s tests -v
python -m pip install -r requirements-build.txt
python tools/check_release.py
python tools/build_windows.py
python tools/verify_release.py
python tools/package_source.py
```

构建产物在 `releases/v2.0.0/`，不会进入 Git。已有同名包默认拒绝覆盖；明确重建时使用 `--overwrite`。GitHub Actions 在手动触发或推送版本标签时运行测试、构建并上传下载产物，不会自动公开创建 Release。

## 限制与验证

当前针对 Windows x64 和游戏 36 键界面。程序能核对游戏进程与前台窗口，不能识别游戏当前乐器。钢琴绝对音高需按听感校准；混合黑白键为滚奏近似，不能保证严格同时发声。单旋律 MIDI 不会自动生成伴奏，踏板、弯音、力度和原音色不转为操作。过密音符可降低速度或减少音轨。

MusicXML 支持 partwise、普通反复与编号房子、声部/和弦/连音及显式时值。小节内反复、嵌套反复或不一致的小节结构会提示先展开；D.C./D.S./Coda/Fine 和装饰记号不展开并显示警告。音频经可选引擎识别后导入，不保证识别准确率；PDF 和图片需要先用外部 OMR 校对导出。详见使用说明中的格式表。

使用者已确认钢琴发声及 F7 暂停/继续、F8 停止正常，先前也确认吉他钢琴《小星星》正常；这些反馈不等于 2.0 新包的全部实机验收。悬浮窗按钮、游戏实际多音数和钢琴绝对音高仍需实听，详见 2.0 发布验证。时序试听使用合成音色，不等于游戏原音色或实际发声确认。

## 资源与许可

项目自有代码采用 [MIT](LICENSE)。仅附自行编码的《小星星》示例；v1.4.0 已移除搜曲、下载功能和目录快照。旧版下载的本地文件保留，可通过“导入曲谱”打开。请使用自有或已获必要授权的素材，模型条款与音乐权利分别适用。

外部站点、曲谱和运行库的来源及许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。软件与游戏官方无关联。
