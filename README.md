# 异环演奏工作台 / NTE Music Desk

Windows 桌面曲谱演奏工具：在《异环》的吉他钢琴模式或钢琴 Shift 黑键模式中演奏 MIDI / MusicXML，支持旋律、和弦、在线搜曲与格式转换。

<img src="src/nte_music_desk/assets/icon.png" alt="异环演奏工作台应用图标" width="160" height="160">

## 下载与使用

从 Releases 获取 Windows x64 便携包，完整解压后双击 **异环演奏工作台.exe**。不需要 Python，也没有 CMD 启动器。请保留同目录的 `_internal` 文件夹。

选曲 → 选择乐器 → 电脑试听 → 游戏试奏 → 完整演奏。首次可用内置《小星星》检查功能。开始游戏演奏时需要手动确认 UAC；F8 停止，切出游戏自动停止。

[完整使用说明](docs/USAGE.md) · [构建与发布](docs/RELEASING.md) · [项目结构](docs/ARCHITECTURE.md) · [发布检查](docs/VALIDATION.md)

## 功能

- 吉他钢琴模式 E3–D#6 与钢琴 Shift 黑键模式（暂按 C3–B5）。
- 旋律简化、最多 6 音和弦、音轨多选、变速、移调、八度折回与起点设置。
- 钢琴全白/全黑键和弦成组触发；混合黑白键约错开 55 毫秒快速分组。
- 在线目录约 12 万条，搜索后下载并自动导入；已下载曲目保存在本机。
- Mutopia 古典目录新增 2,122 个可下载条目，其中 796 个标有钢琴；中文曲名与作曲家组合检索，支持多乐章 ZIP。
- 导入 .mid / .midi / .kar / .rmi / .musicxml / .xml / .mxl，可将原曲全部声部另存为标准 MIDI。
- 合成音色试听、20 秒游戏试奏、键位明细与 JSON 导出。
- 个人设置、下载、缓存和运行记录放在 `%LOCALAPPDATA%\NteMusicDesk`，与软件和源码分开。

## 从源码运行

需要 Windows 和带 Tcl/Tk 的 Python 3.10 或更高版本，运行时只用标准库：

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

MusicXML 支持 partwise、普通反复与编号房子、声部/和弦/连音及显式时值。小节内反复、嵌套反复或不一致的小节结构会提示先展开；D.C./D.S./Coda/Fine 和装饰记号不展开并显示警告。MP3/WAV、PDF 和图片需要先识别音符，不属于本版的确定性格式导入范围。详见使用说明中的格式表。

先前脚本版的钢琴与和弦已由使用者实机确认。此版本另外检查了文件布局、源码导入、EXE 自检、曲库资源、GUI 初始化和打包入口；整理期间不额外发送游戏按键。兼容性并不涵盖所有 Windows 配置或未来游戏更新。

## 资源与许可

项目代码采用 [MIT](LICENSE)。仅附自行编码的《小星星》示例、原创琴键与音符图标和曲库元数据。三叶与黄昏是在线搜索入口，第三方曲谱原件不进入此仓库。原有个人曲谱可通过本地导入继续使用。

外部站点、曲谱和运行库的来源及许可说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。软件与游戏官方无关联。
