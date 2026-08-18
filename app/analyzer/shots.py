"""镜头边界检测（基于 PySceneDetect）。

P0 用 ContentDetector（对硬切稳定、可预测）；后续可换 TransNet V2
或加转场分类器来细分叠化/缩放转场等。
"""
from __future__ import annotations


def detect_shots(video_path: str, detector: str = "content", threshold: float = 27.0) -> list[dict]:
    from scenedetect import AdaptiveDetector, ContentDetector, detect

    if detector == "adaptive":
        det = AdaptiveDetector()
    else:
        det = ContentDetector(threshold=threshold)

    scenes = detect(str(video_path), det)
    shots: list[dict] = []
    for start, end in scenes:
        s = start.get_seconds()
        e = end.get_seconds()
        dur = e - s
        if dur <= 0:
            continue
        shots.append({
            "index": len(shots),
            "start": round(s, 3),
            "end": round(e, 3),
            "duration": round(dur, 3),
        })
    return shots
