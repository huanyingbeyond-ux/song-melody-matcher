// 旋律相似度检测 · Rust 迷你版（~10MB 单文件 EXE）
// 依赖：eframe/egui 界面 + rfd 选文件 + symphonia 解码 + pitch-detection(Yin)
//       + midly(MIDI) + serde_json(索引)。全程本地，不上传。
//
// 构建：cargo build --release  （需 Rust 工具链 + C/C++ 链接器，如 MSVC 或 MinGW）
// 用法：
//   melody-matcher                 启动图形界面
//   melody-matcher query <歌> [曲库目录]      查本地曲库
//   melody-matcher compare <A> <B>           两曲直接对比
//   melody-matcher build <曲库目录> <索引.json>  构建公开/本地索引
//   melody-matcher public <歌> [索引.json]     查公开曲库索引

use std::collections::HashMap;
use std::path::{Path, PathBuf};

const REST: i32 = -99;
const SKIP_PENALTY: f32 = 1.5;

// ---------------- 音高类 / 音程 ----------------
fn midi_hz_to_pc(f0: f32) -> i32 {
    let m = 69.0 + 12.0 * (f0 / 440.0).log2();
    ((m.round() as i32) % 12 + 12) % 12
}

fn pcs_to_intervals(pcs: &[i32]) -> Vec<i32> {
    let mut out = Vec::new();
    let mut prev: Option<i32> = None;
    for &p in pcs {
        if p == REST {
            out.push(REST);
            prev = None;
            continue;
        }
        match prev {
            None => out.push(0),
            Some(pr) => {
                let mut d = (p - pr) % 12;
                if d > 6 {
                    d -= 12;
                }
                out.push(d);
            }
        }
        prev = Some(p);
    }
    out
}

fn collapse_rests(seq: &[i32], max_run: usize) -> Vec<i32> {
    let mut out = Vec::new();
    let mut run = 0;
    for &x in seq {
        if x == REST {
            run += 1;
            if run <= max_run {
                out.push(REST);
            }
        } else {
            run = 0;
            out.push(x);
        }
    }
    out
}

// ---------------- 音频 -> 音高类（symphonia 解码 + Yin） ----------------
fn audio_to_pcs(path: &Path) -> Result<Vec<i32>, String> {
    use symphonia::core::audio::SampleFormat;
    use symphonia::core::io::MediaSourceStream;
    use symphonia::default::get_codecs;
    use symphonia::default::get_probe;

    let f = std::fs::File::open(path).map_err(|e| e.to_string())?;
    let mss = MediaSourceStream::new(Box::new(f), Default::default());
    let probed = get_probe().probe(&mss).map_err(|e| e.to_string())?;
    let mut format = probed.format;
    let track = format.default_track().ok_or("无音频轨道")?;
    let track_id = track.id;
    let sr = track.codec_params.sample_rate.unwrap_or(44100) as usize;
    let mut decoder =
        get_codecs().make(&track.codec_params, &symphonia::core::codec::DecoderOptions::default())
            .map_err(|e| e.to_string())?;

    let mut samples: Vec<f32> = Vec::new();
    loop {
        let packet = match format.next_packet() {
            Ok(p) => p,
            Err(_) => break,
        };
        if packet.track_id() != track_id {
            continue;
        }
        let buf = match decoder.decode(&packet) {
            Ok(b) => b,
            Err(_) => continue,
        };
        match buf.spec().sample_format {
            SampleFormat::F32 => {
                let ch = buf.chan::<f32>(0);
                samples.extend_from_slice(ch);
            }
            SampleFormat::I16 => {
                for &s in buf.chan::<i16>(0) {
                    samples.push(s as f32 / 32768.0);
                }
            }
            SampleFormat::I32 => {
                for &s in buf.chan::<i32>(0) {
                    samples.push(s as f32 / 2147483647.0);
                }
            }
            SampleFormat::U8 => {
                for &s in buf.chan::<u8>(0) {
                    samples.push((s as f32 - 128.0) / 128.0);
                }
            }
            _ => {}
        }
    }
    if samples.is_empty() {
        return Err("解码后无音频".into());
    }

    use pitch_detection::yin::Yin;
    let frame_size = 2048usize;
    let hop = 1024usize;
    let mut yin = Yin::new(sr, frame_size);
    let mut pcs = Vec::new();
    let mut i = 0;
    while i + frame_size <= samples.len() {
        let frame = &samples[i..i + frame_size];
        match yin.get_pitch(frame) {
            Some((pitch, _clar)) => {
                if pitch > 0.0 {
                    pcs.push(midi_hz_to_pc(pitch));
                } else {
                    pcs.push(REST);
                }
            }
            None => pcs.push(REST),
        }
        i += hop;
    }
    Ok(collapse_rests(&pcs, 4))
}

// ---------------- MIDI -> 音高类（midly） ----------------
fn midi_to_pcs(path: &Path) -> Result<Vec<i32>, String> {
    use midly::{MidiMessage, Smf, TrackEventKind};
    let data = std::fs::read(path).map_err(|e| e.to_string())?;
    let smf = Smf::parse(&data).map_err(|e| e.to_string())?;
    let mut best: Vec<u8> = Vec::new();
    for track in &smf.tracks {
        let mut notes = Vec::new();
        for ev in track {
            if let TrackEventKind::Midi { message: MidiMessage::NoteOn { key, .. }, .. } = ev.kind {
                notes.push(key.as_int());
            }
        }
        if notes.len() > best.len() {
            best = notes;
        }
    }
    Ok(best.into_iter().map(|k| (k as i32 % 12 + 12) % 12).collect())
}

// ---------------- ABC -> 音高类 ----------------
fn abc_to_pcs(text: &str) -> Vec<i32> {
    let base: HashMap<char, i32> = [('C', 0), ('D', 2), ('E', 4), ('F', 5), ('G', 7), ('A', 9), ('B', 11)]
        .iter()
        .cloned()
        .collect();
    let mut started = false;
    let mut body = String::new();
    for line in text.lines() {
        let s = line.trim();
        if s.starts_with("K:") {
            started = true;
            continue;
        }
        if !started {
            continue;
        }
        if s.starts_with("w:") || s.starts_with("W:") {
            continue;
        }
        body.push_str(line);
        body.push('\n');
    }
    let chars: Vec<char> = body.chars().collect();
    let mut pcs = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        let c = chars[i];
        if c == '!' {
            while i < chars.len() && chars[i] != '!' {
                i += 1;
            }
            if i < chars.len() {
                i += 1;
            }
            continue;
        }
        if c == '~' {
            i += 1;
            continue;
        }
        if c == '^' || c == '_' || c == '=' {
            let mut acc = 0i32;
            let mut k = i;
            while k < chars.len() && (chars[k] == '^' || chars[k] == '_' || chars[k] == '=') {
                acc += if chars[k] == '^' { 1 } else { -1 };
                k += 1;
            }
            if (k < chars.len() && chars[k].is_ascii_lowercase())
                || (k < chars.len() && chars[k].is_ascii_uppercase())
            {
                let upper = chars[k].to_ascii_uppercase();
                if let Some(&b) = base.get(&upper) {
                    pcs.push(((b + acc) % 12 + 12) % 12);
                }
                k += 1;
                while k < chars.len() && (chars[k] == '\'' || chars[k] == ',') {
                    k += 1;
                }
                while k < chars.len() && (chars[k].is_ascii_digit() || chars[k] == '/') {
                    k += 1;
                }
                i = k;
                continue;
            }
            i = k;
            continue;
        }
        if c.is_ascii_lowercase() || c.is_ascii_uppercase() {
            let upper = c.to_ascii_uppercase();
            if let Some(&b) = base.get(&upper) {
                pcs.push((b % 12 + 12) % 12);
            }
            i += 1;
            while i < chars.len() && (chars[i] == '\'' || chars[i] == ',') {
                i += 1;
            }
            while i < chars.len() && (chars[i].is_ascii_digit() || chars[i] == '/') {
                i += 1;
            }
            continue;
        }
        if c == 'z' || c == 'Z' {
            pcs.push(REST);
            i += 1;
            while i < chars.len() && (chars[i].is_ascii_digit() || chars[i] == '/') {
                i += 1;
            }
            continue;
        }
        if c == '[' {
            let mut j = i + 1;
            while j < chars.len() && chars[j] != ']' {
                j += 1;
            }
            i = if j < chars.len() { j + 1 } else { chars.len() };
            continue;
        }
        i += 1;
    }
    pcs
}

// ---------------- 统一入口 ----------------
fn extract_intervals(path: &Path) -> Result<Vec<i32>, String> {
    let ext = path
        .extension()
        .and_then(|s| s.to_str())
        .unwrap_or("")
        .to_lowercase();
    let pcs = if ext == "mid" || ext == "midi" {
        midi_to_pcs(path)?
    } else if ext == "abc" {
        abc_to_pcs(&std::fs::read_to_string(path).map_err(|e| e.to_string())?)
    } else {
        audio_to_pcs(path)?
    };
    Ok(pcs_to_intervals(&pcs))
}

// ---------------- DTW 子序列 ----------------
fn step_cost(a: i32, b: i32) -> f32 {
    if a == REST || b == REST {
        return 3.0;
    }
    let mut d = (a - b).abs();
    if d > 6 {
        d = 12 - d;
    }
    d as f32
}

fn dtw_subseq(q: &[i32], r: &[i32]) -> (f32, usize, usize) {
    let n = q.len();
    let m = r.len();
    if n == 0 || m == 0 {
        return (0.0, 0, 0);
    }
    let mut d = vec![vec![1e18f32; m + 1]; n + 1];
    let mut b = vec![vec![(0usize, 0usize); m + 1]; n + 1];
    d[0][0] = 0.0;
    for i in 1..=n {
        for j in 1..=m {
            let c = step_cost(q[i - 1], r[j - 1]);
            let mut best = d[i - 1][j - 1];
            let mut bi = i - 1;
            let mut bj = j - 1;
            if d[i][j - 1] + SKIP_PENALTY < best {
                best = d[i][j - 1] + SKIP_PENALTY;
                bi = i;
                bj = j - 1;
            }
            d[i][j] = c + best;
            b[i][j] = (bi, bj);
        }
    }
    let mut i = n;
    let mut j = m;
    let mut rstart = m;
    let mut rend = 0;
    while (i, j) != (0, 0) && b[i][j] != (0, 0) {
        if i <= n && j >= 1 {
            rstart = rstart.min(j - 1);
            rend = rend.max(j - 1);
        }
        let (ni, nj) = b[i][j];
        i = ni;
        j = nj;
    }
    let norm = d[n][m] / (n as f32);
    let sim = (100.0 - norm * 12.0).max(0.0);
    (sim, rstart, rend)
}

// ---------------- 曲库 / 索引 ----------------
fn resolve_corpus() -> PathBuf {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let c = dir.join("corpus");
            if c.is_dir() {
                return c;
            }
        }
    }
    PathBuf::from("corpus")
}

fn resolve_public_index() -> PathBuf {
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            let p = dir.join("public_corpus_index.json");
            if p.exists() {
                return p;
            }
        }
    }
    PathBuf::from("public_corpus_index.json")
}

fn load_corpus(dir: &Path) -> HashMap<String, Vec<i32>> {
    let mut map = HashMap::new();
    if let Ok(entries) = std::fs::read_dir(dir) {
        for e in entries.flatten() {
            let p = e.path();
            let ext = p
                .extension()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_lowercase();
            if ext != "mid" && ext != "midi" && ext != "abc" {
                continue;
            }
            if let Ok(iv) = extract_intervals(&p) {
                if iv.len() >= 4 {
                    map.insert(p.file_name().unwrap().to_string_lossy().to_string(), iv);
                }
            }
        }
    }
    map
}

fn build_index(dir: &Path, out: &Path) -> usize {
    let map = load_corpus(dir);
    if let Ok(json) = serde_json::to_string(&map) {
        let _ = std::fs::write(out, json);
    }
    map.len()
}

fn load_index(path: &Path) -> HashMap<String, Vec<i32>> {
    if let Ok(s) = std::fs::read_to_string(path) {
        serde_json::from_str(&s).unwrap_or_default()
    } else {
        HashMap::new()
    }
}

// ---------------- 结果文本 ----------------
fn fmt_pct(x: f32) -> String {
    format!("{:.1}%", x)
}

fn search_text(file: &Path, corpus_dir: &Path) -> String {
    let q = match extract_intervals(file) {
        Ok(v) => v,
        Err(e) => return format!("⚠ 提取失败: {}", e),
    };
    if q.is_empty() {
        return "⚠ 无法提取旋律".into();
    }
    let corpus = load_corpus(corpus_dir);
    if corpus.is_empty() {
        return "⚠ 曲库为空（往 corpus 目录放 MIDI/ABC）".into();
    }
    let mut res: Vec<(String, f32, usize, usize)> = Vec::new();
    for (name, riv) in &corpus {
        let (fs, rs, re) = dtw_subseq(&q, riv);
        let (bs, rs2, re2) = dtw_subseq(riv, &q);
        let (sim, s, e) = if fs >= bs { (fs, rs, re) } else { (bs, rs2, re2) };
        res.push((name.clone(), sim, s, e));
    }
    res.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
    let mut out = format!("【查本地曲库】{}\n查询旋律 {} 音\n\n", file_name(file), q.len());
    for (i, (name, sim, s, e)) in res.iter().take(5).enumerate() {
        out.push_str(&format!(
            "{}. {}   相似度 {}\n   命中第{}-{}音\n",
            i + 1,
            name,
            fmt_pct(*sim),
            s,
            e
        ));
    }
    out.push_str("\n提示：top 结果明显高出其余才值得重点核对；一堆 70-85% 多为常见句式巧合。\n");
    out
}

fn compare_text(a: &Path, b: &Path) -> String {
    let q = match extract_intervals(a) {
        Ok(v) => v,
        Err(e) => return format!("⚠ A 提取失败: {}", e),
    };
    let r = match extract_intervals(b) {
        Ok(v) => v,
        Err(e) => return format!("⚠ B 提取失败: {}", e),
    };
    if q.is_empty() || r.is_empty() {
        return "⚠ 无法提取旋律".into();
    }
    let (fs, s, e) = dtw_subseq(&q, &r);
    let (bs, s2, e2) = dtw_subseq(&r, &q);
    let (sim, seg_s, seg_e) = if fs >= bs { (fs, s, e) } else { (bs, s2, e2) };
    let tag = if sim >= 85.0 {
        "极可能高度相似"
    } else if sim >= 70.0 {
        "较相似，建议核对"
    } else {
        "相似度不高"
    };
    format!(
        "【两曲对比】{}  vs  {}\n\n相似度：{}   （{}）\n命中段落：参考曲第 {}-{} 音\n查询长度 {} / 参考长度 {}\n\n本工具为旋律形状相似度辅助，非法律意义上的抄袭鉴定。",
        file_name(a),
        file_name(b),
        fmt_pct(sim),
        tag,
        seg_s,
        seg_e,
        q.len(),
        r.len()
    )
}

fn public_text(file: &Path, index: &Path) -> String {
    let q = match extract_intervals(file) {
        Ok(v) => v,
        Err(e) => return format!("⚠ 提取失败: {}", e),
    };
    if q.is_empty() {
        return "⚠ 无法提取旋律".into();
    }
    let idx = load_index(index);
    if idx.is_empty() {
        return "⚠ 公开曲库索引未生成，请先 build 生成 public_corpus_index.json".into();
    }
    let mut res: Vec<(String, f32, usize, usize)> = Vec::new();
    for (name, riv) in &idx {
        let (fs, rs, re) = dtw_subseq(&q, riv);
        let (bs, rs2, re2) = dtw_subseq(riv, &q);
        let (sim, s, e) = if fs >= bs { (fs, rs, re) } else { (bs, rs2, re2) };
        res.push((name.clone(), sim, s, e));
    }
    res.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap());
    let mut out = format!(
        "【查公开开放曲库】{}\n公开曲库规模：{} 首\n\n",
        file_name(file),
        idx.len()
    );
    for (i, (name, sim, s, e)) in res.iter().take(8).enumerate() {
        out.push_str(&format!("{}. {}   相似度 {}\n   命中第{}-{}音\n", i + 1, name, fmt_pct(*sim), s, e));
    }
    out
}

fn file_name(p: &Path) -> String {
    p.file_name().unwrap().to_string_lossy().to_string()
}

fn run_detect(mode: &str, files: &[PathBuf], corpus: &Path, index: &Path) -> String {
    match mode {
        "compare" if files.len() >= 2 => compare_text(&files[0], &files[1]),
        "public" if !files.is_empty() => public_text(&files[0], index),
        "local" if !files.is_empty() => search_text(&files[0], corpus),
        _ => "请选择文件（两曲对比需两首）。".into(),
    }
}

// ---------------- 图形界面 ----------------
struct MelodyApp {
    mode: String,
    files: Vec<PathBuf>,
    output: String,
    status: String,
    rx: Option<std::sync::mpsc::Receiver<String>>,
}

impl eframe::App for MelodyApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        egui::CentralPanel::default().show(ctx, |ui| {
            ui.heading("旋律相似度检测");
            ui.horizontal(|ui| {
                ui.radio_value(&mut self.mode, "local".to_string(), "查本地曲库");
                ui.radio_value(&mut self.mode, "compare".to_string(), "两曲对比");
                ui.radio_value(&mut self.mode, "public".to_string(), "查公开曲库");
            });
            let names: Vec<String> = self
                .files
                .iter()
                .map(|p| file_name(p))
                .collect();
            ui.label(format!("已选：{}", names.join("  |  ")));
            ui.horizontal(|ui| {
                if ui.button("选择文件").clicked() {
                    if let Some(fs) = rfd::FileDialog::new().pick_files() {
                        self.files = fs;
                    }
                }
                if ui.button("开始检测").clicked() {
                    self.start(ctx);
                }
            });
            ui.label(&self.status);
            ui.separator();
            ui.label(&self.output);
        });
        if let Some(rx) = &mut self.rx {
            if let Ok(msg) = rx.try_recv() {
                self.output = msg;
                self.status = "完成".into();
            }
        }
    }
}

impl MelodyApp {
    fn start(&mut self, ctx: &egui::Context) {
        let mode = self.mode.clone();
        let files = self.files.clone();
        let corpus = resolve_corpus();
        let index = resolve_public_index();
        let (tx, rx) = std::sync::mpsc::channel();
        self.rx = Some(rx);
        self.status = "检测中…".into();
        let ctx2 = ctx.clone();
        std::thread::spawn(move || {
            let res = run_detect(&mode, &files, &corpus, &index);
            let _ = tx.send(res);
            ctx2.request_repaint();
        });
    }
}

fn run_gui() {
    let options = eframe::NativeOptions::default();
    let _ = eframe::run_native(
        "旋律相似度检测",
        options,
        Box::new(|_cc| Ok(Box::new(MelodyApp {
            mode: "local".to_string(),
            files: Vec::new(),
            output: "模式说明：\n· 查本地曲库：把歌拖入(或选文件)，与 corpus 目录比对。\n· 两曲对比：选两首直接给相似度。\n· 查公开曲库：与 public_corpus_index.json 比对。\n\n免责：旋律形状相似度辅助，非法律抄袭鉴定。".to_string(),
            status: String::new(),
            rx: None,
        }))),
    );
}

// ---------------- 入口 ----------------
fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() < 2 {
        run_gui();
        return;
    }
    match args[1].as_str() {
        "query" => {
            let file = PathBuf::from(&args[2]);
            let corpus = if args.len() > 3 {
                PathBuf::from(&args[3])
            } else {
                resolve_corpus()
            };
            println!("{}", search_text(&file, &corpus));
        }
        "compare" => {
            if args.len() < 4 {
                eprintln!("用法: melody-matcher compare <A> <B>");
                return;
            }
            println!("{}", compare_text(&PathBuf::from(&args[2]), &PathBuf::from(&args[3])));
        }
        "build" => {
            if args.len() < 4 {
                eprintln!("用法: melody-matcher build <曲库目录> <索引.json>");
                return;
            }
            let n = build_index(&PathBuf::from(&args[2]), &PathBuf::from(&args[3]));
            println!("built {} entries -> {}", n, args[3]);
        }
        "public" => {
            let file = PathBuf::from(&args[2]);
            let index = if args.len() > 3 {
                PathBuf::from(&args[3])
            } else {
                resolve_public_index()
            };
            println!("{}", public_text(&file, &index));
        }
        _ => {
            eprintln!("modes: query <歌> [曲库] | compare <A> <B> | build <曲库> <索引.json> | public <歌> [索引]");
        }
    }
}
