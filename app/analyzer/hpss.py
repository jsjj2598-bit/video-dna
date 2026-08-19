"""谐波/打击乐分离 + 增强音频分析。

对音频的谐波成分（人声、旋律乐器）和打击成分（鼓、瞬态）分别分析，
产生更准确的 BPM（谐波为主）和更精细的 SFX 候选（打击为主）。

所有分析降级安全：librosa 已安装，无需额外模型下载。
"""
from __future__ import annotations

import numpy as np


def hpss_separate(y: np.ndarray | None, sr: int = 22050) -> dict:
    """HPSS 分离，返回 {harmonic, percussive}。

    两个分量都与原信号同长。当 y 为空/静音时返回全零分量。
    """
    empty = {"harmonic": np.zeros(0, dtype=np.float32),
             "percussive": np.zeros(0, dtype=np.float32)}

    if y is None or y.size == 0:
        return empty

    import librosa

    try:
        # 默认窗长 1024，hop 512
        h, p = librosa.effects.hpss(y, margin=4.0)
        return {"harmonic": h.astype(np.float32),
                "percussive": p.astype(np.float32)}
    except Exception:
        return empty


def analyze_harmonic(h: np.ndarray, sr: int = 22050) -> dict:
    """对谐波分量做 BPM/节拍分析——BGM 的基准确度更高。"""
    if h is None or h.ndim != 1 or h.size < sr * 2:  # 至少 2s
        return {"tempo_bpm": None, "beats": [], "beat_count": 0}

    import librosa

    try:
        tempo, beats = librosa.beat.beat_track(y=h, sr=sr, units="time")
        if isinstance(tempo, np.ndarray):
            tempo = float(tempo[0]) if tempo.size else 0.0
        return {
            "tempo_bpm": round(float(tempo), 2) if tempo else None,
            "beats": [round(float(b), 3) for b in beats],
            "beat_count": len(beats),
        }
    except Exception:
        return {"tempo_bpm": None, "beats": [], "beat_count": 0}


def analyze_percussive(p: np.ndarray, sr: int = 22050) -> dict:
    """对打击分量做瞬态检测——音效候选更干净。"""
    if p is None or p.ndim != 1 or p.size < sr:  # 至少 1s
        return {"sfx_candidates": [], "onset_count": 0}

    import librosa

    try:
        onset_env = librosa.onset.onset_strength(y=p, sr=sr, hop_length=512)
        onsets = librosa.onset.onset_detect(
            onset_envelope=onset_env,
            sr=sr,
            hop_length=512,
            units="time",
        )
        if len(onsets) == 0:
            return {"sfx_candidates": [], "onset_count": 0}

        # 取前 70% 分位以上的作为强瞬态
        onset_strength = onset_env[librosa.time_to_frames(onsets, sr=sr, hop_length=512)]
        threshold = float(np.percentile(onset_strength, 70)) if onset_strength.size > 0 else 0
        candidates = [
            {"time": round(float(t), 3), "strength": round(float(s), 3)}
            for t, s in zip(onsets, onset_strength)
            if s >= threshold
        ]

        return {
            "sfx_candidates": candidates,
            "onset_count": len(onsets),
        }
    except Exception:
        return {"sfx_candidates": [], "onset_count": 0}


def analyze_enhanced(wav_path: str, sr: int = 22050) -> dict:
    """增强版音频分析入口：HPSS 分离 → 谐波测 BPM + 打击测 SFX。

    返回 {harmonic, percussive, combined} 三个子字典。
    combined 是原音频的 librosa 分析（向后兼容）。
    """
    import librosa

    y, _sr = librosa.load(wav_path, sr=sr, mono=True)
    sr_actual = _sr  # librosa 返回实际的 sr

    # 1. 原始分析（向后兼容）
    combined = _legacy_analysis(y, sr_actual)

    # 2. HPSS 分离
    sep = hpss_separate(y, sr_actual)

    # 3. 谐波分析 → 更准的 BPM
    harmonic = analyze_harmonic(sep["harmonic"], sr_actual)

    # 4. 打击分析 → 更干净的 SFX
    percussive = analyze_percussive(sep["percussive"], sr_actual)

    # 5. 合并：谐波 BPM 优先（更干净），无效时回退全信号
    result = {**combined}
    if harmonic.get("tempo_bpm") and harmonic["tempo_bpm"] > 0:
        result["tempo_bpm"] = harmonic["tempo_bpm"]
        result["beats"] = harmonic["beats"]
        result["beat_count"] = harmonic["beat_count"]
    # SFX 用打击分量（更干净）
    if percussive.get("sfx_candidates"):
        result["sfx_candidates"] = percussive["sfx_candidates"]
        result["onset_count"] = percussive["onset_count"]
    result["harmonic"] = harmonic
    result["percussive"] = percussive
    return result


def _legacy_analysis(y: np.ndarray, sr: int) -> dict:
    """原 audio.analyze_audio 的逻辑（保持向后兼容）。"""
    import librosa

    if y is None or y.size == 0:
        return {}

    result = {}
    dur = float(len(y)) / sr

    try:
        tempo, beats = librosa.beat.beat_track(y=y, sr=sr, units="time")
        if isinstance(tempo, np.ndarray):
            tempo = float(tempo[0]) if tempo.size else 0.0
        result["tempo_bpm"] = round(float(tempo), 2) if tempo else None
        result["beats"] = [round(float(b), 3) for b in beats]
        result["beat_count"] = len(beats)
    except Exception:
        pass

    try:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
        onsets = librosa.onset.onset_detect(
            onset_envelope=onset_env, sr=sr, hop_length=512, units="time"
        )
        result["onset_count"] = len(onsets)

        onset_strength = onset_env[librosa.time_to_frames(onsets, sr=sr, hop_length=512)]
        threshold = float(np.percentile(onset_strength, 70)) if onset_strength.size > 0 else 0
        result["sfx_candidates"] = [
            {"time": round(float(t), 3), "strength": round(float(s), 3)}
            for t, s in zip(onsets, onset_strength)
            if s >= threshold
        ]
    except Exception:
        pass

    # 能量包络 (10Hz 降采样)
    try:
        hop = sr // 10  # 约 10Hz
        rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
        result["energy"] = {
            "times": [round(float(t), 3) for t in librosa.frames_to_time(
                range(len(rms)), sr=sr, hop_length=hop)],
            "rms_db": [round(float(librosa.amplitude_to_db([r], ref=1.0)[0]), 2)
                       for r in rms],
        }
        # 重新计算 dB
        rms_db = librosa.amplitude_to_db(rms, ref=1.0)
        result["rms_mean_db"] = round(float(np.mean(rms_db)), 2)
        result["rms_max_db"] = round(float(np.max(rms_db)), 2)
    except Exception:
        pass

    # 静音比例
    try:
        silent = np.abs(y) < 0.01
        result["silence_ratio"] = round(float(silent.sum() / y.size), 3)
    except Exception:
        result["silence_ratio"] = 0.0

    result["duration"] = round(dur, 3)
    return result


def empty_analysis() -> dict:
    return {
        "duration": 0.0,
        "tempo_bpm": None,
        "beats": [],
        "beat_count": 0,
        "onset_count": 0,
        "silence_ratio": 0.0,
        "rms_mean_db": 0.0,
        "rms_max_db": 0.0,
        "energy": {"times": [], "rms_db": []},
        "sfx_candidates": [],
        "harmonic": {"tempo_bpm": None, "beats": [], "beat_count": 0},
        "percussive": {"sfx_candidates": [], "onset_count": 0},
    }