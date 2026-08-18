"""音频分析：BPM、节拍点、onset、能量包络、静音、强瞬态（音效候选）。

P1 新增能量/静音/瞬态；后续接 Demucs（人声/音乐/音效分离）与
YAMNet/PANN（音效分类）再补齐音乐与音效的精细维度。
"""
from __future__ import annotations

import numpy as np


def empty_audio_info() -> dict:
    return {
        "duration": 0.0,
        "tempo_bpm": None,
        "beats": [],
        "beat_count": 0,
        "onset_count": 0,
        "silence_ratio": 1.0,
        "rms_mean_db": None,
        "rms_max_db": None,
        "energy": {"times": [], "rms_db": []},
        "sfx_candidates": [],
    }


def analyze_audio(wav_path: str) -> dict:
    import librosa

    y, sr = librosa.load(wav_path, sr=22050, mono=True)
    result = empty_audio_info()
    if y is None or y.size == 0:
        return result

    result["duration"] = round(float(len(y) / sr), 3)

    # 节拍 / BPM
    try:
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        if hasattr(tempo, "__len__"):
            tempo = float(tempo[0])
        beat_times = [round(float(t), 3) for t in librosa.frames_to_time(beat_frames, sr=sr)]
        result["tempo_bpm"] = round(float(tempo), 2)
        result["beats"] = beat_times
        result["beat_count"] = len(beat_times)
    except Exception:
        pass

    # 能量包络 + 静音
    try:
        hop = 512
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
        ref = rms.max() if rms.max() > 0 else 1.0
        rms_db = librosa.amplitude_to_db(rms, ref=ref)
        result["rms_mean_db"] = round(float(rms_db.mean()), 2)
        result["rms_max_db"] = round(float(rms_db.max()), 2)
        result["silence_ratio"] = round(float((rms_db < -40.0).mean()), 3)

        step = max(1, int(sr / hop / 10))  # 降采样到 ~10Hz 供图表
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)
        result["energy"] = {
            "times": [round(float(t), 3) for t in times[::step]],
            "rms_db": [round(float(v), 2) for v in rms_db[::step]],
        }
    except Exception:
        pass

    # 强瞬态（音效候选）：onset 强度显著高于平均水平的瞬态
    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr)
        onset_frames = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, backtrack=True)
        result["onset_count"] = int(len(onset_frames))
        if len(onset_frames):
            strengths = onset_env[onset_frames]
            threshold = float(np.percentile(strengths, 70))
            mask = strengths >= threshold
            strong_times = librosa.frames_to_time(onset_frames[mask], sr=sr)
            result["sfx_candidates"] = [
                {"time": round(float(t), 3), "strength": round(float(s), 3)}
                for t, s in zip(strong_times, strengths[mask])
            ]
    except Exception:
        pass

    return result
