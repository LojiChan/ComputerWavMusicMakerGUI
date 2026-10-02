# -*- coding: utf-8 -*-
"""
ComputerWavMusicMaker - GUI 版 v8.0
- 音色修正：钢琴/小提琴/单簧管/唱诗班
- 新增音色：长笛、架子鼓（Kick/Snare/HiHat/Crash）
- 波表分辨率提升到每 3 个半音一张
- 保留：2x 过采样、抗混叠波表、多进程、FX 效果链
By Loji_

打击乐记号：
  K = 底鼓   S = 军鼓   H = 闭合踩镲   O = 打开踩镲   C = 吊镲
示例： {bpm:76}K---|K---|S---|S---|
"""

import os, sys, re, wave, datetime, threading, queue, time, json
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import numpy as np

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

try:
    from scipy.signal import lfilter, resample_poly, butter
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("[警告] 未安装 scipy，速度会降低。pip install scipy")

# ============================================================
#  全局常量
# ============================================================
SR = 44100
OVERSAMPLE = 2
SR_HI = SR * OVERSAMPLE
WAVETABLE_SIZE = 8192
WAVETABLE_STEP = 3
BASE_KEY = 261.63
SEMITONE = {1: 0, 2: 2, 3: 4, 4: 5, 5: 7, 6: 9, 7: 11}

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SHEET_PATH = os.path.join(SCRIPT_DIR, "SheetMusic.txt")
OUT_DIR    = os.path.join(SCRIPT_DIR, "Out")
OSM_DIR    = os.path.join(SCRIPT_DIR, "OSM")
os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(OSM_DIR, exist_ok=True)


def now_str():
    return datetime.datetime.now().strftime("%Y/%m/%d-%H:%M:%S")


def note_freq(num, octave_shift=0, accidental=0):
    semi = SEMITONE[num] + accidental + 12 * octave_shift
    return BASE_KEY * (2 ** (semi / 12.0))


def play_dingdong(success=True):
    if not HAS_WINSOUND:
        return
    def _play():
        try:
            if success:
                winsound.Beep(880, 150)
                time.sleep(0.05)
                winsound.Beep(1100, 200)
            else:
                winsound.Beep(440, 300)
        except Exception:
            pass
    threading.Thread(target=_play, daemon=True).start()


# ============================================================
#  FX 定义
# ============================================================
FX_LIST = [
    ('双声道立体声', 'stereo',   0.30),
    ('浴室',         'bathroom', 0.00),
    ('音乐厅',       'hall',     0.00),
    ('环绕',         'surround', 0.00),
    ('浑圆',         'warmth',   0.00),
    ('空灵',         'ethereal', 0.00),
    ('环境噪响',     'ambient',  0.00),
]
AMBIENT_TYPES = ['雨声', '风声', '咖啡馆', '篝火']


# ============================================================
#  音色参数
# ============================================================
TIMBRE_RAW = {
    '钢琴': {'n_harmonics': 20, 'amp_power': 1.6,
             'base_decay': 0.35, 'decay_power': 1.2, 'decay_scale': 0.5,
             'inharmonicity': 0.0004,
             'attack': 0.003, 'tail': 3.0,
             'noise_amt': 0.10, 'noise_decay': 40.0,
             'formants': [(110, 60, 0.20), (250, 80, 0.15), (500, 120, 0.10)]},
    '吉他': {'n_harmonics': 16, 'amp_power': 1.8,
             'base_decay': 0.6, 'decay_power': 1.5, 'decay_scale': 1.0,
             'inharmonicity': 0.0002,
             'attack': 0.004, 'tail': 3.5,
             'noise_amt': 0.08, 'noise_decay': 50.0,
             'formants': [(110, 60, 0.30), (250, 80, 0.20), (500, 120, 0.15)]},
    '竖琴': {'n_harmonics': 16, 'amp_power': 1.7,
             'base_decay': 0.4, 'decay_power': 1.3, 'decay_scale': 0.8,
             'inharmonicity': 0.0001,
             'attack': 0.002, 'tail': 5.0,
             'noise_amt': 0.05, 'noise_decay': 60.0},
    '古筝': {'n_harmonics': 16, 'amp_power': 1.7,
             'base_decay': 0.8, 'decay_power': 1.5, 'decay_scale': 1.0,
             'inharmonicity': 0.0006,
             'attack': 0.002, 'tail': 2.0,
             'noise_amt': 0.12, 'noise_decay': 60.0,
             'formants': [(150, 80, 0.20), (400, 150, 0.15)]},
    '小提琴': {'n_harmonics': 24, 'amp_power': 1.3,
               'base_decay': 0.15, 'decay_power': 1.1, 'decay_scale': 0.3,
               'inharmonicity': 0.0,
               'attack': 0.06, 'tail': 10.0,
               'noise_amt': 0.04, 'noise_decay': 15.0,
               'formants': [(265, 60, 0.45), (430, 80, 0.35),
                            (665, 100, 0.30), (3000, 600, 0.25)]},
    '二胡': {'n_harmonics': 20, 'amp_power': 1.4,
             'base_decay': 0.2, 'decay_power': 1.2, 'decay_scale': 0.4,
             'inharmonicity': 0.0,
             'attack': 0.05, 'tail': 8.0,
             'noise_amt': 0.06, 'noise_decay': 15.0,
             'formants': [(400, 150, 0.5), (1200, 400, 0.3)]},
    '唢呐': {'n_harmonics': 24, 'amp_power': 1.2,
             'base_decay': 0.3, 'decay_power': 1.2, 'decay_scale': 0.5,
             'inharmonicity': 0.0,
             'attack': 0.02, 'tail': 6.0,
             'noise_amt': 0.12, 'noise_decay': 30.0,
             'formants': [(1200, 500, 0.6), (2800, 800, 0.7), (5000, 1500, 0.4)]},
    '小号': {'n_harmonics': 20, 'amp_power': 1.3,
             'base_decay': 0.25, 'decay_power': 1.2, 'decay_scale': 0.4,
             'inharmonicity': 0.0,
             'attack': 0.05, 'tail': 8.0,
             'noise_amt': 0.05, 'noise_decay': 20.0,
             'formants': [(1200, 400, 0.6), (2500, 700, 0.4)]},
    '萨克斯': {'n_harmonics': 18, 'amp_power': 1.4,
               'base_decay': 0.3, 'decay_power': 1.2, 'decay_scale': 0.4,
               'inharmonicity': 0.0,
               'attack': 0.04, 'tail': 8.0,
               'noise_amt': 0.06, 'noise_decay': 20.0,
               'formants': [(800, 300, 0.5), (2000, 600, 0.3)]},
    '圆号': {'n_harmonics': 20, 'amp_power': 1.5,
             'base_decay': 0.2, 'decay_power': 1.1, 'decay_scale': 0.3,
             'inharmonicity': 0.0,
             'attack': 0.08, 'tail': 10.0,
             'noise_amt': 0.03, 'noise_decay': 15.0,
             'formants': [(500, 200, 0.4)]},
    '三味线': {'n_harmonics': 16, 'amp_power': 1.5,
               'base_decay': 1.5, 'decay_power': 1.5, 'decay_scale': 1.5,
               'inharmonicity': 0.0,
               'attack': 0.002, 'tail': 1.0,
               'noise_amt': 0.20, 'noise_decay': 100.0,
               'formants': [(550, 150, 0.6)]},
    '单簧管': {'n_harmonics': 16,
               'custom_amps': [1.0, 0.15, 0.85, 0.10, 0.65, 0.08,
                               0.50, 0.06, 0.35, 0.05, 0.25, 0.04,
                               0.18, 0.03, 0.12, 0.02],
               'custom_decays': [(0.15+0.04*k) if k % 2 == 1 else (0.25+0.06*k)
                                 for k in range(1, 17)],
               'inharmonicity': 0.0001, 'attack': 0.05, 'tail': 8.0,
               'noise_amt': 0.06, 'noise_decay': 20.0,
               'formants': [(1500, 600, 0.3), (3000, 1000, 0.2)]},
    '手风琴': {'n_harmonics': 8,
               'custom_amps': [1.0/(k**1.1) for k in range(1, 9)],
               'custom_decays': [0.3+0.05*k for k in range(1, 9)],
               'inharmonicity': 0.0005, 'attack': 0.04, 'tail': 10.0,
               'noise_amt': 0.02, 'noise_decay': 10.0,
               'formants': [(800, 300, 0.3), (2000, 500, 0.2)]},
    '口琴': {'n_harmonics': 12,
             'custom_amps': [1.0/(k**1.3) for k in range(1, 13)],
             'custom_decays': [0.4+0.06*k for k in range(1, 13)],
             'inharmonicity': 0.0, 'attack': 0.03, 'tail': 6.0,
             'noise_amt': 0.08, 'noise_decay': 25.0,
             'formants': [(600, 200, 0.4), (1200, 400, 0.3), (2500, 800, 0.2)]},
    '长号': {'n_harmonics': 16,
             'custom_amps': [a/2.522 for a in [2.522, 1.557, 1.246, 1.802,
                                               1.678, 1.832, 1.701, 1.327,
                                               1.076, 0.898, 0.703, 0.612,
                                               0.449, 0.148, 0.332, 0.221]],
             'custom_decays': [0.2+0.03*k for k in range(1, 17)],
             'inharmonicity': 0.0, 'attack': 0.06, 'tail': 10.0,
             'noise_amt': 0.04, 'noise_decay': 15.0,
             'formants': [(1200, 400, 0.5), (2500, 700, 0.4), (4000, 1000, 0.3)]},
    '长笛': {'n_harmonics': 12,
             'custom_amps': [1.0, 0.45, 0.60, 0.30, 0.25, 0.15,
                             0.12, 0.08, 0.06, 0.04, 0.03, 0.02],
             'custom_decays': [0.15, 0.16, 0.17, 0.18, 0.19, 0.20,
                               0.21, 0.22, 0.23, 0.24, 0.25, 0.26],
             'inharmonicity': 0.0, 'attack': 0.08, 'tail': 8.0,
             'noise_amt': 0.18, 'noise_decay': 25.0,
             'formants': [(500, 150, 0.25), (1500, 200, 0.20), (2500, 300, 0.15)]},
    '木琴': {'n_harmonics': 5, 'custom_ratios': [1.0, 2.76, 5.40, 8.93, 13.34],
             'custom_amps': [1.0, 0.30, 0.15, 0.06, 0.02],
             'custom_decays': [1.0, 8.0, 15.0, 25.0, 40.0],
             'inharmonicity': 0.0, 'attack': 0.001, 'tail': 1.5,
             'noise_amt': 0.05, 'noise_decay': 100.0},
    '少女唱诗班': {'n_harmonics': 8, 'amp_power': 1.2, 'base_decay': 0.3,
                   'decay_power': 1.1, 'decay_scale': 0.2, 'inharmonicity': 0.0,
                   'attack': 0.10, 'tail': 8.0, 'noise_amt': 0.03, 'noise_decay': 8.0,
                   'formants': [(800, 80, 0.6), (1150, 90, 0.5),
                                (2900, 100, 1.0), (3900, 120, 0.6),
                                (8500, 400, 0.35)]},
    '少年唱诗班': {'n_harmonics': 8, 'amp_power': 1.2, 'base_decay': 0.3,
                   'decay_power': 1.1, 'decay_scale': 0.2, 'inharmonicity': 0.0,
                   'attack': 0.11, 'tail': 9.0, 'noise_amt': 0.03, 'noise_decay': 8.0,
                   'formants': [(600, 80, 0.6), (1000, 90, 0.5),
                                (2500, 100, 1.0), (3300, 120, 0.6),
                                (8000, 400, 0.35)]},
    '混合童声': {'n_harmonics': 8, 'amp_power': 1.2, 'base_decay': 0.3,
                 'decay_power': 1.1, 'decay_scale': 0.2, 'inharmonicity': 0.0,
                 'attack': 0.10, 'tail': 8.5, 'noise_amt': 0.03, 'noise_decay': 8.0,
                 'formants': [(700, 80, 0.6), (1100, 90, 0.5),
                              (2700, 100, 1.0), (3600, 120, 0.6),
                              (8200, 400, 0.35)]},
    '男中音': {'n_harmonics': 8, 'amp_power': 1.2, 'base_decay': 0.25,
               'decay_power': 1.0, 'decay_scale': 0.15, 'inharmonicity': 0.0,
               'attack': 0.13, 'tail': 10.0, 'noise_amt': 0.03, 'noise_decay': 8.0,
               'formants': [(500, 80, 0.6), (1500, 100, 0.5),
                            (2400, 100, 1.0), (3000, 120, 0.6),
                            (7000, 500, 0.3)]},
}


def _to_v6_params(old):
    if 'custom_amps' in old and old['custom_amps']:
        amps = list(old['custom_amps'])
    else:
        n = old.get('n_harmonics', 20)
        ap = old.get('amp_power', 1.5)
        amps = [1.0 / (k ** ap) for k in range(1, n + 1)]
    if 'custom_decays' in old and old['custom_decays']:
        decays = list(old['custom_decays'])
    else:
        bd = old.get('base_decay', 0.5)
        dp = old.get('decay_power', 1.3)
        ds = old.get('decay_scale', 0.5)
        decays = [bd + ds * (k ** dp) for k in range(1, len(amps) + 1)]
    return {
        'n_harmonics': len(amps),
        'harmonic_amps': amps,
        'harmonic_decays': decays,
        'custom_ratios': old.get('custom_ratios'),
        'inharmonicity': old.get('inharmonicity', 0.0),
        'formants': old.get('formants', []),
        'attack': old.get('attack', 0.01),
        'tail': old.get('tail', 3.0),
        'noise_amt': old.get('noise_amt', 0.0),
        'noise_decay': old.get('noise_decay', 30.0),
    }


TIMBRE_PARAMS = {name: _to_v6_params(raw) for name, raw in TIMBRE_RAW.items()}
ALL_TIMBRES = ['钢琴', '吉他', '竖琴', '古筝',
               '小提琴', '二胡', '单簧管', '手风琴', '口琴', '长号', '长笛',
               '唢呐', '小号', '萨克斯', '圆号',
               '三味线', '木琴',
               '少女唱诗班', '少年唱诗班', '混合童声', '男中音']
DEFAULT_PARAMS = _to_v6_params({'n_harmonics': 12, 'amp_power': 1.5,
                                'base_decay': 1.0, 'tail': 2.0})


# ============================================================
#  波表
# ============================================================
_wt_cache = {}


def _build_wavetable_v3(timbre, base_semitone):
    params = TIMBRE_PARAMS.get(timbre, DEFAULT_PARAMS)
    base_freq = BASE_KEY * (2 ** (base_semitone / 12.0))
    max_freq = base_freq * (2 ** (WAVETABLE_STEP / 12.0))

    period_samples = int(round(SR_HI / max_freq))
    period_samples = max(16, min(8192, period_samples))
    t = np.arange(period_samples) / SR_HI

    out = np.zeros(period_samples, dtype=np.float64)
    for k in range(1, params['n_harmonics'] + 1):
        if params['custom_ratios'] is not None and k <= len(params['custom_ratios']):
            fk = params['custom_ratios'][k - 1] * base_freq
        elif params['inharmonicity'] > 0:
            fk = k * base_freq * np.sqrt(1.0 + params['inharmonicity'] * k * k)
        else:
            fk = k * base_freq
        if fk > SR_HI * 0.47:
            break
        a = params['harmonic_amps'][k - 1] if k <= len(params['harmonic_amps']) else 1.0 / (k ** 1.5)
        d = params['harmonic_decays'][k - 1] if k <= len(params['harmonic_decays']) else 2.0
        a *= np.exp(-d * 0.05)
        for fc, bw, g in params['formants']:
            a *= 1.0 + g / (1.0 + ((fk - fc) / bw) ** 2)
        out += a * np.sin(2 * np.pi * fk * t + k * 0.13)

    if period_samples != WAVETABLE_SIZE:
        src_x = np.arange(period_samples)
        dst_x = np.linspace(0, period_samples, WAVETABLE_SIZE, endpoint=False)
        table = np.interp(dst_x, src_x, out)
    else:
        table = out
    peak = np.max(np.abs(table))
    if peak > 0:
        table = table / peak
    return table.astype(np.float32)


def get_wavetable_for_freq(timbre, freq):
    if freq <= 0:
        freq = 20
    semitone = 12.0 * np.log2(max(freq, 20.0) / BASE_KEY)
    base_st = int(np.floor(semitone / WAVETABLE_STEP)) * WAVETABLE_STEP
    base_st = max(-36, min(36, base_st))
    key = (timbre, base_st)
    if key in _wt_cache:
        return _wt_cache[key]
    table = _build_wavetable_v3(timbre, base_st)
    _wt_cache[key] = table
    return table


def play_wavetable(table, freq, n_samples, phase0=0.0):
    if n_samples <= 0:
        return np.zeros(0, dtype=np.float32)
    inc = WAVETABLE_SIZE * freq / SR_HI
    phases = phase0 + np.arange(n_samples, dtype=np.float64) * inc
    idx = phases.astype(np.int64)
    frac = phases - idx
    idx0 = (idx % WAVETABLE_SIZE).astype(np.int64)
    idx1 = ((idx + 1) % WAVETABLE_SIZE).astype(np.int64)
    return (table[idx0] * (1 - frac) + table[idx1] * frac).astype(np.float32)


def apply_envelope_smooth(wave, dur, params):
    n = len(wave)
    if n <= 0:
        return wave
    t = np.arange(n) / SR_HI
    attack = params.get('attack', 0.01)
    tail = params.get('tail', 3.0)
    env = np.ones(n, dtype=np.float32)
    a_n = min(int(attack * SR_HI), n)
    if a_n > 0:
        aa = np.arange(a_n) / a_n
        env[:a_n] = (0.5 - 0.5 * np.cos(np.pi * aa)).astype(np.float32)
    if tail < 100:
        env *= np.exp(-t / tail).astype(np.float32)
    r_n = min(int(0.03 * SR_HI), n)
    if r_n > 0:
        rr = np.arange(r_n) / r_n
        env[-r_n:] *= (0.5 + 0.5 * np.cos(np.pi * rr)).astype(np.float32)
    return wave * env


# ============================================================
#  打击乐
# ============================================================
def _drum_sound(symbol, dur):
    n = int(SR_HI * dur)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.arange(n) / SR_HI

    if symbol == 'K':
        pitch = 50 + 100 * np.exp(-t / 0.03)
        phase = 2 * np.pi * np.cumsum(pitch) / SR_HI
        tone = np.sin(phase) * np.exp(-t / 0.4)
        click_n = min(int(SR_HI * 0.005), n)
        click = np.random.randn(click_n).astype(np.float64)
        click = np.diff(click, prepend=0)
        click *= np.exp(-np.arange(click_n) / (SR_HI * 0.001))
        result = tone.copy()
        result[:click_n] += click * 0.4
        return result.astype(np.float32)

    if symbol == 'S':
        tone = np.sin(2 * np.pi * 200 * t) * np.exp(-t / 0.15)
        noise = np.random.randn(n)
        if HAS_SCIPY:
            nyq = SR_HI / 2
            b, a = butter(2, [800 / nyq, 6000 / nyq], btype='band')
            noise = lfilter(b, a, noise)
        noise *= np.exp(-t / 0.25)
        return (tone * 0.5 + noise * 0.5).astype(np.float32)

    if symbol in ('H', 'O'):
        noise = np.random.randn(n)
        if HAS_SCIPY:
            nyq = SR_HI / 2
            b, a = butter(2, 6000 / nyq, btype='high')
            noise = lfilter(b, a, noise)
        decay = 0.08 if symbol == 'H' else 0.5
        noise *= np.exp(-t / decay)
        for f in [8000, 10000, 12000]:
            if f < SR_HI * 0.45:
                noise += 0.05 * np.sin(2 * np.pi * f * t) * np.exp(-t / decay)
        return noise.astype(np.float32)

    if symbol == 'C':
        noise = np.random.randn(n)
        if HAS_SCIPY:
            nyq = SR_HI / 2
            b, a = butter(2, 4000 / nyq, btype='high')
            noise = lfilter(b, a, noise)
        noise *= np.exp(-t / 1.5)
        for f in [3000, 4200, 5500, 6800, 8500, 10500, 12500]:
            if f < SR_HI * 0.45:
                noise += 0.06 * np.sin(2 * np.pi * f * t) * np.exp(-t / 1.2)
        return noise.astype(np.float32)

    return np.zeros(n, dtype=np.float32)


def synth_drum(symbol, dur):
    sound_dur = {'K': 0.5, 'S': 0.35, 'H': 0.10, 'O': 0.6, 'C': 2.0}.get(symbol, 0.3)
    sound = _drum_sound(symbol, sound_dur)
    total = int(SR_HI * dur)
    result = np.zeros(max(total, 1), dtype=np.float32)
    if total > 0 and len(sound) > 0:
        end = min(len(sound), total)
        result[:end] = sound[:end]
    return result


# ============================================================
#  单音符合成
# ============================================================
def synth_note_v6(freq, dur, timbre):
    if isinstance(freq, tuple):
        return synth_drum(freq[1], dur)

    n_hi = int(SR_HI * dur)
    if n_hi <= 0:
        return np.zeros(0, dtype=np.float32)
    params = TIMBRE_PARAMS.get(timbre, DEFAULT_PARAMS)
    if freq <= 0:
        return np.zeros(n_hi, dtype=np.float32)
    table = get_wavetable_for_freq(timbre, freq)
    wave = play_wavetable(table, freq, n_hi, np.random.rand())
    wave = apply_envelope_smooth(wave, dur, params)
    noise_amt = params.get('noise_amt', 0.0)
    if noise_amt > 0:
        nl = min(n_hi, int(SR_HI * 0.08))
        if nl > 0:
            noise = np.random.randn(nl).astype(np.float32)
            a = 0.6
            for i in range(1, nl):
                noise[i] = a * noise[i - 1] + (1 - a) * noise[i]
            t_n = np.arange(nl) / SR_HI
            noise *= np.exp(-params.get('noise_decay', 30.0) * t_n).astype(np.float32)
            wave[:nl] += noise * noise_amt
    return wave


def render_track_v6(notes, timbre, speed_scale, total_samples_hi, octave=0):
    buf = np.zeros(total_samples_hi, dtype=np.float32)
    cursor = 0
    for freq, dur_beats, bpm in notes:
        dur_s = beats_to_seconds(dur_beats, bpm) / speed_scale
        n_hi = int(SR_HI * dur_s)
        if freq is None:
            cursor += n_hi
            continue
        if isinstance(freq, tuple):
            note_audio = synth_drum(freq[1], dur_s)
        else:
            if octave:
                freq = freq * (2 ** octave)
            note_audio = synth_note_v6(freq, dur_s, timbre)
        end = min(cursor + len(note_audio), total_samples_hi)
        if end > cursor:
            buf[cursor:end] += note_audio[:end - cursor]
        cursor += n_hi
    return buf


# ============================================================
#  混响 / 立体声
# ============================================================
def reverb_fast(sig, room_size=0.75, wet=0.35, damp=0.4):
    if not HAS_SCIPY:
        return reverb_slow(sig, room_size, wet, damp)
    sig = sig.astype(np.float64)
    comb_delays = [int(1116 * room_size), int(1188 * room_size),
                   int(1277 * room_size), int(1356 * room_size)]
    comb_gains = [0.77, 0.76, 0.75, 0.74]
    out = np.zeros_like(sig)
    for delay, g in zip(comb_delays, comb_gains):
        if delay < 1:
            continue
        a = np.zeros(delay + 2)
        a[0] = 1.0
        a[delay] = -g * damp
        a[delay + 1] = -g * (1 - damp)
        out += lfilter([1.0], a, sig)
    out /= len(comb_delays)
    return sig * (1 - wet) + out * wet


def reverb_slow(sig, room_size=0.75, wet=0.35, damp=0.4):
    comb_delays = [int(1116 * room_size), int(1188 * room_size),
                   int(1277 * room_size), int(1356 * room_size)]
    comb_gains = [0.77, 0.76, 0.75, 0.74]
    out = np.zeros_like(sig)
    for delay, g in zip(comb_delays, comb_gains):
        if delay < 1:
            continue
        buf = np.zeros(delay)
        fs = 0.0
        comb_out = np.zeros_like(sig)
        for i in range(len(sig)):
            bi = i % delay
            d = buf[bi]
            fs = d * (1 - damp) + fs * damp
            buf[bi] = sig[i] + fs * g
            comb_out[i] = d
        out += comb_out
    out /= len(comb_delays)
    return sig * (1 - wet) + out * wet


def stereo_enhance(sig):
    dl = int(SR * 0.005)
    dr = int(SR * 0.009)
    left = sig.copy()
    right = sig.copy()
    left[dl:] += sig[:-dl] * 0.15
    right[dr:] += sig[:-dr] * 0.15
    right = right - np.roll(sig, 200) * 0.08
    return np.stack([left, right], axis=1)


# ============================================================
#  FX 效果
# ============================================================
def fx_stereo(s, strength):
    if strength <= 0:
        return s
    L, R = s[:, 0].copy(), s[:, 1].copy()
    M = (L + R) * 0.5
    S = (L - R) * 0.5
    S *= (1 + 2.0 * strength)
    delay = int(SR * 0.008 * strength)
    if delay > 0:
        S[delay:] += S[:-delay] * 0.3 * strength
    return np.stack([M + S, M - S], axis=1)


def fx_surround(s, strength):
    if strength <= 0:
        return s
    L, R = s[:, 0].copy(), s[:, 1].copy()
    dl = int(SR * 0.015 * strength)
    dr = int(SR * 0.020 * strength)
    if dl > 0:
        L[dl:] = L[dl:] * (1 - 0.3 * strength) + R[:-dl] * 0.3 * strength
    if dr > 0:
        R[dr:] = R[dr:] * (1 - 0.3 * strength) + L[:-dr] * 0.3 * strength
    return np.stack([L, R], axis=1)


def fx_bathroom(s, strength):
    if strength <= 0:
        return s
    L = reverb_fast(s[:, 0], room_size=0.30, wet=0.6 * strength, damp=0.7)
    R = reverb_fast(s[:, 1], room_size=0.33, wet=0.6 * strength, damp=0.7)
    return np.stack([L, R], axis=1)


def fx_hall(s, strength):
    if strength <= 0:
        return s
    L = reverb_fast(s[:, 0], room_size=1.20, wet=0.4 * strength, damp=0.25)
    R = reverb_fast(s[:, 1], room_size=1.25, wet=0.4 * strength, damp=0.25)
    return np.stack([L, R], axis=1)


def fx_warmth(s, strength):
    if strength <= 0:
        return s
    if HAS_SCIPY:
        b = [1 - 0.95]
        a = [1, -0.95]
        L = s[:, 0] + lfilter(b, a, s[:, 0]) * strength * 0.5
        R = s[:, 1] + lfilter(b, a, s[:, 1]) * strength * 0.5
    else:
        L = s[:, 0].copy()
        R = s[:, 1].copy()
        alpha = 0.95
        for arr in (L, R):
            lp = 0.0
            for i in range(len(arr)):
                lp = alpha * lp + (1 - alpha) * arr[i]
                arr[i] += lp * strength * 0.5
    if strength > 0.3:
        L = np.tanh(L * (1 + strength * 0.3))
        R = np.tanh(R * (1 + strength * 0.3))
    return np.stack([L, R], axis=1)


def fx_ethereal(s, strength):
    if strength <= 0:
        return s
    L = reverb_fast(s[:, 0], room_size=1.5, wet=0.5 * strength, damp=0.15)
    R = reverb_fast(s[:, 1], room_size=1.55, wet=0.5 * strength, damp=0.15)
    return np.stack([L, R], axis=1)


def fx_ambient(s, strength, subtype='雨声'):
    if strength <= 0:
        return s
    n = len(s)
    noise = np.random.randn(n, 2).astype(np.float64)

    if subtype == '雨声':
        if HAS_SCIPY:
            for ch in range(2):
                noise[:, ch] = lfilter([0.08], [1, -0.92], noise[:, ch])
        n_drops = int(n * 0.001 * strength)
        if n_drops > 0:
            di = np.random.randint(0, n, n_drops)
            noise[di, 0] += np.random.randn(n_drops) * 0.3
            noise[di, 1] += np.random.randn(n_drops) * 0.3
        amp = strength * 0.06
    elif subtype == '风声':
        if HAS_SCIPY:
            for ch in range(2):
                noise[:, ch] = lfilter([0.02], [1, -0.98], noise[:, ch])
        t = np.arange(n) / SR
        lfo = 0.5 + 0.5 * np.sin(2 * np.pi * 0.15 * t + np.random.rand() * 6)
        noise[:, 0] *= lfo
        noise[:, 1] *= lfo
        amp = strength * 0.15
    elif subtype == '咖啡馆':
        if HAS_SCIPY:
            for ch in range(2):
                noise[:, ch] = lfilter([0.15], [1, -0.85], noise[:, ch])
        n_peaks = int(n * 0.0002 * strength)
        if n_peaks > 0:
            pi = np.random.randint(0, n, n_peaks)
            for p in pi:
                length = min(int(SR * 0.3), n - p)
                if length > 0:
                    env = np.exp(-3 * np.arange(length) / SR)
                    burst = np.random.randn(length) * env * 0.5
                    noise[p:p + length, 0] += burst
                    noise[p:p + length, 1] += burst
        amp = strength * 0.08
    elif subtype == '篝火':
        if HAS_SCIPY:
            for ch in range(2):
                noise[:, ch] = lfilter([0.1], [1, -0.9], noise[:, ch])
        n_cracks = int(n * 0.003 * strength)
        if n_cracks > 0:
            ci = np.random.randint(0, n, n_cracks)
            for c in ci:
                length = min(int(SR * 0.02), n - c)
                if length > 0:
                    burst = (np.random.randn(length) *
                             np.exp(-100 * np.arange(length) / SR) * 0.8)
                    noise[c:c + length, 0] += burst
                    noise[c:c + length, 1] += burst
        amp = strength * 0.10
    else:
        amp = strength * 0.05
    return s + noise * amp


def apply_fx_chain(stereo, fx_settings, ambient_type='雨声', log=None):
    if not fx_settings:
        return stereo
    if not any(v > 0 for v in fx_settings.values()):
        return stereo
    s = stereo.astype(np.float64)
    if fx_settings.get('warmth', 0) > 0:
        if log: log("  FX: 浑圆 强度=%.2f" % fx_settings['warmth'])
        s = fx_warmth(s, fx_settings['warmth'])
    if fx_settings.get('surround', 0) > 0:
        if log: log("  FX: 环绕 强度=%.2f" % fx_settings['surround'])
        s = fx_surround(s, fx_settings['surround'])
    if fx_settings.get('bathroom', 0) > 0:
        if log: log("  FX: 浴室 强度=%.2f" % fx_settings['bathroom'])
        s = fx_bathroom(s, fx_settings['bathroom'])
    if fx_settings.get('hall', 0) > 0:
        if log: log("  FX: 音乐厅 强度=%.2f" % fx_settings['hall'])
        s = fx_hall(s, fx_settings['hall'])
    if fx_settings.get('ethereal', 0) > 0:
        if log: log("  FX: 空灵 强度=%.2f" % fx_settings['ethereal'])
        s = fx_ethereal(s, fx_settings['ethereal'])
    if fx_settings.get('ambient', 0) > 0:
        if log: log("  FX: 环境噪响(%s) 强度=%.2f" % (ambient_type, fx_settings['ambient']))
        s = fx_ambient(s, fx_settings['ambient'], ambient_type)
    if fx_settings.get('stereo', 0) > 0:
        if log: log("  FX: 双声道立体声 强度=%.2f" % fx_settings['stereo'])
        s = fx_stereo(s, fx_settings['stereo'])
    peak = np.max(np.abs(s))
    if peak > 1.0:
        s = s / peak
    return s.astype(np.float32)


# ============================================================
#  简谱解析
# ============================================================
def parse_score(score):
    if score and not score.startswith('{'):
        idx = score.find('}')
        if idx > 0 and re.match(r'^[a-zA-Z]+[:=]', score[:idx]):
            score = '{' + score

    bpm_markers = [(m.start(), int(m.group(1)))
                   for m in re.finditer(r'\{bpm:(\d+)\}', score)]
    clean_chars, pos_map = [], []
    i = 0
    while i < len(score):
        if score[i] == '{':
            end = score.find('}', i)
            if end == -1:
                end = len(score) - 1
            i = end + 1
            continue
        clean_chars.append(score[i])
        pos_map.append(i)
        i += 1
    clean = ''.join(clean_chars)

    def bpm_at(ci):
        orig = pos_map[ci] if ci < len(pos_map) else len(score)
        cur = 80
        for pos, b in bpm_markers:
            if pos <= orig:
                cur = b
            else:
                break
        return cur

    notes, j = [], 0
    while j < len(clean):
        ch = clean[j]

        if ch == '0':
            j += 1
            dur = 1.0
            while j < len(clean) and clean[j] in '-x.':
                if clean[j] == '-': dur += 1.0; j += 1
                elif clean[j] == 'x': dur = 0.25; j += 1
                elif clean[j] == '.': dur *= 1.5; j += 1
            notes.append((None, dur, bpm_at(j)))
            continue

        if ch in 'KSHOC':
            symbol = ch
            j += 1
            dur = 1.0
            if j < len(clean) and clean[j] == 'x':
                dur = 0.25; j += 1
            while j < len(clean) and clean[j] in '-.':
                if clean[j] == '-': dur += 1.0; j += 1
                elif clean[j] == '.': dur *= 1.5; j += 1
            notes.append((('drum', symbol), dur, bpm_at(j)))
            continue

        if ch in '1234567':
            num = int(ch); oct_shift = 0; acc = 0; j += 1
            while j < len(clean):
                c = clean[j]
                if c == 'd': oct_shift = -1; j += 1
                elif c == 'g': oct_shift = 1; j += 1
                elif c == '#': acc += 1; j += 1
                elif c == 'b': acc -= 1; j += 1
                else: break
            freq = note_freq(num, oct_shift, acc)
            dur = 1.0
            if j < len(clean) and clean[j] == 'x':
                dur = 0.25; j += 1
            while j < len(clean) and clean[j] in '-.':
                if clean[j] == '-': dur += 1.0; j += 1
                elif clean[j] == '.': dur *= 1.5; j += 1
            while j < len(clean) and clean[j] == '=':
                if j + 1 < len(clean) and clean[j + 1] in '1234567':
                    j += 1
                    nxt = clean[j]
                    if nxt == str(num):
                        j += 1
                        if j < len(clean) and clean[j] == 'x':
                            dur += 0.25; j += 1
                        else:
                            dur += 1.0
                    else: break
                else: break
            notes.append((freq, dur, bpm_at(j)))
            continue
        j += 1
    return notes


def beats_to_seconds(b, bpm):
    return b * 60.0 / bpm


def estimate_duration(notes, speed_scale=1.0):
    return sum(beats_to_seconds(d, b) / speed_scale for _, d, b in notes)


# ============================================================
#  单轨合成
# ============================================================
def synth_v7(score, out_path, timbre, speed_scale=1.0, octave_shift=0,
             fx_settings=None, ambient_type='雨声',
             log_callback=None, progress_callback=None):
    def log(m):
        if log_callback: log_callback(m)
    def progress(c, t):
        if progress_callback: progress_callback(c, t)

    notes = parse_score(score)
    total = len(notes)
    log(f"共 {total} 个音符/休止符")
    total_dur = estimate_duration(notes, speed_scale)
    total_samples_hi = int(SR_HI * total_dur) + SR_HI
    log(f"总时长 {total_dur:.2f}s，2x 过采样渲染...")

    buf = np.zeros(total_samples_hi, dtype=np.float32)
    cursor = 0
    for idx, (freq, dur_b, bpm) in enumerate(notes):
        dur_s = beats_to_seconds(dur_b, bpm) / speed_scale
        n_hi = int(SR_HI * dur_s)
        if freq is None:
            cursor += n_hi
        elif isinstance(freq, tuple):
            note_audio = synth_drum(freq[1], dur_s)
            end = min(cursor + len(note_audio), total_samples_hi)
            if end > cursor:
                buf[cursor:end] += note_audio[:end - cursor]
            cursor += n_hi
        else:
            if octave_shift:
                freq = freq * (2 ** octave_shift)
            note_audio = synth_note_v6(freq, dur_s, timbre)
            end = min(cursor + len(note_audio), total_samples_hi)
            if end > cursor:
                buf[cursor:end] += note_audio[:end - cursor]
            cursor += n_hi
        progress(idx + 1, total)
        if (idx + 1) % 100 == 0 or idx == total - 1:
            log(f"合成中 {idx + 1}/{total}")

    log("软削波（2x SR，无混叠）...")
    buf = np.tanh(buf * 0.7)
    log("降采样...")
    if HAS_SCIPY:
        audio = resample_poly(buf, 1, OVERSAMPLE).astype(np.float32)
    else:
        audio = buf[::OVERSAMPLE].copy()

    audio = reverb_fast(audio, room_size=0.7, wet=0.20, damp=0.4)
    audio += np.random.randn(len(audio)).astype(np.float32) * 0.0015
    peak = np.max(np.abs(audio))
    if peak > 0:
        audio = audio / peak * 0.9
    stereo = stereo_enhance(audio)

    if fx_settings and any(v > 0 for v in fx_settings.values()):
        log("应用 FX 效果链...")
        stereo = apply_fx_chain(stereo, fx_settings, ambient_type, log=log)

    with wave.open(out_path, 'w') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    log(f"已生成：{out_path}")
    log(f"时长：{len(stereo) / SR:.2f} 秒")
    return True


# ============================================================
#  多轨合成
# ============================================================
def _track_worker(args):
    notes, timbre, speed_scale, total_samples_hi, octave = args
    return render_track_v6(notes, timbre, speed_scale, total_samples_hi, octave)


def synth_multi_v7(tracks, out_path, speed_scale=1.0,
                   fx_settings=None, ambient_type='雨声',
                   log_callback=None, progress_callback=None):
    def log(m):
        if log_callback: log_callback(m)
    def progress(ti, tt, ci, ct):
        if progress_callback: progress_callback(ti, tt, ci, ct)

    active = [t for t in tracks if not t.get('mute', False)]
    if not active:
        log("错误：所有轨道都被静音了")
        return False
    log(f"开始混合渲染 {len(active)} 条轨道")

    log("--- 轨道详情 ---")
    for i, t in enumerate(active):
        preview = t.get('score', '')[:60].replace('\n', ' ')
        log(f"  轨{i+1}: name={t['name']!r} timbre={t['timbre']!r} "
            f"vol={t.get('volume', 1.0)} pan={t.get('pan', 0.0)} "
            f"oct={t.get('octave', 0)} len={len(t.get('score', ''))} prev={preview!r}")
    log("--- 轨道详情结束 ---")

    parsed = []
    total_dur = 0.0
    for t in active:
        notes = parse_score(t.get('score', ''))
        d = estimate_duration(notes, speed_scale)
        total_dur = max(total_dur, d)
        parsed.append((t, notes, d))
        log(f"  轨道 {t['name']!r} 音符数={len(notes)} 时长={d:.2f}s")

    total_dur += 0.5
    total_samples_hi = int(SR_HI * total_dur) + SR_HI

    log("多进程渲染各轨道...")
    worker_args = [(n, t['timbre'], speed_scale, total_samples_hi, t.get('octave', 0))
                   for t, n, d in parsed]
    try:
        import multiprocessing
        n_workers = min(len(worker_args), os.cpu_count() or 2)
        if n_workers > 1:
            with multiprocessing.Pool(processes=n_workers) as pool:
                track_bufs = pool.map(_track_worker, worker_args)
        else:
            track_bufs = [_track_worker(a) for a in worker_args]
    except Exception as e:
        log(f"多进程失败（{e}），单进程回退")
        track_bufs = [_track_worker(a) for a in worker_args]

    log("混音中...")
    stereo_hi = np.zeros((total_samples_hi, 2), dtype=np.float32)
    for i, ((t, notes, d), mono) in enumerate(zip(parsed, track_bufs)):
        vol = t.get('volume', 1.0)
        pan = t.get('pan', 0.0)
        lg = np.cos((pan + 1) * np.pi / 4)
        rg = np.sin((pan + 1) * np.pi / 4)
        stereo_hi[:, 0] += mono * vol * lg
        stereo_hi[:, 1] += mono * vol * rg
        progress(i + 1, len(active), len(notes), len(notes))

    log("总线归一化 + 软削波...")
    peak = np.max(np.abs(stereo_hi))
    if peak > 0:
        stereo_hi = stereo_hi / peak * 1.4
    stereo_hi = np.tanh(stereo_hi * 0.9) / np.tanh(0.9) * 0.95

    log("降采样...")
    if HAS_SCIPY:
        L = resample_poly(stereo_hi[:, 0], 1, OVERSAMPLE).astype(np.float32)
        R = resample_poly(stereo_hi[:, 1], 1, OVERSAMPLE).astype(np.float32)
    else:
        L = stereo_hi[::OVERSAMPLE, 0].copy()
        R = stereo_hi[::OVERSAMPLE, 1].copy()

    log("基础混响...")
    L = reverb_fast(L, room_size=0.7, wet=0.15, damp=0.4)
    R = reverb_fast(R, room_size=0.7, wet=0.15, damp=0.4)
    L += np.random.randn(len(L)).astype(np.float32) * 0.0015
    R += np.random.randn(len(R)).astype(np.float32) * 0.0015
    peak = max(np.max(np.abs(L)), np.max(np.abs(R)))
    if peak > 0:
        L = L / peak * 0.9
        R = R / peak * 0.9
    stereo = np.stack([L, R], axis=1)

    if fx_settings and any(v > 0 for v in fx_settings.values()):
        log("应用 FX 效果链...")
        stereo = apply_fx_chain(stereo, fx_settings, ambient_type, log=log)

    with wave.open(out_path, 'w') as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((stereo * 32767).astype(np.int16).tobytes())
    log(f"已生成：{out_path}")
    log(f"时长：{stereo.shape[0] / SR:.2f} 秒")
    return True


# ============================================================
#  编曲数据模型
# ============================================================
DEFAULT_TRACK = {
    'name': '轨道', 'timbre': '钢琴', 'score': '',
    'volume': 1.0, 'pan': 0.0, 'octave': 0, 'mute': False,
}


def save_osm(p, path):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


def load_osm(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ============================================================
#  FX 窗口
# ============================================================
class FXWindow:
    def __init__(self, master, app):
        self.app = app
        self.win = tk.Toplevel(master)
        self.win.title("音频效果链")
        self.win.geometry("560x460")
        self.win.resizable(False, False)
        tk.Label(self.win, text="音频效果链（可并行启用）",
                 font=("Microsoft YaHei", 11, "bold")).pack(pady=10)
        self.vars = {}
        for label, key, default in FX_LIST:
            row = tk.Frame(self.win)
            row.pack(fill=tk.X, padx=15, pady=3)
            en = tk.BooleanVar(value=app.fx_settings.get(key, 0) > 0)
            st = tk.DoubleVar(value=app.fx_settings.get(key, default))
            self.vars[key] = (en, st)
            tk.Checkbutton(row, text=label, variable=en,
                           width=12, anchor='w',
                           font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
            tk.Scale(row, from_=0.0, to=1.0, resolution=0.05,
                     orient=tk.HORIZONTAL, length=350,
                     variable=st, showvalue=True).pack(side=tk.LEFT, padx=5)
        ar = tk.Frame(self.win)
        ar.pack(fill=tk.X, padx=15, pady=(10, 3))
        tk.Label(ar, text="环境噪响类型：", width=12, anchor='w',
                 font=("Microsoft YaHei", 10)).pack(side=tk.LEFT)
        self.amb_var = tk.StringVar(value=app.ambient_type)
        ttk.Combobox(ar, textvariable=self.amb_var, values=AMBIENT_TYPES,
                     state='readonly', width=12).pack(side=tk.LEFT, padx=5)
        tk.Label(self.win,
                 text="提示：勾选启用，强度 0 等价于关闭。\n"
                      "多条叠加会自动归一化。",
                 justify=tk.LEFT, fg="#666",
                 font=("Microsoft YaHei", 9)).pack(pady=15)
        br = tk.Frame(self.win)
        br.pack(pady=10)
        tk.Button(br, text="应用", width=12, bg="#00cccc", fg="white",
                  command=self.apply).pack(side=tk.LEFT, padx=5)
        tk.Button(br, text="全部重置", width=12,
                  command=self.reset).pack(side=tk.LEFT, padx=5)
        tk.Button(br, text="取消", width=12,
                  command=self.win.destroy).pack(side=tk.LEFT, padx=5)

    def apply(self):
        for key, (en, st) in self.vars.items():
            self.app.fx_settings[key] = st.get() if en.get() else 0.0
        self.app.ambient_type = self.amb_var.get()
        self.app.log("FX 效果链已更新：")
        for label, key, default in FX_LIST:
            v = self.app.fx_settings.get(key, 0)
            if v > 0:
                self.app.log("  - " + label + " = %.2f" % v)
        self.app.log("  环境类型 = " + self.app.ambient_type)
        self.win.destroy()

    def reset(self):
        for key, (en, st) in self.vars.items():
            default = next((d for _, k, d in FX_LIST if k == key), 0)
            en.set(default > 0)
            st.set(default)


# ============================================================
#  编曲器窗口
# ============================================================
class ComposerWindow:
    def __init__(self, master, app):
        self.master = master
        self.app = app
        self.win = tk.Toplevel(master)
        self.win.title("CWMmaker 编曲器")
        self.win.geometry("1100x700")
        self.tracks = []
        self.current_project_path = None
        self.build_ui()
        self.add_track()

    def log(self, msg):
        self.app.log("[编曲器] " + str(msg))

    def build_ui(self):
        tb = tk.Frame(self.win, pady=5, padx=5)
        tb.pack(fill=tk.X)
        for text, cmd in [("新建工程", self.new_project),
                          ("打开工程", self.open_project),
                          ("保存工程", self.save_project),
                          ("另存为...", self.save_project_as)]:
            tk.Button(tb, text=text, width=10, command=cmd).pack(side=tk.LEFT, padx=2)
        tk.Frame(tb, width=20).pack(side=tk.LEFT)
        tk.Button(tb, text="+ 添加轨道", width=10,
                  command=self.add_track).pack(side=tk.LEFT, padx=2)
        tk.Button(tb, text="混合渲染", width=10, bg="#00cccc", fg="white",
                  command=self.render).pack(side=tk.LEFT, padx=2)

        paned = tk.PanedWindow(self.win, orient=tk.VERTICAL, sashwidth=6)
        paned.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        tf = tk.LabelFrame(paned, text="轨道", padx=5, pady=5)
        paned.add(tf, height=300)
        h = tk.Frame(tf)
        h.pack(fill=tk.X)
        for txt, w in [("轨名", 12), ("音色", 12), ("音量", 10), ("声像", 10),
                       ("八度", 6), ("静音", 6), ("操作", 14)]:
            tk.Label(h, text=txt, width=w, anchor='w').pack(side=tk.LEFT)
        canvas = tk.Canvas(tf, highlightthickness=0)
        sb = tk.Scrollbar(tf, orient='vertical', command=canvas.yview)
        self.track_list_frame = tk.Frame(canvas)
        self.track_list_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.track_list_frame, anchor='nw')
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        vf = tk.LabelFrame(paned, text="可视化编曲", padx=5, pady=5)
        paned.add(vf, height=250)
        self.viz_canvas = tk.Canvas(vf, bg="#fafafa",
                                    highlightthickness=1,
                                    highlightbackground="#cccccc")
        self.viz_canvas.pack(fill=tk.BOTH, expand=True)
        self.viz_canvas.bind("<Configure>", lambda e: self.redraw_viz())

    def add_track(self):
        track = dict(DEFAULT_TRACK)
        track['name'] = "轨道" + str(len(self.tracks) + 1)
        self.tracks.append(track)
        self.refresh_track_list()
        self.log("新增 " + track['name'])

    def remove_track(self, idx):
        if 0 <= idx < len(self.tracks):
            n = self.tracks[idx]['name']
            del self.tracks[idx]
            self.refresh_track_list()
            self.log("删除 " + n)

    def refresh_track_list(self):
        for w in self.track_list_frame.winfo_children():
            w.destroy()
        for i, t in enumerate(self.tracks):
            row = tk.Frame(self.track_list_frame)
            row.pack(fill=tk.X, pady=1)
            nv = tk.StringVar(value=t['name'])
            tk.Entry(row, textvariable=nv, width=12).pack(side=tk.LEFT)
            nv.trace_add('write',
                         lambda *a, i=i, v=nv: self.update_track(i, 'name', v.get()))
            tv = tk.StringVar(value=t['timbre'])
            ttk.Combobox(row, textvariable=tv, values=ALL_TIMBRES,
                         state='readonly', width=10).pack(side=tk.LEFT)
            tv.trace_add('write',
                         lambda *a, i=i, v=tv: self.update_track(i, 'timbre', v.get()))
            vv = tk.DoubleVar(value=t.get('volume', 1.0))
            tk.Scale(row, from_=0.0, to=2.0, resolution=0.05,
                     orient=tk.HORIZONTAL, length=80, showvalue=True,
                     variable=vv,
                     command=lambda v, i=i: self.update_track(i, 'volume', float(v))
                     ).pack(side=tk.LEFT)
            pv = tk.DoubleVar(value=t.get('pan', 0.0))
            tk.Scale(row, from_=-1.0, to=1.0, resolution=0.1,
                     orient=tk.HORIZONTAL, length=80, showvalue=True,
                     variable=pv,
                     command=lambda v, i=i: self.update_track(i, 'pan', float(v))
                     ).pack(side=tk.LEFT)
            ov = tk.IntVar(value=t.get('octave', 0))
            tk.Spinbox(row, from_=-2, to=2, textvariable=ov, width=4,
                       command=lambda i=i, v=ov: self.update_track(i, 'octave', int(v.get()))
                       ).pack(side=tk.LEFT)
            ov.trace_add('write',
                         lambda *a, i=i, v=ov: self.update_track(i, 'octave', int(v.get())))
            mv = tk.BooleanVar(value=t.get('mute', False))
            tk.Checkbutton(row, variable=mv,
                           command=lambda i=i, v=mv: self.update_track(i, 'mute', v.get())
                           ).pack(side=tk.LEFT)
            tk.Button(row, text="编辑乐谱", width=8,
                      command=lambda i=i: self.edit_score(i)).pack(side=tk.LEFT, padx=2)
            tk.Button(row, text="删除", width=5,
                      command=lambda i=i: self.remove_track(i)).pack(side=tk.LEFT, padx=2)
        self.redraw_viz()

    def update_track(self, idx, key, value):
        if 0 <= idx < len(self.tracks):
            self.tracks[idx][key] = value
            if key == 'score':
                self.redraw_viz()

    def edit_score(self, idx):
        if not (0 <= idx < len(self.tracks)):
            return
        t = self.tracks[idx]
        dlg = tk.Toplevel(self.win)
        dlg.title("编辑乐谱 - " + t['name'])
        dlg.geometry("700x520")
        tk.Label(dlg,
                 text="轨道：" + t['name'] + "  /  音色：" + t['timbre'] +
                      "\n打击乐记号：K=底鼓 S=军鼓 H=闭合镲 O=开镲 C=吊镲",
                 font=("Microsoft YaHei", 10, "bold"), justify=tk.LEFT).pack(pady=5)
        txt = scrolledtext.ScrolledText(dlg, font=("Consolas", 10))
        txt.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        txt.insert('1.0', t.get('score', ''))

        def save():
            self.tracks[idx]['score'] = txt.get('1.0', 'end').strip()
            self.log(t['name'] + " 乐谱已更新")
            self.redraw_viz()
            dlg.destroy()

        bf = tk.Frame(dlg)
        bf.pack(pady=5)
        tk.Button(bf, text="保存", width=10, command=save).pack(side=tk.LEFT, padx=5)
        tk.Button(bf, text="取消", width=10, command=dlg.destroy).pack(side=tk.LEFT, padx=5)

    def redraw_viz(self):
        self.viz_canvas.delete('all')
        W = self.viz_canvas.winfo_width()
        H = self.viz_canvas.winfo_height()
        if W <= 1 or H <= 1:
            return
        n = len(self.tracks)
        if n == 0:
            return
        durs = []
        for t in self.tracks:
            try:
                durs.append(estimate_duration(parse_score(t.get('score', '')), 1.0))
            except Exception:
                durs.append(0)
        md = max(durs) if durs else 1.0
        if md <= 0:
            md = 1.0
        rh = max(20, H // max(n, 1))
        lm = 40
        rm = 10
        uw = W - lm - rm
        for i, t in enumerate(self.tracks):
            y0 = i * rh + 2
            y1 = y0 + rh - 4
            self.viz_canvas.create_rectangle(lm, y0, W - rm, y1,
                                             fill="#f0f8ff", outline="#cccccc")
            self.viz_canvas.create_text(4, (y0 + y1) / 2,
                                        text=t['name'][:3], anchor='w',
                                        font=("Microsoft YaHei", 8))
            try:
                notes = parse_score(t.get('score', ''))
            except Exception:
                notes = []
            cur = 0.0
            for f, db, bpm in notes:
                ds = beats_to_seconds(db, bpm)
                if f is None:
                    cur += ds
                    continue
                x0 = lm + (cur / md) * uw
                x1 = lm + ((cur + ds) / md) * uw
                if x1 - x0 < 1:
                    x1 = x0 + 1
                col = "#888888" if isinstance(f, tuple) else self.freq_to_color(f)
                self.viz_canvas.create_rectangle(x0, y0 + 2, x1, y1 - 2,
                                                 fill=col, outline='')
                cur += ds

    def freq_to_color(self, freq):
        import colorsys
        if freq <= 0:
            return "#cccccc"
        lo, hi = 60, 2000
        t = (np.log(max(freq, lo)) - np.log(lo)) / (np.log(hi) - np.log(lo))
        t = max(0.0, min(1.0, t))
        r, g, b = colorsys.hsv_to_rgb(0.7 - 0.7 * t, 0.6, 0.9)
        return "#{:02x}{:02x}{:02x}".format(int(r * 255), int(g * 255), int(b * 255))

    def new_project(self):
        if self.tracks and not messagebox.askyesno("新建工程", "当前未保存，确定？"):
            return
        self.tracks = []
        self.current_project_path = None
        self.add_track()

    def open_project(self):
        path = filedialog.askopenfilename(
            initialdir=OSM_DIR, title="打开 OSM 工程",
            filetypes=[("OSM 工程", "*.osm"), ("JSON", "*.json"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            p = load_osm(path)
            self.tracks = p.get('tracks', [])
            for t in self.tracks:
                for k, v in DEFAULT_TRACK.items():
                    t.setdefault(k, v)
            self.current_project_path = path
            self.refresh_track_list()
            self.log("已打开：" + path)
        except Exception as e:
            messagebox.showerror("打开失败", str(e))

    def save_project(self):
        if self.current_project_path:
            self._do_save(self.current_project_path)
        else:
            self.save_project_as()

    def save_project_as(self):
        path = filedialog.asksaveasfilename(
            initialdir=OSM_DIR, title="保存 OSM 工程",
            defaultextension=".osm",
            filetypes=[("OSM 工程", "*.osm"), ("JSON", "*.json")])
        if path:
            self._do_save(path)

    def _do_save(self, path):
        try:
            save_osm({'version': '1.0',
                      'created': datetime.datetime.now().isoformat(),
                      'tracks': self.tracks}, path)
            self.current_project_path = path
            self.log("已保存：" + path)
            messagebox.showinfo("保存成功", "已保存到：\n" + path)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def render(self):
        if not self.tracks:
            messagebox.showwarning("无轨道", "请先添加至少一条轨道")
            return
        for t in self.tracks:
            if not t.get('score', '').strip():
                messagebox.showwarning("乐谱为空", "轨道 " + t['name'] + " 乐谱为空")
                return
        active = [t for t in self.tracks if not t.get('mute', False)]
        if not active:
            messagebox.showwarning("无音频", "所有轨道都被静音了")
            return
        self.app.composer_tracks = active
        self.app.source_var.set("composer")
        self.app.on_source_change()
        self.log("已把 " + str(len(active)) + " 条轨道交给主窗口")
        messagebox.showinfo("准备就绪",
                            "已加载 " + str(len(active)) + " 条轨道到主界面。\n"
                            "请回主界面点开始合成。")


# ============================================================
#  主窗口
# ============================================================
class CWMmakerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("CWMmaker - Computer Wav Music Maker v8.0")
        self.root.geometry("800x740")
        self.root.resizable(False, False)

        self.score = self.load_score()
        self.notes = parse_score(self.score) if self.score else []
        self.is_running = False
        self.synth_mode = 'single'
        self.pending_tracks = None
        self.msg_queue = queue.Queue()
        self.composer_tracks = None
        self.composer_win = None

        self.fx_settings = {key: default for _, key, default in FX_LIST}
        self.ambient_type = AMBIENT_TYPES[0]

        self.octave_var = tk.IntVar(value=0)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.filename_var = tk.StringVar(value="newAudio")
        self.estimate_var = tk.StringVar(value="--:--")
        self.source_var = tk.StringVar(value="sheet")

        self.build_ui()
        self.update_estimate()
        self.poll_queue()

    def load_score(self):
        if not os.path.exists(SHEET_PATH):
            return ""
        with open(SHEET_PATH, "r", encoding="utf-8") as f:
            return f.read().strip()

    def build_ui(self):
        main = tk.Frame(self.root, padx=10, pady=10)
        main.pack(fill=tk.BOTH, expand=True)

        src = tk.LabelFrame(main, text="音源", padx=5, pady=5)
        src.pack(fill=tk.X, pady=(0, 5))
        tk.Radiobutton(src, text="SheetMusic.txt（单轨）",
                       variable=self.source_var, value="sheet",
                       command=self.on_source_change).pack(side=tk.LEFT, padx=10)
        tk.Radiobutton(src, text="编曲器工程（多轨）",
                       variable=self.source_var, value="composer",
                       command=self.on_source_change).pack(side=tk.LEFT, padx=10)
        self.source_status = tk.Label(src, text="（使用 SheetMusic.txt）",
                                      fg="#888", font=("Microsoft YaHei", 9))
        self.source_status.pack(side=tk.LEFT, padx=20)

        top = tk.Frame(main)
        top.pack(fill=tk.X)
        lb = tk.LabelFrame(top, text="音色（单轨）", padx=5, pady=5)
        lb.pack(side=tk.LEFT, fill=tk.Y)
        self.timbre_list = tk.Listbox(lb, width=22, height=18,
                                      exportselection=False,
                                      font=("Microsoft YaHei", 9))
        for t in ALL_TIMBRES:
            self.timbre_list.insert(tk.END, t)
        self.timbre_list.selection_set(0)
        self.timbre_list.pack(side=tk.LEFT, fill=tk.Y)
        sb = tk.Scrollbar(lb, command=self.timbre_list.yview)
        sb.pack(side=tk.RIGHT, fill=tk.Y)
        self.timbre_list.config(yscrollcommand=sb.set)

        param = tk.LabelFrame(top, text="参数", padx=10, pady=10)
        param.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        tk.Label(param, text="升降八度：", anchor='w').grid(row=0, column=0, sticky='w', pady=3)
        self.octave_lbl = tk.Label(param, text="0", width=4)
        self.octave_lbl.grid(row=0, column=2, sticky='w')
        self.octave_scale = tk.Scale(param, from_=-3, to=3, orient=tk.HORIZONTAL,
                                     length=280, resolution=1, showvalue=False,
                                     variable=self.octave_var,
                                     command=self.on_octave_change)
        self.octave_scale.grid(row=0, column=1, sticky='we')
        tk.Label(param, text="速度倍率：", anchor='w').grid(row=1, column=0, sticky='w', pady=3)
        self.speed_lbl = tk.Label(param, text="1.00", width=4)
        self.speed_lbl.grid(row=1, column=2, sticky='w')
        self.speed_scale = tk.Scale(param, from_=0.5, to=2.0, orient=tk.HORIZONTAL,
                                    length=280, resolution=0.05, showvalue=False,
                                    variable=self.speed_var,
                                    command=self.on_speed_change)
        self.speed_scale.grid(row=1, column=1, sticky='we')
        tk.Label(param, text="文件名：", anchor='w').grid(row=2, column=0, sticky='w', pady=(12, 3))
        tk.Entry(param, textvariable=self.filename_var, width=28,
                 font=("Consolas", 10)).grid(row=2, column=1, columnspan=2,
                                             sticky='we', pady=(12, 3))
        tk.Label(param, text="预计时长：", anchor='w').grid(row=3, column=0, sticky='w', pady=3)
        tk.Label(param, textvariable=self.estimate_var,
                 fg="#00aa88", font=("Consolas", 11, "bold")).grid(
            row=3, column=1, sticky='w', pady=3)
        param.columnconfigure(1, weight=1)

        pf = tk.Frame(main, pady=5)
        pf.pack(fill=tk.X)
        tk.Label(pf, text="进度：", font=("Microsoft YaHei", 9)).pack(side=tk.LEFT)
        self.progress_bar = ttk.Progressbar(pf, orient='horizontal',
                                            length=680, mode='determinate')
        self.progress_bar.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 5))
        self.progress_lbl = tk.Label(pf, text="0/0", width=12,
                                     font=("Consolas", 9))
        self.progress_lbl.pack(side=tk.RIGHT)

        mid = tk.LabelFrame(main, text="状态", padx=5, pady=5)
        mid.pack(fill=tk.BOTH, expand=True, pady=(5, 0))
        self.status_text = scrolledtext.ScrolledText(mid, width=95, height=9,
                                                     state='disabled',
                                                     font=("Consolas", 9),
                                                     wrap=tk.WORD)
        self.status_text.pack(fill=tk.BOTH, expand=True)

        b = tk.Frame(main)
        b.pack(fill=tk.X, pady=(10, 0))
        self.start_btn = tk.Button(b, text="开始合成",
                                   font=("Microsoft YaHei", 12, "bold"),
                                   bg="#00cccc", fg="white",
                                   activebackground="#00aaaa",
                                   activeforeground="white",
                                   width=12, height=2, relief=tk.FLAT,
                                   command=self.on_start)
        self.start_btn.pack(side=tk.LEFT)
        self.reload_btn = tk.Button(b, text="重新载入乐谱",
                                    font=("Microsoft YaHei", 10),
                                    bg="#eeeeee", fg="#333",
                                    activebackground="#dddddd",
                                    width=12, height=2, relief=tk.FLAT,
                                    command=self.on_reload)
        self.reload_btn.pack(side=tk.LEFT, padx=(10, 0))
        self.composer_btn = tk.Button(b, text="打开编曲器",
                                      font=("Microsoft YaHei", 10, "bold"),
                                      bg="#ffaa33", fg="white",
                                      activebackground="#ee9922",
                                      activeforeground="white",
                                      width=12, height=2, relief=tk.FLAT,
                                      command=self.open_composer)
        self.composer_btn.pack(side=tk.LEFT, padx=(10, 0))
        self.fx_btn = tk.Button(b, text="音频效果",
                                font=("Microsoft YaHei", 10, "bold"),
                                bg="#aa66ff", fg="white",
                                activebackground="#9955ee",
                                activeforeground="white",
                                width=12, height=2, relief=tk.FLAT,
                                command=self.open_fx)
        self.fx_btn.pack(side=tk.LEFT, padx=(10, 0))
        tk.Label(b, text="By Loji_", font=("Consolas", 10, "italic"),
                 fg="#666").pack(side=tk.RIGHT, padx=10)

        self.log("已加载乐谱：" + str(len(self.notes)) + " 个音符")
        self.log("输出目录：" + OUT_DIR)
        self.log("架构：v8.0（音色修正 + 长笛 + 架子鼓 + 3 半音波表）")
        self.log("打击乐记号：K=底鼓 S=军鼓 H=闭合镲 O=开镲 C=吊镲")

    def on_octave_change(self, val):
        self.octave_lbl.config(text=str(int(float(val))))

    def on_speed_change(self, val):
        self.speed_lbl.config(text="%.2f" % float(val))
        self.update_estimate()

    def on_source_change(self):
        if self.source_var.get() == "composer":
            if self.composer_tracks:
                n = len(self.composer_tracks)
                self.source_status.config(
                    text="已加载编曲器工程：" + str(n) + " 条轨道",
                    fg="#00aa88")
                self.log("音源切换：编曲器工程（" + str(n) + " 轨）")
            else:
                self.source_status.config(text="（编曲器工程为空）", fg="#cc3333")
        else:
            self.source_status.config(text="（使用 SheetMusic.txt）", fg="#888")

    def update_estimate(self):
        if not self.notes:
            self.estimate_var.set("--:--")
            return
        sec = estimate_duration(self.notes, self.speed_var.get())
        m, s = divmod(int(sec), 60)
        self.estimate_var.set("{:02d}:{:02d}".format(m, s))

    def log(self, msg):
        ts = now_str()
        self.status_text.config(state='normal')
        self.status_text.insert(tk.END, "[" + ts + "] " + str(msg) + "\n")
        self.status_text.see(tk.END)
        self.status_text.config(state='disabled')

    def on_reload(self):
        self.score = self.load_score()
        if self.score:
            self.notes = parse_score(self.score)
            self.log("重新载入：" + str(len(self.notes)) + " 个音符")
            self.update_estimate()
        else:
            self.notes = []
            self.log("重新载入失败")
            self.estimate_var.set("--:--")

    def open_composer(self):
        self.composer_win = ComposerWindow(self.root, self)
        self.log("打开编曲器")

    def open_fx(self):
        FXWindow(self.root, self)
        self.log("打开音频效果窗口")

    def on_start(self):
        if self.is_running:
            return
        if self.source_var.get() == "composer":
            if not self.composer_tracks:
                messagebox.showwarning("无工程", "编曲器工程为空")
                play_dingdong(False)
                return
            self.start_multi_render(self.composer_tracks)
            return
        if not self.notes:
            self.log("错误：没有可用的乐谱")
            play_dingdong(False)
            return
        sel = self.timbre_list.curselection()
        if not sel:
            self.log("错误：未选择音色")
            play_dingdong(False)
            return
        timbre = ALL_TIMBRES[sel[0]]
        speed = self.speed_var.get()
        octave = self.octave_var.get()
        prefix = self.filename_var.get().strip() or "newAudio"
        prefix = re.sub(r'[\\/:*?"<>|]', "_", prefix)

        today = datetime.datetime.now().strftime("%Y_%m_%d")
        filename = prefix + "_" + today + ".wav"
        wav_path = os.path.join(OUT_DIR, filename)
        if os.path.exists(wav_path):
            base, ext = os.path.splitext(filename)
            k = 2
            while os.path.exists(os.path.join(OUT_DIR, base + "_" + str(k) + ext)):
                k += 1
            filename = base + "_" + str(k) + ext
            wav_path = os.path.join(OUT_DIR, filename)

        self.is_running = True
        self.synth_mode = 'single'
        self.start_btn.config(state=tk.DISABLED, text="合成中...")
        self.reload_btn.config(state=tk.DISABLED)
        self.composer_btn.config(state=tk.DISABLED)
        self.fx_btn.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = len(self.notes)
        self.progress_lbl.config(text="0/" + str(len(self.notes)))
        self.log("开始合成：音色=" + timbre + " 速度=" + str(speed) + "x 八度=" + str(octave))

        threading.Thread(target=self.worker,
                         args=(timbre, speed, octave, wav_path),
                         daemon=True).start()

    def worker(self, timbre, speed, octave, wav_path):
        t0 = time.time()
        try:
            def pc(c, t):
                self.msg_queue.put(('progress', c, t))
            ok = synth_v7(self.score, wav_path, timbre, speed, octave,
                          fx_settings=self.fx_settings,
                          ambient_type=self.ambient_type,
                          log_callback=lambda m: self.msg_queue.put(('log', m)),
                          progress_callback=pc)
            t1 = time.time()
            if ok:
                self.msg_queue.put(('success', wav_path, t1 - t0))
            else:
                self.msg_queue.put(('error', '合成失败'))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.msg_queue.put(('error', type(e).__name__ + ': ' + str(e)))

    def start_multi_render(self, tracks):
        if self.is_running:
            messagebox.showwarning("正在合成", "请等待当前合成完成")
            return
        if not tracks:
            messagebox.showwarning("无轨道", "没有可混合的轨道")
            return
        ts = datetime.datetime.now().strftime("%Y_%m_%d_%H%M%S")
        default_name = "mix_" + ts + ".wav"
        path = filedialog.asksaveasfilename(
            initialdir=OUT_DIR, title="保存混合音频",
            initialfile=default_name, defaultextension=".wav",
            filetypes=[("WAV 音频", "*.wav")])
        if not path:
            return
        self.is_running = True
        self.synth_mode = 'multi'
        self.pending_tracks = tracks
        self.start_btn.config(state=tk.DISABLED, text="混合中...")
        self.reload_btn.config(state=tk.DISABLED)
        self.composer_btn.config(state=tk.DISABLED)
        self.fx_btn.config(state=tk.DISABLED)
        self.progress_bar['value'] = 0
        self.progress_bar['maximum'] = len(tracks)
        self.progress_lbl.config(text="0/" + str(len(tracks)))
        self.log("接收到编曲工程：" + str(len(tracks)) + " 条轨道")
        for t in tracks:
            self.log("  - " + t['name'] + " (" + t['timbre'] + ") vol=" +
                     str(t.get('volume', 1.0)) + " pan=" + str(t.get('pan', 0.0)))
        speed = self.speed_var.get()
        threading.Thread(target=self.multi_worker,
                         args=(tracks, speed, path),
                         daemon=True).start()

    def multi_worker(self, tracks, speed, path):
        t0 = time.time()
        try:
            def pc(ti, tt, ci, ct):
                self.msg_queue.put(('multi_progress', ti, tt, ci, ct))
            ok = synth_multi_v7(tracks, path, speed,
                                fx_settings=self.fx_settings,
                                ambient_type=self.ambient_type,
                                log_callback=lambda m: self.msg_queue.put(('log', m)),
                                progress_callback=pc)
            t1 = time.time()
            if ok:
                self.msg_queue.put(('success', path, t1 - t0))
            else:
                self.msg_queue.put(('error', '混合失败'))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.msg_queue.put(('error', type(e).__name__ + ': ' + str(e)))

    def poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                kind = msg[0]
                if kind == 'log':
                    self.log(msg[1])
                elif kind == 'progress':
                    c, t = msg[1], msg[2]
                    self.progress_bar['value'] = c
                    self.progress_lbl.config(text=str(c) + "/" + str(t))
                elif kind == 'multi_progress':
                    ti, tt, ci, ct = msg[1], msg[2], msg[3], msg[4]
                    self.progress_bar['value'] = ti + (ci / max(ct, 1))
                    self.progress_lbl.config(text="轨道 " + str(ti + 1) + "/" + str(tt))
                elif kind == 'success':
                    path, elapsed = msg[1], msg[2]
                    self.log("合成成功！总耗时 %.2f 秒" % elapsed)
                    self.log("输出文件：" + path)
                    self.is_running = False
                    self.start_btn.config(state=tk.NORMAL, text="开始合成")
                    self.reload_btn.config(state=tk.NORMAL)
                    self.composer_btn.config(state=tk.NORMAL)
                    self.fx_btn.config(state=tk.NORMAL)
                    self.progress_bar['value'] = self.progress_bar['maximum']
                    self.progress_lbl.config(text="完成")
                    play_dingdong(True)
                elif kind == 'error':
                    self.log("错误：" + str(msg[1]))
                    self.is_running = False
                    self.start_btn.config(state=tk.NORMAL, text="开始合成")
                    self.reload_btn.config(state=tk.NORMAL)
                    self.composer_btn.config(state=tk.NORMAL)
                    self.fx_btn.config(state=tk.NORMAL)
                    play_dingdong(False)
        except queue.Empty:
            pass
        self.root.after(150, self.poll_queue)


def main():
    root = tk.Tk()
    app = CWMmakerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()