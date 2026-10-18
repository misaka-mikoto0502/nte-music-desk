# 第三方资源与运行时

本项目的 MIT 许可适用于项目自有代码、原创图标与自行编码的示例 MIDI，不授予第三方音乐、游戏素材或外部站点内容的权利。程序图标沿用原创的琴键与音符设计，没有使用游戏截图或官方角色素材。

## 曲谱与曲库

- 内置 `twinkle.mid` 根据传统《小星星》旋律自行编码，用作功能测试，不包含录音或第三方编曲。
- 《三叶的主题曲》《黄昏之时》作为搜曲快捷入口，不随源码或软件包分发原始曲谱。下载文件及来源记录保存在用户自己的数据目录。导入的曲谱按各自来源信息使用。
- [BitMidi](https://bitmidi.com/)：[项目代码](https://github.com/feross/bitmidi.com)。附带的目录快照来自公开站点地图，2026-10-17 共 113,229 个条目；只保存标题与链接标识，没有复制整站 MIDI。
- [动漫 MIDI 公开目录](https://murashin.sakura.ne.jp/cgi-bin/upload.cgi?dir=&page=Main&sort=filename)：目录正文允许个人非商业用途直接链接，并要求注意服务器负载。附带快照为 6,769 个条目。程序只在用户选择时下载单个 MIDI，不批量下载曲库文件。
- [Mutopia Project](https://www.mutopiaproject.org/)：读取其公开 musiccache.dat 元数据，2,124 个原始条目中 2,122 个提供 MIDI 或 MIDI ZIP，796 个标有 Piano。随包只保留曲目、作曲家、乐器、编号、许可与文件链接，不保存维护者邮箱等字段。选定下载的单曲或乐章包保存来源与许可记录，各作品按原页声明使用；参见 [许可说明](https://www.mutopiaproject.org/legal.html)。
- 各来源不提供本工具的服务保证；文件和访问方式可能改变。目录快照不代表其中曲目的再分发许可。来源网站的权利与使用条件独立于本项目许可。

## Windows 便携版运行时

便携版由 PyInstaller 构建，并包含构建环境对应的 Python、Tcl/Tk 及所需运行库。相关许可随 `_internal` 中收集的文件一并保留。

- [Python 许可](https://docs.python.org/3/license.html)
- [Tcl/Tk 许可](https://www.tcl-lang.org/software/tcltk/license.html)
- [PyInstaller 许可与引导器例外](https://pyinstaller.org/en/stable/license.html)

源码运行不需要第三方 Python 运行时模块。`requirements-build.txt` 中列出的工具只用于构建。软件与《异环》官方无关联。

MusicXML 导入器依据 [W3C MusicXML 4.0 格式](https://www.w3.org/2021/06/musicxml40/) 编写。内置 twinkle.musicxml 由本项目根据同一传统旋律自行编码，不包含外部曲谱原件。
