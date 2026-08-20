"""Analysis orchestration independent from HTTP request handling."""

from __future__ import annotations

import asyncio
import threading
from pathlib import Path

from ..analyzer import pipeline
from .storage import StorageService
from .tasks import TaskStore


class AnalysisService:
    def __init__(self, storage: StorageService, tasks: TaskStore) -> None:
        self.storage = storage
        self.tasks = tasks

    def start(
        self,
        *,
        session_id: str,
        video_path: Path,
        source_name: str,
        detector: str,
        backend: str,
        openai_key: str | None = None,
        qwen_key: str | None = None,
    ) -> None:
        worker = threading.Thread(
            target=self._run_and_persist,
            kwargs={
                "session_id": session_id,
                "video_path": video_path,
                "source_name": source_name,
                "detector": detector,
                "backend": backend,
                "openai_key": openai_key,
                "qwen_key": qwen_key,
            },
            daemon=True,
            name=f"video-dna-{session_id[:8]}",
        )
        worker.start()

    async def run_and_wait(self, **kwargs) -> dict:
        return await asyncio.to_thread(self._run_and_persist, **kwargs)

    def analyze_video(
        self,
        *,
        session_id: str,
        video_path: Path,
        detector: str,
        backend: str,
        openai_key: str | None = None,
        qwen_key: str | None = None,
    ) -> dict:
        def report(stage: str, pct: int, message: str) -> None:
            # The pipeline reports "done" before the result is persisted. Keep
            # clients waiting until the atomic result write has completed.
            if stage == "done":
                self.tasks.report(session_id, "finalizing", 99, "分析完成，正在保存结果")
            else:
                self.tasks.report(session_id, stage, pct, message)

        return pipeline.analyze(
            str(video_path),
            work_dir=str(self.storage.session_dir(session_id)),
            extract_keyframes=True,
            detector=detector,
            detect_transitions=True,
            describe_shots=True,
            vlm_backend=backend,
            openai_key=openai_key,
            qwen_key=qwen_key,
            keep_workdir=True,
            progress_cb=report,
        )

    def _run_and_persist(
        self,
        *,
        session_id: str,
        video_path: Path,
        source_name: str,
        detector: str,
        backend: str,
        openai_key: str | None = None,
        qwen_key: str | None = None,
    ) -> dict:
        try:
            result = self.analyze_video(
                session_id=session_id,
                video_path=video_path,
                detector=detector,
                backend=backend,
                openai_key=openai_key,
                qwen_key=qwen_key,
            )
            persisted = self.storage.save_result(session_id, result, source_name)
            self.tasks.finish(session_id)
            removed = self.storage.cleanup_history(keep_session_id=session_id)
            for removed_session in removed:
                self.tasks.remove(removed_session)
            return persisted
        except Exception as exc:
            self.tasks.fail(session_id, exc)
            raise
