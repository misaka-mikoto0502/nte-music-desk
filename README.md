# 异环演奏工作台 / NTE Music Desk

Windows 桌面曲谱演奏工具：导入或下载曲谱，一键操控《异环》的吉他钢琴模式或钢琴 Shift 黑键模式。支持多轨声部适配、试听、在线搜曲，以及可选的本地音频转谱。

<img src="src/nte_music_desk/assets/icon.png" alt="异环演奏工作台应用图标" width="160" height="160">

## 下载与使用

从 Releases 获取 Windows x64 便携包，完整解压后双击 **异环演奏工作台.exe**。曲谱导入与演奏不需要安装 Python。请保留同目录的 `_internal` 文件夹。可选音频转谱需另行配置 Python 引擎与授权模型。

选曲 → 选择乐器与片段 → 时序试听 → 游戏试奏 → 开始演奏。首次可用内置《小星星》检查功能。开始游戏演奏时需要手动确认 UAC；F8 停止，切出游戏自动停止。

[完整使用说明](docs/USAGE.md) · [构建与发布](docs/RELEASING.md) · [项目结构](docs/ARCHITECTURE.md) · [发布检查](docs/VALIDATION.md)

[音频转谱配置](docs/AUDIO_TRANSCRIPTION.md) · [本轮复查与下一轮计划](docs/NEXT_STEPS.md)

## 功能

- 吉他钢琴模式 E3–D#6 与钢琴 Shift 黑键模式（暂按 C3–B5）。
- 多轨工作区：乐器、原轨/通道、音域、声部角色、独奏/静音与音符总览，游标随播放移动。
- 原曲声部模式默认每组保留 12 音，可调 2–36；另有旋律＋低音、旧旋律与 6 音和弦模式。
- 保留声部独立起音，优先整体八度移动；支持变速、移调与片段起止（支持分:秒）。
- 可选 MuScriptor 本地音频转多轨 MIDI，提供独立安装、取消与结果导入，原始转谱与游戏适配分开保留。
- 按曲谱内容与乐器自动记忆方案，文件改名后仍可恢复；音轨可单独试听。
- 推荐最多 3 个移调候选，说明折回、丢音、重合等差异，手动应用后试听。
- 钢琴全白/全黑键和弦成组触发；混合黑白键约错开 55 毫秒快速分组。
- 在线目录约 12 万条，搜索后下载并自动导入；已下载曲目保存在本机。
- Mutopia 古典目录新增 2,122 个可下载条目，其中 796 个标有钢琴；中文曲名与作曲家组合检索，支持多乐章 ZIP。
- 导入 .mid / .midi / .kar / .rmi / .musicxml / .xml / .mxl，可将原曲全部声部另存为标准 MIDI。
- 原谱对照与按键时序合成试听、20 秒游戏试奏、键位明细与 JSON 导出。
- 可导出的适配报告，定位简化、折回、丢弃或合并的音符，显示并行键峰值与计划起音偏差。
- 个人设置、下载、缓存和运行记录放在 `%LOCALAPPDATA%\NteMusicDesk`，与软件和源码分开。

## 从源码运行

需要 Windows 和带 Tcl/Tk 的 Python 3.10 或更高版本，核心曲谱功能只用标准库，可选音频引擎独立安装：

```powershell
python src/nte_music_desk/_bootstrap.py
```

也可安装为桌面启动命令：

```powershell
python -m pip install -e .
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
python tools/build_windows.py
```

构建产物在 `releases/`，不会进入 Git。GitHub Actions 在手动触发或推送版本标签时运行测试、构建并上传下载产物，不会自动公开创建 Release。

## 限制与验证

当前针对 Windows x64 和游戏 36 键界面。程序能核对游戏进程与前台窗口，不能识别游戏当前乐器。钢琴绝对音高需按听感校准；混合黑白键为滚奏近似，不能保证严格同时发声。单旋律 MIDI 不会自动生成伴奏，踏板、弯音、力度和原音色不转为操作。过密音符可降低速度或减少音轨。

MusicXML 支持 partwise、普通反复与编号房子、声部/和弦/连音及显式时值。小节内反复、嵌套反复或不一致的小节结构会提示先展开；D.C./D.S./Coda/Fine 和装饰记号不展开并显示警告。音频经可选引擎识别后导入，不保证识别准确率；PDF 和图片需要先用外部 OMR 校对导出。详见使用说明中的格式表。

先前脚本版的钢琴与和弦已由使用者实机确认。1.3.0 的多轨、方案迁移、排程与转谱进程流程经过本地检查；未进行新增游戏输入测试，也未进行需要授权权重的真实 AI 推理验收。每组音数不是游戏实际多音上限。时序试听使用合成音色，不等于游戏原音色或实际发声确认。

## 资源与许可

项目代码采用 [MIT](LICENSE)。仅附自行编码的《小星星》示例、原创琴键与音符图标和曲库元数据。三叶与黄昏是在线搜索入口，第三方曲谱原件不进入此仓库。原有个人曲谱可通过本地导入继续使用。

外部站点、曲谱和运行库的来源及许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。软件与游戏官方无关联。
