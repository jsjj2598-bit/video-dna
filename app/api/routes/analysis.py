"""Video analysis submission and task progress endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from ...container import analysis, storage, tasks
from ...core.security import require_api_token
from ...services.storage import StorageError

router = APIRouter(prefix="/api", tags=["analysis"], dependencies=[Depends(require_api_token)])


def _validate_options(detector: str, backend: str) -> None:
    if detector not in {"content", "adaptive"}:
        raise HTTPException(status_code=400, detail="detector 只能是 content 或 adaptive")
    if backend not in {"auto", "openai", "qwen", "heuristic"}:
        raise HTTPException(status_code=400, detail="backend 只能是 auto / openai / qwen / heuristic")


@router.post("/analyze", status_code=202)
async def analyze_video(
    file: UploadFile = File(...),
    detector: str = "content",
    backend: str = "auto",
    openai_key: str | None = Form(None),
    qwen_key: str | None = Form(None),
    session_id: str | None = Form(None),
):
    _validate_options(detector, backend)
    source_name = file.filename or "video.mp4"
    try:
        session_id = storage.validate_session_id(session_id) if session_id else storage.new_session_id()
        video_path = await storage.save_upload(file, session_id)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    tasks.create(session_id, f"文件已上传：{source_name}")
    analysis.start(
        session_id=session_id,
        video_path=video_path,
        source_name=source_name,
        detector=detector,
        backend=backend,
        openai_key=openai_key,
        qwen_key=qwen_key,
    )
    return {"session_id": session_id, "status": "running"}


@router.post("/analyze/wait")
async def analyze_and_wait(
    file: UploadFile = File(...),
    detector: str = "content",
    backend: str = "auto",
    openai_key: str | None = Form(None),
    qwen_key: str | None = Form(None),
):
    _validate_options(detector, backend)
    session_id = storage.new_session_id()
    source_name = file.filename or "video.mp4"
    try:
        video_path = await storage.save_upload(file, session_id)
        tasks.create(session_id, f"文件已上传：{source_name}")
        return await analysis.run_and_wait(
            session_id=session_id,
            video_path=video_path,
            source_name=source_name,
            detector=detector,
            backend=backend,
            openai_key=openai_key,
            qwen_key=qwen_key,
        )
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"分析失败: {exc}") from exc


@router.get("/progress/{session_id}")
def get_progress(session_id: str):
    try:
        session_id = storage.validate_session_id(session_id)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    state = tasks.get(session_id)
    if state:
        return state
    if storage.read_result(session_id) is not None:
        return {"session_id": session_id, "stage": "done", "pct": 100, "logs": [], "error": None, "done": True}
    raise HTTPException(status_code=404, detail="任务不存在")


@router.get("/result/{session_id}")
def get_result(session_id: str):
    try:
        session_id = storage.validate_session_id(session_id)
        state = tasks.get(session_id)
        if state and state["stage"] == "error":
            raise HTTPException(status_code=422, detail=state.get("error") or "分析失败")
        result = storage.read_result(session_id)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="分析尚未完成或不存在")
    return result

