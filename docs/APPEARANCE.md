# 1.3.1 界面设计记录

风格采用暖灰底、墨绿侧栏和少量铜色提示。侧栏作为曲目架，右侧作为演奏台；主要操作保持在底部。减少重复的大号统计卡和流程编号，将时长、音符、音域合并为一条信息栏。

按钮、面板使用不同大小的圆角：主要按钮约 12 px，内容面板约 20 px。基于 Pillow 超采样绘制边缘，按钮仍为 Tk 原生 Button，保留键盘焦点、空格触发、invoke 和禁用行为。树表、输入框与系统菜单继续使用原生交互。这里只更改界面和外观偏好，不改变曲谱或按键调度。

## 背景与隐私

- 背景文件：`src/nte_music_desk/assets/city-session.png`。
- 原素材：用户提供素材库中的 `26_10_15_15_54_51.png`，夜间城市持吉他截图。
- 使用内置 imagegen 工具清除灰色相框、底栏、日期、UID 和角落文字；原始截图和 UID 不放入项目。
- 应用运行时对背景降低饱和度并叠加暖灰遮罩，左侧文字区域更淡。透明度只影响背景区，不使窗口文字和控件变透明。
- “外观”菜单提供关闭、淡雅、柔和、清晰四档，默认 .32；选择保存到个人设置文件。缺少图片时回退为纯色背景。
- 游戏角色、场景和截图衍生背景的权利归相应权利人；它不在项目自有 MIT 图标的许可范围内。原图标保持不变。

最终背景编辑提示词（内置 imagegen，非 CLI）：

> Edit this exact supplied Neverness to Everness game screenshot into a clean rectangular background plate for the user's private desktop music tool. Preserve the existing game-rendered character, guitar, street, lighting, colors, architecture, and composition faithfully. Remove ONLY the surrounding gray photo-frame border, the entire bottom information strip containing player UID and date, and all corner labels/watermarks/text. Deliver only the existing city scene filling a wide 16:9 rectangle, with no added typography, logos, frame, UID, UI panels, or invented objects. This is a clean extraction, not a redesign or new illustration. Do not put any player identifier anywhere. Do not apply fading or blur: the app will control opacity at runtime.

## 运行与验证

源码界面增加 Pillow 依赖，使用 `python -m pip install -e .` 安装。EXE 已包含依赖，无需用户安装。构建使用 Pillow 13.0.0，并收集其许可证。

检查普通/最小窗口、展开高级设置、多轨、曲库和音频窗口；菜单浓度切换、长标题截断、禁用按钮和样式重建均不能修改演奏方案。原有功能测试继续执行，并对新的冻结包做独立解压自检。
