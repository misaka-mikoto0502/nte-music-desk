# 音频转谱（可选）

本功能调用 [MuScriptor](https://github.com/muscriptor/muscriptor) 0.3.0 的本地命令行，识别音频中的音高、起止时间和乐器声部，生成多轨 MIDI。之后再由工作台适配成游戏键位。它不是把 MP3 改个扩展名，也不保证与原曲一致。人声、打击乐和复杂混音需要逐段试听核对。

## 一次性配置

1. 安装完整的 Python 3.10+（推荐 3.12），打开工作台左侧“音频转谱”。
2. 点击“安装 / 更新独立引擎”，选择该 Python 的 `python.exe`。工具在个人数据目录创建 `audio-engine` 虚拟环境并安装固定版本 MuScriptor；不修改原 Python 环境。PyTorch 等依赖体积较大，需要联网和足够磁盘空间。安装失败或取消后可重试。
3. 点击“模型授权页面”，在 Hugging Face 登录并接受对应模型的许可。上游代码为 MIT，模型权重另受 **CC BY-NC 4.0** 非商用许可约束；请按模型页面条款使用。工作台不附带权重，不代替你接受许可。
4. 在 PowerShell 中，使用刚安装环境的 `hf.exe` 完成登录。默认路径示例：

```powershell
& "$env:LOCALAPPDATA\NteMusicDesk\audio-engine\Scripts\hf.exe" auth login
```

令牌只交给 Hugging Face 官方登录程序，不要填写到工作台、公开日志或 GitHub。首次转谱时，上游引擎会下载已授权的权重；以后使用本地缓存。环境变量 `HF_TOKEN` 也由上游支持，但无需将它写进本项目配置。

已有引擎时，可以直接选择安装了 MuScriptor 的 `python.exe` 或 `muscriptor.exe`。工作台支持单独引擎环境，便携包自身不包含 Python 开发环境、PyTorch 或模型。

## 日常流程

1. 选择 WAV、MP3、FLAC、OGG、M4A 或 AIFF 文件。能否解码具体文件取决于引擎与 libsndfile，失败时可先转成 WAV。文件上限 512 MB；推荐先准备 15–30 秒片段。本版不在导入前裁音频。
2. CPU 先选 `small + cpu`。`medium` 和 `large` 更占资源；GPU 需自行配置匹配的 PyTorch/CUDA，不能仅靠选择 `cuda` 获得 GPU 支持。
3. 点击“开始音频转谱”。进度条表示任务运行中，不表示准确完成百分比；下方显示引擎输出。可取消，取消会终止本任务的进程树并丢弃未完成 MIDI。
4. 成功且输出通过 MIDI 校验后，自动导入工作台。打开多轨工作区，查看各乐器、静音不需要的声部、指定旋律/低音，再对比原谱和按键时序试听。转谱不会自动开始游戏演奏。
5. 选择适合的游戏乐器，先游戏试奏，再完整演奏。

## 保留内容与边界

- 转谱默认不限制为钢琴乐器、不网格量化、不补休止，单批次连续识别以减少分段声部跳变。将多乐器转成钢琴是工作台后续适配步骤。
- 每次结果保存在个人数据目录 `transcriptions/<任务编号>/original.mid`，附 `provenance.json`（源文件名、散列、模型选项、输出散列等）和经过令牌遮盖的日志尾部。不会复制源音频或向工作台自己的服务上传音频。
- 工作台保留已有 MIDI 中的力度，试听会反映相对力度；MuScriptor 本身不恢复原曲力度。游戏琴键也无法表达 MIDI 踏板、连续力度或原乐器音色。
- 原始 MIDI 与游戏适配结果分开。36 键音域折回、声部删减、钢琴 Shift 分组都可能改变听感，报告中的排程偏差不是 AI 识别准确率，也不是游戏实际发声测量。
- 本轮已验证真实子进程的结果导入、坏文件拒绝和取消清理；未获得模型授权前，不声称真实模型识别质量已经验收。

官方说明：[安装与模型许可](https://github.com/muscriptor/muscriptor)、[模型主页](https://huggingface.co/MuScriptor)、[0.3.0 发布信息](https://pypi.org/project/muscriptor/0.3.0/)。
