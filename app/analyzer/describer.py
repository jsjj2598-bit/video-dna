"""多模态镜头描述（VLM）。支持 OpenAI GPT-4o / Qwen-VL API，内置 OpenCV 启发式降级。

对每个镜头的关键帧图片进行内容理解，输出：
- content: 自然语言场景描述
- camera_motion: 固定/摇镜/推拉/…… 
- shot_scale: 远景/全景/中景/近景/特写

API 需要环境变量 OPENAI_API_KEY 或 DASHSCOPE_API_KEY。
无 API Key 时使用 OpenCV 启发式分析（基本够用）。
"""
from __future__ import annotations

import os
import base64
from pathlib import Path

import cv2
import numpy as np


# ── 启发式降级（无需 API）────────────────────────────────────

def _estimate_brightness(bgr: np.ndarray) -> str:
    """粗略亮度估计。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    mean = gray.mean()
    if mean < 40:
        return "暗场"
    if mean < 80:
        return "较暗"
    if mean < 160:
        return "正常光"
    if mean < 200:
        return "明亮"
    return "过曝"


def _estimate_contrast(bgr: np.ndarray) -> str:
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    std = gray.std()
    if std < 20:
        return "低对比"
    if std < 50:
        return "中等对比"
    return "高对比"


def _estimate_shot_scale(bgr: np.ndarray) -> str:
    """通过人体/人脸检测启发式推断景别——降级版基于画面复杂度。"""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 边缘密度（Canny）
    edges = cv2.Canny(gray, 50, 150)
    edge_density = edges.sum() / (h * w)

    # 人脸检测（OpenCV Haar Cascades，能用的场合）
    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    faces = face_cascade.detectMultiScale(
        gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30)
    )

    if len(faces) > 0:
        biggest_face = max(f[2] for f in faces)
        face_ratio = biggest_face / w
        if face_ratio > 0.3:
            return "特写"
        if face_ratio > 0.15:
            return "近景"
        if face_ratio > 0.08:
            return "中景"
        return "全景"

    # 无脸时用边缘密度 + 亮度方差推断
    if edge_density < 0.02:
        return "远景" if _estimate_contrast(bgr) == "低对比" else "中景"
    if edge_density < 0.08:
        return "中景"
    if edge_density < 0.15:
        return "近景"
    return "特写"


def _estimate_camera_motion(bgr: np.ndarray, prev_bgr: np.ndarray | None) -> str:
    """通过帧间光流推算相机运动（仅在两帧都可用时）。"""
    if prev_bgr is None:
        return "固定"

    import cv2

    prev_gray = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

    # 缩小以加速
    scale = 0.25
    pw = int(prev_gray.shape[1] * scale)
    ph = int(prev_gray.shape[0] * scale)
    prev_small = cv2.resize(prev_gray, (pw, ph))
    curr_small = cv2.resize(curr_gray, (pw, ph))

    try:
        flow = cv2.calcOpticalFlowFarneback(
            prev_small, curr_small, None, 0.5, 3, 15, 3, 5, 1.2, 0
        )
        dx, dy = flow[..., 0].mean(), flow[..., 1].mean()
        magnitude = np.sqrt(dx**2 + dy**2)
        if magnitude < 0.5:
            return "固定"
        if magnitude < 2.0:
            return "轻微摇镜"
        if abs(dx) > abs(dy) * 2:
            return "水平摇镜" if dx > 0 else "水平摇镜"
        if abs(dy) > abs(dx) * 2:
            return "垂直摇镜" if dy > 0 else "垂直摇镜"
        return "推拉" if magnitude > 3.0 else "手持/轻微抖动"
    except Exception:
        return "固定"


def _build_prompt(sh_idx: int, bgr: np.ndarray, shot_info: dict) -> str:
    """构建发给 VLM 的 Prompt。"""
    return (
        "你是一个专业视频剪辑师和镜头分析师。请一眼描述这个镜头：\n"
        f"1. 画面内容（10字以内，如：「穿红色外套的女人在咖啡店看手机」「纯色转场画面」）\n"
        f"2. 景别（远景/全景/中景/近景/特写）\n"
        f"3. 相机运动（固定/摇镜/推拉/手持/抖动）\n"
        f"4. 冷暖色调/氛围关键词\n\n"
        f"请只返回 JSON 格式，字段：content, shot_scale, camera_motion, mood"
    )


def _call_openai(bgr: np.ndarray, prompt: str, model: str = "gpt-4o") -> dict | None:
    """调用 OpenAI GPT-4o Vision。"""
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        return None
    try:
        import httpx

        _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                            },
                        ],
                    }
                ],
                "max_tokens": 256,
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            text = resp.json()["choices"][0]["message"]["content"]
            try:
                import json
                return json.loads(text)
            except Exception:
                return {"content": text, "shot_scale": None, "camera_motion": None, "mood": None}
    except Exception:
        return None


def _call_qwen(bgr: np.ndarray, prompt: str, model: str = "qwen-vl-max") -> dict | None:
    """调用通义千问 VL API。"""
    key = os.environ.get("DASHSCOPE_API_KEY")
    if not key:
        return None
    try:
        import httpx
        import json

        _, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 85])
        b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

        resp = httpx.post(
            "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            },
            json={
                "model": model,
                "input": {
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {"text": prompt},
                                {"image": f"data:image/jpeg;base64,{b64}"},
                            ],
                        }
                    ]
                },
                "parameters": {"max_tokens": 256, "result_format": "message"},
            },
            timeout=30.0,
        )
        if resp.status_code == 200:
            output = resp.json()
            text = (
                output.get("output", {})
                .get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            try:
                return json.loads(text)
            except Exception:
                return {"content": text, "shot_scale": None, "camera_motion": None, "mood": None}
    except Exception:
        return None


def describe_shot(
    keyframe_path: str | Path,
    shot_index: int,
    shot_info: dict | None = None,
    prev_keyframe_path: str | Path | None = None,
    backend: str = "auto",
    model: str = "gpt-4o",
) -> dict:
    """对一个关键帧做语义描述。

    Args:
        keyframe_path: 关键帧图片路径
        shot_index: 镜头序号（仅用于 Prompt）
        shot_info: 镜头元信息（start/end/duration/transition）
        prev_keyframe_path: 前一镜头关键帧（用于运动检测）
        backend: auto → 先 OpenAI，再 Qwen，再 OpenCV 降级
        model: 使用的模型 ID

    Returns:
        {content, shot_scale, camera_motion, mood, method}
        method: "openai" / "qwen" / "heuristic"
    """
    bgr = cv2.imread(str(keyframe_path))
    if bgr is None:
        return {"content": None, "shot_scale": None, "camera_motion": None, "mood": None, "method": "error"}

    prev_bgr = None
    if prev_keyframe_path:
        prev_bgr = cv2.imread(str(prev_keyframe_path))

    prompt = _build_prompt(shot_index, bgr, shot_info or {})

    # API 尝试
    if backend in ("auto", "openai"):
        result = _call_openai(bgr, prompt, model=model)
        if result:
            result["method"] = "openai"
            # 补缺失字段
            result.setdefault("camera_motion", _estimate_camera_motion(bgr, prev_bgr))
            result.setdefault("shot_scale", _estimate_shot_scale(bgr))
            result.setdefault("mood", _estimate_brightness(bgr) + "·" + _estimate_contrast(bgr))
            return result

    if backend in ("auto", "qwen"):
        result = _call_qwen(bgr, prompt, model=model)
        if result:
            result["method"] = "qwen"
            result.setdefault("camera_motion", _estimate_camera_motion(bgr, prev_bgr))
            result.setdefault("shot_scale", _estimate_shot_scale(bgr))
            result.setdefault("mood", _estimate_brightness(bgr) + "·" + _estimate_contrast(bgr))
            return result

    # 降级：OpenCV 启发式
    shot_scale = _estimate_shot_scale(bgr)
    camera_motion = _estimate_camera_motion(bgr, prev_bgr)
    mood = f"{_estimate_brightness(bgr)}·{_estimate_contrast(bgr)}"

    # 用颜色直方图生成一句话描述
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    dominant_hue = int(np.median(hsv[..., 0]))
    dominant_sat = int(np.median(hsv[..., 1]))

    if dominant_sat < 30:
        hue_desc = "黑白/低饱和度画面"
    elif dominant_hue < 20 or dominant_hue > 160:
        hue_desc = "暖色调画面"
    elif 80 < dominant_hue < 140:
        hue_desc = "冷色调画面"
    else:
        hue_desc = "中性色调画面"

    if shot_info and shot_info.get("transition"):
        content = f"转场画面（{shot_info['transition']}）"
    else:
        content = f"{shot_scale}·{camera_motion}·{hue_desc}"

    return {
        "content": content,
        "shot_scale": shot_scale,
        "camera_motion": camera_motion,
        "mood": mood,
        "method": "heuristic",
    }


def describe_all(
    dna: dict,
    frames_dir: str | Path,
    backend: str = "auto",
    model: str = "gpt-4o",
) -> dict:
    """对 DNA 中所有镜头进行语义描述，就地更新 shots 字段。"""
    frames_dir = Path(frames_dir)
    shots = dna.get("shots", [])

    prev_kf = None
    for i, sh in enumerate(shots):
        kf = sh.get("keyframe")
        if not kf:
            continue
        kf_path = frames_dir / kf
        if not kf_path.exists():
            continue

        desc = describe_shot(
            kf_path, i, shot_info=sh, prev_keyframe_path=prev_kf,
            backend=backend, model=model,
        )
        sh["content"] = desc.get("content")
        sh["shot_scale"] = desc.get("shot_scale")
        sh["camera_motion"] = desc.get("camera_motion")
        sh["content_method"] = desc.get("method")

        prev_kf = kf_path

    return dna