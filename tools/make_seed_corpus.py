#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成本地种子曲库（6 首公有领域旋律的 MIDI），写到仓库根目录 corpus/。

仅依赖 mido（与本项目运行期依赖一致），不依赖 pretty_midi / scipy。
克隆仓库后运行：  python tools/make_seed_corpus.py
"""
import sys
from pathlib import Path

NOTE_OFFSET = {'C': 0, 'C#': 1, 'D': 2, 'D#': 3, 'E': 4, 'F': 5,
               'F#': 6, 'G': 7, 'G#': 8, 'A': 9, 'A#': 10, 'B': 11}


def name_to_midi(name):
    letter = name[0]
    i = 1
    sharp = ''
    if name[1] in ('#', 'b'):
        sharp = name[1]
        i = 2
    octave = int(name[i:])
    off = NOTE_OFFSET[letter]
    if sharp == '#':
        off += 1
    elif sharp == 'b':
        off -= 1
    return 12 * (octave + 1) + off


def write_midi(path, notes, bpm=120, ticks_per_beat=480):
    """notes: list of (note_name_or_midi, beats)。写出单声部旋律 MIDI。"""
    import mido
    mid = mido.MidiFile(ticks_per_beat=ticks_per_beat)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage('set_tempo', tempo=mido.bpm2tempo(bpm)))
    for n, beats in notes:
        midi = n if isinstance(n, int) else name_to_midi(n)
        dur = int(round(beats * ticks_per_beat))
        track.append(mido.Message('note_on', note=midi, velocity=90, time=0))
        track.append(mido.Message('note_off', note=midi, velocity=0, time=dur))
    mid.save(path)


# ---- 公有领域旋律（音名, 拍数）----
TWINKLE = [  # 小星星
    ("C4", 1), ("C4", 1), ("G4", 1), ("G4", 1), ("A4", 1), ("A4", 1), ("G4", 2),
    ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 1), ("D4", 1), ("C4", 2),
    ("G4", 1), ("G4", 1), ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 2),
    ("G4", 1), ("G4", 1), ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 2),
    ("C4", 1), ("C4", 1), ("G4", 1), ("G4", 1), ("A4", 1), ("A4", 1), ("G4", 2),
    ("F4", 1), ("F4", 1), ("E4", 1), ("E4", 1), ("D4", 1), ("D4", 1), ("C4", 2),
]
ODE_TO_JOY = [  # 欢乐颂
    ("E4", 1), ("E4", 1), ("F4", 1), ("G4", 1), ("G4", 1), ("F4", 1), ("E4", 1), ("D4", 1),
    ("C4", 1), ("C4", 1), ("D4", 1), ("E4", 1), ("E4", 1.5), ("D4", 0.5), ("D4", 2),
    ("E4", 1), ("E4", 1), ("F4", 1), ("G4", 1), ("G4", 1), ("F4", 1), ("E4", 1), ("D4", 1),
    ("C4", 1), ("C4", 1), ("D4", 1), ("E4", 1), ("D4", 1.5), ("C4", 0.5), ("C4", 2),
]
TWO_TIGERS = [  # 两只老虎
    ("C4", 1), ("D4", 1), ("E4", 1), ("C4", 1), ("C4", 1), ("D4", 1), ("E4", 1), ("C4", 1),
    ("E4", 1), ("F4", 1), ("G4", 2), ("E4", 1), ("F4", 1), ("G4", 2),
    ("G4", 0.75), ("A4", 0.25), ("G4", 0.75), ("F4", 0.25), ("E4", 1), ("C4", 1),
    ("G4", 0.75), ("A4", 0.25), ("G4", 0.75), ("F4", 0.25), ("E4", 1), ("C4", 1),
    ("C4", 1), ("G3", 1), ("C4", 2), ("C4", 1), ("G3", 1), ("C4", 2),
]
HAPPY_BIRTHDAY = [  # 生日歌（已公有领域）
    ("C4", 0.75), ("C4", 0.25), ("D4", 1), ("C4", 1), ("F4", 1), ("E4", 2),
    ("C4", 0.75), ("C4", 0.25), ("D4", 1), ("C4", 1), ("G4", 1), ("F4", 2),
    ("C4", 0.75), ("C4", 0.25), ("C5", 1), ("A4", 1), ("F4", 1), ("E4", 1), ("D4", 1),
    ("A#4", 0.75), ("A#4", 0.25), ("A4", 1), ("F4", 1), ("G4", 1), ("F4", 2),
]
JASMINE = [  # 茉莉花（传统民歌，公有领域）
    ("E4", 1), ("E4", 1), ("G4", 1.5), ("A4", 0.5), ("C5", 1), ("C5", 1), ("A4", 2),
    ("G4", 1), ("E4", 1), ("D4", 1.5), ("E4", 0.5), ("G4", 1), ("A4", 1), ("G4", 2),
    ("A4", 1), ("G4", 1), ("E4", 1.5), ("D4", 0.5), ("E4", 1), ("G4", 1), ("D4", 2),
    ("C4", 1), ("D4", 1), ("E4", 1), ("G4", 1), ("A4", 1), ("G4", 1), ("E4", 1), ("D4", 1),
    ("C4", 2),
]
CANON = [  # 卡农 in D 主线条（帕赫贝尔，公有领域）
    ("F#4", 1), ("E4", 1), ("D4", 1), ("C#4", 1), ("B3", 1), ("A3", 1), ("B3", 1), ("C#4", 1),
    ("D4", 1), ("C#4", 1), ("B3", 1), ("A3", 1), ("G3", 1), ("F#3", 1), ("G3", 1), ("E3", 1),
]

SEED_SONGS = {
    "小星星_Twinkle": TWINKLE,
    "欢乐颂_OdeToJoy": ODE_TO_JOY,
    "两只老虎_TwoTigers": TWO_TIGERS,
    "生日歌_HappyBirthday": HAPPY_BIRTHDAY,
    "茉莉花_Jasmine": JASMINE,
    "卡农_CanonInD": CANON,
}


def main(out_dir=None):
    out_dir = Path(out_dir) if out_dir else (Path(__file__).parent.parent / "corpus")
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, notes in SEED_SONGS.items():
        write_midi(str(out_dir / f"{name}.mid"), notes)
    print(f"已生成 {len(SEED_SONGS)} 首种子旋律到 {out_dir}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
