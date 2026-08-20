"""Thread-safe, bounded in-memory task progress storage."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field


@dataclass(slots=True)
class TaskState:
    stage: str = "queued"
    pct: int = 0
    logs: list[dict] = field(default_factory=list)
    error: str | None = None
    updated_at: float = field(default_factory=time.time)

    def snapshot(self, session_id: str) -> dict:
        return {
            "session_id": session_id,
            "stage": self.stage,
            "pct": self.pct,
            "logs": list(self.logs),
            "error": self.error,
            "done": self.stage in {"done", "error", "cancelled"},
        }


class TaskStore:
    def __init__(self, ttl_seconds: int = 24 * 60 * 60, max_logs: int = 200) -> None:
        self._ttl_seconds = ttl_seconds
        self._max_logs = max_logs
        self._states: dict[str, TaskState] = {}
        self._lock = threading.RLock()

    def create(self, session_id: str, message: str) -> None:
        with self._lock:
            self._prune_locked()
            state = TaskState(stage="uploaded", pct=1)
            state.logs.append(self._log("upload", 1, message))
            self._states[session_id] = state

    def report(self, session_id: str, stage: str, pct: int, message: str) -> None:
        with self._lock:
            state = self._states.setdefault(session_id, TaskState())
            state.stage = stage
            state.pct = max(state.pct, min(100, int(pct)))
            state.logs.append(self._log(stage, pct, message))
            state.logs = state.logs[-self._max_logs :]
            state.updated_at = time.time()

    def finish(self, session_id: str) -> None:
        self.report(session_id, "done", 100, "分析完成，结果已保存")

    def fail(self, session_id: str, error: Exception | str) -> None:
        message = str(error)
        with self._lock:
            state = self._states.setdefault(session_id, TaskState())
            state.stage = "error"
            state.pct = 100
            state.error = message
            state.logs.append(self._log("error", 100, f"分析失败: {message}"))
            state.logs = state.logs[-self._max_logs :]
            state.updated_at = time.time()

    def get(self, session_id: str) -> dict | None:
        with self._lock:
            self._prune_locked()
            state = self._states.get(session_id)
            return state.snapshot(session_id) if state else None

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._states.pop(session_id, None)

    def clear(self) -> None:
        with self._lock:
            self._states.clear()

    def clear_completed(self) -> None:
        with self._lock:
            completed = [session_id for session_id, state in self._states.items() if state.stage in {"done", "error", "cancelled"}]
            for session_id in completed:
                self._states.pop(session_id, None)

    def is_active(self, session_id: str) -> bool:
        with self._lock:
            state = self._states.get(session_id)
            return bool(state and state.stage not in {"done", "error", "cancelled"})

    def active_session_ids(self) -> set[str]:
        with self._lock:
            return {session_id for session_id, state in self._states.items() if state.stage not in {"done", "error", "cancelled"}}

    @staticmethod
    def _log(stage: str, pct: int, message: str) -> dict:
        return {"t": time.strftime("%H:%M:%S"), "stage": stage, "pct": int(pct), "msg": message}

    def _prune_locked(self) -> None:
        cutoff = time.time() - self._ttl_seconds
        expired = [session_id for session_id, state in self._states.items() if state.updated_at < cutoff]
        for session_id in expired:
            self._states.pop(session_id, None)
