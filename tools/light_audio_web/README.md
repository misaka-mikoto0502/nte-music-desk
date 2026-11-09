# 轻量转谱开发构建

在此目录执行 npm ci、npm run build。打包 core/converter/CPU、单线程 WASM/SIMD 和 Basic Pitch 后处理，不打入 tfjs-layers、GPU、Node 或 Python。目标 assets/light_audio 包含固定版本官方模型、页面脚本及完整许可；每次生成 SHA-256 清单，总预算 4.5 MB。桌面窗口和浏览器兼容入口共用 pipeline.js，不分别维护识别流程。

开发环境的依赖目录不在此处时，可设置 NTE_LIGHT_NODE_MODULES 为绝对 node_modules 路径。运行时资源无需联网获取。模型与第三方代码保持各自许可证，详见生成的 licenses.txt。

预计剩余时间包含识别、曲谱整理和保存。整理尚未测速时用按音频长度放大的粗略范围，之后根据三轮解码的实际完成进度修正；初始范围不代表机器性能测量。运行 `node test.mjs` 可验证阶段计时、超出预估、CPU 回退、取消、连续任务与实际页面处理函数。

复现六份校准短句，在仓库根目录：

```text
python tools/create_audio_benchmark.py --output .build/piano-benchmark
python tools/create_light_audio_benchmark.py --samples .build/piano-benchmark --output .build/light-benchmark
node tools/light_audio_web/build.mjs --benchmark .build/light-benchmark
```

样本生成需要开发环境里的 numpy/scipy/soundfile。只下载官方 CC0 单音采样，生成自制短句，不下载歌曲；不把音频、PCM 或开发依赖加入桌面包。输出 browser-engine-results.json 与参考 MIDI 可用 audio_quality.compare_notes 的同音高/起音 100 ms 一对一规则比较。“突出旋律”的结果再筛选 amplitude >= .55；此值不是正确概率。

--benchmark 复用正式 engine.js，在 Node CPU 中运行并报告模型释放后的 Tensor 数量。六份样本用于校准和回归，不是独立真实音乐质量验收，也不能证明普遍达到 90–95%。
