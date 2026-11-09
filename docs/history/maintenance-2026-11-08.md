# 2026-11-08 构建与分支收尾

按使用者要求，清理已归档、已上传及已被当前实现取代的开发副本，并建立后续发布收尾规则。

## 保留布局

`.build/` 从约 5.27 GB 收敛为约 1.10 GB，根目录只保留说明和三个分类：

- `current/`：当前一套离线开发预览、Windows／Source ZIP、校验文件、验收报告和源码开发入口。
- `cache/`：原生引擎源码、固定版本编译器压缩包、FFmpeg 源码压缩包、GAME 下载包和 WebView2 SDK。
- `validation/`：当前钢琴、真实人声和受控混音语料，客观评分、三组最终冻结推理、工作流与取消任务记录。

删除了重复独立解压的应用、过期界面调整包、旧集成验收目录、多个资源暂存副本、展开的编译器及可重建的中间产物。当前原生运行资源仍保留在 `src/nte_music_desk/assets/offline_audio/`，主应用代码、开发环境和用户正常数据目录未清理。

## Git 分支

经远端更新确认，以下七条本地分支均已合并到 `origin/main`，完成收尾：

- `dev/after-2.0.0`
- `docs/2.0-presentation`
- `feat/audio-accompaniment-beta`
- `feat/mini-player-1.5`
- `feat/multitrack-1.3`
- `feat/visual-refresh-1.3.1`
- `feat/workbench-1.2`

同时删除已合并的远端 `feat/audio-accompaniment-beta`，将本地 `main` 快进到远端公开主线。保留 `main`、`release/2.0.0`、正式版本标签与发布包。当前离线功能的未发布修改仍在 `release/2.0.0` 工作区，没有上传或混入已发布标签。

## 归档与核对

GitHub v2.0.1 发布附件与本地正式包 SHA-256 一致。清理前保存了所有 Git 引用的 bundle，以及 10,523 份小型报告、脚本、日志、标注、许可和 MIDI 等记录的压缩归档及逐文件校验清单，存于仓库外私有归档。

当前运行实例关闭前保留其原路径；归并后以 `.build/current/` 为唯一当前预览入口。一个未发布预览副本暂存于私有归档，待发布确认后再按收尾规则处理。旧报告中的绝对路径保留为历史事实，实际位置通过 `.build/validation/relocations.json` 查询。

后续目录和分支规则写入 `AGENTS.md`；构建、组件准备和独立验证的默认工作目录分别改为 `.build/cache/package`、`.build/cache` 和 `.build/validation`。旧操作记录中的输出路径保留历史含义，当前开发以协作规则、发布指南及 `.build/README.md` 为准。
