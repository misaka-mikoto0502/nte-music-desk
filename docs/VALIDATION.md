# 发布检查

## 1.1.1 · 2026-10-18

- 13 项自包含 unittest 全部通过，覆盖转换、曲库、格式导入、停止清理与隐藏 GUI 流程。
- 与 1.1.0 源码包逐文件比较：业务代码、测试、构建脚本与曲库资源一致；Python 文件仅版本常量改为 1.1.1。
- PNG、ICO 与 1.1.0 原创琴键音符图标逐字节一致；最终 EXE 的 16、24、32、48、64、128、256 像素图标资源也与原 ICO 一致。
- 最终 Windows ZIP 解压后，在无 Python/Tcl 环境变量、仅系统 PATH、中文与空格路径下运行离线自检：status=passed、version=1.1.1、frozen=true、game_input_sent=false。
- Windows 文件属性中的 FileVersion、ProductVersion 均为 1.1.1；EXE 为 Windows x64 图形程序。MusicXML 转 MIDI、拒绝覆盖原曲、内置资源保持只读均通过。
- 便携包 CRC 与 SHA-256 通过；保留的 1.1.0 ZIP 与其原校验文件一致。

此版本是发布整理更新，没有修改演奏、转换、在线曲库或界面功能。未向游戏发送按键；原有实机验证与限制仍适用。

## 1.1.0

日期：2026-10-17。

## 已执行

- 13 项自包含 unittest：原 MIDI、调度、GUI 与曲库检查，加上中文古典别名、钢琴优先排序、乐章 ZIP 自然排序与来源许可持久化，以及 MusicXML 连音、声部、休止、变速、反复房子、UTF-16、MXL/RMI/KAR、XML/ZIP 边界和 MIDI 往返。包括隐藏界面的“古典 ZIP → 自动载入第一乐章 → 切换 MusicXML → 另存 MIDI”完整流程。以模拟 Win32 接口验证失焦停止，以及琴键先于程序持有的 Shift 释放，不调用真实输入 API。
- 源码隔离模式自检：两种乐器 × 两种模式、内置 MIDI 与 MusicXML 的 42 音示例、122,120 条目录、MusicXML 转 MIDI、合成试听与 GUI 加载。
- 实际联网下载：Mutopia《致爱丽丝》单个 MIDI、《月光奏鸣曲》三乐章 ZIP，均完成下载、解析、自动转换与来源保存；只下载这两部选定作品，不发送游戏输入。
- [MusicXML 官方真实示例](https://www.musicxml.com/music-in-musicxml/example-set/)：莫扎特钢琴奏鸣曲 XML/MXL 的 51 个音符与时刻一致；舒曼《诗人之恋》359 音、勃拉姆斯样例 172 音均可导入并另存 MIDI，最大实测音符时刻偏差低于 0.5 毫秒。装饰音提示保留；舒伯特仅第一页的样例因缺失反复终点被明确拒绝。下载的示例仅用于本地验证，不进入源码或软件包。
- 最终边界复查：空拍号、小节内反复、超大科学计数法变音、XML 实体与 ZIP 路径异常均产生明确错误；普通反复、编号房子和反复时速度/divisions 恢复仍通过。
- 冻结 EXE 自检：从最终发布 ZIP 解压到含中文与空格的新目录，移除 PATH 中的 Python/Anaconda，清除 PYTHONHOME、PYTHONPATH 和 Tcl/Tk 环境变量，从另一个工作目录启动，报告 frozen=true、status=passed、game_input_sent=false。随后完成中文路径 XML → MIDI，确认拒绝覆盖原曲，且内置资源内容未被修改。
- EXE 窗口检查：原创图标、版本号、菜单、内置示例和主窗口。增加侧栏滚动以保持底部快捷键可见。
- 发布 ZIP 完整性与 SHA-256；源码 ZIP 不含 CMD、EXE、个人设置、下载、运行记录、日志或 Python 缓存。

本次软件整理没有请求游戏演奏或向游戏发送按键。使用者已确认整理前的钢琴与和弦逻辑实机可用；EXE 版 UAC 演奏仍应由使用者在自己的游戏中试奏。其他 Windows 机器和未来游戏更新不在本次验证范围内。

构建环境：Windows 11 x64、Python 3.12.4、PyInstaller 6.22.3。源码运行不依赖第三方 Python 模块；EXE 自带运行时。GitHub Actions 配置已随源码提供，本地未连接 GitHub 运行工作流。
