# 夜景背景与缩放适配

用户于 2026-11-19 选择游戏截图 `26_05_23_16_42_26.png` 作为工作台背景。项目素材为 `src/nte_music_desk/assets/background-city-cropped.png`，由内置 image_gen 按下述提示准备，已裁去外框和底部信息栏；用户原始文件不改写。

主窗与五个分页共用同一张背景，按窗口比例等比铺满、裁去溢出部分，中心人物保持在画面中部。基础图片显示强度为 22%，内容面板再叠加 76% 白色底。透明效果仅由图片合成实现，不调整整个窗口的不透明度。原生输入框、列表和音符图保留清楚的工作底色。

`backdrop.py` 负责统一坐标、窗口缩放后重新取景与页面滚动后的纹理对齐。连续缩放事件合并后处理；普通容器从同一窗口取景中裁切实际可见区域，滚动时及时更新取样，避免图案随内容上下移动。原生颜色统一处理大小写，圆角边缘延续背景；装饰层不进入键盘焦点。保留原生按钮、文件拖入目标、标题文字与演奏数据。图片缺失或不可读取时回到纯色界面。背景相关检查位于 `tests/test_backdrop.py`，不触发游戏按键、整套回归或打包。

## 2026-11-19 实机复核

当时核对了默认窗口、最大化、恢复默认尺寸、分段页滚动与切换转谱页，检查取景比例、圆角与按钮边缘。背景专项四项自动检查通过，覆盖颜色格式兼容、容器统一坐标、分页／滚动／缩放、原生拖入目标及演奏数据不变。但后续使用反馈仍出现连续滚动跳动，说明这些稳定状态检查不能证明滚动过程没有中间画面。日常只更新源码和相关检查，不执行整套回归或打包。

## 固定视口与滚动回归修正

滚动容器的背景使用固定在窗口坐标中的原生图层，不再把背景图片作为滚动画布内容项。滚动容器的内容边界只由内容决定，避免背景图参与滚动范围。调整页、曲目栏与共用滚动页都通过画布的视口通知更新背景，覆盖滚轮、滚动条拖动及跳转。

面板取样位置按当前画布原点计算，不等待原生子窗口位置更新；交给图片合成前统一转为整数像素，修复浮点坐标引起的异常。局部回归直接滚动画布并运行正常布局通知，不手动刷新背景，对比同一窗口位置在滚动前后的背景像素，还检查跳回、背景图层坐标与明音进度条。6 项相关检查通过，未做整套回归或打包。

## 滚动更新与分页重新显示

`scrolling.py` 中的 `SceneScrollCanvas` 统一承载曲目栏、调整页及共用滚动页。Windows 下先暂停该视口及已显示子窗口的重绘，完成内容移动、空闲布局与背景取样；恢复显示后，向可见控件直接发送 Tk 绘制通知，再处理由此产生的绘制任务。异常退出也恢复原生重绘。布局、背景取样与内容重绘在一次滚动处理内完成，不运行嵌套的全事件循环。原生控件、键盘焦点与文件拖入目标继续保留。

此前采用的临时 `WS_EX_COMPOSITED` 子窗口双缓冲已经移除：Tk 的 `WM_PAINT` 处理会先生成 `Expose` 事件，实际绘制可能随后执行，系统缓冲会在这之前被提交或丢弃，使滚动内容出现黑框。仅调用 Windows 重绘和 `update_idletasks()` 仍不足以保证这些窗口事件已处理；现在先直接分发绘制通知，确认控件显示状态已恢复，再完成绘制队列。该行为可对照 [Tk Windows 事件处理源码](https://github.com/tcltk/tk/blob/core-8-6-branch/win/tkWinX.c) 的 `TkWinChildProc`／`GenerateXEvent`。

分页隐藏会使 Canvas 承载的内容窗口取消显示；再次显示相同尺寸的画布时，Tk 可能没有重新安排这些窗口的绘制，表现为分段／转谱区域空白，滚动后才出现。画布现在在自身收到 `<Map>` 时显式使窗口项重新绘制，保留原有项目状态与滚动位置，不模拟滚轮，也不把视口重置到顶部。

专项回归在修复前稳定复现了转谱页再次进入时内容窗口未显示，修复后覆盖首次进入、反复切页、不滚动即显示，以及离开后原滚动位置仍保留。滚动相关检查另外验证背景像素对齐、原生重绘的暂停／恢复顺序、异常恢复、不启用系统子窗口缓冲，以及分段／转谱页在主窗口滚轮绑定处理返回前收到内容绘制通知。

## 2026-11-22 绘制性能补充

性能补充：2026-11-22 起，背景装饰使用可见裁片，避免每个小容器都重绘窗口尺寸的原生 Label。离开视口的容器不重新取样；局部与完整刷新使用同一个实际裁片键，滚动不重建静止的视口背景。原生重绘仅覆盖可见区域，完全被不透明兄弟控件覆盖的装饰层不额外强制绘制。对应检查直接核对可见裁片与窗口照片的像素一致性，以及静止视口图片的复用。详见 [流畅性记录](RESPONSIVENESS.md)。

## 2026-11-23 乐器切换后的已删除图层引用

按“滚到分段编辑区选择方案，再回到顶部切换乐器”复现了 `bad window path name` 连续弹窗。声部区重建时清空全部子控件，把背景装饰 Label 一起删掉；该区域在视口外时，背景刷新跳过了可见区域的重新注册，却仍尝试隐藏旧 Label。错误与具体演奏方案无关。

声部区现在仅重建自己拥有的复选框；背景刷新在可见性判断前移除装饰层已不存在的记录，区域再次进入视口时恢复图层。没有通过忽略异常来隐藏错误。新增回归在修复前复现相同控件路径，修复后连同乐器方案恢复、撤销、背景像素和原生滚动等 13 项相关检查通过。四种方案分别检查钢琴与吉他切换，以及 A/B 预览曲谱生成。另模拟装饰层被外部重建删除，验证视口外刷新与滚回后的像素对齐。

本次仍只更新源码和局部验证；性能补测位于 `.build/validation/2.1.1-responsiveness/instrument-layer-fix-20261123.json`。同机 5,000 音／64 段样例的拖选、滚动、设置刷新中位数分别为 1.62、38.04、191.70 ms，界面回调未报错。原 2.1.1 归档保留。

## 素材准备提示词

执行方式：内置 image_gen 编辑工具；输入为用户指定截图，输出另存为项目背景素材。

```text
Use case: precise-object-edit
Asset type: native desktop app background, landscape 16:9.
Input image: the supplied game screenshot is the edit target, not a style reference.
Primary request: tightly crop to the photograph INSIDE the silver outer frame, excluding the entire silver frame, the top frame labels and the bottom identity/UID/date information strip. This is a crop-only preparation task. Preserve the central silver-haired character's exact face, pose, outfit, the blue night city, red tower, sky, balcony, lighting and all image details as closely as possible. Do not redesign, paint over, beautify, extend the scene, add objects, add text, or change colors. Keep any game logo already inside the actual photograph. Fill the output with the inner photograph, no border and no identity strip. Retain the character centered and the city skyline. No transparency or opacity wash yet; the app will apply that while rendering.
```

