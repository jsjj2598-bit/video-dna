"""Filesystem persistence for uploads, results, history, and media."""

from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path

from fastapi import UploadFile

from ..core.config import Settings


class StorageError(ValueError):
    """Raised when a user-controlled storage operation is invalid."""


class StorageService:
    chunk_size = 1024 * 1024

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.uploads_dir = settings.uploads_dir

    @staticmethod
    def new_session_id() -> str:
        return uuid.uuid4().hex

    @staticmethod
    def validate_session_id(session_id: str) -> str:
        candidate = str(session_id or "").strip()
        if not candidate or not candidate.replace("-", "").isascii() or not candidate.replace("-", "").isalnum():
            raise StorageError("session_id 非法")
        return candidate

    def session_dir(self, session_id: str) -> Path:
        return self.uploads_dir / self.validate_session_id(session_id)

    async def save_upload(self, upload: UploadFile, session_id: str) -> Path:
        work_dir = self.session_dir(session_id)
        if (work_dir / "result.json").exists() or any(work_dir.glob("source.*")):
            raise StorageError("session_id 已存在，请使用新的会话 ID")
        work_dir.mkdir(parents=True, exist_ok=True)
        suffix = Path(upload.filename or "video.mp4").suffix.lower() or ".mp4"
        if suffix not in self.settings.allowed_video_suffixes:
            raise StorageError(f"不支持的视频格式: {suffix}")
        destination = work_dir / f"source{suffix}"
        total = 0
        try:
            with destination.open("wb") as target:
                while chunk := await upload.read(self.chunk_size):
                    total += len(chunk)
                    if total > self.settings.max_upload_bytes:
                        raise StorageError(f"视频超过上传上限 {self.settings.max_upload_bytes // 1024**2}MB")
                    target.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            if not any(work_dir.iterdir()):
                work_dir.rmdir()
            raise
        return destination

    def source_video(self, session_id: str) -> Path | None:
        work_dir = self.session_dir(session_id)
        return next((path for path in work_dir.glob("source.*") if path.is_file()), None)

    def save_result(self, session_id: str, result: dict, source_name: str) -> dict:
        work_dir = self.session_dir(session_id)
        payload = dict(result)
        payload["_session_id"] = session_id
        payload["_source_file"] = Path(source_name or "video").name
        payload["_video_url"] = f"/api/sessions/{session_id}/video"
        payload["_frame_base"] = f"/api/sessions/{session_id}/frames/"
        tmp = work_dir / "result.json.tmp"
        target = work_dir / "result.json"
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)
        return payload

    def read_result(self, session_id: str) -> dict | None:
        result_path = self.session_dir(session_id) / "result.json"
        if not result_path.exists():
            return None
        return json.loads(result_path.read_text(encoding="utf-8"))

    def safe_media_path(self, base: Path, filename: str) -> Path:
        resolved_base = base.resolve()
        candidate = (resolved_base / filename).resolve()
        if candidate == resolved_base or resolved_base not in candidate.parents:
            raise StorageError("非法文件路径")
        return candidate

    def list_history(self) -> list[dict]:
        items: list[dict] = []
        directories = sorted(
            (path for path in self.uploads_dir.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for directory in directories:
            result_path = directory / "result.json"
            if not result_path.exists():
                continue
            try:
                result = json.loads(result_path.read_text(encoding="utf-8"))
                meta = result.get("meta", {})
                items.append({
                    "session_id": directory.name,
                    "name": result.get("_source_file") or meta.get("source_file") or f"分析 {directory.name[:8]}",
                    "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(directory.stat().st_mtime)),
                    "total_shots": meta.get("total_shots", 0),
                    "duration": meta.get("duration", 0),
                    "bpm": result.get("audio", {}).get("tempo_bpm"),
                    "summary": result.get("summary", ""),
                    "has_video": self.source_video(directory.name) is not None,
                    "shot_count": len(result.get("shots", [])),
                })
            except (OSError, ValueError, json.JSONDecodeError):
                continue
        return items

    def delete_session(self, session_id: str) -> bool:
        directory = self.session_dir(session_id)
        if not directory.exists():
            return False
        shutil.rmtree(directory)
        return True

    def clear_history(self, keep_session_ids: set[str] | None = None) -> None:
        keep_session_ids = keep_session_ids or set()
        for directory in self.uploads_dir.iterdir():
            if directory.is_dir() and directory.name not in keep_session_ids:
                shutil.rmtree(directory)

    def cleanup_history(self, keep_session_id: str | None = None) -> list[str]:
        directories = [path for path in self.uploads_dir.iterdir() if path.is_dir()]
        sizes = {path: self._directory_size(path) for path in directories}
        total = sum(sizes.values())
        if total <= self.settings.max_history_bytes:
            return []
        keep = self.session_dir(keep_session_id).resolve() if keep_session_id else None
        removed: list[str] = []
        for directory in sorted(directories, key=lambda path: path.stat().st_mtime):
            if keep is not None and directory.resolve() == keep:
                continue
            size = sizes[directory]
            shutil.rmtree(directory)
            total -= size
            removed.append(directory.name)
            if total <= self.settings.max_history_bytes:
                break
        return removed

    @staticmethod
    def _directory_size(directory: Path) -> int:
        return sum(path.stat().st_size for path in directory.rglob("*") if path.is_file())
