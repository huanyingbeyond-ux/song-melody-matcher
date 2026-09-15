# -*- mode: python ; coding: utf-8 -*-
# 单文件 EXE 打包（精简版：无 librosa/scipy/pretty_midi/music21，仅 numpy + soundfile + mido + tkinter）
#
# 用法（需先生成数据）：
#   1) python tools/build_public.py        # 生成 public_corpus_index.json + public_corpus_data.py
#   2) python tools/make_seed_corpus.py     # 生成 corpus/*.mid 本地种子曲库
#   3) pyinstaller build_exe.spec --noconfirm
#
# 产物：dist/旋律相似度检测.exe（约 27 MB，含 15000+ 首公开曲库，离线可用）
import os
from PyInstaller.utils.hooks import collect_all

# PyInstaller 执行 spec 时不定义 __file__，用它提供的 SPECPATH（spec 所在目录）
HERE = SPECPATH

block_cipher = None

datas = []
binaries = []
hiddenimports = []

# soundfile 需要带 libsndfile 动态库
tmp = collect_all('soundfile')
datas += tmp[0]
binaries += tmp[1]
hiddenimports += tmp[2]
hiddenimports += ['numpy', 'mido', 'public_corpus_data']

# 曲库数据：
#  - 公开曲库索引/曲名表以「内嵌模块」public_corpus_data.py 形式随 PYZ 压缩打包
#    （经 hiddenimports 引入），运行时内存加载，避免部分系统上临时目录被杀毒软件锁文件；
#    故不再重复打包 public_corpus_*.json（那是源码运行时的外置数据）。
#  - 本地种子曲库 corpus/ 仍需随包分发。
datas.append((os.path.join(HERE, 'corpus'), 'corpus'))

a = Analysis(
    [os.path.join(HERE, 'melody_app.pyw')],
    pathex=[HERE],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['librosa', 'scipy', 'pretty_midi', 'music21', 'numba',
              'matplotlib', 'PIL', 'torch', 'tensorflow', 'sklearn',
              'pandas', 'sympy', 'notebook', 'IPython'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='旋律相似度检测',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
