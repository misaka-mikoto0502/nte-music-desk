# 第三方资源与运行时

本项目的 MIT 许可适用于项目自有代码、原创图标与自行编码的示例 MIDI，不授予第三方音乐、游戏素材或外部站点内容的权利。程序图标沿用原创的琴键与音符设计，没有使用游戏截图或官方角色素材。1.3.1 的可关闭背景取自用户提供的《异环》截图，经清除 UID、相框和标注后作为 city-session.png 使用；其游戏角色和场景权利归相应权利人，不属于自有 MIT 图标素材。处理记录见 docs/APPEARANCE.md。

## 曲谱与历史目录

- 内置 twinkle.mid / twinkle.musicxml 由本项目根据传统《小星星》旋律自行编码，不包含第三方录音或编曲。
- v1.4.0已删除 BitMidi、动漫公开目录和 Mutopia 的搜索下载代码及随包元数据。旧 Git 版本和已发布的旧软件仍保留历史行为，不能用新版说明替代旧版事实。
- 用户旧下载文件不删除，仅支持本地导入和读取原曲名。来源记录不等于授权证明。
- 项目不提供商业歌曲录音、第三方曲谱或转谱结果下载。合法获取输入文件、模型许可、改编与公开传播权限需分别核对。

## Windows 便携版运行时

便携版由 PyInstaller 构建，并包含构建环境对应的 Python、Tcl/Tk 及所需运行库。相关许可随 `_internal` 中收集的文件一并保留。

- [Python 许可](https://docs.python.org/3/license.html)
- [Tcl/Tk 许可](https://www.tcl-lang.org/software/tcltk/license.html)
- [PyInstaller 许可与引导器例外](https://pyinstaller.org/en/stable/license.html)

曲谱解析和按键调度使用标准库；1.3.1 的界面使用 [Pillow](https://python-pillow.github.io/) 绘制圆角和淡背景，构建所用 Pillow 13.0.0 的 MIT-CMU 许可及随包第三方许可保留在便携版 licenses 目录。`requirements-build.txt` 固定构建环境和界面依赖版本。软件与《异环》官方无关联。

## 可选音频转谱

轻量 Beta 随包提供 [Spotify Basic Pitch TypeScript 1.0.1](https://github.com/spotify/basic-pitch-ts) 的后处理和官方未修改模型，以及 [TensorFlow.js 3.21.0](https://github.com/tensorflow/tfjs) 的 core/converter/CPU JavaScript 代码及单线程 WASM/SIMD 组件，采用 Apache 2.0。其他实际打入脚本的依赖分别保留 MIT/Apache 通知；WASM 所含 XNNPACK、FP16、FXdiv、pthreadpool、cpuinfo、psimd、Emscripten 等依赖的通知与全文亦随包保留。完整许可、来源和包版本位于 `_internal/nte_music_desk/assets/light_audio/licenses.txt`，逐文件 SHA-256 位于 manifest.json。它们不是本项目自有 MIT 内容。复用用户已有浏览器，不分发 Node、PyTorch 或浏览器内核；音频不上传外部服务。

[MuScriptor](https://github.com/muscriptor/muscriptor) 引擎代码采用 MIT，工作台调用固定版本 0.3.0 的外部命令行，不将其代码、PyTorch 或权重打入便携包。用户选择安装时在独立虚拟环境中获取依赖；相关依赖各自保留许可。

[MuScriptor 模型](https://huggingface.co/MuScriptor/muscriptor-medium) 权重另受 CC BY-NC 4.0 非商用许可及附加条件约束，尤其要求输入音乐具备转谱所需的权利。用户自行接受上游条款并完成官方认证。工作台 MIT 许可不替代权重许可，不代表识别结果可自由传播。

[GAME](https://github.com/openvpi/GAME) 代码为 MIT，[1.0 系列模型权重](https://github.com/openvpi/GAME/releases/tag/v1.0.0)为 CC BY-NC-SA 4.0。v1.4.0以官方 1.0.3 small ONNX 权重作为可选旋律 Beta，确认条件后才下载或使用；不把权重放进源码或便携包。遵循官方 ONNX 接口调用本机模型，相关第三方依赖许可各自适用。

[Audio Separator](https://github.com/nomadkaraoke/python-audio-separator) 包装程序采用 MIT。前期尝试的 ViperX BS-RoFormer 检查点独立权重许可尚未核实，继续停用下载与调用，不随当前引擎安装或软件包分发。

当前开发版分离采用 [Open-Unmix 1.3.0](https://github.com/sigsep/open-unmix-pytorch) 和 [UMX-HQ 官方权重](https://zenodo.org/records/3370489)，两者官方声明为 MIT；官方权重记录 API 的 metadata.license.id 为 mit-license。Recorded/created by Fabian-Robert Stöter and Antoine Liutkus (Inria/LIRMM). 四份权重约 143 MB，首次分离时获取并校验发布者校验值，采用 weights_only 加载，不随桌面包分发。不使用许可不同的 UMXL，也不把分离模型的许可等同于输入音乐授权。

音频引擎还使用 PyTorch、ONNX Runtime、NumPy、SciPy、SoundFile 和 imageio-ffmpeg 等外部依赖；包括解码器在内的组件按自身许可使用，不能统称为本项目 MIT 内容。它们在用户选择的独立环境安装，不打入桌面便携包。

许可核对日期为 2026-10-22；详见 docs/COPYRIGHT_AND_MODELS.md 与 docs/AUDIO_TRANSCRIPTION.md。仅核对公开声明，未对上游训练数据作完整权利审计。

MusicXML 导入器依据 [W3C MusicXML 4.0 格式](https://www.w3.org/2021/06/musicxml40/) 编写。内置 twinkle.musicxml 由本项目根据同一传统旋律自行编码，不包含外部曲谱原件。


## 桌面音频窗口

Microsoft.Web.WebView2 SDK 1.0.2903.40（Core/WinForms/x64 Loader）采用其 NuGet 包中的 BSD 许可；完整 LICENSE.txt、NOTICE.txt 与资源哈希在 `_internal/nte_music_desk/assets/audio_window/`。本项目窗口宿主源码为 MIT。系统 WebView2 Evergreen Runtime 与 .NET Framework 是系统组件，不随本包分发，遵循其各自许可。
