"""Rhythm templates and safe cut-plan generation."""

from __future__ import annotations

RHYTHM_TEMPLATES = [
    {"id": "beat_kardian", "name": "抖音卡点快剪", "desc": "0.8s 短镜卡点，BPM≥120 燃向音乐，适合变装/舞蹈/高燃混剪", "icon": "🔥", "bpm": 128, "shot": 0.8, "pattern": [1.0, 0.8, 0.8, 0.6, 0.8, 0.8, 1.2, 0.8]},
    {"id": "vlog_relax", "name": "Vlog 生活慢叙", "desc": "3~6s 长镜慢节奏，BGM 轻快，适合日常记录/旅行/美食", "icon": "🌿", "bpm": 92, "shot": 4.0, "pattern": [4.0, 3.5, 5.0, 3.0, 4.5, 3.0]},
    {"id": "film_cinema", "name": "电影感叙事", "desc": "5~8s 大景别慢镜 + 叠化转场，适合短剧/宣传片/情感向", "icon": "🎬", "bpm": 70, "shot": 6.0, "pattern": [6.0, 5.0, 8.0, 5.0, 6.0, 4.0, 7.0]},
    {"id": "game_esport", "name": "电竞高燃卡点", "desc": "0.4~1s 极速切镜 + 强瞬态音效，BPM≥140，适合游戏集锦", "icon": "🎮", "bpm": 144, "shot": 0.6, "pattern": [0.6, 0.4, 0.6, 0.8, 0.5, 0.4, 0.6, 0.8, 0.5, 1.0]},
    {"id": "story_bite", "name": "短剧钩子节奏", "desc": "开头 3s 强钩子 + 中段对话推进 + 结尾反转留白", "icon": "🎭", "bpm": 100, "shot": 2.5, "pattern": [3.0, 2.0, 2.5, 2.0, 2.5, 3.0, 2.0, 2.5, 3.5, 4.0]},
]


def template_dna(template: dict, duration: float) -> dict:
    shots = []
    cursor = 0.0
    index = 0
    while cursor < duration - 0.001:
        shot_duration = min(float(template["pattern"][index % len(template["pattern"])]), duration - cursor)
        shots.append({"start": round(cursor, 3), "end": round(cursor + shot_duration, 3), "duration": round(shot_duration, 3), "index": index})
        cursor += shot_duration
        index += 1
    return {
        "meta": {"duration": round(duration, 3), "total_shots": len(shots), "source_file": template["name"], "template_id": template["id"]},
        "shots": shots,
        "audio": {"tempo_bpm": template["bpm"]},
    }


def build_cut_plan(template: dict, target: dict, minimum_shot_duration: float = 0.25) -> dict:
    target_duration = float(target.get("meta", {}).get("duration") or 0.0)
    if target_duration <= 0:
        raise ValueError("目标视频时长无效")
    template_shots = sorted(template.get("shots") or [], key=lambda shot: float(shot.get("start", 0)))
    if not template_shots:
        raise ValueError("模板缺少镜头")
    template_duration = max(
        float(template.get("meta", {}).get("duration") or 0),
        float(template_shots[-1].get("end") or 0),
    )
    if template_duration <= 0:
        raise ValueError("模板时长无效")

    max_segments = max(1, int(target_duration / minimum_shot_duration))
    desired_boundaries = [
        max(0.0, min(1.0, float(shot.get("end", 0)) / template_duration))
        for shot in template_shots[:-1]
    ]
    if len(desired_boundaries) > max_segments - 1:
        step = len(desired_boundaries) / max(1, max_segments - 1)
        desired_boundaries = [desired_boundaries[min(len(desired_boundaries) - 1, int(index * step))] for index in range(max_segments - 1)]

    beats = sorted(float(beat) for beat in target.get("audio", {}).get("beats") or [])
    boundaries = [0.0]
    aligned_flags: list[bool] = []
    for ratio in desired_boundaries:
        raw = ratio * target_duration
        boundary = raw
        aligned = False
        if beats:
            nearest = min(beats, key=lambda beat: abs(beat - raw))
            if abs(nearest - raw) <= 0.45:
                boundary = nearest
                aligned = True
        lower = boundaries[-1] + minimum_shot_duration
        remaining = len(desired_boundaries) - len(aligned_flags)
        upper = target_duration - remaining * minimum_shot_duration
        boundary = min(max(boundary, lower), upper)
        if boundary <= boundaries[-1] or boundary >= target_duration:
            continue
        boundaries.append(boundary)
        aligned_flags.append(aligned)
    boundaries.append(target_duration)

    cuts = []
    for index, (start, end) in enumerate(zip(boundaries, boundaries[1:], strict=False)):
        if end - start < 0.001:
            continue
        cuts.append({
            "index": index,
            "start": round(start, 3),
            "end": round(end, 3),
            "duration": round(end - start, 3),
            "aligned_to_beat": aligned_flags[index] if index < len(aligned_flags) else False,
            "template_ratio": round(end / target_duration, 4),
        })
    return {
        "source": template.get("meta", {}).get("source_file") or "示例视频",
        "template_duration": round(template_duration, 3),
        "target_duration": round(target_duration, 3),
        "cuts": cuts,
        "total": len(cuts),
        "beat_aligned_count": sum(1 for cut in cuts if cut["aligned_to_beat"]),
    }
