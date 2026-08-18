"""编排完整分析管线，产出「剪辑 DNA」JSON。

P0：元信息 + 镜头切分 + 节拍卡点 + 节奏统计。
P1：转场类型识别 + 音频能量/静音/强瞬态。
P2：ASR 台词转写 + 语音段落检测 + 台词-镜头对齐。
P3：谐波/打击乐分离 → 更准 BPM + 更干净音效候选。
P4：多模态语义描述（VLM API / OpenCV 降级）。
P5：EDL / FCP7XML / Cutmark JSON 导出（app/exporter.py）。
"""
from __future__ import annotations

import bisect
import shutil
import tempfile
from pathlib import Path

from . import audio as old_audio  # 旧版保持向后兼容
from . import ffmpeg_utils, hpss, shots, speech, transitions
from .describer import describe_all


def _nearest_beat(t: float, beats: list[float], tol: float = 0.15):
    if not beats:
        return False, None
    i = bisect.bisect_left(beats, t)
    candidates = []
    if i < len(beats):
        candidates.append(beats[i])
    if i > 0:
        candidates.append(beats[i - 1])
    offset = min(abs(c - t) for c in candidates)
    return offset <= tol, round(offset, 3)


_TRANSITION_LABELS = {
    "cut": "硬切",
    "dissolve": "叠化",
    "fade": "淡入淡出",
    "white_flash": "闪白",
    "unknown": "未知",
}


def _summarize(shots_list, audio_info: dict, beat_ratio: float, transition_counts: dict) -> str:
    parts = []
    if shots_list:
        avg = sum(s["duration"] for s in shots_list) / len(shots_list)
        parts.append(f"共 {len(shots_list)} 个镜头，平均 {avg:.2f} 秒/镜")
        if avg < 2:
            pace = "极快"
        elif avg < 4:
            pace = "快"
        elif avg < 8:
            pace = "中等"
        else:
            pace = "慢"
        parts.append(f"整体节奏偏{pace}")
        parts.append(f"卡点率约 {beat_ratio * 100:.0f}%")
    if transition_counts:
        order = ["cut", "dissolve", "fade", "white_flash", "unknown"]
        seg = "、".join(
            f"{_TRANSITION_LABELS.get(k, k)}×{transition_counts[k]}" for k in order if k in transition_counts
        )
        parts.append(f"转场：{seg}")
    if audio_info.get("tempo_bpm"):
        parts.append(
            f"BGM 约 {audio_info['tempo_bpm']:.0f} BPM，"
            f"检测到 {audio_info.get('beat_count', 0)} 个节拍点"
        )
    else:
        parts.append("未检测到明显节拍（可能无音乐）")
    sfx = audio_info.get("sfx_candidates", [])
    if sfx:
        parts.append(f"检测到 {len(sfx)} 个强瞬态（音效候选）")
    sr = audio_info.get("speech_regions", [])
    if sr:
        parts.append(f"检测到 {len(sr)} 段语音")
    wc = audio_info.get("word_count", 0)
    if wc:
        parts.append(f"台词约 {wc} 字")
    # VLM 描述状态
    described = sum(1 for s in shots_list if s.get("content"))
    if described:
        method = shots_list[0].get("content_method", "heuristic")
        parts.append(f"已完成 {described} 个镜头语义描述（{method}）")
    return "；".join(parts) + "。"


def analyze(
    video_path: str,
    work_dir: str | None = None,
    extract_keyframes: bool = True,
    detector: str = "content",
    detect_transitions: bool = True,
    describe_shots: bool = True,   # 默认启用 OpenCV 启发式描述（无需 API）
    vlm_backend: str = "auto",
    vlm_model: str = "gpt-4o",
    keep_workdir: bool = False,
) -> dict:
    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="videodna_"))
    else:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        meta = ffmpeg_utils.probe(str(video_path))
        shots_list = shots.detect_shots(str(video_path), detector=detector)

        # ── 音频分析（HPSS 增强） ──
        wav = None
        if meta.get("audio_codec"):
            wav = ffmpeg_utils.extract_audio(str(video_path), str(work_dir))
            audio_info = hpss.analyze_enhanced(wav)
            # ASR 台词
            try:
                transcript = speech.transcribe(wav)
                audio_info.update(transcript)
            except Exception:
                pass
        else:
            audio_info = old_audio.empty_audio_info()

        # ── 节拍卡点 ──
        beats = audio_info.get("beats", [])
        aligned_count = 0
        for sh in shots_list:
            aligned, offset = _nearest_beat(sh["start"], beats)
            sh["beat_aligned"] = aligned
            sh["beat_offset"] = offset
            sh["transition"] = None
            sh["transition_confidence"] = None
            sh["content"] = None
            sh["camera_motion"] = None
            sh["shot_scale"] = None
            sh["content_method"] = None
            if aligned:
                aligned_count += 1

        beat_ratio = (aligned_count / len(shots_list)) if shots_list else 0.0

        # ── 转场分类 ──
        transition_counts: dict = {}
        if detect_transitions and len(shots_list) > 1:
            trans = transitions.classify_transitions(str(video_path), shots_list, str(work_dir))
            for i, t in enumerate(trans):
                if t is None:
                    continue
                shots_list[i]["transition"] = t["type"]
                shots_list[i]["transition_confidence"] = t["confidence"]
                transition_counts[t["type"]] = transition_counts.get(t["type"], 0) + 1

        # ── 台词对齐到镜头 ──
        if audio_info.get("segments"):
            for sh in shots_list:
                segs = []
                for ts in audio_info["segments"]:
                    if ts["end"] > sh["start"] and ts["start"] < sh["end"]:
                        t = ts.get("text")
                        if t:
                            segs.append(t)
                sh["transcript"] = "，".join(segs) if segs else None
        else:
            for sh in shots_list:
                sh["transcript"] = None

        # ── 关键帧提取 ──
        if extract_keyframes:
            frames_dir = work_dir / "frames"
            frames_dir.mkdir(exist_ok=True)
            for sh in shots_list:
                mid = (sh["start"] + sh["end"]) / 2
                fname = f"shot_{sh['index']:03d}.jpg"
                try:
                    ffmpeg_utils.extract_frame(str(video_path), mid, str(frames_dir / fname))
                    sh["keyframe"] = fname
                except Exception:
                    sh["keyframe"] = None
        else:
            for sh in shots_list:
                sh["keyframe"] = None

        # ── VLM 语义描述（可选） ──
        if describe_shots and extract_keyframes and shots_list:
            frames_dir = work_dir / "frames"
            try:
                describe_all(
                    {"shots": shots_list},
                    frames_dir,
                    backend=vlm_backend,
                    model=vlm_model,
                )
            except Exception:
                pass

        # ── 统计 ──
        avg_shot = (sum(s["duration"] for s in shots_list) / len(shots_list)) if shots_list else 0.0

        return {
            "meta": {
                **meta,
                "total_shots": len(shots_list),
                "avg_shot_duration": round(avg_shot, 3),
                "beat_alignment_ratio": round(beat_ratio, 3),
                "transitions": transition_counts,
            },
            "audio": audio_info,
            "shots": shots_list,
            "summary": _summarize(shots_list, audio_info, beat_ratio, transition_counts),
        }
    finally:
        if not keep_workdir and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)