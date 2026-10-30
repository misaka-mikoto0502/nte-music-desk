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

## 追加：CPU 与轻量候选比较

同一份 8.5 秒 / 20 音钢琴基准，未手工修改模型输出。开发环境、缓存和初次导入状态影响耗时，以下不是端到端安装/启动时间，也未测低配机器。

| 方案 | 设备 | 匹配 / 漏音 / 额外音 | 起音/音高 F1 | 起音误差中位数 | 结束误差中位数 | 本次计时 |
|---|---|---|---:|---:|---:|---|
| MuScriptor medium，约 306.5M 实际参数 | CPU，4 线程，禁用 GPU | 18 / 2 / 3 | 0.8780 | 19.8 ms | 219.8 ms | 已缓存权重加载约 2.94 秒；推理约 7.71 秒 |
| Basic Pitch 0.4.0，官方 230,444 字节 ONNX | CPU / ONNX Runtime | 20 / 0 / 12 | 0.7692 | 6.8 ms | 54.5 ms | predict 调用约 1.38 秒，含 ONNX 会话创建和音频读取 |
| High-resolution Piano Transcription，约 42.95M 参数 | CPU，4 线程 | 20 / 0 / 5 | 0.8889 | 3.9 ms | 54.3 ms | transcribe 调用约 4.12 秒；含模型加载、音频读取约 13.63 秒 |

medium 使用 PyTorch 2.8.0+cu128 的 CPU 路径，CUDA_VISIBLE_DEVICES=-1、torch.set_num_threads(4)、OMP_NUM_THREADS=4、MKL_NUM_THREADS=4；不是无 CUDA 软件包的干净机器安装验收。实际参数通过 sum(p.numel()) 计数。Basic Pitch 使用默认起音/帧阈值，没有为本样本调参，手动配置 ONNX 依赖，未安装 TensorFlow；0.4.0 的 Python 依赖声明在 3.12 上会要求 TensorFlow，正式组件不能直接照搬 pip 的默认解析。

Basic Pitch 的官方代码、模型与 NOTICE 随 wheel 提供，Apache 2.0 来源见 [官方仓库](https://github.com/spotify/basic-pitch)。本样本额外音明显更多，暂不接入为默认引擎。钢琴专用候选的 [官方检查点](https://zenodo.org/records/4034264)标注 CC BY 4.0，文件 171,966,578 字节，校验发布者 MD5 后测得 SHA-256 c3fa9730725bf4a762f1c14bc80cd5986eacda01b026f5a4a2525cd607876141；但 [推理代码仓库](https://github.com/qiuqiangkong/piano_transcription_inference)缺少 LICENSE，且 [补充许可的上游问题](https://github.com/qiuqiangkong/piano_transcription_inference/issues/25)尚未解决。只作隔离研究，未复制到产品、未打包或替换默认引擎。

另比较 medium 的 beam=1/2/4 与自动/钢琴乐器提示，共六种设置：均为 18 个匹配、2 个漏音、3 个额外音，没有证明加大搜索宽度能改善该样本。发现末尾和弦存在约 10 ms 的短音，结束误差中位数不能完整反映这一问题；尚未采用按曲手修或无条件延长尾音。后续需增加持续时间、尾部误差及更多测试短句，再决定通用修复。

large 在用户追加 1B 上限时下载已完成，未加载推理，随后清理本轮缓存并移除调用入口。部署约束和未完成项见 AUDIO_DEPLOYMENT.md；以上 CPU 实验不等于已经交付无需 Python 的音频组件。

## 追加：已接入的 1.51 MB 轻量 Beta

采用固定 npm @spotify/basic-pitch 1.0.1 的官方 TensorFlow.js 模型及 Apache 2.0 代码，使用 tfjs-core/converter/backend-cpu 3.21.0，移除完整 Python、Node 运行时、GPU/WASM 后端和 layers。页面、Worker、模型、许可与清单约 1.51 MB；本机 HTTP 使用随机会话路径，绑定 127.0.0.1，资源白名单、来源检查和有界 JSON 返回。音频不离开浏览器标签页，桌面接收音符与来源信息。此大小不包括用户已有浏览器，也不是运行内存。

真实浏览器实测原 8.5 秒/20 音短句成功导入桌面：选中结果 24 音，匹配 20、漏 0、额外 4，音高/起音 F1=0.9091，起音/结束误差中位数约 7.3 / 72.9 ms。原始较宽松识别结果另存 model_raw.mid。计算在 Web Worker 中，约 39% 时实际取消后界面恢复，没有增加输出任务目录或导入半成品；HTTP 旧任务提交拒绝另有自动测试。

另外用同一 CC0 采样库合成六份短句，比较固定“保留和弦”（onset .7、frame .4、最短 11 帧、melodia 关闭）与“突出旋律”（再过滤平均激活低于 .55 的音）。以下用于参数比较，不能算独立泛化验收；不是对真实歌曲或录音的正确率证明：

| 短句 | 参考音符 | 保留和弦 F1 | 突出旋律 F1 |
|---|---:|---:|---:|
| 音阶 | 16 | 86.5% | 100% |
| 分解和弦 | 16 | 88.9% | 100% |
| 重复短音 | 16 | 69.6% | 100% |
| 同时和弦 | 16 | 96.8% | 81.5% |
| 连奏重叠 | 8 | 76.2% | 88.9% |
| 强弱变化 | 12 | 81.5% | 95.7% |

固定筛选能减少某些泛音，但也会减少真实和弦，不能把“突出旋律”宣传为可靠的主旋律分离。轻量模式现作为 Beta 提供，尚未稳定达到用户提出的 90–95% 质量要求。最终 Worker 改为逐窗口计算和释放 Tensor，模型权重不变；构建脚本的 --benchmark 路径可在 Node CPU 上复核同一 engine.js，Node 仅用于开发验证。


## 2026-10-30：CPU WASM 加速与可选后处理

使用同一 engine.js、同一模型和同一批 6 份 PCM，在 Node 中分别执行纯 JS CPU 与单线程 WASM。新增两份本机 WASM 二进制及完整许可后，资源清单内文件合计 2,329,728 字节（清单自身另计），共 10 个实际打入脚本的 npm 包。不引入 GPU、Node、Python 或浏览器内核。

| 短句 | JS CPU 秒 | WASM 秒 | 所选音数 |
| --- | ---: | ---: | ---: |
| scale | 5.892 | .902 | 21 |
| arpeggio | 5.724 | .634 | 20 |
| repeated | 5.620 | .647 | 30 |
| triads | 5.573 | .642 | 15 |
| legato | 5.527 | .633 | 13 |
| dynamics | 7.025 | .787 | 15 |

每份的两后端音高、起音、时长逐项完全相同；平均激活存在微小浮点差异，故不宣称全部中间数值逐位相同。释放后 Tensor 数为 0。本机短句约 6.5–9 倍速度，不是对所有机器/整曲或浏览器速度的承诺。此前真实浏览器的加速页已生成 20 音 arpeggio 与 16 音 triads，自动下载文件成功；与 Node PCM 的 triads 数量差异可能来自浏览器解码/重采样，未完成同浏览器两后端比较，不把它当作加速误差或准确率结论。

新增动态 ETA、自动下载/稳定结果链接、分栏布局和文件拖入。初始化失败、返回 false、运行时失败的回退策略由可注入测试覆盖，完整浏览器故障回退尚待人工验证。可选弱音预设与 24ms 起音对齐的参数、基准与边界见 [音频质量排查](AUDIO_QUALITY_1.5.md)。均衡模式默认保持，宽松选项不宣称提升准确率。

开发复现：生成原有 CC0 短句后，在 tools/light_audio_web 执行 `node build.mjs --benchmark <短句目录> cpu polyphonic`、`node build.mjs --benchmark <短句目录> wasm polyphonic`、`node build.mjs --benchmark <短句目录> wasm detail`。输出保留后端与预设名称，不覆盖其他比较文件。Node 仅用于开发，用户仍在浏览器本机运行。
