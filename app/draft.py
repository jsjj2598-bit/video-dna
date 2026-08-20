"""剪映专业版（JianyingPro / CapCut 桌面版）草稿生成器。

把「剪辑方案」（源视频 + 剪切区间列表）生成一个完整的剪映草稿工程文件夹：
- {草稿文件夹}/draft_content.json   时间线（视频轨 + 音频轨片段）
- {草稿文件夹}/draft_meta_info.json 草稿元信息
- {草稿文件夹}/draft_cover.jpg      草稿封面
- {草稿文件夹}/{视频副本}            素材视频（保证草稿内包含视频）

剪映草稿即一个文件夹，直接把该文件夹复制到剪映草稿目录即可打开。
时间单位为微秒（µs），与剪映草稿格式一致。
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

DRAFT_VERSION = 1776001


def _uuid() -> str:
    return uuid.uuid4().hex


def _usec(seconds: float) -> int:
    return int(round(seconds * 1_000_000))


def build_draft_meta(name: str, draft_id: str | None = None) -> dict:
    import time

    now_ms = int(time.time() * 1000)
    return {
        "draft_id": draft_id or _uuid(),
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
    for raw_c in cuts:
        seg_id = _uuid()
        try:
            cs = max(0.0, float(raw_c.get("start") or 0.0))
            ce = max(0.0, float(raw_c.get("end") or 0.0))
        except (ValueError, TypeError, AttributeError):
            cs, ce = 0.0, 0.0
        if duration > 0:
            cs = min(cs, duration)
            ce = min(ce, duration)
        if ce <= cs:
            continue  # 跳过非法/空区间
        seg_dur = _usec(ce - cs)
        source_start = _usec(cs)
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


def _safe_name(name: str) -> str:
    return "".join(c for c in name if c not in '\\/:*?"<>|').strip() or "videodna"


def export_draft_folder(
    project_name: str,
    video_path: str,
    cuts: list[dict],
    probe_info: dict,
    out_dir: str | Path,
) -> str:
    """生成剪映工程文件夹（非 ZIP），返回草稿文件夹路径。

    结构：
      {out_dir}/{project_name}/
        draft_content.json    时间线
        draft_meta_info.json  元信息
        draft_cover.jpg       封面
        {media_name}          视频副本（草稿自带素材，可直接打开）
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    name = _safe_name(project_name or "video_dna_draft")
    draft_id = _uuid()
    draft_dir = out_dir / name
    draft_dir.mkdir(parents=True, exist_ok=True)

    # 1) 复制视频到草稿文件夹内（保证草稿自带视频，打开不会缺素材）
    src = Path(video_path)
    media_name = src.name
    media_dst = draft_dir / media_name
    if media_dst.resolve() != src.resolve():
        try:
            shutil.copy2(src, media_dst)
        except Exception:
            media_dst = src
            media_name = src.name
    media_path = str(media_dst.resolve()).replace("\\", "/")

    # 分辨率缺失时回退到 1920x1080（避免 None 崩溃）
    try:
        w_s, h_s = (probe_info.get("resolution") or "1920x1080").split("x")
        width = int(w_s or 1920)
        height = int(h_s or 1080)
    except (ValueError, TypeError, AttributeError):
        width, height = 1920, 1080

    content = build_draft_content(
        name=name,
        video_path=media_path,
        cuts=cuts,
        duration=float(probe_info.get("duration") or 0.0),
        width=width,
        height=height,
        fps=float(probe_info.get("fps") or 30.0),
    )
    meta = build_draft_meta(name, draft_id=draft_id)

    (draft_dir / "draft_content.json").write_text(
        json.dumps(content, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (draft_dir / "draft_meta_info.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 2) 生成封面（草稿列表中显示）
    try:
        from .analyzer import ffmpeg_utils

        cover_time = float(probe_info.get("duration") or 0.0) * 0.2
        ffmpeg_utils.extract_frame(str(media_dst), cover_time, str(draft_dir / "draft_cover.jpg"))
    except Exception:
        pass

    # 3) 说明文件
    (draft_dir / "使用说明.txt").write_text(
        (
            "【Video DNA Analyzer · 剪映草稿使用说明】\n"
            "\n"
            "1. 本文件夹就是一个完整的剪映草稿工程（内含视频素材）。\n"
            "2. 打开剪映专业版 → 右上角「设置」→「全局设置」→ 查看「草稿位置」。\n"
            "   默认位置（Windows）：\n"
            "   %LOCALAPPDATA%\\JianyingPro\\User Data\\Projects\\com.lveditor.draft\\\n"
            "3. 把整个「" + name + "」文件夹复制到上面的草稿位置。\n"
            "4. 重启剪映（或点击草稿列表的刷新按钮），即可看到并打开该草稿。\n"
            "\n"
            "提示：素材视频已内置于草稿文件夹中，无需额外链接。\n"
        ),
        encoding="utf-8",
    )

    return str(draft_dir)


def export_draft_zip(
    project_name: str,
    video_path: str,
    cuts: list[dict],
    probe_info: dict,
    out_path: str | Path,
) -> str:
    """生成剪映草稿 ZIP（含视频素材 + 草稿 JSON），返回 ZIP 路径。"""
    import tempfile
    import zipfile

    out_path = Path(out_path)
    name = _safe_name(project_name or "video_dna_draft")

    with tempfile.TemporaryDirectory(prefix="vdna_draft_") as tmp:
        folder = export_draft_folder(
            project_name=name,
            video_path=video_path,
            cuts=cuts,
            probe_info=probe_info,
            out_dir=tmp,
        )
        folder_path = Path(folder)
        with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in folder_path.rglob("*"):
                if f.is_file():
                    zf.write(f, f"{folder_path.name}/{f.relative_to(folder_path)}")
    return str(out_path)
