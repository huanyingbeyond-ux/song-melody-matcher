# 旋律相似度检测 · Melody Similarity Matcher

> 把一首歌拖进去，立刻告诉你它的旋律「像哪首歌 / 是否疑似抄袭」。
> 支持三种比对模式：本地曲库、两曲直接对比、以及**内置 12,000+ 首公共领域开放曲库**。

**English:** Drag in a song (audio / MIDI / ABC) and get an instant report of which
tunes its melody resembles, with human-readable tune titles. Three modes: local corpus,
two-song compare, and a built-in **12,000+ public-domain tune corpus**. Pure local, no
upload, no network.

---

## 特性

- **三种比对模式**
  - 🔍 查本地曲库：与 `corpus/` 文件夹里的旋律比对（往里加 MIDI 扩充）。
  - ⚖️ 两曲直接对比：同时拖两首，直接给相似度（最准、最实用；想知道「像不像某首具体的歌」就用它）。
  - 🌍 查公开开放曲库：与内置的 **12,977 首公共领域旋律**比对（离线、无需联网），结果**显示真实曲名**。
- **可读结果**：公开曲库每首都有曲名（取自 ABC 的 `T:` 字段，如 *The White Cockade*），并给出一句**结论**
  （≥70% 提示「较明显相似，建议核对」；低于 55% 提示「属常见句式巧合」）。
- **旋律形状比对**：提取「有符号音程序列」（移调 / 变速不变），用子序列 DTW 找最像的段落。
- **跨格式**：音频（mp3/wav/ogg/flac/m4a，自写 NumPy Yin 音高检测）、MIDI、ABC。
- **轻量**：单文件 EXE 约 27 MB（无 librosa/scipy/pretty_midi/music21 运行时依赖）。
- **可交互 GUI**：tkinter 单窗口，支持 Windows 拖拽（`WM_DROPFILES`，无额外依赖）。
- **全部本地运行**：不上传、不保存你的歌曲。

### 内置公开曲库包含什么

全部来自 [music21](https://github.com/cuthbertLab/music21) 内置的公共领域 ABC 曲库，共 **12,977 首**，
以**传统 / 民间曲调**为主：

| 集合 | 内容 |
| --- | --- |
| Ryan's Mammoth Collection（1059 个文件） | 爱尔兰 / 苏格兰 / 北美传统提琴曲（reel / jig / hornpipe / strathspey） |
| O'Neill's Music of Ireland（1850） | 爱尔兰传统曲调 |
| Aird's Airs | 苏格兰 / 英格兰 / 爱尔兰乐曲 |
| Essen Folksong Collection | 德国传统民谣（ballad / Erk / Böhme / Fink 等）及中国民谣（`han1`） |
| Josquin 等 | 文艺复兴复调（定量记谱转 ABC） |
| miscFolk / Nottingham | 美国军笛曲、诺丁汉数据集 |

> ⚠️ 曲库**不含当代流行歌**（公共领域限制）。所以把一首流行歌放进「查公开开放曲库」，
> 结果通常是中低分——那**不代表没问题**，只说明这批古旧民谣里没有与之雷同的。
> 真正判断「是否抄袭某首流行歌」，请用**两曲直接对比**去比那首你怀疑的原曲。

> ⚠️ 免责声明：本工具给出的是**旋律形状相似度的辅助参考**，**不是法律意义上的抄袭鉴定**。
> 结果多为「常见句式巧合」（全音阶里级进/三度本就常见）；只有明显高出其余的结果才值得重点核对，
> 最终请结合试听与专业鉴定判断。

---

## 安装与运行（源码）

```bash
pip install numpy soundfile mido tkinter   # tkinter 通常随 Python 自带
python tools/make_seed_corpus.py            # 生成 corpus/*.mid 本地种子曲库
python melody_app.pyw                       # 启动 GUI（无参数 = 图形界面）
```

命令行 / 自动化模式（带参数时走无界面模式）：

```bash
python melody_app.pyw selftest                       # 自测
python melody_app.pyw local  corpus/小星星_Twinkle.mid
python melody_app.pyw compare corpus/小星星_Twinkle.mid corpus/欢乐颂_OdeToJoy.mid
python melody_app.pyw public  corpus/小星星_Twinkle.mid   # 需先生成公开曲库索引
```

公开曲库索引（不入库，需自行生成；约 3.3 MB 索引 + 0.6 MB 曲名表）：

```bash
pip install music21                                # 仅构建期需要
python tools/build_public.py
# 生成：public_corpus_index.json（音程索引）+ public_corpus_titles.json（曲名表）
#       + public_corpus_data.py（zlib+base85 内嵌模块，供打包 EXE 时内存加载）
```

打包成单文件 EXE（`build_exe.spec` 已配好，约 27 MB）：

```bash
pip install pyinstaller
pyinstaller build_exe.spec --noconfirm
# 产物 dist/旋律相似度检测.exe
```

---

## 算法简介

1. **旋律表示**：把旋律转成「音高类（pitch class）序列」，再取相邻音的**有符号音程**
   （`-6..+6`，模 12 折叠到最近方向）。这一步对移调（整体升降调）和变速（快慢）都不变，
   是旋律比对的稳健特征。
2. **比对**：用**子序列动态时间规整（subsequence DTW）**把查询旋律作为参考旋律的子序列对齐，
   允许跳过参考曲里的音（应对速度/留白差异），双向各跑一次（q⊂r 与 r⊂q）取较优。
3. **大规模检索（公开曲库）**：先以「相邻音程对集合」做 O(n) 量级 **n-gram 快速预筛**，
   仅对少量候选跑精确 DTW，使 1.2 万+ 首的检索从约 45 秒/首降到约 1 秒/首（秒级、不卡死）。

该思路属于音乐信息检索（MIR）中 query-by-humming 类的标准做法，本项目为**从零实现的原创代码**，
未直接复制任何仓库的源码（详见下方「引用与致谢」）。

---

## Rust 迷你版（约 10 MB）

`rust/` 目录是用 Rust 重写的等价实现（eframe + symphonia + pitch-detection + midly），
目标单文件 EXE 约 10 MB。源码完整可编译，在有 Rust 的机器上：

```bash
cd rust
cargo build --release      # 产物 target/release/melody-matcher.exe（约 8–12 MB）
```

（当前打包环境无法安装 Rust 工具链，故仅提供源码；详见 `rust/README.md`。）

---

## 作为 WorkBuddy Skill 使用

本仓库本身即一个 WorkBuddy skill。把整个目录复制到
`~/.workbuddy/skills/song-melody-matcher/` 即可在 WorkBuddy 中调用。

---

## 引用与致谢（Attribution）

本项目**旋律匹配算法为原创实现，未复制任何 GitHub 仓库的源码**。唯一「借用」的是**数据**：
公开曲库的 12,977 首旋律来自 [music21](https://github.com/cuthbertLab/music21) 内置的公共领域曲库。

- **music21** — Michael Scott Cuthbert 等，[github.com/cuthbertLab/music21](https://github.com/cuthbertLab/music21)
  许可证：**BSD-3-Clause OR LGPL-3.0**。本项目**仅将其作为曲库数据源**（构建期定位其内置 ABC 目录），
  运行期不需要 music21；曲库解析用的是本项目自写的 `abc_to_pcs`。
- 内置曲库由 music21 `corpus/` 下的 **ABC 文件**构成，共 12,977 首，主要是以下公共领域传统曲集：
  - **Ryan's Mammoth Collection**（爱尔兰 / 苏格兰 / 北美传统提琴曲）
  - **O'Neill's Music of Ireland (1850)**（爱尔兰传统曲调）
  - **Aird's Selection of Scotch, English, Irish and Foreign Airs**
  - **Essen Folksong Collection**（德国传统民谣、中国民谣）——见下条
  - **Josquin 等文艺复兴复调**、美国军笛曲（`miscFolk`）、诺丁汉数据集
  - 说明：只解析 `.abc`；music21 中以 `.mxl` / `.krn` 存在的语料（如巴赫众赞歌）**不在本索引内**。
- **Essen Folksong Collection（Essen 民谣集）**：由 Helmut Schaffrath 编集
  （德国 Essen 音乐学院，1982–1994）；其 ABC 编码由 **Seymour Shlien** 授权随 music21 分发。
  标准引用：
  > Schaffrath, Helmut (1995). *The Essen Folksong Collection in Kern Format.*
  > D. Huron (ed.). Menlo Park, CA: Center for Computer Assisted Research in the Humanities.
  - GitHub 镜像：<https://github.com/ccarh/essen-folksong-collection>
- 各曲编码在美/欧/加等地依音乐本身多属公共领域，或经授权非商业使用；再分发衍生数据集前请自行核对各曲授权。

### Rust 版第三方依赖（均开源，MIT / Apache-2.0）

- [egui / eframe](https://github.com/emilk/egui) — 跨平台 GUI
- [Symphonia](https://github.com/pdeljanov/Symphonia) — 音频解码（mp3/wav/ogg/flac）
- [pitch-detection](https://crates.io/crates/pitch-detection) — Yin 音高检测
- [midly](https://github.com/Woyten/midly) — MIDI 解析

### 说明

此前曾尝试接入 [thesession.org](https://thesession.org) 的实时曲库 API 作为在线数据源，
但其批量接口（`/tunes.json`）现已返回 404，故未采用，仅在此说明。

---

## 许可证

[MIT](./LICENSE) © 2026 Dean (丁宇)
