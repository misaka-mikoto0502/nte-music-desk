# 构建与 GitHub 发布

## 本地构建

在 Windows x64 上安装带 Tcl/Tk 的 Python（推荐 python.org 的 Python 3.12），进入仓库根目录：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-build.txt
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe tools/build_windows.py
```

releases 中会生成“异环演奏工作台”目录、Windows x64 ZIP 及 SHA-256 文件。完整解压即可运行 EXE。发布时上传整个 ZIP，不能只复制 EXE 而丢掉 _internal。

使用目录便携版以便普通界面与 UAC 演奏进程共享安装资源，不使用自解压单文件管理员程序。构建方式见 [PyInstaller 目录打包说明](https://pyinstaller.org/en/stable/operating-mode.html#bundling-to-one-folder)。

安全离线自检（不会提权、联网下载或发送游戏按键）：

```powershell
& './releases/异环演奏工作台/异环演奏工作台.exe' --data-dir './test-data' --self-test './self-test.json'
```

报告应为 status=passed、frozen=true、game_input_sent=false。该检查覆盖内置资源、四种转换组合、试听文件生成和隐藏 GUI 初始化；不替代真实游戏试听。

## 上传 GitHub

源码目录包含 README、MIT 许可、第三方说明、pyproject.toml、构建依赖、src、tests、tools、docs 和 .github。可把这些内容作为仓库根目录，或解压 Source 源码包后上传。不要上传父目录的 outputs/work。

.gitignore 已排除 releases 二进制、构建环境、缓存、下载、运行记录、个人设置和日志。个人曲谱、绝对文件路径与账号信息不应加入源码仓库。release 可执行文件作为 GitHub Release 附件分发，不作为源码提交。

Actions 在 pull_request、手动触发或推送 v* 标签时运行自包含测试、构建 EXE、运行冻结自检并保存构建产物。工作流仅有 contents:read 权限，不会自动创建公开 Release；可以下载 Actions 产物后自行发布。

## 升级版本

同步修改 src/nte_music_desk/__init__.py、pyproject.toml、tools/version_info.txt 和 CHANGELOG.md。再次测试、构建，校验 ZIP 与 SHA-256。检查第三方曲谱没有被复制进资源目录。

每个功能验证完成后单独创建本地 commit，再同步版本与发布说明。1.2.0 在 feat/workbench-1.2 分支开发；本地提交与标签不会自动上传 GitHub。

更新后的发布版须额外检查普通双击、资源导入、数据目录、合成试听、UAC 子进程与停止功能；本轮只执行无游戏输入的检查。1.2.0 将既有调度规则移入统一演奏计划，新版本实机效果仍需试奏。EXE 未进行商业代码签名。
