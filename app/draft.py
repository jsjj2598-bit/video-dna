"""剪映专业版（JianyingPro / CapCut 桌面版）草稿生成器。

把「剪辑方案」（源视频 + 剪切区间列表）打包为一个可在剪映中打开的草稿：
- draft_content.json：时间线（视频轨 + 音频轨片段）
- draft_meta_info.json：草稿元信息
- 使用说明.txt：草稿安装到本机剪映草稿文件夹的方法

时间单位为微秒（µs），与剪映草稿格式一致。
"""
from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

DRAFT_VERSION = 1776001


def _uuid() -> str:
    return uuid.uuid4().hex


def _usec(seconds: float) -> int:
    return int(round(seconds * 1_000_000))


def build_draft_meta(name: str) -> dict:
    import time

    now_ms = int(time.time() * 1000)
    return {
        "draft_id": _uuid(),
        "draft_name": name,
        "tm_draft_modified": now_ms,
        "tm_draft_create": now_ms,
        "draft_root_path": f"JianyingPro Drafts/{name}",
        "tm_draft_removed": False,
        "draft_removed_storage": False,
        "tm_draft_type": "NEW_DRAFT",
        "draft_fold_path": "",
    }


def build_draft_content(
    name: str,
    video_path: str,
    cuts: list[dict],
    duration: float,
    width: int,
    height: int,
    fps: float,
) -> dict:
    """cuts: [{"start": 0.0, "end": 3.2}, ...] 秒。"""
    path = str(Path(video_path).resolve()).replace("\\", "/")
    media_name = Path(video_path).name

    video_material_id = _uuid()
    audio_material_id = _uuid()
    track_id = _uuid()
    audio_track_id = _uuid()

    video_dur = _usec(duration)

    segments = []
    audio_segments = []
    cursor = 0
    for c in cuts:
        seg_id = _uuid()
        seg_dur = _usec(max(c["end"] - c["start"], 0.01))
        source_start = _usec(c["start"])
        base = {
            "id": seg_id,
            "target_timeline": {"duration": seg_dur, "start": cursor, "speed": 1},
            "source_timeline": {"duration": seg_dur, "start": source_start, "speed": 1},
            "keyframes": [],
            "extra_material_refs": [],
            "is_scale_in_range": False,
            "is_overlap": False,
        }
        segments.append({
            **base,
            "material_id": video_material_id,
            "transform": {"x": 0, "y": 0, "scale": 1, "rotation": 0},
            "color_adjust": {
                "brightness": 0, "contrast": 0, "saturation": 0,
                "highlight": 0, "shadow": 0, "temperature": 0, "vignette": 0,
            },
            "animation": {"inner_type": None},
            "smart_remove_mask": {"is_remove_mask": False},
            "original_rot_angle": 0,
            "speed_duration": seg_dur,
            "speed_curve_keyframes": [],
            "smart_retime_scope_segment_ids": [],
        })
        audio_segments.append({
            **base,
            "material_id": audio_material_id,
            "render_index": -1,
            "audio_fade": {
                "inner_type": "None", "start_fade": "None", "end_fade": "None",
                "start_fade_time": 0, "end_fade_time": 0,
            },
            "adjustments": [],
            "track_attribute": 0,
        })
        cursor += seg_dur

    total_dur = cursor

    return {
        "duration": total_dur,
        "version": DRAFT_VERSION,
        "fps": max(int(round(fps or 30)), 1),
        "canvas_config": {
            "ratio": "original",
            "width": width or 1920,
            "height": height or 1080,
            "color": "#000000",
        },
        "name": name,
        "materials": {
            "videos": [
                {
                    "id": video_material_id,
                    "path": path,
                    "material_name": media_name,
                    "duration": video_dur,
                    "width": width or 1920,
                    "height": height or 1080,
                    "type": "video",
                    "material_audio": {
                        "id": audio_material_id,
                        "path": path,
                        "type": "audio",
                        "duration": video_dur,
                        "material_name": media_name,
                        "source": "video",
                    },
                    "rotate": 0,
                    "rate": 1,
                    "cover": "",
                    "standard_mode": "video",
                }
            ],
            "audio_materials": [],
            "texts": [],
            "stickers": [],
            "effects": [],
            "transitions": [],
            "adjustments": [],
            "audio_effects": [],
            "bubbles": [],
            "text_templates": [],
            "meme_materials": [],
            "video_effects": [],
            "filter_effects": [],
            "animation_effects": [],
            "emotion_effects": [],
            "auto_captions": [],
            "chat_groups": [],
            "highlight_moments": [],
            "materials": [],
            "plists": [],
        },
        "tracks": [
            {
                "id": track_id,
                "type": "video",
                "segments": segments,
                "is_default_name": True,
                "attribute": 0,
                "common_attrs": {"canvas_config": {"use_default": True}},
            },
            {
                "id": audio_track_id,
                "type": "audio",
                "segments": audio_segments,
                "is_default_name": True,
                "attribute": 0,
                "common_attrs": {"canvas_config": {"use_default": True}},
            },
        ],
        "keyframes": [],
        "speed_curve_refs": {},
        "subtitle_tracks": [],
        "stats": {
            "storyboard": {
                "video_duration": total_dur,
                "video_frame_count": int(total_dur / 1e6 * (fps or 30)),
                "video_count": len(segments),
                "effect_video_count": 0,
                "mark_count": 0,
                "speed_point_count": 0,
            }
        },
        "configs": {},
        "attachments": [],
    }


def export_draft_zip(
    project_name: str,
    video_path: str,
    cuts: list[dict],
    probe_info: dict,
    out_path: str | Path,
) -> str:
    """生成剪映草稿 ZIP（含两个草稿 JSON + 说明），返回 ZIP 路径。"""
    out_path = Path(out_path)
    name = project_name or "video_dna_draft"

    content = build_draft_content(
        name=name,
        video_path=video_path,
        cuts=cuts,
        duration=float(probe_info.get("duration") or 0.0),
        width=int(probe_info.get("resolution", "0x0").split("x")[0] or 0),
        height=int(probe_info.get("resolution", "0x0").split("x")[1] or 0),
        fps=float(probe_info.get("fps") or 30.0),
    )
    meta = build_draft_meta(name)

    instructions = (
        "【Video DNA Analyzer · 剪映草稿安装说明】\n"
        "\n"
        "1. 解压本压缩包，得到一个文件夹：draft（即你的剪映草稿）。\n"
        "2. 打开剪映专业版 → 右上角「设置」→「全局设置」→ 查看「草稿位置」。\n"
        "   默认位置（Windows）：\n"
        "   %LOCALAPPDATA%\\JianyingPro\\User Data\\Projects\\com.lveditor.draft\\\n"
        "3. 把解压出来的文件夹复制到上面的草稿位置。\n"
        "4. 重启剪映（或点击草稿列表的刷新按钮），即可看到并打开该草稿。\n"
        "\n"
        "提示：草稿引用的视频文件为：\n"
        + str(Path(video_path).resolve())
        + "\n请保持该文件存在。若视频被移动，可在剪映中重新链接素材。\n"
    )

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("draft/draft_content.json", json.dumps(content, ensure_ascii=False, indent=2))
        zf.writestr("draft/draft_meta_info.json", json.dumps(meta, ensure_ascii=False, indent=2))
        zf.writestr("draft/使用说明.txt", instructions)
    return str(out_path)
