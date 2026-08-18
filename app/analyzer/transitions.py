"""转场类型识别（基于 OpenCV 帧跳转的分类器，不依赖 ffmpeg -ss）。

对每个镜头边界，用 OpenCV VideoCapture 按帧号跳转到边界附近，
顺序读取一个时间窗的帧，分析：
- 亮度序列 → 识别闪白（接近纯白）/ 淡入淡出（经过黑场）
- 帧间 BGR 颜色差异分布 → 区分硬切（单帧跳变）与叠化（多帧渐变）

使用 BGR 差异而非灰度差异，确保色相不同的等亮度颜色也能可靠检测。
"""
from __future__ import annotations

import cv2
import numpy as np


def _open_video(video_path: str):
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {video_path}")
    return cap


def _read_frames(cap, start_frame: int, count: int, max_width: int = 320):
    """从 start_frame 开始读取 count 帧 BGR，缩放到 max_width，返回 float32 列表。"""
    cap.set(cv2.CAP_PROP_POS_FRAMES, max(0, start_frame))
    frames = []
    for _ in range(count):
        ok, bgr = cap.read()
        if not ok:
            break
        h, w = bgr.shape[:2]
        if w > max_width:
            scale = max_width / w
            new_w = max_width
            new_h = int(h * scale)
            bgr = cv2.resize(bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        frames.append(bgr.astype(np.float32))
    return frames


def _mean_brightness(bgr_frame: np.ndarray) -> float:
    """从 BGR 帧计算亮度（加权灰度）的均值。"""
    gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
    return float(gray.mean())


def _color_diff(prev: np.ndarray, curr: np.ndarray) -> float:
    """BGR 三通道逐像素绝对差均值（颜色差异，不仅限于亮度）。"""
    return float(cv2.absdiff(prev, curr).mean())


def classify_boundary(video_path: str, boundary_sec: float, fps: float = 30.0,
                      window_frames: int = 24) -> tuple[str, float]:
    cap = _open_video(video_path)
    try:
        src_fps = cap.get(cv2.CAP_PROP_FPS)
        if src_fps > 0:
            fps = src_fps

        boundary_frame = int(round(boundary_sec * fps))
        half_win = window_frames // 2
        start_frame = max(0, boundary_frame - half_win)

        frames = _read_frames(cap, start_frame, window_frames)
        if len(frames) < 3:
            return "unknown", 0.0

        # 亮度序列（用于检测闪白/淡入淡出）
        lums = [_mean_brightness(f) for f in frames]

        # BGR 颜色帧间差异序列
        diffs = [_color_diff(frames[i - 1], frames[i]) for i in range(1, len(frames))]

        lum_min, lum_max = min(lums), max(lums)
        lum_avg = float(np.mean(lums))

        # 闪白：窗口内出现接近纯白的帧
        if lum_max > 240 and lum_avg > 100:
            return "white_flash", 0.9

        # 淡入/淡出：经过黑场（且窗口并非全黑）
        if lum_min < 20 and lum_max > 60:
            return "fade", 0.85

        if not diffs:
            return "unknown", 0.0
        total = float(sum(diffs))
        if total < 3.0:   # BGR 差异阈值比灰度高（3 通道）
            return "unknown", 0.0

        concentration = max(diffs) / total
        if concentration > 0.45:   # BGR 差异分布偏窄，阈值略降
            return "cut", round(min(concentration, 1.0), 3)
        return "dissolve", round(1.0 - concentration, 3)
    finally:
        cap.release()


def classify_transitions(video_path: str, shots: list[dict], work_dir: str | None = None,
                         fps: float = 30.0) -> list:
    """返回与 shots 对齐的列表：元素 i 为镜头 i 的入点转场；shots[0] 恒为 None。"""
    del work_dir  # 不再需要临时目录
    result: list = [None]
    for i in range(1, len(shots)):
        t = shots[i]["start"]
        try:
            kind, conf = classify_boundary(video_path, t, fps=fps)
        except Exception:
            kind, conf = "unknown", 0.0
        result.append({"type": kind, "confidence": conf})
    return result