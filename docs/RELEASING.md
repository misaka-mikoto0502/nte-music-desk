# 构建与 GitHub 发布

## 大版本长期分支

每个大版本维护一条长期代码分支。当前 `2.0.1`、`2.0.2`、`2.1.0` 等 2.x 版本持续提交到已有的 `release/2.0.0`；进入 3.0.0 时再创建 `release/3.0.0`。小版本不创建新发布分支，使用 `v2.0.1`、`v2.0.2` 等标签保留准确快照。通过正常提交更新同一分支的最新文件，保留历史和回退能力。协作规则同时记录于仓库根目录 `AGENTS.md`。

## 本地构建

开发期间可先运行 `python tools/check_workflows.py` 验证内置和合成样例，再使用 `build_windows.py --output <验证目录> --work <构建目录>` 创建独立验证包。运行 `verify_release.py --archive <验证ZIP> --report <独立报告.json>` 可将证据写到单独位置，保留正式版本的验证记录。

在 Windows x64 上安装带 Tcl/Tk 的 Python（推荐 python.org 的 Python 3.12），进入仓库根目录：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-build.txt
.venv/Scripts/python.exe -m pip install -e .
.venv/Scripts/python.exe -m unittest discover -s tests -v
.venv/Scripts/python.exe tools/check_release.py
.venv/Scripts/python.exe tools/build_windows.py
.venv/Scripts/python.exe tools/verify_release.py
.venv/Scripts/python.exe tools/package_source.py
```

releases/v2.0.1 中会生成“异环演奏工作台”目录、Windows x64 ZIP、Source ZIP 及各自 SHA-256 文件。完整解压即可运行 EXE。发布时上传整个 ZIP，不能只复制 EXE 而丢掉 _internal。已有同名 ZIP 默认拒绝覆盖；确认重建才传 --overwrite。源码与应用版本、Windows 属性和随包帮助先由 check_release.py 校验。

使用目录便携版以便启动提权后的界面与演奏进程共享安装资源，不使用自解压单文件管理员程序。构建方式见 [PyInstaller 目录打包说明](https://pyinstaller.org/en/stable/operating-mode.html#bundling-to-one-folder)。

安全离线自检（不会提权、联网下载或发送游戏按键）：

```powershell
& './releases/v2.0.1/异环演奏工作台/异环演奏工作台.exe' --data-dir './test-data' --self-test './self-test.json'
```

报告应为 status=passed、frozen=true、game_input_sent=false。该检查覆盖内置资源、两种乐器与四种模式、试听、圆角控件、四种基础色和隐藏 GUI 初始化；不替代真实游戏试听。

## 上传 GitHub

源码目录包含 README、MIT 许可、第三方说明、pyproject.toml、构建依赖、src、tests、tools、docs 和 .github。可把这些内容作为仓库根目录，或解压 Source 源码包后上传。不要上传父目录的 outputs/work。

.gitignore 已排除 releases 二进制、构建环境、缓存、下载、运行记录、个人设置和日志。个人曲谱、绝对文件路径与账号信息不应加入源码仓库。release 可执行文件作为 GitHub Release 附件分发，不作为源码提交。

Actions 在 pull_request、手动触发或推送 v* 标签时运行自包含测试、构建 EXE、运行冻结自检并保存构建产物。工作流仅有 contents:read 权限，不会自动创建公开 Release；可以下载 Actions 产物后自行发布。

README、项目简介和 GitHub 首页信息需要分别维护：README 与 `pyproject.toml` 随源码提交，网站 About、Topics 和 Release 说明需单独保存。当前推荐描述、标签及对外发布清单见 [GitHub 首页与发布信息](GITHUB_PRESENTATION.md)。

## 升级版本

同步修改 src/nte_music_desk/__init__.py、pyproject.toml、tools/version_info.txt 和 CHANGELOG.md。再次测试、构建，校验 ZIP 与 SHA-256。检查第三方曲谱没有被复制进资源目录。

更新 docs 中的当前使用说明后，将对应六份帮助同步到 src/nte_music_desk/assets；过期副本会阻止打包。执行 `node tools/light_audio_web/test.mjs` 检查 ETA、回退与共享参数。修改轻量页面/算法时，在 tools/light_audio_web 内 npm ci、npm run build 并提交生成资源与清单；未改页面时直接复用已校验资源，不需要把 Node 放进便携包。

## v2.0.1 本地定版

2026-11-08 使用者确认界面后，将本轮全部改进统一定为最终 2.0.1，发布分支为 release/2.0.0。更新说明使用 docs/RELEASE_NOTES_2.0.1.md，检查结果使用 docs/VALIDATION_2.0.1.md；新产物写入 releases/v2.0.1。初始本地检查点保存在 archive/v2.0.1-initial-20261108 及私有备份中，最终 v2.0.1 标签指向已检查的发布提交。GitHub 推送、附件和正文操作见 [发布指南](PUBLISH_2.0.1.md)。

## v2.0.0 发布准备（历史记录）

当时分支 release/2.0.0，整合之前 1.5 开发期间的全部变更。更新说明用 docs/RELEASE_NOTES_2.0.0.md，软件证据与人工待验收项用 docs/VALIDATION_2.0.md。旧分支、v1.5.0 标签和历史包保留，不挪动、不覆盖。

GitHub Release 附件上传 releases/v2.0.0 下 Windows x64 ZIP、Source ZIP 和两个 SHA-256 文件。源码按正常 Git 流程提交/合并到准备发布的分支，再在该提交建立 v2.0.0 标签；不要把整个 releases 或 .build 放进源码。当前仅本地准备，不代上传或创建标签，待使用者决定发布时间。

Actions 会执行 Python/JavaScript 回归、元数据校验、Windows 构建、独立解压验证和源码打包，保存 ZIP 与校验文件；不发布公开 Release。自动检查不代表 UAC/游戏鼠标操作、独占全屏覆盖或音乐准确率已由用户验收。

以下版本记录为历史，不能用其路径和描述代替 2.0 更新说明。

每个功能验证完成后单独创建本地 commit，再同步版本与发布说明。1.3.0 在 feat/multitrack-1.3 分支开发；本地提交与标签不会自动上传 GitHub。

1.3.1 界面更新位于 feat/visual-refresh-1.3.1。构建环境新增 Pillow，收集其完整许可证；保留 1.3.0 产物，避免覆盖可回退版本。

更新后的发布版须额外检查普通双击、资源导入、数据目录、合成试听、启动 UAC、迷你播放器、暂停与停止功能；本轮只执行无游戏输入的检查。1.3.0 的新增多音实机效果和授权模型真实推理单独验收，不能用进程夹具测试代替。EXE 未进行商业代码签名。

音频引擎、权重、登录缓存、个人转谱和 Python 虚拟环境不得放进源码包或便携包。软件须附带音频配置说明和上游许可边界。冻结自检要覆盖多轨窗口、音频配置和静音定位，明确其自身不执行模型推理；外部引擎的真实推理单独记录。

本地构建后运行 `python tools/verify_release.py`，核对 ZIP 散列、CRC、独立解压、隔离环境启动、片段转换和资源只读。默认读取当前版本 releases/v<版本> 目录，其他位置可用 --archive 指定。

## v1.4.0 发布范围

开发分支 feat/audio-accompaniment-beta。在 releases/v1.4.0 独立生成 Windows 包，保留历史版本。在线搜曲、下载及目录资源均已移除；可选音频识别仍属实验功能，原唱分离停用。发布说明使用 docs/RELEASE_NOTES_1.4.0.md，不能宣传已完成高保真模型或原唱分离验收。

构建使用干净资源副本，排除本机 __pycache__。独立验证还检查不包含曲库快照、个人数据目录和模型权重。Source 包和 Windows 包均不得包含 .build、outputs 或父目录 work。

## v1.5.0 发布范围

此处对应此前的本地检查点，用户决定继续完善后再定稿。后续音频源码已加入 UMX-HQ 分离、双路输出和同位置试听；开发检查包仅放在 .build/dev-audio-1.5，不移动已有标签或覆盖 releases/v1.5.0。最终发布时需重新确定版号并核对源码、标签和包的一致性。

分支 feat/mini-player-1.5；独立生成 releases/v1.5.0，旧包保留。应用使用普通清单和启动时的 ShellExecute runas，在 GUI 创建前请求权限；离线自检和转换不提权，不使用 requireAdministrator 清单强制所有命令请求 UAC。演奏子进程只继承现有管理员权限。

发布前核对主窗最小化后的小窗显示、默认位置、暂停时间轴及 Shift 释放；实际 UAC 由用户手动确认，不自动点击。普通顶层窗不保证覆盖独占全屏，发布说明必须写明推荐无边框全屏以及独占全屏的 F7/F8 操作。离线检查不能当作游戏兼容性或权限提示的实机验收。

开发整合检查点可用 `python tools/package_source.py --output .build/dev-integrated-1.5/NTE-Music-Desk-1.5-dev-integrated-Source.zip`。已有输出默认拒绝覆盖；正式明确替换时才使用 --overwrite。源码包需保留 .gitattributes、C# 宿主源码、指定 SDK 文件及完整许可，不能捎带 node_modules 或个人运行数据。
