"""History, keyframe, and source-video endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from ...container import storage, tasks
from ...core.security import require_api_token
from ...services.storage import StorageError

router = APIRouter(prefix="/api", tags=["media"], dependencies=[Depends(require_api_token)])

VIDEO_MIME = {
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
    ".webm": "video/webm", ".avi": "video/x-msvideo", ".m4v": "video/x-m4v",
    ".ts": "video/mp2t", ".flv": "video/x-flv", ".wmv": "video/x-ms-wmv",
}


def _video_chunk(path: Path, start: int, length: int, chunk_size: int = 1 << 16):
    with path.open("rb") as source:
        source.seek(start)
        remaining = length
        while remaining > 0:
            data = source.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


@router.get("/sessions/{session_id}/frames/{filename}")
def serve_session_frame(session_id: str, filename: str):
    try:
        frame_path = storage.safe_media_path(storage.session_dir(session_id) / "frames", filename)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not frame_path.is_file():
        raise HTTPException(status_code=404, detail="关键帧未找到")
    media_type = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".gif": "image/gif"}.get(frame_path.suffix.lower(), "image/jpeg")
    return FileResponse(frame_path, media_type=media_type)


@router.get("/sessions/{session_id}/video")
def serve_session_video(session_id: str, request: Request):
    try:
        video_path = storage.source_video(session_id)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if video_path is None:
        raise HTTPException(status_code=404, detail="源视频未找到")
    media_type = VIDEO_MIME.get(video_path.suffix.lower(), "application/octet-stream")
    size = video_path.stat().st_size
    range_header = request.headers.get("range", "")
    if range_header.lower().startswith("bytes="):
        try:
            start_text, end_text = range_header[6:].split("-", 1)
            start = int(start_text) if start_text.strip() else 0
            end = int(end_text) if end_text.strip() else size - 1
            end = min(end, size - 1)
            if start < 0 or start > end or start >= size:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            length = end - start + 1
            return StreamingResponse(
                _video_chunk(video_path, start, length),
                status_code=206,
                media_type=media_type,
                headers={"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes", "Content-Length": str(length)},
            )
        except (ValueError, IndexError):
            pass
    return FileResponse(video_path, media_type=media_type, headers={"Accept-Ranges": "bytes"})


@router.get("/history")
def list_history():
    return {"items": storage.list_history()}


@router.get("/history/{session_id}")
def get_history_detail(session_id: str):
    try:
        result = storage.read_result(session_id)
        video = storage.source_video(session_id)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="该记录不存在")
    result["_session_id"] = session_id
    result["_video_url"] = f"/api/sessions/{session_id}/video" if video else None
    result["_frame_base"] = f"/api/sessions/{session_id}/frames/"
    return result


@router.delete("/history")
def clear_history():
    active = tasks.active_session_ids()
    storage.clear_history(keep_session_ids=active)
    tasks.clear_completed()
    return {"ok": True}


@router.delete("/history/{session_id}")
def delete_history(session_id: str):
    if tasks.is_active(session_id):
        raise HTTPException(status_code=409, detail="任务正在运行，不能删除")
    try:
        removed = storage.delete_session(session_id)
    except StorageError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="该记录不存在")
    tasks.remove(session_id)
    return {"ok": True}
