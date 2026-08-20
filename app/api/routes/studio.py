"""Template application, draft export, storyboard, and BGM helpers."""

from __future__ import annotations

import json
import re
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ... import draft as draft_export
from ... import registry
from ...analyzer import ffmpeg_utils
from ...container import analysis, settings, storage, tasks
from ...core.security import require_api_token
from ...services.storage import StorageError
from ...services.templates import RHYTHM_TEMPLATES, build_cut_plan, template_dna
from .analysis import _validate_options

router = APIRouter(prefix="/api", tags=["studio"], dependencies=[Depends(require_api_token)])


async def _analyze_template_target(file: UploadFile, detector: str, backend: str) -> tuple[str, dict]:
    _validate_options(detector, backend)
    session_id = storage.new_session_id()
    source_name = file.filename or "video.mp4"
    try:
        video_path = await storage.save_upload(file, session_id)
        tasks.create(session_id, f"文件已上传：{source_name}")
        result = await analysis.run_and_wait(
            session_id=session_id,
            video_path=video_path,
            source_name=source_name,
            detector=detector,
            backend=backend,
        )
        return session_id, result
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"分析失败: {exc}") from exc


@router.post("/template/apply")
async def apply_template(
    file: UploadFile = File(...),
    template: str = Form(...),
    detector: str = "content",
    backend: str = "auto",
):
    try:
        template_data = json.loads(template)
        if not isinstance(template_data, dict) or not template_data.get("shots"):
            raise ValueError("模板数据无效")
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"模板 JSON 无效: {exc}") from exc
    session_id, result = await _analyze_template_target(file, detector, backend)
    try:
        cut_plan = build_cut_plan(template_data, result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["_cut_plan"] = cut_plan
    result = storage.save_result(session_id, result, result.get("_source_file", file.filename or "video.mp4"))
    return {"analysis": result, "cut_plan": cut_plan}


@router.post("/ai/apply")
async def apply_ai_template(
    file: UploadFile = File(...),
    template: str = Form(...),
    detector: str = "content",
    backend: str = "auto",
):
    selected = next((item for item in RHYTHM_TEMPLATES if item["id"] == template), None)
    if selected is None:
        raise HTTPException(status_code=400, detail=f"模板不存在: {template}")
    session_id, result = await _analyze_template_target(file, detector, backend)
    duration = float(result.get("meta", {}).get("duration") or 0)
    try:
        cut_plan = build_cut_plan(template_dna(selected, duration), result)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["_cut_plan"] = cut_plan
    result = storage.save_result(session_id, result, result.get("_source_file", file.filename or "video.mp4"))
    return {"analysis": result, "cut_plan": cut_plan, "template": selected}


@router.post("/draft/export")
async def export_draft(body: dict):
    session_id = str(body.get("session_id") or "").strip()
    if not session_id:
        raise HTTPException(status_code=400, detail="缺少 session_id")
    try:
        source_video = storage.source_video(session_id)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if source_video is None:
        raise HTTPException(status_code=404, detail="源视频不存在")
    cuts = body.get("cuts") or []
    if not isinstance(cuts, list) or not cuts:
        raise HTTPException(status_code=400, detail="缺少剪辑区间")
    probe_info = ffmpeg_utils.probe(str(source_video))
    duration = float(probe_info.get("duration") or 0)
    if duration <= 0:
        raise HTTPException(status_code=422, detail="无法读取源视频元信息")
    for cut in cuts:
        try:
            start, end = float(cut["start"]), float(cut["end"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="剪辑区间格式错误") from exc
        if not 0 <= start < end <= duration + 0.001:
            raise HTTPException(status_code=400, detail=f"剪辑区间越界: {start}-{end}")
    output_dir = Path(str(body.get("download_dir") or settings.downloads_dir / "drafts")).expanduser()
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        folder = draft_export.export_draft_folder(
            project_name=str(body.get("project_name") or "VideoDNA剪辑方案"),
            video_path=str(source_video),
            cuts=cuts,
            probe_info=probe_info,
            out_dir=output_dir,
        )
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"草稿目录不可写: {exc}") from exc
    return {"path": folder, "download_dir": str(output_dir)}


@router.get("/ai/templates")
def list_ai_templates():
    return {"templates": RHYTHM_TEMPLATES}


@router.post("/ai/storyboard")
async def create_storyboard(body: dict):
    topic = str(body.get("topic") or "").strip()
    try:
        length = max(3, min(int(body.get("length") or 6), 20))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="镜头数量格式错误") from exc
    if not topic:
        raise HTTPException(status_code=400, detail="请输入主题或文案")
    chat = registry.get_enabled_chat_model()
    if chat is None:
        scenes = ["开场钩子：快速吸引注意力", "主体推进：展示核心内容", "情绪强化：特写/慢镜", "高潮：节奏加快", "结尾：留白与引导"]
        cameras = ["中景固定", "推近", "侧移跟拍", "特写", "拉远"]
        shots = [{"index": index, "duration": 3.0, "scene": scenes[index % len(scenes)], "camera": cameras[index % len(cameras)], "voiceover": ""} for index in range(length)]
        return {"method": "heuristic", "topic": topic, "shots": shots, "hint": "未配置对话模型，已生成基础框架。"}
    prompt = (
        f"你是短视频分镜脚本导演。为主题「{topic}」创作 {length} 个镜头的分镜脚本，输出 JSON 数组。"
        "每项包含 scene、camera、duration、voiceover、transition。只输出 JSON。"
    )
    try:
        output = registry.chat_complete(chat, [{"role": "system", "content": "你是专业分镜脚本导演，只输出 JSON。"}, {"role": "user", "content": prompt}])
        match = re.search(r"\[.*\]", output, re.S)
        if not match:
            raise ValueError("模型未返回分镜数组")
        return {"method": "llm", "model": chat["model"], "topic": topic, "shots": json.loads(match.group(0))}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"分镜生成失败: {exc}") from exc


@router.post("/ai/bgm")
async def recommend_bgm(body: dict):
    dna = body.get("dna") if isinstance(body, dict) else None
    if not dna and isinstance(body, dict) and body.get("session_id"):
        try:
            dna = storage.read_result(str(body["session_id"]))
        except StorageError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not dna:
        raise HTTPException(status_code=400, detail="请提供 dna 或 session_id")
    bpm = float(dna.get("audio", {}).get("tempo_bpm") or 0)
    average = float(dna.get("meta", {}).get("avg_shot_duration") or 0)
    if bpm <= 0:
        raise HTTPException(status_code=400, detail="未检测到 BPM，无法推荐")
    if bpm >= 120:
        mood, genres = "高燃/活力", ["EDM", "Trap", "电子舞曲", "Bounce"]
    elif bpm >= 90:
        mood, genres = "轻快/向上", ["流行", "Future Bass", "Pop 电子", "轻摇滚"]
    elif bpm >= 60:
        mood, genres = "舒缓/叙事", ["钢琴抒情", "Lo-fi", "氛围电子", "民谣"]
    else:
        mood, genres = "低沉/悬疑", ["暗黑氛围", "Drone", "悬疑配乐", "低频垫乐"]
    return {
        "bpm": bpm,
        "mood": mood,
        "recommend": genres,
        "hint": f"镜头平均 {average:.1f}s，建议切点对齐 BPM 节拍（每拍 {60 / bpm:.2f}s）",
        "search_hint": f"在剪映/BGM 平台搜索关键词：{'、'.join(genres)}",
    }

