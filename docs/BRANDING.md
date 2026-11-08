# 中文字标设计记录

2026-11-08 · 2.0.1 中文字标

## 本轮字标

使用者指定的七字文案为“异环演奏工具台”。全部文字作为一个图形设计，采用“异环演奏／工具台”两行居中组合，七个字保持一致的笔画语言和相近的视觉字号。字形采用较饱满的笔画、开放内白和柔和切角，深绿色为主，少量绿色笔画作强调。侧栏显示宽度为 176 px，不另加英文缩写或系统字体副标。

生成方式为内置 imagegen，透明 PNG 原图保存于 `src/nte_music_desk/assets/brand-wordmark.png`，1774 × 887，668,834 字节。运行时仅按透明边界和侧栏尺寸进行显示适配，原图完整保留。窗口标题、可执行文件名和发布入口沿用现有名称。

## 参考与取舍

- [方正 GDC 体设计说明](https://www.foundertype.com/index.php/FontInfo/index/id/5721)：参考其笔画语言统一、内白舒适和装饰克制的设计思路。
- [汉仪品牌字体定制](https://fund.hanyi.com.cn/orderFont)：参考其将整个名称作为统一品牌字形系统的方式。
- [中文字标案例集](https://chinesefontdesign.com/20p-experience-summary-of-chinese-font-design-in-2017.html)：观察饱满笔画、字间距与音乐类字标的视觉节奏。

以上作为设计思路参考，最终资产由图像生成工具创建；不嵌入第三方商业字体文件，不直接复制参考页面的字标图片。

前一版仅将“异环”绘成细线条，下方是普通文字，整体层级和字形不够统一。旧实现继续保留于 Git 历史。

## 完整生成提示词

```text
Use case: logo-brand. Create ONE finished, original Chinese typographic wordmark as a transparent PNG asset for a calm, refined desktop music application. Text must be EXACTLY these seven simplified Chinese characters in this reading order: 异环演奏工具台. Carefully verify each character: 异 / 环 / 演 / 奏 / 工 / 具 / 台. Layout is precisely TWO centered lines: first line 异环演奏 (four characters), second line 工具台 (three characters). All SEVEN characters are custom artistic lettering in the SAME cohesive type style, same stroke character and similar optical size; the bottom line must NOT look like an ordinary small-font subtitle. Develop beautiful professionally drawn, optically balanced Chinese glyphs: confident medium-bold solid strokes, subtly rounded corners, a few elegant restrained terminal cuts, generous open counters, carefully balanced widths and spacing, musical rhythm through the typography itself. Contemporary Chinese music-studio identity, quiet, warm and highly readable. Think mature editorial logotype craftsmanship, not generic typed system text. Use ONLY deep charcoal green #293A32 and a sparing evergreen accent #326B52 in a few chosen strokes; no other paint colors. Whole mark has approximately a 2:1 width-to-height ratio, compact yet airy, with clean transparent margins of roughly 5 percent. The logo will be displayed only 176 pixels wide in an app sidebar, so every character must remain recognizable at small size. Do not add any Latin letters, NTE, English tagline, extra Chinese words, music-note icons, pictograms, borders, enclosing badge, frame, background rectangle, paper texture, shadow, gradient, glow, 3D or mockup. Do not imitate an existing brand logo. Smooth crisp flat artwork with genuine alpha transparency, suitable as a production UI asset, not a presentation sheet.
```
