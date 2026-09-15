# -*- coding: utf-8 -*-
"""旋律相似度检测 - 图形界面（tkinter，单文件 EXE 友好）"""
import os
import sys
import json
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import melody_engine as me

CORPUS_DIR = me.resolve_corpus()
PUBLIC_INDEX = me.resolve_public_index()

# ---------------- 拖拽（Windows WM_DROPFILES，无需额外依赖） ----------------
try:
    import ctypes
    from ctypes import wintypes, WINFUNCTYPE
    _SHELL = ctypes.windll.shell32
    _USER = ctypes.windll.user32
    GWL_WNDPROC = -4
    WM_DROPFILES = 0x0233
    DragAcceptFiles = _SHELL.DragAcceptFiles
    DragQueryFile = _SHELL.DragQueryFileW
    DragFinish = _SHELL.DragFinish
    SetWindowLongPtr = _USER.SetWindowLongPtrW
    CallWindowProc = _USER.CallWindowProcW
    HAVE_DND = True
except Exception:
    HAVE_DND = False


def enable_drop(hwnd, callback):
    proto = WINFUNCTYPE(wintypes.LRESULT, wintypes.HWND,
                        wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

    def wndproc(h, msg, wp, lp):
        if msg == WM_DROPFILES:
            count = DragQueryFile(wp, 0xFFFFFFFF, None, 0)
            files = []
            for i in range(count):
                length = DragQueryFile(wp, i, None, 0) + 1
                buf = ctypes.create_unicode_buffer(length)
                DragQueryFile(wp, i, buf, length)
                files.append(buf.value)
            DragFinish(wp)
            callback(files)
            return 0
        return CallWindowProc(prev, h, msg, wp, lp)

    fn = proto(wndproc)
    prev = SetWindowLongPtr(hwnd, GWL_WNDPROC, fn)
    DragAcceptFiles(hwnd, True)
    return fn


# ---------------- 结果格式化 ----------------
def fmt_pct(x):
    return f"{x:.1f}%"


def format_result(res, mode):
    if 'error' in res:
        return "⚠ " + res['error']
    lines = []
    if mode == 'compare':
        lines.append(f"【两曲对比】{res['a']}  vs  {res['b']}")
        lines.append("")
        sim = res['similarity']
        tag = "极可能高度相似" if sim >= 85 else ("较相似，建议核对" if sim >= 70 else "相似度不高")
        lines.append(f"相似度：{fmt_pct(sim)}   （{tag}）")
        # fwd 命中落在 b 内，bwd 命中落在 a 内
        where = res['b'] if res.get('dir', 'fwd') == 'fwd' else res['a']
        lines.append(f"命中段落：{where} 第 {res['hit'][0]}–{res['hit'][1]} 个音   "
                     f"（{res['a']} 长 {res['q_len']} 音 / {res['b']} 长 {res['r_len']} 音）")
        lines.append("")
        lines.append("说明：这是旋律形状相似度辅助结果，非法律意义上的抄袭鉴定，")
        lines.append("请结合试听与专业鉴定判断。")
    else:
        title = "本地曲库" if mode == 'local' else "公开开放曲库"
        lines.append(f"【查 {title}】{res.get('query','')}  （查询旋律 {res.get('query_len',0)} 音）")
        if mode == 'public':
            lines.append(f"公开曲库规模：{res.get('public_total',0)} 首  预筛候选：{res.get('candidates',0)} 首")
        lines.append("")
        top = res.get('top', [])
        if not top:
            lines.append("未找到足够相似的曲目。")
        else:
            best = top[0]['similarity']
            if best >= 70:
                verdict = f"★ 结论：发现较明显相似曲目（最高 {fmt_pct(best)}）——重点核对下面第 1 条。"
            elif best >= 55:
                verdict = (f"结论：存在一定相似（最高 {fmt_pct(best)}）——可参考，"
                           f"但未必是同一旋律。")
            else:
                verdict = (f"结论：未发现明显相似曲目——最高仅 {fmt_pct(best)}，"
                           f"属常见旋律句式的巧合，基本可认为该曲库里没有高度雷同的歌。")
            lines.append(verdict)
            if mode == 'public':
                lines.append("（注明：公开库以传统民谣、古典主题、巴赫众赞歌等公共领域旋律为主，"
                             "不含当代流行歌；流行歌在此得低分是正常的。）")
            lines.append("")
        for i, t in enumerate(top, 1):
            nm = (t.get('title') or '').strip() or t.get('song', '')
            lines.append(f"{i}. {nm}   相似度 {fmt_pct(t['similarity'])}")
            seg = t.get('segment', [0, 0])
            where = "参考曲" if t.get('dir', 'fwd') == 'fwd' else "本曲"
            lines.append(f"   命中位置：{where}第 {seg[0]}–{seg[1]} 音，覆盖 {t.get('coverage',0):.0%}")
        lines.append("")
        lines.append("提示：看第 1 条与第 2 条的分数差——明显高出一截才值得重点核对；")
        lines.append("一堆分数挤在一起（如 40% 上下）多为常见句式的巧合。")
    return "\n".join(lines)


class App:
    def __init__(self, root):
        self.root = root
        self.files = []
        self._wndproc_ref = None
        root.title("旋律相似度检测 · 查抄袭 / 像哪首歌")
        root.geometry("720x560")
        try:
            root.tk.call('tk', 'scaling', 1.4)
        except Exception:
            pass

        # 模式
        top = tk.Frame(root)
        top.pack(fill='x', padx=10, pady=8)
        tk.Label(top, text="比对模式：", font=("", 11)).pack(side='left')
        self.mode = tk.StringVar(value='local')
        for txt, val in [("查本地曲库", "local"),
                         ("两曲直接对比", "compare"),
                         ("查公开开放曲库", "public")]:
            tk.Radiobutton(top, text=txt, variable=self.mode, value=val,
                           command=self.on_mode).pack(side='left', padx=6)

        # 文件列表
        mid = tk.Frame(root)
        mid.pack(fill='both', expand=True, padx=10)
        self.lb = tk.Listbox(mid, height=6, font=("", 10))
        self.lb.pack(side='left', fill='both', expand=True)
        side = tk.Frame(mid)
        side.pack(side='left', padx=6)
        tk.Button(side, text="＋ 添加文件", command=self.add_files, width=12).pack(pady=2)
        tk.Button(side, text="－ 移除选中", command=self.remove_file, width=12).pack(pady=2)
        tk.Button(side, text="清空", command=self.clear_files, width=12).pack(pady=2)

        hint = tk.Label(root, text="把歌曲文件拖进窗口即可（支持 mp3/wav/mid/abc）",
                        fg="#555")
        hint.pack(padx=10, anchor='w')

        # 操作
        act = tk.Frame(root)
        act.pack(fill='x', padx=10, pady=6)
        tk.Button(act, text="▶ 开始检测", command=self.start,
                  bg="#2e7d32", fg="white", width=14, height=1,
                  font=("", 11)).pack(side='left', padx=4)
        tk.Button(act, text="打开曲库文件夹", command=self.open_corpus,
                  width=14).pack(side='left', padx=4)
        tk.Button(act, text="公开曲库状态", command=self.build_public,
                  width=14).pack(side='left', padx=4)
        self.status = tk.Label(act, text="", fg="#1565c0")
        self.status.pack(side='left', padx=10)

        # 结果
        self.out = scrolledtext.ScrolledText(root, font=("", 10), wrap='word')
        self.out.pack(fill='both', expand=True, padx=10, pady=6)
        self.out.insert('end', "模式说明：\n"
                        "· 查本地曲库：把你怀疑的歌拖入，与本地 corpus 文件夹比对（往里加 MIDI 扩充）。\n"
                        "· 两曲直接对比：同时拖两首，直接给相似度（最准、最实用；想知道「像不像某首具体的歌」就用它）。\n"
                        "· 查公开开放曲库：与内置的 1.3 万首「公共领域」旋律比对（索引已随程序内置，无需生成）。\n"
                        "  曲库内容：欧美传统民谣、苏格兰/爱尔兰提琴曲、中国民谣、古典主题、巴赫众赞歌等，\n"
                        "  均属公共领域（无版权），**不含当代流行歌**。结果会显示真实曲名。\n\n"
                        "怎么看结果：公开库以传统/古典旋律为主，流行歌通常不在其中，得低分属正常；\n"
                        "真正判断「是否抄袭」，最靠谱的是用「两曲直接对比」去比那首你怀疑的原曲。\n\n"
                        "「公开曲库状态」按钮：查看内置曲库规模与位置（不需要点它也能直接查曲库）。\n\n"
                        "免责：本工具为旋律形状相似度辅助，非法律意义上的抄袭鉴定。")

        # 免责 footer
        tk.Label(root, text="全程本地运行，不上传、不保存你的歌曲。",
                 fg="#888").pack(padx=10, anchor='w', pady=(0, 6))

        # 拖拽
        if HAVE_DND:
            try:
                hwnd = root.winfo_id()
                self._wndproc_ref = enable_drop(hwnd, self.on_drop)
            except Exception:
                pass

    def on_mode(self):
        self.refresh_hint()

    def refresh_hint(self):
        pass

    def on_drop(self, files):
        for f in files:
            if os.path.isfile(f):
                self.files.append(f)
                self.lb.insert('end', os.path.basename(f))

    def add_files(self):
        f = filedialog.askopenfilenames(
            title="选择歌曲文件",
            filetypes=[("音频/MIDI", "*.mp3 *.wav *.ogg *.flac *.m4a *.mid *.midi *.abc"),
                       ("所有文件", "*.*")])
        for p in f:
            self.files.append(p)
            self.lb.insert('end', os.path.basename(p))

    def remove_file(self):
        sel = self.lb.curselection()
        for i in reversed(sel):
            self.lb.delete(i)
            del self.files[i]

    def clear_files(self):
        self.files.clear()
        self.lb.delete(0, 'end')

    def open_corpus(self):
        if not os.path.isdir(CORPUS_DIR):
            os.makedirs(CORPUS_DIR, exist_ok=True)
        os.startfile(CORPUS_DIR)

    def build_public(self):
        """公开曲库状态查询 / 需要时重建索引。

        发行版 EXE 已内置约 1.3 万首索引，无需生成——本按钮先报状态；
        只有在「本机装了 music21」的开发环境里，才提供重建入口。
        """
        st = me.public_index_status()
        src_txt = {'bundled': '程序内置', 'external': 'exe 旁外置索引文件',
                   'none': '无'}.get(st['source'], '无')
        total = st['total']

        if not st['can_rebuild']:
            if total:
                messagebox.showinfo(
                    "公开曲库已就绪",
                    f"无需生成——这份索引是打包时预先生成、并已内置在程序里的。\n\n"
                    f"· 可用曲目：{total} 首（{src_txt}）\n"
                    f"· 曲名表：{st['title_count']} 条\n"
                    f"· 索引位置：{st['index_path']}\n\n"
                    "直接选「查公开开放曲库」，把歌拖进窗口就能比对。\n\n"
                    "为什么不能在这里重新生成？\n"
                    "本机没有安装 music21（程序刻意不带这个库，才把体积从 120MB "
                    "压到 27MB 并保持完全离线可用），因此无法从零重建索引。\n"
                    "如需更新/扩充曲库，见 README 的「更新公开曲库」一节。")
            else:
                messagebox.showerror(
                    "无法生成公开曲库索引",
                    "本机没有 music21 曲库，程序内也没有自带索引，无法生成。\n\n"
                    "解决办法（需联网，仅构建时一次性）：\n"
                    "  1) pip install music21\n"
                    "  2) python tools/build_public.py\n"
                    "  3) pyinstaller build_exe.spec --noconfirm")
            return

        if total:
            if not messagebox.askyesno(
                    "重建公开曲库索引",
                    f"当前曲库：{total} 首（{src_txt}）。\n"
                    f"重建会用本机 music21 曲库重新解析全部旋律，约需十几分钟。\n"
                    f"（结果写入 exe 所在目录，会覆盖现有外置索引）\n\n"
                    f"确定重建？"):
                return
        elif not messagebox.askyesno(
                "生成公开曲库索引",
                "将用 music21 把 15000+ 首开放旋律解析为索引（约需十几分钟）。继续？"):
            return
        self.status.configure(text="正在生成索引…")
        threading.Thread(target=self._build_public, daemon=True).start()

    def _build_public(self):
        try:
            # 写到程序所在目录（打包后即 exe 同级），重启后仍能生效
            out = os.path.join(me.app_dir(), me.PUBLIC_INDEX_NAME)
            n = me.build_public_index(out)
            self.root.after(0, lambda: self.status.configure(
                text=f"索引生成完成：{n} 首"))
            self.root.after(0, lambda: messagebox.showinfo(
                "完成", f"已生成 {n} 首公开曲库索引\n保存到：{out}"))
        except Exception as e:
            msg = str(e)
            self.root.after(0, lambda: self.status.configure(text="生成失败"))
            self.root.after(0, lambda m=msg: messagebox.showerror("生成失败", m))

    def start(self):
        mode = self.mode.get()
        if mode == 'compare' and len(self.files) < 2:
            messagebox.showwarning("需要两首", "两曲对比模式请拖入/添加两首歌。")
            return
        if mode != 'compare' and len(self.files) < 1:
            messagebox.showwarning("需要文件", "请先拖入/添加一首歌。")
            return
        self.status.configure(text="检测中…（音频提取可能需十几秒）")
        self.out.delete('1.0', 'end')
        threading.Thread(target=self._run, args=(mode,), daemon=True).start()

    def _run(self, mode):
        try:
            if mode == 'local':
                res = me.search(self.files[0], CORPUS_DIR, 5)
            elif mode == 'compare':
                res = me.compare_two(self.files[0], self.files[1])
            else:
                ip = me.resolve_public_index()
                res = me.public_search(self.files[0], os.path.dirname(ip), ip, 8)
            text = format_result(res, mode)
        except Exception as e:
            text = "⚠ 处理出错：" + str(e)
        self.root.after(0, lambda: self.out.insert('end', text))
        self.root.after(0, lambda: self.status.configure(text="完成"))


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


def headless_main():
    """命令行/后台模式：无界面跑三种检索，便于验证与自动化。
    GUI 版 EXE 无控制台，故结果同时写入用户主目录的 melody_headless_result.txt。
    也可直接 `python melody_engine.py <mode> ...` 看 stdout 输出。"""
    import argparse
    ap = argparse.ArgumentParser(description="旋律相似度检测（命令行）")
    ap.add_argument('mode', nargs='?', default='',
                    help='local / compare / public / public-status / selftest')
    ap.add_argument('a', nargs='?', default='')
    ap.add_argument('b', nargs='?', default='')
    args = ap.parse_args()
    res = None
    try:
        if args.mode == 'selftest':
            res = me.self_test()
        elif args.mode == 'public-status':
            res = me.public_index_status()
        elif args.mode == 'local':
            res = me.search(args.a, CORPUS_DIR, 5)
        elif args.mode == 'compare':
            res = me.compare_two(args.a, args.b)
        elif args.mode == 'public':
            ip = me.resolve_public_index()
            res = {'index_path': ip, 'index_exists': os.path.exists(ip),
                   **me.public_search(args.a, os.path.dirname(ip), ip, 8)}
        else:
            res = {'usage': 'local|compare|public|selftest [文件] [文件2]'}
    except Exception as e:
        res = {'error': str(e)}
    txt = json.dumps(res, ensure_ascii=False, indent=2)
    out_path = os.path.join(os.path.expanduser('~'),
                            'melody_headless_result.txt')
    try:
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(txt)
    except Exception:
        pass
    try:
        print(txt)
    except Exception:
        pass


if __name__ == '__main__':
    # 有命令行参数时走无界面模式，否则启动 GUI
    if len(sys.argv) > 1:
        headless_main()
    else:
        main()
