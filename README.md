# 异环演奏工作台 / NTE Music Desk

<img src="src/nte_music_desk/assets/icon.png" alt="异环演奏工作台应用图标" width="112" height="112" align="right">

**导入本地曲谱或音频，试听后，由工具自动操控《异环》中的钢琴或吉他钢琴模式演奏。无需自己按谱弹奏。**

**2.0.1 · Windows x64 · MIT**

[下载便携版](https://github.com/misaka-mikoto0502/nte-music-desk/releases) · [使用说明](docs/USAGE.md) · [2.0.1 更新说明](docs/RELEASE_NOTES_2.0.1.md) · [问题反馈](https://github.com/misaka-mikoto0502/nte-music-desk/issues)

把文件拖进工作台 → 曲谱直接载入 / 音频本机转谱 → 试听与适配 → 在游戏中自动演奏。

## 2.0 带来了什么

2.0.1 重点整理使用体验：左侧曲目栏、中央“演奏／调整”页面与固定播放区各司其职；四种基础色、圆角按钮和原生下拉框统一外观，入门帮助按需打开，操作按钮随任务状态切换。

| 功能 | 使用体验 |
| --- | --- |
| 本地音频转 MIDI · Beta | 独立桌面窗口，本机 CPU 处理；轻量模式无需安装 Python、GPU 或登录账号。显示处理进度与预计剩余时间。 |
| 拖入与曲目架 | 拖入曲谱直接载入，拖入音频打开转谱窗口。导入与生成的曲谱加入曲目架，重启后继续使用。 |
| 自动保存与载入 | 识别完成自动保存 MIDI 到系统下载目录，并交给工作台；手动点“下载 MIDI”可另选目录和文件名。 |
| 从中间演奏 | 主窗与迷你播放器支持点击、拖动进度；记住暂停、停止和退出时的位置，变速后也能续播。 |
| 迷你播放器 | 置顶小窗提供演奏、暂停/继续和停止；启动时确认一次 UAC，演奏过程中继承权限。 |
| 两档识别对比 | 一次推理保留均衡版与弱音版，无需重新识别即可切换、试听并载入。弱音版可能补回细节，也可能增加误音。 |
| 多轨与演奏适配 | 查看音轨、乐器与音符，独奏/静音声部，选择音域、移调、速度和片段；提供适配报告及可选的近同时起音对齐。 |

界面采用纯色背景和圆角面板。普通曲谱导入和轻量音频处理均可直接使用便携版；高级分离与转谱引擎另行配置。

## 下载与开始使用

1. 从 [Releases](https://github.com/misaka-mikoto0502/nte-music-desk/releases) 选择对应版本，下载 `NTE-Music-Desk-v2.0.1-Windows-x64.zip`。Source ZIP 供开发者使用。尚未上传的版本可由维护者从本地 `releases/v2.0.1/` 获取。
2. 完整解压到新目录，保留 `_internal`，双击 **异环演奏工作台.exe**，手动确认启动权限提示。升级时先关闭旧版。
3. 将本地曲谱或音频拖入左侧区域。音频识别完成后会自动载入曲谱，可先试听，再选择乐器、声部和片段。
4. 在游戏中进入相应的 36 键演奏界面，再点击演奏。默认倒计时 **3 秒**，**F7** 暂停/继续，**F8** 停止。

首次可用内置《小星星》检查。演奏时切出游戏会自动停止；需要点击悬浮窗时推荐无边框全屏，独占全屏可使用 F7/F8。

轻量转谱窗口复用系统 **WebView2 Runtime** 与 **.NET Framework 4.6.2+**，不捆绑浏览器内核。缺少组件时可使用“文件 → 轻量转谱（浏览器兼容）”。[轻量模式说明](docs/LIGHT_AUDIO.md)

个人设置、曲目架和转换结果位于 `%LOCALAPPDATA%\NteMusicDesk`，升级不需要删除该目录。发布附件提供 SHA-256 校验文件。

## 支持哪些输入

| 输入 | 处理方式 |
| --- | --- |
| `.mid` / `.midi` / `.kar` / `.rmi` | 直接读取曲谱，选择声部并适配游戏键位。 |
| `.musicxml` / `.xml` / `.mxl` | 读取 MusicXML 曲谱，也可将全部原声部另存为标准 MIDI。复杂反复与装饰记号有支持边界，见使用说明。 |
| MP3、WAV、FLAC 等本地音频 | 先通过轻量转谱 Beta 识别为 MIDI，再试听与适配；具体格式取决于系统 WebView2 的解码支持。 |
| PDF、乐谱图片 | 需先用外部 OMR 工具识别、校对并导出 MusicXML 或 MIDI。 |

音频识别更适合清晰单乐器。复杂混音、人声、弱音和快速重复音可能有错漏；弱音版与起音对齐供用户比较，不代表必然更接近原曲。轻量组件资源约 **2.34 MB**，不会附带高级模型或 GPU 环境。[质量说明与基准](docs/AUDIO_BENCHMARK.md)

## 演奏与试听

- **两种游戏乐器**：吉他钢琴模式 E3–D#6；钢琴 Shift 黑键模式暂按 C3–B5，绝对音高仍需实听校准。
- **多声部选择**：原曲声部默认每组保留 12 音，可调 2–36；另有旋律＋低音、旧旋律与 6 音和弦模式。配置数量不等于游戏实际发声数量。
- **曲谱与时序对照**：支持原谱、适配后的合成试听、单轨试听、20 秒游戏试奏，以及键位明细和 JSON 导出。
- **移调与报告**：推荐最多 3 个移调候选，显示折回、合并或删音差异；报告可检查并行键峰值与计划起音偏差。
- **设置记忆**：按曲谱内容与乐器保存演奏方案；曲目改名后可恢复，继续位置以原曲时间记录。

钢琴使用全局 Shift，全白键或全黑键可成组触发，混合黑白键约错开 **55 毫秒**快速分组；吉他钢琴模式没有这项分组限制。短暂的 Shift / 重复键冲突采用有上限的局部延后，原 MIDI 不改写。近同时起音对齐默认关闭，琶音不宜随意对齐。

程序核对游戏进程与前台窗口，不能识别当前乐器界面。踏板、弯音、力度和原音色不转换为游戏操作；合成试听不等于游戏原音色。单旋律曲谱也不会自动生成伴奏。

## 可选高级音频处理

需要分离原唱或尝试其他识别方式时，可在文件菜单打开高级配置。这些能力**不包含在默认轻量转谱环境内**，需要独立安装依赖，并遵守对应模型许可。

| 引擎 | 用途 |
| --- | --- |
| UMX-HQ | 分离人声与伴奏，独立导出 WAV，或继续转谱。 |
| MuScriptor | 将伴奏或纯音乐识别为多轨 MIDI；受限模型需单独授权。 |
| GAME · Beta | 尝试提取歌声旋律；可与伴奏双路处理，分别保留结果及合并 MIDI。 |

高级流程支持选段、取消、环境检查，以及原音频、分离音频和曲谱合成音的同位置对照试听。质量与资源需求因引擎而异。[配置说明](docs/AUDIO_TRANSCRIPTION.md) · [模型许可](docs/COPYRIGHT_AND_MODELS.md)

## 验证与已知边界

2.0.1 已通过 **118 项 Python 回归**、JavaScript 检查、Windows 包独立解压自检及一次真实轻量转谱，详情见 [本版验证记录](docs/VALIDATION_2.0.1.md)。2.0.0 已完成的 115 项回归、8 组真实轻量转谱、自动载入、两档切换和重启恢复检查另存于 [2.0 验证记录](docs/VALIDATION_2.0.md)。

新版悬浮窗按钮、拖动时的游戏前台保持、实际多音数及钢琴绝对音高仍需人工验收；系统另存框的实际点选也保留为人工项目。软件检查通过不代表所有曲目的音乐还原率已通过验证。

## 从源码运行与构建

需要 Windows 和带 Tcl/Tk 的 Python 3.10 或更高版本。界面依赖 Pillow，高级音频引擎独立安装：

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
node tools/light_audio_web/test.mjs
node tools/light_audio_web/test_downloads.mjs
python -m pip install -r requirements-build.txt
python tools/check_release.py
python tools/build_windows.py
python tools/verify_release.py
python tools/package_source.py
```

产物在 `releases/v2.0.1/`，不进入 Git。同名包默认拒绝覆盖，明确重建才使用 `--overwrite`。GitHub Actions 在 PR、手动触发或推送版本标签时检查并构建，保存产物，公开 Release 需另行发布。

[构建与发布](docs/RELEASING.md) · [项目结构](docs/ARCHITECTURE.md) · [后续计划](docs/NEXT_STEPS.md) · [界面设计](docs/APPEARANCE.md)

## 素材与许可

项目自有代码采用 [MIT](LICENSE)，仅附自行编码的《小星星》示例。**不提供在线搜曲或音乐下载**，请自行提供本地文件，并合法合理使用输入与转换结果。音频在本机处理；可选引擎安装或首次获取模型可能联网。

代码、第三方依赖、模型和音乐素材分别适用各自许可。来源说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) 与 [许可边界](docs/COPYRIGHT_AND_MODELS.md)。本工具与游戏官方无关联。
