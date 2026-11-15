# 2.1.0 GitHub 发布指南

本版在 `release/2.0.0` 上维护，`v2.1.0` 标记本轮提交。上传材料位于本地 `releases/v2.1.0/`，当前可运行目录为 `.build/current/异环演奏工作台/`。

```powershell
git status --short --branch
git rev-parse release/2.0.0
git rev-parse 'v2.1.0^{commit}'
git push -u origin release/2.0.0
git push origin refs/tags/v2.1.0
```

推送前确认两个 `rev-parse` 输出一致。在 GitHub 从 `release/2.0.0` 向 `main` 提交合并请求，检查 Actions 通过后合并。创建 Release 时选择 `v2.1.0` 标签，标题使用“异环演奏工作台 v2.1.0 · 钢琴谱适配与界面优化”，正文复制发布目录中的 `发布正文.md`。

公开附件只需这两份，开发者可使用 GitHub 自动生成的 `Source code (zip)`。

```text
NTE-Music-Desk-v2.1.0-Windows-x64.zip
NTE-Music-Desk-v2.1.0-Windows-x64.zip.sha256
```

本地 Source ZIP 及其校验值用于复现和归档。公开前确认附件的 SHA-256 与本地清单一致，保留旧版本标签、ZIP 和录制用目录。
