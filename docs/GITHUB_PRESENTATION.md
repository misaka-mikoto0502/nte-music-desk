# GitHub 首页与发布信息

本页提供 2.0.0 对外介绍及维护清单。README 和 Python 项目元数据随 Git 提交更新；GitHub 的 About、Topics、Release 名称与说明在网站单独维护，不会因 `git push` 自动同步。

## About 描述

在仓库 Code 首页右侧 About 的齿轮中，将 Description 替换为：

> 异环演奏工作台：导入本地 MIDI / MusicXML，或将音频转为 MIDI（Beta），由工具自动操控《异环》钢琴与吉他钢琴模式演奏。支持多轨试听、进度拖动、断点续播与迷你播放器。

描述不写死版本号，避免每次发版都要修改；当前版本由 README、标签和 Release 表达。不再使用“在线搜曲”“音乐下载”或“无需任何系统组件”等表述。

Topics 可使用以下标签，便于按游戏、曲谱格式和识别用途发现项目：

```text
neverness-to-everness
nte
midi
musicxml
audio-to-midi
basic-pitch
music-tools
windows
python
```

没有独立官网时 Website 可留空。主页应展示 Releases，不应把本机 `127.0.0.1` 转谱链接填作网站。

## 2.0.0 Release

- Tag：`v2.0.0`，指向已合并并核对过的发布提交。
- 标题：`异环演奏工作台 v2.0.0`。
- 说明：使用 [2.0.0 更新说明](RELEASE_NOTES_2.0.0.md)，保留音频 Beta 和本轮游戏实测跳过的边界。
- 附件：Windows x64 ZIP、Source ZIP，以及各自的 `.sha256`。Windows ZIP 是普通用户的运行包，Source ZIP 用于开发和构建。
- 发布后检查它是否为最新 Release，确认附件名称与版本一致。

2026-11-02 本次核对时，公开 About 仍包含已移除的“在线搜曲”，Topics 为空；公开最新 Release 为 v1.4.0，main 已合并 2.0.0 源码。以上是当时状态，不能据此宣称 2.0.0 的下载附件已经发布，也无需改写旧版本 Release 的历史说明。

## 后续版本维护

1. 同步应用版本、`pyproject.toml`、Windows 属性、CHANGELOG 和对应发布说明。
2. 核对 README 的版本、下载文件名、功能与限制；发布前不要让下载按钮跳到不存在的版本附件。
3. 修改帮助时同步随包副本，执行发布元数据检查。重新生成 Source ZIP 与校验文件，使附件包含最终文档；只有文档和项目介绍变化时，记录 Windows 包复用的依据。
4. 推送源码、合并到 main 后，单独发布 Release。保留原有标签和旧版说明。
5. 只有功能范围变化时才调整 About 和 Topics；它们不受版本控制，修改后需要在网页确认。

不自动上传代码、修改 GitHub 设置或发布 Release。具体构建和同步流程见 [构建与发布](RELEASING.md)。
