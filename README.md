# 异环演奏工作台 / NTE Music Desk

<img src="src/nte_music_desk/assets/icon.png" alt="异环演奏工作台应用图标" width="112" height="112" align="right">

**导入本地曲谱或音频，试听后，由工具自动操控《异环》中的钢琴或吉他钢琴模式演奏。无需自己按谱弹奏。**

**2.1.0 · Windows x64 · 自有代码 MIT**

**2.1.0 增加密集钢琴谱自动适配。** 当黑白键切换或同键重复过密时，工作台会尝试合并、重新分组和局部延后，必要时才减少冲突音符。适配试听和报告可用于检查变化，原始 MIDI 保留完整。

主窗口默认更紧凑，支持 Windows 高 DPI 显示。顶部可直接开关迷你播放器，游戏内按 F6 可在录制时隐藏小窗。音频统一通过「导入音乐」进入本地转谱。

**[下载 Windows 便携版](https://github.com/misaka-mikoto0502/nte-music-desk/releases/latest)** · [使用说明](docs/USAGE.md) · [2.1.0 更新说明](docs/RELEASE_NOTES_2.1.0.md) · [问题反馈](https://github.com/misaka-mikoto0502/nte-music-desk/issues)

把文件拖进工作台 → 曲谱直接载入 / 音频本机转谱 → 试听与适配 → 在游戏中自动演奏。

## 2.0 带来了什么

2.0.1 重点整理使用体验：曲目栏、演奏／调整页面与固定播放区各司其职；点击和拖入共用导入入口，原谱对照位于演奏页，进度条统一定位。四种基础色、完整中文图片字标、明音速度滑块和圆角控件统一外观，入门帮助按需打开，操作按钮随任务状态切换。移调推荐覆盖全部 73 个半音，适配报告区分原曲位置与总时长。

2.0.2 进一步加入钢琴专用离线识别、演唱旋律与伴奏分轨、后台转谱、曲目重命名／移除，以及自动显示的迷你播放器、明音进度条与曲名下拉换曲。

| 功能 | 使用体验 |
| --- | --- |
| 本地音频转 MIDI · Beta | 钢琴采用 Transkun 2 ONNX，歌曲采用 GAME small＋MuScriptor small；完整包自带环境，无需额外配置或联网。显示真实阶段和动态剩余时间。 |
| 拖入与曲目架 | 曲谱直接载入，音频打开原生转谱窗口。曲目跨重启保留，右键可重命名显示名称或从列表移除，原文件与方案保留。 |
| 自动保存与载入 | MIDI、原始预测和对照试听保存在个人数据目录。普通前台任务完成后载入，后台任务只入库，保留当前曲目和播放。 |
| 从中间演奏 | 主窗与迷你播放器支持点击、拖动进度；记住暂停、停止和退出时的位置，变速后也能续播。 |
| 迷你播放器 | 置顶小窗提供演奏、暂停/继续和停止，明音进度滑块与曲名下拉换曲；启动时确认一次 UAC，演奏过程中继承权限。 |
| 后台转谱 | 转谱时继续选曲、演奏与试听；停止播放和取消转谱互不影响。“导入音乐”下方可重新打开转谱窗口。 |
| 多轨与演奏适配 | 查看音轨、乐器与音符，独奏/静音声部，选择音域、移调与速度；提供进度定位、适配报告及可选的近同时起音对齐。 |

界面采用纯色背景和圆角面板。顶部“迷你播放器”打开演奏小窗，“帮助”内可查看使用说明、许可和数据目录。

## 下载与开始使用

1. 从 GitHub [Releases](https://github.com/misaka-mikoto0502/nte-music-desk/releases/latest) 下载 `NTE-Music-Desk-v2.1.0-Windows-x64.zip`。便携包已包含完整运行环境与离线转谱模型。Release 下的 `Source code (zip)` 供开发者使用。
2. 完整解压到新目录，保留 `_internal`，双击 **异环演奏工作台.exe**，手动确认启动权限提示。升级时先关闭旧版。
3. 点击左侧“导入音乐”或将本地曲谱／音频拖入这个按钮。音频识别完成后自动载入曲谱，可先试听，选择乐器与声部，再通过进度条定位。
4. 在游戏中进入相应的 36 键演奏界面，再点击演奏。默认倒计时 **3 秒**，**F7** 暂停/继续，**F8** 停止。

首次可用内置《小星星》检查。点击“开始演奏”后自动聚焦游戏并显示迷你播放器，无需手动打开，小窗不抢游戏焦点。演奏时切出游戏会自动停止；需要点击悬浮窗时推荐无边框全屏，独占全屏可使用 F7/F8。

按 **F6** 可隐藏或恢复迷你播放器，录制时可在游戏中直接操作。

个人设置、曲目架和转换结果位于 `%LOCALAPPDATA%\NteMusicDesk`，升级不需要删除该目录。发布附件提供 SHA-256 校验文件。

## 为什么请求管理员权限

工作台通过 Windows 键盘输入接口模拟演奏按键。当游戏以管理员权限运行时，普通权限工具的模拟输入可能受到 Windows 权限隔离的限制，因此工作台申请管理员权限以兼容这类游戏窗口。演奏采用系统模拟按键，不通过修改游戏内存、注入游戏进程或修改游戏文件实现。[权限机制与使用说明](docs/USAGE.md#管理员权限说明)

**当前版本在打开主界面时统一请求一次 UAC 授权**，需用户手动确认；取消则不启动主界面。授权作用于整个程序，从界面启动的演奏、音频处理等子进程也会继承权限。

读谱、音频转谱和本地试听本身不需要管理员权限；命令行分析、转换与离线自检可在普通权限下运行。请从本项目 Releases 获取便携包，并按随包 SHA-256 文件核对下载内容。

## 支持哪些输入

| 输入 | 处理方式 |
| --- | --- |
| `.mid` / `.midi` / `.kar` / `.rmi` | 直接读取曲谱，选择声部并适配游戏键位。 |
| `.musicxml` / `.xml` / `.mxl` | 读取 MusicXML 曲谱，也可将全部原声部另存为标准 MIDI。复杂反复与装饰记号有支持边界，见使用说明。 |
| MP3、WAV、FLAC 等本地音频 | 使用自带解码器与本地模型识别为 MIDI，再试听和适配；不依赖浏览器解码。 |
| PDF、乐谱图片 | 需先用外部 OMR 工具识别、校对并导出 MusicXML 或 MIDI。 |

完整 Windows ZIP 约 **352 MB**。钢琴专用识别在受控短句上优于旧轻量方案；歌曲会分别保留演唱旋律与其他声部，但密集混音、人声滑音、混响和快速重复音仍可能有错漏，不能承诺任意歌曲准确率。[当前质量验证](docs/VALIDATION_OFFLINE_AUDIO.md) · [旧轻量基准](docs/AUDIO_BENCHMARK.md)

## 演奏与试听

- **两种游戏乐器**：吉他钢琴模式 E3–D#6；钢琴 Shift 黑键模式暂按 C3–B5，绝对音高仍需实听校准。
- **多声部选择**：原曲声部默认每组保留 12 音，可调 2–36；另有旋律＋低音、旧旋律与 6 音和弦模式。配置数量不等于游戏实际发声数量。
- **曲谱与时序对照**：支持原谱、适配后的合成试听、单轨试听，以及键位明细和 JSON 导出；游戏演奏从进度条当前位置开始。
- **移调与报告**：推荐最多 3 个移调候选，显示折回、合并或删音差异；报告可检查并行键峰值与计划起音偏差。
- **设置记忆**：按曲谱内容与乐器保存演奏方案；曲目改名后可恢复，继续位置以原曲时间记录。

钢琴使用全局 Shift，全白键或全黑键可成组触发，混合黑白键约错开 **55 毫秒**快速分组；吉他钢琴模式没有这项分组限制。短暂的 Shift / 重复键冲突采用有上限的局部延后，原 MIDI 不改写。近同时起音对齐默认关闭，琶音不宜随意对齐。

钢琴遇到密集曲谱时，先合并折回后的重叠同键音、有限重新分组，再以最多 **50 毫秒额外延后**消解冲突，仍无法安全执行时才局部剪枝，优先保留明确的旋律与低音。适配报告记录合并、剪枝及延后，原始 MIDI 与原谱对照保留完整。设计与样例验证见 [钢琴通用适配](docs/PIANO_ADAPTATION.md)。

程序核对游戏进程与前台窗口，不能识别当前乐器界面。踏板、弯音、力度和原音色不转换为游戏操作；合成试听不等于游戏原音色。单旋律曲谱也不会自动生成伴奏。

## 验证与已知边界

2.1.0 的发布检查见 [本版验证](docs/VALIDATION_2.1.0.md)。钢琴／歌声样例评分、整首性能、后台转谱与换曲的评测方法见 [离线转谱验证记录](docs/VALIDATION_OFFLINE_AUDIO.md)。

2026-11-09 复核：当时版本通过 176 项 Python 检查、96 组样例转换及 JavaScript 检查。完整便携包处理 288.301 秒歌曲实测 149.813 秒，输出与已认可基准逐字节一致；后台转谱、换曲、取消及失败重试另行验证，不能以这一首样例推断所有硬件和曲目的耗时。

已发布 2.0.1 的 124 项回归、96 组转换等历史证据保留于 [发布版验证](docs/VALIDATION_2.0.1.md)，2.0.0 记录见 [2.0 验证](docs/VALIDATION_2.0.md)。

新版悬浮窗按钮、拖动时的游戏前台保持、实际多音数及钢琴绝对音高仍需人工验收；系统另存框的实际点选也保留为人工项目。软件检查通过不代表所有曲目的音乐还原率已通过验证。

## 从源码运行与构建

需要 Windows 和带 Tcl/Tk 的 Python（构建推荐 3.12）。项目安装 Pillow、NumPy 和 ONNX Runtime；默认转谱的模型与本机组件需由开发者另行准备，完整 Windows 包的使用者无需这些步骤：

```powershell
python -m pip install -e .
python src/nte_music_desk/_bootstrap.py
```

安装后也可运行 `nte-music-desk`。只分析或转换文件不会请求管理员权限或发送游戏按键：

```powershell
python src/nte_music_desk/_bootstrap.py --inspect my-song.mid
python src/nte_music_desk/_bootstrap.py --convert my-song.mid --instrument piano --mode chords --output my-score.json
python src/nte_music_desk/_bootstrap.py --convert my-song.mid --start 35 --end 50 --output excerpt.json
python src/nte_music_desk/_bootstrap.py --to-midi my-score.mxl --output converted.mid
```

开发检查与打包：

```powershell
python -m unittest discover -s tests -v
python tools/check_workflows.py
python -m pip install -r requirements-build.txt
python tools/check_release.py
python tools/prepare_offline_audio.py
python tools/build_windows.py --output .build/current
python tools/verify_release.py --archive .build/current/NTE-Music-Desk-v2.1.0-Windows-x64.zip --report .build/current/verification.json
python tools/package_source.py --output .build/current/NTE-Music-Desk-v2.1.0-Source.zip
python tools/verify_current.py --folder .build/current --report .build/validation/current-identity.json
```

本地当前应用在 `.build/current/`，默认发布构建输出 `releases/v2.1.0/`。构建产物不进入 Git。同名包默认拒绝覆盖，当前程序须正常关闭后才可明确使用 `--overwrite`。可以先在 `.build/cache/` 临时构建并验证，再替换当前入口。`verify_current.py` 使用与打包相同版本的 Python，检查源码包逐文件内容、EXE 内嵌代码、资源及 Windows ZIP。上传操作见 [2.1.0 发布指南](docs/PUBLISH_2.1.0.md)。

2.x 的源码持续维护在 `release/2.0.0`，小版本通过版本标签区分；新大版本才建立新的长期分支。协作规则见 [AGENTS.md](AGENTS.md)。

[构建与发布](docs/RELEASING.md) · [项目结构](docs/ARCHITECTURE.md) · [后续计划](docs/NEXT_STEPS.md) · [界面设计](docs/APPEARANCE.md)

## 素材与许可

项目自有代码采用 [MIT](LICENSE)，仅附自行编码的《小星星》示例。**不提供在线搜曲或音乐下载**，请自行提供本地文件，并合法合理使用输入与转换结果。音频在本机处理；可选引擎安装或首次获取模型可能联网。

代码、第三方依赖、模型和音乐素材分别适用各自许可。自带 MuScriptor／GAME 权重含非商业使用限制，工作台 MIT 许可不替代模型许可。来源说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [许可边界](docs/COPYRIGHT_AND_MODELS.md)。本工具与游戏官方无关联。
