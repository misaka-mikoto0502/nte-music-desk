# 音频实测记录 · 2026-10-22

本记录区分真实模型推理、流程测试与游戏实听。当前为 1.5 开发阶段，不是最终版质量承诺。

## 环境和素材

- Windows、Python 3.12.4、PyTorch 2.8.0+cu128、RTX 4060 Laptop GPU；Open-Unmix 1.3.0、MuScriptor 0.3.0 medium。
- MuScriptor 模型修订：f32236969308476e01fd3aae67357de5feb05a2d。用户自行接受门控条款并登录，工具仅检查访问权限；未在记录中保存令牌。
- 钢琴基准为自行编写的 8.5 秒双声部短句，20 个已知 MIDI 音符，保留开头休止。音频由 [VSCO 2 CE](https://github.com/sgossner/VSCO-2-CE) 的三份 CC0 钢琴单音采样生成，不使用商业歌曲或其转谱结果。
- 采样录制：Sam Gossner、Simon Dalzell；剪辑：Elan Hickler。采样许可见 [CC0 原文](https://github.com/sgossner/VSCO-2-CE/blob/master/LICENSE)，音高映射来自官方 SFZ。生成器把实际 URL、SHA-256 与映射保存到测试目录 fixture.json。
- 分离使用 [UMX-HQ 官方权重记录](https://zenodo.org/records/3370489)。实查 API metadata.license.id=mit-license，四份文件均匹配官方发布者校验值；不是许可未核实的 ViperX 或非商业 UMXL。

## 真实推理结果

| 路径 | 已知音符 | 输出音符 | 匹配 | 漏音 | 额外音符 | 起音误差中位数 | 结束误差中位数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 钢琴音频直接 → MuScriptor | 20 | 21 | 18 | 2 | 3 | 约 19.8 ms | 约 219.8 ms |
| 同一钢琴音频 → UMX-HQ → MuScriptor | 20 | 21 | 18 | 2 | 3 | 约 19.8 ms | 约 219.8 ms |

规则：有音高音符的一对一匹配，MIDI 音高必须相同，起音容差 100 ms；忽略鼓组。Precision=0.8571、Recall=0.9、起音/音高 F1=0.8780。结束时间只报告误差，不参与匹配。此分数只描述这一份样本的音符匹配，不是“原曲还原率”。

直接转谱整个流程约 12.46 秒，其中引擎日志中的 transcribe total 为 1.24 秒；经过分离的整个流程约 17.78 秒。这些时间包含本轮启动和文件处理，使用已缓存权重，不是所有机器或长歌曲的速度指标。单独对 6 秒自制正弦音频运行 UMX-HQ，缓存后整个调用约 5.03 秒，两份输出都保留 264600 帧、44100 Hz。真实模型已加载和执行，但这不是歌声分离质量评分。

失败样本同样保留：第一份纯正弦短句运行 MuScriptor 后没有可用音符，程序明确拒绝空结果。没有修改算法去套这一首旋律，也没有把失败算作成功。

## 如何复现

在可选音频引擎环境生成测试素材（首次从官方仓库获取三份 CC0 单音采样）：

```powershell
python tools/create_audio_benchmark.py --output .build/piano-benchmark
```

在工作台导入生成的 reference.wav，先用“已有伴奏 / 纯音乐”识别，再选“原唱 / 含人声”验证分离路径。后者是流程对照，样本没有真实歌声，不应据此判断人声去除效果。对未经游戏适配的输出 MIDI 执行：

```powershell
python tools/evaluate_transcription.py .build/piano-benchmark/reference.mid "输出的伴奏.mid" --output .build/notes-report.json
```

## 仍需验收

真实独唱、合唱、弦乐/鼓组 BGM、不同混音及长片段；需要具备相应使用权的素材。GAME 的真实歌声识别与合并质量继续为 Beta，本轮只用夹具验证双路合并与失败保留伴奏。此钢琴样本上分离没有提高音符匹配，因此已有伴奏优先直转，不无条件增加分离。

游戏音域折回、删音、Shift 分组和最终游戏发声单独验收。对照试听的轻量合成音只辅助检查音高与节奏；模型、采样及听感的权利和质量判断不能由软件测试替代。
