# 第三方资源与运行时

## 完整离线转谱

默认原生转谱窗口使用 Transkun 2 ONNX（Yujia Yan，MIT；TuesdayCrowd 导出；前端与解码器参考 audio-claudio 的 Unlicense 实现）、GAME 1.0.3 small ONNX（OpenVPI，代码 MIT、权重 CC BY-NC-SA 4.0）及 MuScriptor small F16 GGUF（Mirelo/Kyutai，权重 CC BY-NC 4.0 及上游条件；Damien Ronssin 转换；muscriptor.cpp/ggml 代码 MIT、pffft 许可保留）。不对模型重新训练或修改权重。模型均可离线运行，非商业权重许可不由工作台 MIT 许可替代。

包内还包含 NumPy 2.2.6、ONNX Runtime 1.22.1 与 app-local Visual C++ 运行库；它们的声明按组件保留。FFmpeg 7.1 由固定源码以仅音频、禁用网络、无外部编解码器的配置构建，采用 LGPL 2.1，完整对应源码和重编译参数随包提供，允许用户修改与重新链接该独立组件。固定来源和模型 SHA-256 位于 `tools/offline_audio/resources.json`，完整声明与模型卡位于 `_internal/nte_music_desk/assets/offline_audio/licenses/`。

本项目的 MIT 许可适用于项目自有代码、原创图标与自行编码的示例 MIDI，不授予第三方音乐、游戏素材或外部站点内容的权利。程序图标沿用原创的琴键与音符设计，没有使用游戏截图或官方角色素材。1.3.1 的可关闭背景取自用户提供的《异环》截图，经清除 UID、相框和标注后作为 city-session.png 使用；其游戏角色和场景权利归相应权利人，不属于自有 MIT 图标素材。处理记录见 docs/APPEARANCE.md。

## 中文图片字标

`src/nte_music_desk/assets/brand-wordmark.png` 为本项目使用内置 imagegen 创建的七字图像字标，原图随源码保留。未嵌入参考页面的商业字体文件或直接复制其字标图片。设计参考和完整生成提示词见 [docs/BRANDING.md](docs/BRANDING.md)。

## 明音速度与进度滑块

`src/nte_music_desk/assets/mingyin-icon.webp` 为《异环》角色明音凛头像，取自[环世全鉴角色资料页](https://wiki.mysqil.com/characters/mingyin)的[头像文件](https://wiki.mysqil.com/images/characters/mingyin-icon.webp)，获取日期 2026-11-08。原文件保留，圆形裁切与缩放仅在控件显示时进行。角色及游戏美术权利归《异环》相应权利人，不属于本项目 MIT 授权内容；社区站点对其自有内容声明 CC BY-NC-SA 4.0，不将此声明视作游戏美术的独立再授权。

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

MusicXML 导入器依据 [W3C MusicXML 4.0 格式](https://www.w3.org/2021/06/musicxml40/) 编写。内置 twinkle.musicxml 由本项目根据同一传统旋律自行编码，不包含外部曲谱原件。
