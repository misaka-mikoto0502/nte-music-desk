# 2.0.1 GitHub 发布操作

本次发布使用统一后的 `release/2.0.0` 分支与本地 `v2.0.1` 标签。上传目录为 `releases/v2.0.1/`。发布说明使用 [RELEASE_NOTES_2.0.1.md](RELEASE_NOTES_2.0.1.md)，验证记录使用 [VALIDATION_2.0.1.md](VALIDATION_2.0.1.md)。

## 1. 推送当前源码和标签

2.0.1 属于 2.x，复用 `release/2.0.0`；后续 2.0.2、2.1.0 也继续更新这条分支，仅使用各自版本标签。

在项目根目录手动执行：

```powershell
git status
git push -u origin release/2.0.0
git push origin refs/tags/v2.0.1
```

这两个 push 将发布分支和指定标签上传到 GitHub。无需推送全部历史标签，不使用强制覆盖。初始本地 2.0.1 检查点已经另行归档，不能把旧安装包当作本次附件。

如需让仓库首页 README 同步当前版本，在 GitHub 将 `release/2.0.0` 合并到 `main`。Release 的源码始终以已推送的 `v2.0.1` 标签为准。

## 2. 创建 GitHub Release

进入仓库 Releases，创建新 Release：

- 标签：选择已推送的 `v2.0.1`。
- 标题：`异环演奏工作台 v2.0.1`。
- 正文：复制 `docs/RELEASE_NOTES_2.0.1.md` 内容。正文中的相对文档链接在 GitHub Release 编辑器中可改成仓库 `blob/v2.0.1/docs/...` 链接。
- 附件：上传下面四个文件。

```text
NTE-Music-Desk-v2.0.1-Windows-x64.zip
NTE-Music-Desk-v2.0.1-Windows-x64.zip.sha256
NTE-Music-Desk-v2.0.1-Source.zip
NTE-Music-Desk-v2.0.1-Source.zip.sha256
```

Windows ZIP 是普通用户运行包；Source ZIP 包含项目源码、开发构建工具和历史文档。GitHub 自动生成的 Source code 附件可保留。

`releases/v2.0.1/发布正文.md` 是已替换文档链接、可直接复制到 Release 编辑器的正文；`SHA256SUMS.txt` 可用于集中核对散列。不要上传运行数据、构建环境或整个 `.build`。

## 3. 发布后核对

确认标签对应本轮最终提交，两个 ZIP 和校验文件均可下载。Windows ZIP 需完整解压并保留 `_internal`。公开说明继续保留音频 Beta、误音和游戏实机待验收边界，具体参考验证记录。

源码、提交和发布材料在本地整理完成；GitHub 推送与公开发布由维护者执行。
