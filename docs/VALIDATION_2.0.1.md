# 2.0.1 最终发布验证

2026-11-08 · Windows x64 · 发布分支 release/2.0.0

本记录对应使用者确认界面后统一整理的最终 2.0.1。完整中文字标、明音速度条、导入合并、操作精简、移调推荐及时间报告均包含在本次发布包中。

## 本轮实际检查

| 检查 | 结果 |
| --- | --- |
| Python 回归 | 124 项通过，22.865 秒 |
| 工作流样例 | 4 组输入 × 2 种乐器 × 4 种方案 × 3 种速度，共 96 组转换与排程通过 |
| JavaScript | ETA、CPU 回退、文件参数、自动保存、下载路由、取消及写入失败检查通过 |
| 版本和帮助 | 应用、pyproject、Windows 属性统一为 2.0.1；六份随包帮助与 docs 对应文件一致 |
| 原生界面与控件 | 统一导入按钮、旧方案迁移、页面恢复、图片生命周期、数值边界／禁用状态、播放按钮状态和固定尺寸检查通过 |
| 定位与试听 | 原曲第 12 秒变速及重启后保持同一位置；原谱／适配试听生成独立且内容不同的 WAV |
| 旧方案保护 | 2–9 秒旧片段逐字节备份后迁移到完整时间轴；8 组无效速度输入不覆盖有效方案 |
| 移调和报告 | 找到唯一 +17 半音候选；钢琴样例额外延后从 10 ms 降为 0；180 秒变更显示 03:00.000，与原曲总长分别列出 |
| 实际音频交接 | 源码真实 WebView2 识别 20 音并自动载入工作台，保存与下载 MIDI 一致 |
| 最终包音频资源 | 新包资源实际识别琶音 20 音；移除 WASM 入口后 CPU 回退识别三和弦 16 音，保存／下载与 3 组窗口布局通过 |
| Windows 独立解压 | SHA-256、ZIP CRC、中文及空格目录、隔离 PATH、冻结自检和片段转换通过 |
| 发布资源 | 中文字标、角色滑块、轻量转谱及桌面宿主随包完整；解压资源与当前源码逐文件一致，运行后资源只读 |
| CI 样例入口 | 无需音频权重的 check_workflows.py 命令通过，并纳入 Windows 构建工作流 |

本轮仅使用独立数据目录，没有向游戏发送按键。普通与最小窗口的实际显示已在本轮开发过程中检查；软件检查不代替真实游戏听感验收。

## 音频质量边界

使用已知参考 MIDI、相同音高和起音误差不超过 100 ms 的一对一匹配：

| 样例 | 参考 | 识别 | 匹配 | 漏音 | 多余音 | 音高／起音 F1 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 琶音 | 16 | 20 | 16 | 0 | 4 | 88.89% |
| 三和弦 CPU 回退 | 16 | 16 | 15 | 1 | 1 | 93.75% |

识别继续为 Beta。输出数量一致不代表音符全部正确；两个合成短句不能推断所有歌曲的准确率，也不衡量音色和游戏发声。完整样例方法见 [工作流验证](VALIDATION_WORKFLOWS_2026-11-08.md)，历史 2.0 证据见 [VALIDATION_2.0.md](VALIDATION_2.0.md)。

## 最终发布包

Windows ZIP：`releases/v2.0.1/NTE-Music-Desk-v2.0.1-Windows-x64.zip`，24,819,367 字节。

```text
SHA-256 7a5b3c6c081cab2fe3bb6ce84925ea28d37e1fbba990bd9c5eca1d9ae37dd2f9
```

同目录另有 Source ZIP、两个逐包 SHA-256 文件、`SHA256SUMS.txt` 和可直接复制到 GitHub 的 `发布正文.md`。Source 包包含应用、开发构建工具、测试、发布流程和历史文档，排除个人数据、模型、虚拟环境、缓存及构建输出。

初始本地 2.0.1 检查点已用 `archive/v2.0.1-initial-20261108` 和 Git bundle 保存，初始更新说明及验证记录见 [2.0.2 标签中的历史记录](https://github.com/misaka-mikoto0502/nte-music-desk/tree/v2.0.2/docs/history/2.0.1-initial)。此前的安装包及本机证据已迁入私有归档；最终 ZIP 和校验文件随 2.0.1 Release 发布。

## 复现

```powershell
python -m unittest discover -s tests -v
node tools/light_audio_web/test.mjs
node tools/light_audio_web/test_downloads.mjs
python tools/check_workflows.py
python tools/check_release.py
python tools/build_windows.py
python tools/verify_release.py
python tools/package_source.py
```

本轮机器可读冻结报告为 `.build/release-validation-2.0.1.json`。最终构建、回归、96 组样例与真实音频证据位于 `.build/final-release-2.0.1/`。发布步骤见 [PUBLISH_2.0.1.md](PUBLISH_2.0.1.md)。

## 人工与独立模型待验收

UAC 实际确认、物理拖入、游戏内 F7／F8、迷你播放器前台保持、多音实际发声及钢琴绝对音高仍需人工检查。可选高级分离／MuScriptor／GAME 的授权模型真实推理未在本轮重跑。
