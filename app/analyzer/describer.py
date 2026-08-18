"""多模态镜头描述（VLM）。支持 OpenAI GPT-4o / Qwen-VL API，内置 OpenCV 启发式降级 + AI短剧/漫剧优化。

对每个镜头的关键帧进行深度分析，输出：
- content, shot_scale, camera_motion, mood, method
- scene_type: dialogue / action / establishing / closeup / emotional / transition
- face_count: 人脸数量
- color_tone: warm / cool / neutral
- emotion: 情绪标签

API 需要环境变量 OPENAI_API_KEY 或 DASHSCOPE_API_KEY。
无 API Key 时使用 OpenCV 启发式分析（含人脸检测 + 色调分析 + 场景分类）。
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
    """通过人脸检测 + 边缘密度推断景别。"""
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = edges.sum() / (h * w)

    faces = _get_face_cascade().detectMultiScale(
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

    if edge_density < 0.02:
        return "远景" if _estimate_contrast(bgr) == "低对比" else "中景"
    if edge_density < 0.08:
        return "中景"
    if edge_density < 0.15:
        return "近景"
    return "特写"


def _estimate_camera_motion(bgr: np.ndarray, prev_bgr: np.ndarray | None) -> str:
    """通过帧间光流推算相机运动。"""
    if prev_bgr is None:
        return "固定"

    prev_gray = cv2.cvtColor(prev_bgr, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)

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
            return "水平摇镜"
        if abs(dy) > abs(dx) * 2:
            return "垂直摇镜"
        return "推拉" if magnitude > 3.0 else "手持/轻微抖动"
    except Exception:
        return "固定"


# ── AI 短剧/漫剧 优化函数 ────────────────────────────────

_face_cascade = None


def _get_face_cascade():
    """懒加载人脸检测器。"""
    global _face_cascade
    if _face_cascade is None:
        _face_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
    return _face_cascade


def _count_faces(bgr: np.ndarray) -> int:
    """检测画面中的人脸数量。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    faces = _get_face_cascade().detectMultiScale(
        gray, scaleFactor=1.15, minNeighbors=4, minSize=(40, 40)
    )
    return len(faces)


def _estimate_color_tone(bgr: np.ndarray) -> str:
    """分析冷暖色调：warm / cool / neutral + 描述。"""
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    hues = hsv[..., 0].astype(np.float32)
    sats = hsv[..., 1].astype(np.float32)

    # 排除低饱和度像素（黑白）
    mask = sats > 30
    if mask.sum() < bgr.size * 0.02:  # 几乎无彩色
        return "黑白"

    dominant_hue = int(np.median(hues[mask]))
    if dominant_hue < 20 or dominant_hue > 160:
        return "暖色调"
    if 80 < dominant_hue < 140:
        return "冷色调"
    return "中性色调"


def _classify_scene_type(
    bgr: np.ndarray,
    face_count: int,
    shot_scale: str,
    motion: str,
) -> str:
    """镜头类型分类：dialogue / action / establishing / closeup / emotional / transition。

    短剧/漫剧专用的场景分类。
    """
    h, w = bgr.shape[:2]
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 50, 150)
    edge_density = edges.sum() / (h * w)

    # 过渡画面（纯色/极低边缘）
    if edge_density < 0.005:
        return "transition"

    # 特写
    if shot_scale == "特写":
        return "closeup"

    # 对话：≥2 张人脸，或 1 张中景人脸
    if face_count >= 2:
        return "dialogue"
    if face_count == 1 and shot_scale in ("中景", "近景", "全景"):
        return "dialogue"

    # 动作：高边缘密度 + 推拉/手持相机
    if edge_density > 0.12 and motion in ("推拉", "手持/轻微抖动", "水平摇镜", "垂直摇镜"):
        return "action"

    # 全景/远景 → 交代镜头
    if shot_scale in ("远景", "全景"):
        return "establishing"

    # 高对比 + 面部/近景 → 情绪镜头
    if shot_scale in ("近景", "特写") and _estimate_contrast(bgr) in ("高对比", "中等对比"):
        return "emotional"

    return "dialogue"  # fallback


def _analyze_emotion(bgr: np.ndarray) -> str:
    """基于亮度 + 色调 + 对比度分析情绪：positive / negative / neutral / tense。"""
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
    brightness = gray.mean()
    contrast = gray.std()
    tone = _estimate_color_tone(bgr)

    if brightness < 50:
        return "阴暗/紧张" if contrast > 40 else "压抑/忧郁"
    if brightness > 180:
        return "明朗/轻快" if tone == "暖色调" else "明亮/冷静"
    if contrast > 60:
        return "强烈/戏剧性" if tone == "冷色调" else "明快/生动"
    if tone == "暖色调":
        return "温暖/柔和"
    if tone == "冷色调":
        return "冷静/忧郁"

    return "平静/中性"


# ── 原 Prompt / API 函数 ─────────────────────────────

def _build_prompt(sh_idx: int, bgr: np.ndarray, shot_info: dict) -> str:
    """构建发给 VLM 的 Prompt（含短剧/漫剧分类）。"""
    return (
        "你是一个专业视频剪辑师和镜头分析师。请一眼描述这个镜头：\n"
        f"1. 画面内容（10字以内，如：「穿红色外套的女人在咖啡店看手机」「纯色转场画面」）\n"
        f"2. 景别（远景/全景/中景/近景/特写）\n"
        f"3. 相机运动（固定/摇镜/推拉/手持/抖动）\n"
        f"4. 冷暖色调/氛围关键词\n"
        f"5. 镜头类型（dialogue对话/action动作/establishing交代/closeup特写/emotional情绪/transition过渡）\n"
        f"6. 画面中有几张人脸\n\n"
        f"请只返回 JSON 格式，字段：content, shot_scale, camera_motion, mood, scene_type, face_count"
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
                return {"content": text, "shot_scale": None, "camera_motion": None, "mood": None, "scene_type": None, "face_count": None}
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
                return {"content": text, "shot_scale": None, "camera_motion": None, "mood": None, "scene_type": None, "face_count": None}
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
    """对一个关键帧做深度语义描述（含 AI 短剧/漫剧优化字段）。

    Returns:
        {content, shot_scale, camera_motion, mood, method,
         scene_type, face_count, color_tone, emotion}
    """
    bgr = cv2.imread(str(keyframe_path))
    if bgr is None:
        return {
            "content": None, "shot_scale": None, "camera_motion": None,
            "mood": None, "method": "error",
            "scene_type": None, "face_count": 0, "color_tone": None, "emotion": None,
        }

    prev_bgr = None
    if prev_keyframe_path:
        prev_bgr = cv2.imread(str(prev_keyframe_path))

    prompt = _build_prompt(shot_index, bgr, shot_info or {})

    # — API 尝试 —
    if backend in ("auto", "openai"):
        result = _call_openai(bgr, prompt, model=model)
        if result:
            result["method"] = "openai"
            result.setdefault("camera_motion", _estimate_camera_motion(bgr, prev_bgr))
            result.setdefault("shot_scale", _estimate_shot_scale(bgr))
            result.setdefault("mood", _estimate_brightness(bgr) + "·" + _estimate_contrast(bgr))
            result.setdefault("scene_type", _classify_scene_type(bgr, _count_faces(bgr), result.get("shot_scale", "中景"), result.get("camera_motion", "固定")))
            result.setdefault("face_count", _count_faces(bgr))
            result.setdefault("color_tone", _estimate_color_tone(bgr))
            result.setdefault("emotion", _analyze_emotion(bgr))
            return result

    if backend in ("auto", "qwen"):
        result = _call_qwen(bgr, prompt, model=model)
        if result:
            result["method"] = "qwen"
            result.setdefault("camera_motion", _estimate_camera_motion(bgr, prev_bgr))
            result.setdefault("shot_scale", _estimate_shot_scale(bgr))
            result.setdefault("mood", _estimate_brightness(bgr) + "·" + _estimate_contrast(bgr))
            result.setdefault("scene_type", _classify_scene_type(bgr, _count_faces(bgr), result.get("shot_scale", "中景"), result.get("camera_motion", "固定")))
            result.setdefault("face_count", _count_faces(bgr))
            result.setdefault("color_tone", _estimate_color_tone(bgr))
            result.setdefault("emotion", _analyze_emotion(bgr))
            return result

    # — 降级：OpenCV 启发式（全面） —
    shot_scale = _estimate_shot_scale(bgr)
    camera_motion = _estimate_camera_motion(bgr, prev_bgr)
    face_count = _count_faces(bgr)
    color_tone = _estimate_color_tone(bgr)
    scene_type = _classify_scene_type(bgr, face_count, shot_scale, camera_motion)
    emotion = _analyze_emotion(bgr)
    mood = f"{_estimate_brightness(bgr)}·{_estimate_contrast(bgr)}"

    # 转场画面优先
    if shot_info and shot_info.get("transition"):
        content = f"转场画面（{shot_info['transition']}）"
    else:
        # 构建语义标签：场景类型·景别·色调·运动
        content = f"{scene_type}·{shot_scale}·{color_tone}·{camera_motion}"
        if face_count > 0:
            content += f"·{face_count}人脸"

    return {
        "content": content,
        "shot_scale": shot_scale,
        "camera_motion": camera_motion,
        "mood": mood,
        "method": "heuristic",
        "scene_type": scene_type,
        "face_count": face_count,
        "color_tone": color_tone,
        "emotion": emotion,
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
        sh["scene_type"] = desc.get("scene_type")
        sh["face_count"] = desc.get("face_count")
        sh["color_tone"] = desc.get("color_tone")
        sh["emotion"] = desc.get("emotion")

        prev_kf = kf_path

    return dna