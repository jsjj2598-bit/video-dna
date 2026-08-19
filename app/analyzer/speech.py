"""语音/说话人检测 + ASR 台词转写。

两级：先用 librosa 能量检测找出语音段落（always works），
再尝试 faster-whisper 做精确转写（需要网络下载模型，失败则跳过）。
"""
from __future__ import annotations

import numpy as np


def empty_transcript() -> dict:
    return {
        "language": None,
        "text": "",
        "segments": [],
        "word_count": 0,
        "speech_regions": [],
    }


def _speech_regions_from_energy(wav_path: str, sr: int = 22050,
                                min_speech_sec: float = 0.3,
                                silence_threshold_db: float = -35.0) -> list[dict]:
    """用能量检测找出语音段落（不依赖 ASR 模型）。"""
    import librosa
    y, sr = librosa.load(wav_path, sr=sr, mono=True)
    if y.size == 0:
        return []

    hop = 512
    rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=hop)[0]
    ref = rms.max() if rms.max() > 0 else 1.0
    rms_db = librosa.amplitude_to_db(rms, ref=ref)
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop)

    # 标记静音帧
    is_speech = rms_db > silence_threshold_db

    # 合并连续的 speech 帧为段落
    regions: list[dict] = []
    start_time = None
    for i, sp in enumerate(is_speech):
        if sp and start_time is None:
            start_time = float(times[i])
        elif not sp and start_time is not None:
            dur = float(times[i]) - start_time
            if dur >= min_speech_sec:
                regions.append({"start": round(start_time, 3),
                                "end": round(float(times[i]), 3),
                                "text": None})
            start_time = None

    if start_time is not None:
        dur = float(times[-1]) - start_time
        if dur >= min_speech_sec:
            regions.append({"start": round(start_time, 3),
                            "end": round(float(times[-1]), 3),
                            "text": None})

    return regions


def transcribe(wav_path: str, model_size: str = "small",
               language: str | None = None, use_whisper: bool = True) -> dict:
    """台词转写。先尝试 faster-whisper（网络模型），失败则降级到能量检测。

    use_whisper=False 时直接使用能量检测（组件关闭 ASR 时）。
    """
    result = empty_transcript()

    # 1. 尝试 faster-whisper ASR
    asr_ok = False
    if use_whisper:
        try:
            from faster_whisper import WhisperModel
            import os

            # 检查缓存中是否有模型
            model = WhisperModel(model_size, device="cpu", compute_type="int8")
            segments, info = model.transcribe(
                wav_path,
                language=language,
                beam_size=5,
                vad_filter=True,
            )

            if info is not None:
                result["language"] = info.language

            segs: list[dict] = []
            texts: list[str] = []
            for seg in segments:
                segs.append({
                    "start": round(float(seg.start), 3),
                    "end": round(float(seg.end), 3),
                    "text": seg.text.strip(),
                })
                texts.append(seg.text.strip())

            result["segments"] = segs
            result["text"] = "\n".join(texts)
            result["word_count"] = sum(len(t) for t in texts)

            # 也用 ASR 的结果填充 speech_regions
            result["speech_regions"] = [
                {"start": s["start"], "end": s["end"], "text": s["text"]}
                for s in segs
            ]
            asr_ok = True

        except Exception:
            pass  # ASR 失败（无网络/无模型），走降级

    # 2. 降级：能量检测语音段落
    if not asr_ok:
        regions = _speech_regions_from_energy(wav_path)
        result["speech_regions"] = regions
        result["segments"] = [
            {"start": r["start"], "end": r["end"], "text": None}
            for r in regions
        ]
        result["word_count"] = 0
        result["text"] = ""
        result["language"] = None

    return result