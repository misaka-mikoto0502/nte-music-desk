# 2.0.1 发布验证

2026-11-08 · Windows x64

## 验证范围

本版主要变更为主窗布局、共享控件、引导和显示时机。发布检查使用独立数据目录，不发送游戏按键。

此前的 [2.0 验证记录](VALIDATION_2.0.md) 保留历史音频与人工反馈证据。

## 软件检查结果

| 检查 | 本轮结果 |
| --- | --- |
| Python 回归 | 118 项通过，耗时 25.536 秒 |
| JavaScript | ETA、加速与回退、参数边界、自动备份、另存为路由、取消和写入失败检查通过 |
| 版本与随包帮助 | 应用、pyproject、Windows 文件属性均为 2.0.1；六份帮助与 docs 对应文件一致 |
| 原生控件与布局 | 旧方案与偏好迁移、引导、页面恢复、按钮状态及固定尺寸、原生下拉值／禁用状态和图像生命周期回归通过 |
| 本轮界面复核 | 源码阶段已观察主窗和实际下拉列表；原生弹出列表留白通过 Tcl 查询确认 |
| Windows 独立解压 | SHA-256、ZIP CRC、中文与空格路径、隔离 PATH、冻结自检、片段转换和资源只读检查通过 |
| 冻结界面与功能 | 两种乐器、四种方案、MusicXML、多轨、音频设置、迷你播放器、四种基础色、圆角控件及无游戏输入的试听检查通过 |
| 实际轻量转谱 | 使用新包资源在系统 WebView2 执行 arpeggio WAV：20 音，自动保存与下载 MIDI 一致，3 组窗口布局检查通过 |

本轮真实转谱使用均衡预设和加速路径。完整音频质量基准、其他预设与回退流程的历史实测见 2.0 验证记录。可选高级引擎的授权模型推理未在本轮重新执行。

## 发布产物与复现

产物目录为 `releases/v2.0.1/`，包含独立 Windows 便携包、Source 源码包及各自的 SHA-256 文件。源码包按明确的目录清单生成，收录开发、测试、构建、部署和历史文档，排除个人数据、模型、虚拟环境与缓存。2.0.0 的历史包继续保留。

Windows 包：`NTE-Music-Desk-v2.0.1-Windows-x64.zip`，24,213,285 字节；SHA-256：

```text
5004104f56ae71e4055de83295c8443104207b55b25ddb1dd474c184a0ac93da
```

复现命令：

```powershell
python -m unittest discover -s tests -v
node tools/light_audio_web/test.mjs
node tools/light_audio_web/test_downloads.mjs
python tools/check_release.py
python tools/build_windows.py
python tools/verify_release.py
python tools/package_source.py
```

真实轻量转谱使用维护者已有的合成测试音频，通过 `tools/check_audio_window.py` 的 `--audio`、`--assets`、`--expected-notes 20` 与 `--output` 指定输入、新包资源和独立输出目录。该检查不会向游戏发送按键。

本机机器可读证据保存在 `.build/release-validation-2.0.1.json`，本轮测试与构建日志及轻量转谱证据保存在 `.build/release-2.0.1/`。构建细节见 [发布说明](RELEASING.md)。

## 人工待验收

- 普通双击启动时的 UAC 确认和实际游戏操作。
- 新布局下悬浮窗按钮、拖动时的前台保持，以及 F7／F8 在游戏中的操作。
- 吉他钢琴模式、并行发声数量、钢琴绝对音高及真实曲目的听感。

软件回归和隔离自检通过不等于游戏实测或音乐准确率通过。
