# -*- coding: utf-8 -*-
"""
旋律相似度检测引擎（精简版，无 librosa/scipy/pretty_midi 依赖）
- 音频 -> 音高类序列 -> 有符号音程（移调/变速不变） via 自写 NumPy Yin + soundfile
- MIDI  -> 主旋律 -> 音高类序列 via mido
- ABC   -> 音高类序列（公开曲库 thesession.org 用）
- 子序列 DTW 双向比对，找最像的段落
依赖：numpy, soundfile, mido（可选 aubio 加速）
"""
import os
import sys
import json
import math
import urllib.request

import numpy as np
import soundfile as sf

try:
    import mido
    HAVE_MIDO = True
except Exception:
    HAVE_MIDO = False

try:
    import aubio
    HAVE_AUBIO = True
except Exception:
    HAVE_AUBIO = False

# ---------------- 常量 ----------------
REST = -99            # 休止哨兵
REST_PENALTY = 3.0   # 休止 vs 音符的代价
MAX_INTERVAL = 6     # 音程取值范围，用于相似度归一化
SKIP_PENALTY = 1.5   # 跳过参考音（子序列滑动）的代价
SIM_SCALE = 12.0     # 相似度缩放

NOTE_BASE = {'C': 0, 'D': 2, 'E': 4, 'F': 5, 'G': 7, 'A': 9, 'B': 11}


# ---------------- 音高类 / 音程 ----------------
def midi_hz_to_pc(f0):
    m = 69 + 12 * math.log2(f0 / 440.0)
    return ((int(round(m)) % 12) + 12) % 12


def pcs_to_intervals(pcs):
    ivs = []
    prev = None
    for p in pcs:
        if p == REST:
            ivs.append(REST)
            prev = None
            continue
        if prev is None:
            ivs.append(0)
        else:
            d = (p - prev) % 12
            if d > 6:
                d -= 12
            ivs.append(d)
        prev = p
    return ivs


def _collapse_rests(seq, max_run=4):
    out = []
    run = 0
    for x in seq:
        if x == REST:
            run += 1
            if run <= max_run:
                out.append(REST)
        else:
            run = 0
            out.append(x)
    return out


# ---------------- 音频 -> 音高类 ----------------
def _resample_mean(x, factor):
    if factor <= 1:
        return x
    n = len(x) // factor * factor
    if n == 0:
        return x
    return x[:n].reshape(-1, factor).mean(axis=1)


def _yin_frame(frame, sr, fmin, fmax, threshold):
    n = len(frame)
    tau_max = int(sr / fmin)
    tau_min = max(1, int(sr / fmax))
    if tau_max >= n:
        tau_max = n - 1
    if tau_max < 2:
        return 0.0
    d = np.zeros(tau_max + 1, dtype=np.float64)
    for tau in range(1, tau_max + 1):
        diff = frame[tau:] - frame[:n - tau]
        d[tau] = float(np.dot(diff, diff))
    cmnd = np.ones(tau_max + 1, dtype=np.float64)
    s = 0.0
    for tau in range(1, tau_max + 1):
        s += d[tau]
        cmnd[tau] = (d[tau] * tau / s) if s > 0 else 1.0
    tau = tau_min
    while tau < tau_max:
        if cmnd[tau] < threshold:
            while tau + 1 < tau_max and cmnd[tau + 1] < cmnd[tau]:
                tau += 1
            break
        tau += 1
    if tau >= tau_max or cmnd[tau] >= threshold:
        return 0.0
    if 0 < tau < tau_max:
        x0, x1, x2 = cmnd[tau - 1], cmnd[tau], cmnd[tau + 1]
        denom = (x0 + x2 - 2 * x1)
        p = 0.5 * (x0 - x2) / denom if denom != 0 else 0.0
        tau = tau + p
    return sr / tau


def _audio_to_f0_aubio(path, sr_target=11025, hop=512, fmin=70, fmax=1000):
    from aubio import source, pitch
    s = source(path, 0, hop, 1)
    p = pitch("yin", hop, 2048, 1)
    p.set_unit("Hz")
    p.set_silence(-40)
    f0s = []
    while True:
        samples, read = s()
        if read < 1:
            break
        f = p(samples)[0]
        f0s.append(f if fmin <= f <= fmax else 0.0)
    return f0s


def audio_to_pcs(path, sr_target=11025, hop=512, win=1024, fmin=70, fmax=1000,
                 threshold=0.12):
    if HAVE_AUBIO:
        try:
            f0s = _audio_to_f0_aubio(path, sr_target, hop, fmin, fmax)
            pcs = [midi_hz_to_pc(f) if f > 0 else REST for f in f0s]
            return _collapse_rests(pcs)
        except Exception:
            pass
    data, sr = sf.read(path, dtype='float32', always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    factor = max(1, int(round(sr / sr_target)))
    if factor > 1:
        data = _resample_mean(data.astype(np.float64), factor)
        sr = sr // factor
    peak = np.max(np.abs(data))
    if peak > 0:
        data = data / peak
    n = len(data)
    pcs = []
    for start in range(0, max(1, n - win), hop):
        frame = data[start:start + win]
        if len(frame) < win:
            frame = np.pad(frame, (0, win - len(frame)))
        f0 = _yin_frame(frame, sr, fmin, fmax, threshold)
        pcs.append(midi_hz_to_pc(f0) if f0 > 0 else REST)
    return _collapse_rests(pcs)


# ---------------- MIDI -> 音高类 ----------------
def midi_to_pcs(path):
    if not HAVE_MIDO:
        raise RuntimeError("未安装 mido，无法解析 MIDI")
    mid = mido.MidiFile(path)
    best = []
    for track in mid.tracks:
        notes = [msg.note for msg in track
                 if msg.type == 'note_on' and msg.velocity > 0]
        if len(notes) > len(best):
            best = notes
    if not best:
        return []
    return [((nt % 12) + 12) % 12 for nt in best]


# ---------------- ABC -> 音高类 ----------------
def _abc_notes_to_pcs(body):
    pcs = []
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c == '!':
            j = body.find('!', i + 1)
            i = j + 1 if j >= 0 else n
            continue
        if c == '~':
            i += 1
            continue
        if c in '^_=':
            acc = 0
            k = i
            while k < n and body[k] in '^_=':
                acc += 1 if body[k] == '^' else -1
                k += 1
            if k < n and body[k] in 'abcdefgABCDEFG':
                pc = NOTE_BASE[body[k].upper()] + acc
                pcs.append(((pc % 12) + 12) % 12)
                k += 1
                while k < n and body[k] in "'.,":
                    k += 1
                while k < n and body[k] in '0123456789/':
                    k += 1
                i = k
                continue
            i = k
            continue
        if c in 'abcdefgABCDEFG':
            pcs.append(NOTE_BASE[c.upper()] % 12)
            i += 1
            while i < n and body[i] in "'.,":
                i += 1
            while i < n and body[i] in '0123456789/':
                i += 1
            continue
        if c in 'zZ':
            pcs.append(REST)
            i += 1
            while i < n and body[i] in '0123456789/':
                i += 1
            continue
        if c == '[':
            j = body.find(']', i)
            seg = body[i + 1:j] if j >= 0 else ''
            sub = _abc_notes_to_pcs(seg)
            if sub:
                pcs.append(sub[0])
            i = j + 1 if j >= 0 else n
            continue
        if c == ']':
            i += 1
            continue
        i += 1
    return pcs


def abc_to_pcs(text):
    lines = text.splitlines()
    started = False
    body = []
    for line in lines:
        s = line.strip()
        if s.startswith('K:'):
            started = True
            continue
        if not started:
            continue
        if s.startswith('w:') or s.startswith('W:'):
            continue
        body.append(s)
    return _abc_notes_to_pcs('\n'.join(body))


# ---------------- 统一入口：文件 -> 音程序列 ----------------
def extract_intervals(path):
    ext = os.path.splitext(path)[1].lower()
    if ext in ('.mid', '.midi'):
        pcs = midi_to_pcs(path)
    elif ext in ('.abc',):
        with open(path, 'r', encoding='utf-8', errors='replace') as f:
            pcs = abc_to_pcs(f.read())
    else:
        pcs = audio_to_pcs(path)
    return pcs_to_intervals(pcs)


# ---------------- DTW 子序列 ----------------
def _step_cost(a, b):
    if a == REST or b == REST:
        return REST_PENALTY
    d = abs(a - b)
    if d > 6:
        d = 12 - d
    return float(d)


def dtw_subseq(q, r, max_skip=30):
    """把 q 作为 r 的子序列对齐（允许跳过 r 的音），返回归一代价与命中段落。"""
    n = len(q)
    m = len(r)
    if n == 0 or m == 0:
        return dict(norm_cost=1e9, similarity=0.0, ref_start=0, ref_end=0,
                    ref_len=m, query_len=n)
    INF = 1e18
    D = [[INF] * (m + 1) for _ in range(n + 1)]
    B = [[None] * (m + 1) for _ in range(n + 1)]
    D[0][0] = 0.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            c = _step_cost(q[i - 1], r[j - 1])
            best = D[i - 1][j - 1]
            bi, bj = i - 1, j - 1
            if D[i][j - 1] + SKIP_PENALTY < best:
                best = D[i][j - 1] + SKIP_PENALTY
                bi, bj = i, j - 1
            D[i][j] = c + best
            B[i][j] = (bi, bj)
    cells = []
    i, j = n, m
    while (i, j) != (0, 0) and B[i][j] is not None:
        cells.append((i, j))
        i, j = B[i][j]
    cells.append((0, 0))
    cells.reverse()
    rused = [c[1] - 1 for c in cells if c[0] <= n and c[1] >= 1]
    rstart = min(rused) if rused else 0
    rend = max(rused) if rused else 0
    norm = D[n][m] / max(1, n)
    sim = max(0.0, 100.0 - norm * SIM_SCALE)
    return dict(norm_cost=round(norm, 3), similarity=round(sim, 1),
                ref_start=rstart, ref_end=rend, ref_len=m, query_len=n)


def compare_two(a, b, max_len=4000):
    q = extract_intervals(a)
    r = extract_intervals(b)
    if max_len:
        q = q[:max_len]
        r = r[:max_len]
    fwd = dtw_subseq(q, r)
    bwd = dtw_subseq(r, q)
    use_fwd = fwd['similarity'] >= bwd['similarity']
    best = fwd if use_fwd else bwd
    return {
        'a': os.path.basename(a), 'b': os.path.basename(b),
        'similarity': best['similarity'],
        'norm_cost': best['norm_cost'],
        'hit': [best['ref_start'], best['ref_end']],
        # fwd: 命中落在 b（参考曲）内；bwd: 命中落在 a 内
        'dir': 'fwd' if use_fwd else 'bwd',
        'q_len': len(q), 'r_len': len(r),
    }


# ---------------- 本地曲库 ----------------
def load_corpus(corpus_dir, max_len=4000):
    corpus = {}
    if not corpus_dir or not os.path.isdir(corpus_dir):
        return corpus
    for fn in sorted(os.listdir(corpus_dir)):
        ext = os.path.splitext(fn)[1].lower()
        if ext not in ('.mid', '.midi', '.abc'):
            continue
        try:
            iv = extract_intervals(os.path.join(corpus_dir, fn))
            if len(iv) >= 4:
                corpus[fn] = iv[:max_len]
        except Exception:
            continue
    return corpus


def search(file, corpus_dir, top_k=5, max_len=4000):
    q = extract_intervals(file)
    if not q:
        return {'error': '无法提取旋律'}
    corpus = load_corpus(corpus_dir, max_len)
    if not corpus:
        return {'error': '曲库为空', 'query_len': len(q)}
    results = []
    for name, riv in corpus.items():
        fwd = dtw_subseq(q, riv)
        bwd = dtw_subseq(riv, q)
        best = fwd if fwd['similarity'] >= bwd['similarity'] else bwd
        results.append({
            'song': name,
            'similarity': best['similarity'],
            'norm_cost': best['norm_cost'],
            'segment': [best['ref_start'], best['ref_end']],
            'coverage': round(best['ref_end'] / max(1, best['ref_len']), 2),
        })
    results.sort(key=lambda x: x['similarity'], reverse=True)
    return {'query': os.path.basename(file), 'query_len': len(q),
            'top': results[:top_k]}


# ---------------- 公开曲库（内置开放旋律索引，构建自 music21 曲库） ----------------
# music21 本地曲库含 15000+ 首公共领域旋律（Essen 民谣 / 古典 / 巴赫众赞歌等），
# 构建期用 build_public_index() 解析为音程索引 JSON 打进 EXE；
# 运行时只需 numpy + DTW 即可检索，EXE 依旧小巧、无需联网、无需 music21。
PUBLIC_INDEX_NAME = 'public_corpus_index.json'
PUBLIC_TITLES_NAME = 'public_corpus_titles.json'


def resolve_public_index():
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    meipass = getattr(sys, '_MEIPASS', '')
    if meipass:
        cands.append(os.path.join(meipass, PUBLIC_INDEX_NAME))
    cands.append(os.path.join(here, PUBLIC_INDEX_NAME))
    cands.append(os.path.join(here, 'public_corpus', PUBLIC_INDEX_NAME))
    for c in cands:
        if c and os.path.exists(c):
            return c
    return os.path.join(here, PUBLIC_INDEX_NAME)


def resolve_public_titles():
    """定位公开曲库「曲名表」文件（id -> 可读曲名）。"""
    here = os.path.dirname(os.path.abspath(__file__))
    cands = []
    meipass = getattr(sys, '_MEIPASS', '')
    if meipass:
        cands.append(os.path.join(meipass, PUBLIC_TITLES_NAME))
    cands.append(os.path.join(here, PUBLIC_TITLES_NAME))
    for c in cands:
        if c and os.path.exists(c):
            return c
    return os.path.join(here, PUBLIC_TITLES_NAME)


def _find_music21_corpus():
    """定位 music21 内置曲库目录（构建期用，仅定位路径，不解析）。"""
    try:
        import music21
        d = os.path.dirname(music21.__file__)
        cand = os.path.join(d, 'corpus')
        if os.path.isdir(cand):
            return cand
    except Exception:
        pass
    import glob as _glob
    for sp in _glob.glob(os.path.join(sys.prefix, 'lib', 'site-packages', '*')):
        cand = os.path.join(sp, 'music21', 'corpus')
        if os.path.isdir(cand):
            return cand
    return None


def _split_abc_tunes(text):
    """按 X: 头把一份 ABC 文件拆成多首独立曲目。"""
    blocks, cur, started = [], [], False
    for ln in text.splitlines():
        if ln.strip().startswith('X:'):
            if cur:
                blocks.append('\n'.join(cur))
            cur, started = [ln], True
        elif started:
            cur.append(ln)
    if cur:
        blocks.append('\n'.join(cur))
    return blocks


def _abc_title(block):
    """取 ABC 曲目的可读曲名（T: 字段；无则返回空串）。"""
    for ln in block.splitlines():
        s = ln.strip()
        if len(s) >= 2 and s[0] in 'Tt' and s[1] == ':':
            t = s[2:].strip()
            if t:
                return t
    return ''


def build_public_index(out_path, max_len=600):
    """构建期调用：把 music21 内置曲库的全部 ABC 按曲目拆开，解析为音程索引。
    纯 Python（abc_to_pcs），不调用 music21 解析器，速度快、无重依赖。
    同时写出「曲名表」public_corpus_titles.json（id -> 真实曲名）。"""
    import glob as _glob
    root = _find_music21_corpus()
    if not root:
        raise RuntimeError('未找到 music21 曲库，请先 pip install music21')
    idx = {}
    titles = {}
    count = 0
    files = sorted(_glob.glob(os.path.join(root, '**', '*.abc'), recursive=True))
    for path in files:
        try:
            with open(path, 'r', encoding='utf-8', errors='replace') as f:
                text = f.read()
        except Exception:
            continue
        base = os.path.splitext(os.path.basename(path))[0]
        for ti, tb in enumerate(_split_abc_tunes(text), 1):
            try:
                pcs = abc_to_pcs(tb)
            except Exception:
                continue
            iv = pcs_to_intervals(pcs)[:max_len]
            if len(iv) >= 4:
                key = f'{base}#{ti}'
                idx[key] = iv
                titles[key] = _abc_title(tb)
                count += 1
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(idx, f)
    tpath = os.path.join(os.path.dirname(os.path.abspath(out_path)), PUBLIC_TITLES_NAME)
    with open(tpath, 'w', encoding='utf-8') as f:
        json.dump(titles, f, ensure_ascii=False)
    return count


def load_public_titles(titles_path=None):
    """加载曲名表；外部文件读取失败时回退到内嵌模块（内存加载）。"""
    try:
        if titles_path and os.path.exists(titles_path):
            with open(titles_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    try:
        import public_corpus_data
        return getattr(public_corpus_data, 'PUBLIC_TITLES', {})
    except Exception:
        return {}


def load_public_index(index_path, rebuild=False, max_len=600):
    # 优先读外部 JSON（便于用户自行更新索引）；
    # 若读取失败（少数系统上临时目录被杀毒软件锁定），回退到内嵌索引（内存加载，无需临时文件）。
    try:
        if index_path and os.path.exists(index_path):
            with open(index_path, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception:
        pass
    try:
        import public_corpus_data
        return public_corpus_data.PUBLIC_INDEX
    except Exception:
        return {}


def _bigrams(iv):
    """相邻音程对集合，作为快速预筛特征（旋律轮廓的局部形状）。"""
    return set((iv[i], iv[i + 1]) for i in range(len(iv) - 1))


def public_search(file, public_dir, index_path, top_k=8, rebuild=False, max_len=600,
                  filter_frac=0.2, max_candidates=200, dtw_ref_cap=300):
    """对 1.2 万+ 首公开曲库做相似检索。

    两阶段：阶段1 用相邻音程对的集合交集做 O(n) 量级快速预筛（秒级），
    仅保留与查询重合度达标的候选；阶段2 再对少量候选跑精确子序列 DTW，
    避免对万首曲目逐一跑 O(n·m) 动态规划导致卡死。
    """
    q = extract_intervals(file)[:max_len]
    if not q:
        return {'error': '无法提取旋律'}
    idx = load_public_index(index_path, rebuild, max_len)
    if not idx:
        return {'error': '公开曲库索引未生成，请先点“生成公开曲库索引”（需 music21）',
                'query_len': len(q)}
    titles = load_public_titles(os.path.join(os.path.dirname(index_path), PUBLIC_TITLES_NAME))
    qbg = _bigrams(q)
    if not qbg:
        return {'error': '旋律太短，无法比对', 'query_len': len(q)}
    # 阶段1：n-gram 快速预筛
    cands = []
    for name, riv in idx.items():
        rbg = _bigrams(riv)
        if not rbg:
            continue
        frac = len(qbg & rbg) / len(qbg)
        if frac >= filter_frac:
            cands.append((name, riv, frac))
    cands.sort(key=lambda x: x[2], reverse=True)
    if len(cands) > max_candidates:
        cands = cands[:max_candidates]
    # 阶段2：仅对候选跑精确子序列 DTW
    results = []
    for name, riv, frac in cands:
        rcap = riv[:dtw_ref_cap]
        fwd = dtw_subseq(q, rcap)
        bwd = dtw_subseq(rcap, q)
        use_fwd = fwd['similarity'] >= bwd['similarity']
        best = fwd if use_fwd else bwd
        results.append({
            'song': name,
            'title': (titles.get(name) or '').strip(),
            'similarity': best['similarity'],
            'norm_cost': best['norm_cost'],
            'segment': [best['ref_start'], best['ref_end']],
            'coverage': round(best['ref_end'] / max(1, best['ref_len']), 2),
            'dir': 'fwd' if use_fwd else 'bwd',
            'prefilter': round(frac, 2),
        })
    results.sort(key=lambda x: x['similarity'], reverse=True)
    return {'query': os.path.basename(file), 'query_len': len(q),
            'public_total': len(idx), 'candidates': len(cands),
            'best_similarity': (results[0]['similarity'] if results else 0.0),
            'top': results[:top_k]}


def resolve_corpus():
    here = os.path.dirname(os.path.abspath(__file__))
    meipass = getattr(sys, '_MEIPASS', '')
    if meipass:
        cand = os.path.join(meipass, 'corpus')
        if os.path.isdir(cand):
            return cand
    cand = os.path.join(here, 'corpus')
    if os.path.isdir(cand):
        return cand
    return os.path.join(here, '..', 'corpus')


# ---------------- 自测 ----------------
def self_test():
    out = {}
    # 1) 移调不变：用本地曲库小星星测试
    corpus_dir = resolve_corpus()
    star = None
    for fn in os.listdir(corpus_dir):
        if '小星星' in fn or 'Twinkle' in fn:
            star = os.path.join(corpus_dir, fn)
    if star:
        r = search(star, corpus_dir, top_k=1)
        out['transpose_self'] = r.get('top', [{}])[0].get('similarity')
    # 2) 音频提取：合成正弦旋律
    try:
        import tempfile
        sr = 11025
        freqs = [440, 440, 494, 523, 587, 523, 494, 440]
        sig = np.concatenate([np.sin(2 * np.pi * f * np.arange(sr // 4) / sr)
                              for f in freqs]).astype(np.float32)
        td = tempfile.mkdtemp()
        wav = os.path.join(td, 'tone.wav')
        sf.write(wav, sig, sr)
        pcs = audio_to_pcs(wav)
        out['audio_pcs'] = pcs
    except Exception as e:
        out['audio_err'] = str(e)
    return out


if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else ''
    if mode == 'self-test':
        print(json.dumps(self_test(), ensure_ascii=False, indent=2))
    elif mode == 'query':
        r = search(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else resolve_corpus(),
                   top_k=int(sys.argv[4]) if len(sys.argv) > 4 else 5)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    elif mode == 'compare':
        print(json.dumps(compare_two(sys.argv[2], sys.argv[3]),
                         ensure_ascii=False, indent=2))
    elif mode == 'build-public':
        here = os.path.dirname(os.path.abspath(__file__))
        out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(here, PUBLIC_INDEX_NAME)
        n = build_public_index(out)
        print(f'built {n} entries -> {out}')
    elif mode == 'public':
        here = os.path.dirname(os.path.abspath(__file__))
        ip = sys.argv[3] if len(sys.argv) > 3 else os.path.join(here, PUBLIC_INDEX_NAME)
        r = public_search(sys.argv[2], os.path.dirname(ip), ip,
                           top_k=int(sys.argv[4]) if len(sys.argv) > 4 else 8)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else:
        print('modes: self-test | query <file> [corpus] [top] | compare <a> <b> | '
              'fetch-public [dir] | public <file> [dir] [top]')
