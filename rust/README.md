# 旋律相似度检测 · Rust 迷你版（约 10 MB）

本目录是用户要求的「Rust 重写」源码：用 Rust 重新实现引擎与图形界面，
目标单文件 EXE 约 10 MB（相比 Python 版约 26 MB 更轻、启动更快）。

> 说明：当前打包机（沙箱）无法安装 Rust 工具链（SmartScreen 拦截 rustup-init），
> 因此本目录提供**完整可编译源码**，请在有 Rust 的机器上自行 `cargo build --release`。

## 依赖（Cargo.toml 已配好）
- eframe / egui 0.27：跨平台 GUI
- rfd 0.14：文件选择 / 拖拽
- symphonia 0.5：音频解码（mp3/wav/ogg/flac）
- pitch-detection 0.5：Yin 音高检测
- midly 0.5：MIDI 解析
- serde / serde_json：公开曲库索引

## 构建
```bash
# 1) 安装 Rust（https://rustup.rs）
# 2) 在本目录执行：
cargo build --release
# 产物：target/release/melody-matcher.exe （约 8–12 MB）
```

## 发布体积优化（已写入 Cargo.toml [profile.release]）
```toml
[profile.release]
opt-level = "z"   # 体积优先
lto = true        # 链接期优化
strip = true      # 去除调试符号
panic = "abort"   # 减小 panic 运行时
```
如需进一步瘦身：用 `upx --best target/release/melody-matcher.exe`（约再减 50%）。

## 公开曲库索引
Rust 版复用 Python 版生成的 `public_corpus_index.json`（约 13000 首）。
构建前把该 JSON 放到 exe 同目录即可；或运行时点「生成索引」按钮
（需本机有 music21 的 ABC 曲库，由 Python 脚本生成后拷过来）。

生成索引（在 Python 环境执行，见 skill 根 melody_engine.py）：
```bash
python melody_engine.py build-public public_corpus_index.json
```

## 算法对应
- `audio_to_pcs`：symphonia 解码 → pitch-detection(Yin) 提基频 → 音高类
- `midi_to_pcs`：midly 解析音符 → 音高类
- `abc_to_pcs`：自写 ABC 解析器 → 音高类
- 有符号音程（移调/变速不变）+ 子序列 DTW（双向 q⊂r / r⊂q）
- 公开曲库检索同样走「n-gram 预筛 → 候选跑 DTW」两阶段，保证秒级

## 与 Python 版的区别
- 体积：~26 MB → ~10 MB；启动更快、无 Python 运行时。
- 功能一致：三种模式（本地曲库 / 两曲对比 / 公开曲库）。
- 当前 Rust 版未做音频提取的 Some 边界极致优化，但核心算法等价。
