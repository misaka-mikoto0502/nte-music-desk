# 2.0.2 GitHub 发布操作

此页记录 2.0.2 的发布操作。最新版本的发布步骤见 [2.1.0 发布指南](PUBLISH_2.1.0.md)。2.0.2 的附件在 `releases/v2.0.2/`，以独立 `v2.0.2` 标签保留快照。

## 推送代码与标签

先确认本地版本提交和 `v2.0.2` 指向一致，再执行：

```powershell
git status
git log -1 --oneline
git rev-parse 'v2.0.2^{commit}'
git push -u origin release/2.0.0
git push origin refs/tags/v2.0.2
```

不新建 2.0.2 分支，不使用强制推送，不移动旧标签。将 `release/2.0.0` 合并到 `main`，使首页 README 和默认代码包含本版更新；Release 的源码仍以 `v2.0.2` 标签为准。

## 创建 Release

- 标签：`v2.0.2`。
- 标题：`异环演奏工作台 v2.0.2 · 完整离线转谱与后台演奏`。
- 正文：复制发布目录内的 `发布正文.md`，其文档链接已转成标签地址。
- 作为正式版本发布；音频识别功能本身仍在正文中保留 Beta 说明。
- 附件：下面四个文件。

```text
NTE-Music-Desk-v2.0.2-Windows-x64.zip
NTE-Music-Desk-v2.0.2-Windows-x64.zip.sha256
NTE-Music-Desk-v2.0.2-Source.zip
NTE-Music-Desk-v2.0.2-Source.zip.sha256
```

`SHA256SUMS.txt` 可选一并上传，用于集中核对。`verification.json` 是不含个人路径的发布检查摘要，可留作维护记录；完整本机日志保留在 `.build/validation`。不要上传 `.build`、构建环境、模型散文件或个人运行数据。模型及运行环境已在 Windows ZIP 内，Source ZIP 保留开发与重建资料。

## 上传后核对与录制

核对 `main`、`release/2.0.0`、标签目标及附件校验值。历史正式标签和附件保留供回退；当前大版本分支继续用于后续小版本。GitHub 上传完成后再按 AGENTS.md 清理已合并的临时分支及过期构建记录。

原展示提纲见 [2.0.2 标签](https://github.com/misaka-mikoto0502/nte-music-desk/blob/v2.0.2/docs/DEMO_2.0.2.md)。录制版本以 `releases/v2.0.2/` 中的归档运行说明为准。
