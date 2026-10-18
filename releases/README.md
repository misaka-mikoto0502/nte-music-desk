# 本地发布产物

本地保留已发布基线与新版本产物。v1.1.0、v1.1.1 与 v1.2.0 目录互不覆盖；Source 源码包为整理后的仓库内容。

当前版本：v1.2.0/NTE-Music-Desk-v1.2.0-Windows-x64.zip。运行 python tools/build_windows.py --output releases/v1.2.0 可重新构建，python tools/package_source.py 可生成源码包。

仅本说明进入 Git；其他构建产物由 .gitignore 排除。GitHub Release 可上传 Windows x64 ZIP 与校验文件，源码仓库请上传项目文件或 Source 包内容。
