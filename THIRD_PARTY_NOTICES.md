# 第三方资源与运行时

本项目的 MIT 许可适用于项目自有代码、原创图标与自行编码的示例 MIDI，不授予第三方音乐、游戏素材或外部站点内容的权利。程序图标沿用原创的琴键与音符设计，没有使用游戏截图或官方角色素材。1.3.1 的可关闭背景取自用户提供的《异环》截图，经清除 UID、相框和标注后作为 city-session.png 使用；其游戏角色和场景权利归相应权利人，不属于自有 MIT 图标素材。处理记录见 docs/APPEARANCE.md。

## 曲谱与历史目录

- 内置 twinkle.mid / twinkle.musicxml 由本项目根据传统《小星星》旋律自行编码，不包含第三方录音或编曲。
- 当前开发版已删除 BitMidi、动漫公开目录和 Mutopia 的搜索下载代码及随包元数据。旧 Git 版本和已发布的旧软件仍保留历史行为，不能用新版说明替代旧版事实。
- 用户旧下载文件不删除，仅支持本地导入和读取原曲名。来源记录不等于授权证明。
- 项目不提供商业歌曲录音、第三方曲谱或转谱结果下载。合法获取输入文件、模型许可、改编与公开传播权限需分别核对。

## Windows 便携版运行时

便携版由 PyInstaller 构建，并包含构建环境对应的 Python、Tcl/Tk 及所需运行库。相关许可随 `_internal` 中收集的文件一并保留。

- [Python 许可](https://docs.python.org/3/license.html)
- [Tcl/Tk 许可](https://www.tcl-lang.org/software/tcltk/license.html)
- [PyInstaller 许可与引导器例外](https://pyinstaller.org/en/stable/license.html)

曲谱解析和按键调度使用标准库；1.3.1 的界面使用 [Pillow](https://python-pillow.github.io/) 绘制圆角和淡背景，构建所用 Pillow 13.0.0 的 MIT-CMU 许可及随包第三方许可保留在便携版 licenses 目录。`requirements-build.txt` 固定构建环境和界面依赖版本。软件与《异环》官方无关联。

## 可选音频转谱

[MuScriptor](https://github.com/muscriptor/muscriptor) 引擎代码采用 MIT，工作台调用固定版本 0.3.0 的外部命令行，不将其代码、PyTorch 或权重打入便携包。用户选择安装时在独立虚拟环境中获取依赖；相关依赖各自保留许可。

[MuScriptor 模型](https://huggingface.co/MuScriptor) 权重另受 CC BY-NC 4.0 非商用许可约束，需要用户接受上游条款并完成官方认证后下载。工作台 MIT 许可不替代权重许可，也不意味着识别结果没有原音乐的权利限制。详细配置见音频转谱说明。

MusicXML 导入器依据 [W3C MusicXML 4.0 格式](https://www.w3.org/2021/06/musicxml40/) 编写。内置 twinkle.musicxml 由本项目根据同一传统旋律自行编码，不包含外部曲谱原件。
