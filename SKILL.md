---
name: song-melody-matcher
version: 2.0.0
description: 旋律相似度检测——把一首歌（音频/ MIDI / ABC）放进来，判断其旋律是否抄袭或特别像曲库中的某首歌 / 或直接对比两首歌 / 或与内置的万首级公开开放曲库比对。适用于"这首歌是不是抄的""特别像某首歌"类诉求。
trigger:
  - 这首歌抄袭
  - 旋律抄袭
  - 这首歌像哪首歌
  - 旋律相似度
  - 是不是抄袭
  - 这首歌特别像
  - 查重 旋律
  - 接一个曲库 / 公开曲库 / 全世界最全曲库
  - melody plagiarism / similarity
---

# 旋律相似度检测（Song Melody Matcher）v2

用户丢进来一首歌（或两首歌），快速判断：**它的旋律是否抄袭 / 特别像另一首歌**。

## 三种比对模式（v2 新增第三种）
1. **查本地曲库**（`local`）：把怀疑的歌与同目录 `corpus/` 里的曲库比对；往 `corpus/` 加 MIDI 即可扩充。
2. **两曲直接对比**（`compare`）：同时拖两首，直接给相似度（最准、最实用）。
3. **查公开开放曲库**（`public`）：与内置的 **music21 公共领域开放曲库（12,977 首）** 比对，
   无需联网、无需 music21 运行时；**结果会显示真实曲名**（如 *The White Cockade*）。

## 工作原理（一句话）
提取歌曲的**旋律轮廓（音高走向 → 有符号音程）**，该表示**移调不变、变速不变**；再用子序列 DTW 比对，输出相似度最高的若干首及命中段落。

## 轻量化（v2 重点）
- 旧版依赖 librosa / scipy / pretty_midi（EXE ~120 MB）。
- 新版**自写 NumPy Yin 音高检测** + soundfile（音频解码）+ mido（MIDI），去掉全部重型依赖，单文件 EXE **约 26.6 MB**
  （**含** 12,977 首公开曲库+曲名表；内嵌数据用 zlib+base85 压缩，否则会因 pyc 膨胀多约 2.5 MB）。
- 公开曲库检索用「n-gram 预筛 → 候选跑 DTW」两阶段，单首检索 **约 1 秒**（旧版逐首跑 O(n·m) 约 45 秒会卡死）。
- 另附 **Rust 迷你版源码**（`rust/`，`cargo build --release` 后约 10 MB），见底部。

## 关键路径（绝对路径）
- EXE 打包环境（带 tkinter 9.0）：`C:\Users\Dean\.workbuddy\binaries\python\envs\melody-matcher-slim314\Scripts\python.exe`
- 索引构建环境（需 music21）：`C:\Users\Dean\.workbuddy\binaries\python\envs\melody-matcher-slim\Scripts\python.exe`
- 引擎：`C:\Users\Dean\.workbuddy\skills\song-melody-matcher\melody_engine.py`
- 界面：`C:\Users\Dean\.workbuddy\skills\song-melody-matcher\melody_app.pyw`
- 公开曲库索引：`...\public_corpus_index.json`（12,977 首，3.3 MB）
- 公开曲库曲名表：`...\public_corpus_titles.json`（id → 真实曲名，约 0.6 MB）
- 内嵌数据模块：`...\public_corpus_data.py`（**zlib 压缩 + base85 内嵌**，导入时解压出 `PUBLIC_INDEX` + `PUBLIC_TITLES`，仅约 758 KB；
  早期用"超大 Python 字面量"写法会让 .pyc 膨胀到 5.4MB / 包内 3.9MB，已废弃）
- 本地种子曲库：`C:\Users\Dean\.workbuddy\skills\song-melody-matcher\corpus\`（6 首公有领域 MIDI）

## 命令行 / 无界面用法（便于验证与自动化）
```bash
"<PY>" "<SKILL>/melody_engine.py" self-test
"<PY>" "<SKILL>/melody_engine.py" query  <歌> [corpus目录] [top]      # 本地曲库
"<PY>" "<SKILL>/melody_engine.py" compare <歌A> <歌B>                 # 两曲对比
"<PY>" "<SKILL>/melody_engine.py" public <歌> [index路径] [top]       # 公开曲库

# EXE 也支持命令行（有参数即走无界面模式）：
"旋律相似度检测.exe" local   <歌>
"旋律相似度检测.exe" compare <歌A> <歌B>
"旋律相似度检测.exe" public  <歌>
"旋律相似度检测.exe" selftest
```

## 公开曲库索引（"接一个公开的最全的曲库"）
- 来源：**music21 内置 ABC 曲库（公共领域）**，共 **12,977 首**旋律，全部公有领域、可合法使用。
  实际构成（以传统/民间曲调为主）：
  - `ryansMammoth`（1059 文件）Ryan's Mammoth Collection —— 爱尔兰/苏格兰/北美传统提琴曲（reel/jig/hornpipe/strathspey）
  - `oneills1850` O'Neill's Music of Ireland —— 爱尔兰传统曲调
  - `airdsAirs` Aird's Airs —— 苏格兰/英格兰/爱尔兰
  - `essenFolksong` Essen 民谣集 —— 德国传统民谣 + 中国民谣（`han1`）
  - `josquin` 文艺复兴复调；`miscFolk`/`nottingham` 美国军笛曲等
  - **注意：不含当代流行歌**（公共领域限制），也**不含巴赫众赞歌**（那些是 .mxl/.krn，非 .abc，本索引只解析 .abc）。把流行歌放进 public 模式得中低分属正常。
- 两个产物：
  - `public_corpus_index.json` —— id → 有符号音程序列（约 3.3 MB）
  - `public_corpus_titles.json` —— id → **可读曲名**（取自 ABC 的 `T:` 字段，12,977/12,977 全部有名字）
- 构建（仅构建期需要 music21，运行时不需要）：
  ```bash
  "<SLIM_PY>" "<SKILL>/tools/build_public.py"
  ```
  内部用**纯 Python ABC 解析**（`_split_abc_tunes` + `abc_to_pcs` + `_abc_title`），不依赖 music21 解析器，约 5 秒完成。
  该脚本同时生成内嵌模块 `public_corpus_data.py`（`PUBLIC_INDEX` + `PUBLIC_TITLES`），供 EXE 内存加载。
- 运行时：`public_search()` 加载索引，先做相邻音程对（bigram）集合交集的快速预筛（候选 ≤200），再对候选跑精确子序列 DTW，**秒级**返回；
  用 `load_public_titles()` 取曲名，结果含 `title` / `dir`（命中方向）/ `best_similarity`（最高分，便于出结论）。
- thesession.org 等在线源已失效（API 返回 404），故改用本地 music21 曲库，稳定、离线、无版权风险。

## 曲库扩充
- 本地曲库：把已知歌曲转成 MIDI 丢进 `corpus/` 即可被 `local` 模式检索（musescore / free MIDI 库等获取途径）。
- 公开曲库：已内置 13000 首；如需更多，可换更大 ABC 曲库重新 `build-public`。

## 离线自测（验证引擎没坏）
```bash
"<SLIM314_PY>" "<SKILL>/melody_engine.py" self-test
```
预期：`transpose_self`（小星星 MIDI 自比）≈ 100.0；`audio_pcs` 能正确抓出 A-B-C-D 轮廓。

## 向用户汇报时的口径（重要：必须给"到底是什么歌"）
- **公开模式必须显示曲名，不能只给 `book6#179` 这类文件名编号**（这是 v2 修过的用户痛点）。
- 结论行阈值（`format_result` 已内置）：
  - 最高分 **≥ 70**：`★ 发现较明显相似曲目` —— 重点核对第 1 条。
  - **55–70**：`存在一定相似，可参考，但未必是同一旋律`。
  - **< 55**：`未发现明显相似曲目（属常见句式巧合）`，并说明公开库不含流行歌。
- 务必说明：这是**旋律形状相似度**辅助工具，受编曲/伴奏/人声清晰度影响；看第 1 名与第 2 名的分差（明显高出一截才值得核对），一堆分数挤在一起多为巧合。结果仅供参考，不能替代音乐版权专业鉴定。
- 想判断"像不像某首具体的流行歌"：引导用**两曲直接对比**（把怀疑的原曲也拖进去），而不是 public 模式。
- 音频（尤其整首混音的歌）旋律提取噪声大，MIDI / 清唱 / 主旋律轨效果最好。

## 给普通用户的 EXE（双击即用，推荐）
- 交付位置：`C:\Users\Dean\Desktop\旋律相似度检测\` —— 内含 `旋律相似度检测.exe`（约 27 MB）+ `corpus\` + `使用说明.txt`。
- 用法：双击 exe → 选模式 → 把歌曲拖进窗口（或点「＋ 添加文件」）→ 「▶ 开始检测」。支持 mp3/wav/ogg/flac/m4a/mid/midi/abc。
- 后台自动加载同目录 `corpus` 与**内嵌**的公开曲库（索引+曲名表）；点「打开曲库文件夹」往里加本地 MIDI。

## 重新打包 EXE
```bash
GP="C:/Users/Dean/.workbuddy/binaries/python/envs/melody-matcher-slim314/Scripts/python.exe"
SK="C:/Users/Dean/.workbuddy/skills/song-melody-matcher"
"$GP" -m PyInstaller "$SK/build_exe.spec" \
  --distpath "$SK/dist_exe" --workpath "$SK/build" --noconfirm
```
- 关键点：`melody-matcher-slim314` 是带 tkinter 9.0 的 venv（系统 Python 3.14 建的），含 numpy/soundfile/mido/pyinstaller。
- **spec 坑**：`build_exe.spec` 里取目录必须用 PyInstaller 注入的 `SPECPATH`，**不能用 `__file__`**（spec 执行环境不定义它，会报 `NameError: name '__file__' is not defined`）。
- spec 已配好：--windowed 单文件、排除 librosa/scipy/pretty_midi/music21 等重型包、把 `corpus/` 与内嵌 `public_corpus_data.py` 打进 EXE；
  **不再重复打包 `public_corpus_*.json`**（那份是源码运行时的外置数据，重复打包只会白涨体积并触发临时目录权限问题）。
- 打包后在 `dist_exe/` 生成 exe；拷到 Desktop 交付目录即可。
- 验证：`旋律相似度检测.exe selftest` 看 `transpose_self` 是否 100；`旋律相似度检测.exe public <某mid>` 看结果里是否有 `title` 字段且秒级返回。

## Rust 迷你版（约 10 MB，需自备 Rust 工具链）
- 源码：`rust/`（eframe/egui GUI + symphonia 解码 + pitch-detection(Yin) + midly(MIDI) + 纯 ABC 解析 + serde_json 索引）。
- 构建：`cd rust && cargo build --release` → `target/release/melody-matcher.exe`（约 8–12 MB）。
- 当前打包机无法装 Rust（SmartScreen 拦截 rustup-init），故仅交付源码；公开曲库索引复用 Python 版生成的 `public_corpus_index.json`。
- 详见 `rust/README.md`。

## 依赖
- 引擎/CLI 环境 `melody-matcher-slim`：numpy, soundfile, mido, music21（仅构建索引用）。
- EXE 打包环境 `melody-matcher-slim314`：numpy, soundfile, mido, tkinter 9.0, pyinstaller（**不含 music21**，运行时不需）。
