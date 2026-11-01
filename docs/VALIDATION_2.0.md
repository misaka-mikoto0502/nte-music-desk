# 2.0 发布验证 · 2026-11-01

本次按 2.0.0 整理本地发布候选，不自动推送 GitHub、创建公开 Release 或移动旧标签。当前分支 release/2.0.0，完整保留原 1.5 开发提交。

## 软件检查

所有检查使用自制样本和隔离数据目录，不向游戏发送输入，不操作 UAC，不运行个人歌曲。

| 检查 | 结果 |
| --- | --- |
| Python 回归 | 仓库内 94 项全部通过；预检源码 ZIP 独立解压后再次运行 94 项，全部通过 |
| JavaScript | ETA 测速/停滞、WASM 初始化失败和运行失败回退、CPU 失败、共享文件/片段/预设边界通过 |
| 从源码重建轻量资源 | 2,332,937 字节，生成脚本、模型、许可和清单与已提交资源一致 |
| 实际 WebView2 流程 | 使用最终包内宿主及页面资源，配合当前同源 HTTP 后端；解码、重采样、推理、保存、下载与恢复通过，具体见下表 |
| 页面布局 | 七次成功转换各检查 1280×720、1000×650、900×600；无文档滚动、面板溢出或页脚遮挡，下载按钮可见 |
| Windows 冻结包 | 中文/空格路径独立解压、仅系统 PATH 启动、隐藏 GUI 初始化、两种乐器/四种模式、MusicXML 片段转换通过；资源与当前源码一致且运行前后未改写 |
| 版本与原图标 | 应用、pyproject 与实际 EXE 的 FileVersion/ProductVersion 均为 2.0.0；icon.png/icon.ico 与旧版相同；六份随包帮助与 docs 同步 |
| 包完整性 | Windows ZIP 的 SHA-256/CRC、源码 ZIP CRC 通过；不含用户音频/曲谱、账号令牌、node_modules、开发环境或高级模型权重。只附自行编码的小星星示例及明确列明的轻量模型 |
| 发布保护 | Windows/Source 同名 ZIP 再次生成均被拒绝，需明确 --overwrite；旧包和标签未覆盖 |
| 高级引擎环境 | MuScriptor 0.3.0、Open-Unmix 1.3.0、ONNX Runtime、PyTorch 和解码器可加载；当前诊断未发现 MuScriptor 权重缓存，未下载模型或重跑高级推理 |

### 实际转谱与结果保存

| 自制输入 / 设置 | 输出音符 | 检查 |
| --- | ---: | --- |
| arpeggio WAV，均衡、WASM | 20 | 保存与实际下载字节相同 |
| triads WAV，均衡、WASM | 16 | 保存与实际下载字节相同 |
| 同一 triads WAV，实际缺失 WASM | 16 | 自动 CPU 回退；与加速结果 MIDI 字节完全相同 |
| arpeggio WAV，弱音＋24ms 对齐 | 28 | 参数记录、候选谱、对齐前谱保留；下载一致 |
| arpeggio WAV，突出旋律 | 16 | 保存/下载、参数记录正常 |
| arpeggio WAV，首次推理后取消 | 无文件 | 解除忙碌，不保存或导入半成品 |
| 同一自制 arpeggio 的 MP3 | 19 | 格式解码、保存、下载及布局通过 |
| 同一自制 arpeggio 的 FLAC | 20 | 格式解码、保存、下载及布局通过 |

这些输出数量是流程回归数据，不是正确音符数量。进一步对同一 arpeggio 的 16 音参考谱，以同音高、起音容差 100ms 一对一匹配：WAV/FLAC 都匹配 16 音、额外 4 音，F1=0.889；MP3 匹配 16 音、额外 3 音，F1=0.914。这不能推出 MP3 普遍更准，也不代表原曲听感还原率；本轮不更改默认识别阈值，继续标为 Beta。

### 发布附件与复现

Windows 包：`releases/v2.0.0/NTE-Music-Desk-v2.0.0-Windows-x64.zip`，24,260,097 字节，解压应用 52,690,988 字节。

SHA-256：`121e4c974a9e1c69306fdce5c37d66d9122f1adde6925c523bbe490cc16854ee`。Source ZIP 和两份校验文件放在同一版本目录，最终源码包包含本检查说明；不把源码包自身散列写进包内文档。

复现入口：`python -m unittest discover -s tests -v`、`node tools/light_audio_web/test.mjs`、`python tools/check_release.py`、`python tools/verify_release.py`。`tools/check_audio_window.py` 可对权利明确的短音频运行真实转谱流程，支持 --without-wasm、--profile、--align、--cancel；需要系统 WebView2。

本地详细证据位于 .build/release-2.0-tests.log、source-2.0-validation.log、release-validation-2.0.0.json、release-2.0-qa/；它们不进入 Git 或发布附件。CI 已补入 JS/元数据、独立冻结验证和源码打包步骤，本轮尚未在 GitHub 远程执行，不将本地通过描述为 Actions 已通过。

## 人工反馈与尚待验收

- 使用者此前已确认：主窗 MIDI/音频拖入成功；窗口正常弹出；钢琴《小星星》发声及 F7 暂停/继续、F8 停止正常；更早的吉他钢琴《小星星》发声正常。
- 以上是使用者反馈，没有新 2.0 包的运行日志来证明版本归属，不能写成 2.0 全部实机通过。10 月 30 日曾有一次 UAC 取消，之后的成功反馈单独保留，两者不相互覆盖。
- 待使用者方便时确认：新包悬浮窗按钮“演奏 → 暂停 → 继续 → 停止”，点击是否保持游戏前台，演奏过程中是否没有再次 UAC；新包吉他钢琴模式与识别结果的和弦听感。
- 尚未测定：游戏 12–36 音的可靠实际同时发声数、钢琴绝对音高。软件发送计数与合成试听不能替代这些结论。
- 高级引擎已有真实 MuScriptor/UMX-HQ 短句记录，未完成真实歌声双路识别、复杂混音的普遍质量验收，不作为 2.0 稳定准确率承诺。

本轮只完成可独立检查的部分，不会为了出包把以上项目标为通过。历史检查见 [1.5 统一检查](INTEGRATION_1.5.md) 和 [游戏记录](GAME_VALIDATION_1.5.md)。
