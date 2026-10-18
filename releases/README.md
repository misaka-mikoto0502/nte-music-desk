# 本地发布产物

本地保留基线与正式版本产物，各版本目录互不覆盖；Source 源码包为整理后的仓库内容，不含个人数据、模型或构建环境。

当前版本：v1.3.0/NTE-Music-Desk-v1.3.0-Windows-x64.zip。运行 python tools/build_windows.py --output releases/v1.3.0 可重新构建，python tools/package_source.py 可生成源码包。

1.3.0 音频转谱为可选独立引擎，需要另行安装、接受模型许可与登录；便携包不附带模型。原曲谱导入与游戏演奏无需安装 Python。

仅本说明进入 Git；其他构建产物由 .gitignore 排除。GitHub Release 可上传 Windows x64 ZIP 与校验文件，源码仓库请上传项目文件或 Source 包内容。
