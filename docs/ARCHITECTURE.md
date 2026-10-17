# 项目结构

```text
nte-music-desk/
├── src/nte_music_desk/
│   ├── _bootstrap.py       # 源码与 EXE 共同入口
│   ├── cli.py              # 命令行、演奏调度、合成试听与子进程
│   ├── ui.py               # 主窗口
│   ├── library_ui.py       # 在线曲库窗口
│   ├── midi.py             # 标准 MIDI 读取、节奏与音域转换
│   ├── notation.py         # MusicXML/MXL、KAR/RMI 统一导入
│   ├── instruments.py      # 乐器键位表
│   ├── keyboard.py         # 前台核对、按键及 UAC 启动
│   ├── catalog.py          # 搜索索引、受限下载与来源记录
│   ├── paths.py            # 资源与用户数据目录
│   ├── diagnostics.py      # 不发送按键的离线发布自检
│   └── assets/             # 图标、帮助、示例 MIDI、曲库快照
├── tests/                  # 自包含离线测试，不使用个人曲谱
├── tools/                  # EXE 构建与版本元信息
├── docs/                   # 使用、结构与发布说明
├── .github/workflows/      # Windows 自动构建
└── releases/               # 本地发布产物，Git 忽略二进制
```

程序启动不会提权或向游戏发送按键。只有游戏演奏操作才保存转换后的 JSON、启动带 UAC 的同一程序，并传递明确的曲谱、报告、取消标记与数据目录。源码模式使用包内 bootstrap，冻结后直接重启 EXE，不再把 Python 的 -I/-S 参数传给 EXE。

调度使用一个单调时钟，重复键先松再按，异常与取消后释放自己持有的键。窗口标题、HTGame.exe、窗口进程和前台焦点均被核对。钢琴仅允许程序持有的左 Shift，人工按下的其他修饰键会中止；混合黑白和弦以快速分组适应全局 Shift 状态。

只读资源与写入目录分开：资源来自包内 assets（EXE 中为 _internal 下的包资源），写入默认位于 %LOCALAPPDATA%\NteMusicDesk。可用 --data-dir 或 NTE_MUSIC_DESK_DATA_DIR 覆盖数据目录，方便离线测试与个人备份。

在线搜索默认读随包目录。下载限制为支持的 HTTPS 来源域名，校验重定向、大小、MIDI 头及可解析性后保存；不用 Cookie、登录凭据或网页脚本。索引更新与下载均在后台线程执行，可取消；过时任务不能重新导入或自动演奏。

Mutopia 目录只解析公开 musiccache.dat 的曲目字段，保留作曲家、乐器、许可与普通下载路径，省去维护者邮箱等字段。多乐章 ZIP 在内存中校验并读取 MIDI，不按压缩包路径写文件。MXL 同样不解压到磁盘，拒绝重复、越界、过大或加密的内部文件。MusicXML 不解析实体或访问外部 DTD。

所有导入最终生成同一 MidiSong 时间化音符模型，复用选轨、演奏与试听。另存 MIDI 以固定速度网格编码秒级音符时刻，面向互通和演奏，不作为保真制谱文档导出。
