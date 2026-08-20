"""Typed application settings and platform-aware data directories."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

APP_NAME = "Video DNA Analyzer"
APP_SLUG = "video-dna-analyzer"
APP_VERSION = "0.3.1"


def _platform_data_dir() -> Path:
    override = os.environ.get("VIDEODNA_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if sys.platform == "win32":
        root = Path(os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or Path.home())
        return root / APP_NAME
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share")
    return root / APP_SLUG


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    data_dir: Path
    static_dir: Path
    max_upload_bytes: int
    max_history_bytes: int
    task_ttl_seconds: int
    api_token: str | None
    allowed_video_suffixes: frozenset[str]

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def plugins_dir(self) -> Path:
        return self.data_dir / "plugins"

    @property
    def config_file(self) -> Path:
        return self.data_dir / "config.json"

    @property
    def downloads_dir(self) -> Path:
        return self.data_dir / "downloads"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    package_dir = Path(__file__).resolve().parents[1]
    settings = Settings(
        data_dir=_platform_data_dir(),
        static_dir=package_dir / "static",
        max_upload_bytes=_env_int("VIDEODNA_MAX_UPLOAD_BYTES", 2 * 1024**3),
        max_history_bytes=_env_int("VIDEODNA_MAX_HISTORY_BYTES", 8 * 1024**3),
        task_ttl_seconds=_env_int("VIDEODNA_TASK_TTL_SECONDS", 24 * 60 * 60),
        api_token=os.environ.get("VIDEODNA_API_TOKEN") or None,
        allowed_video_suffixes=frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v", ".ts", ".flv", ".wmv"}),
    )
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.plugins_dir.mkdir(parents=True, exist_ok=True)
    settings.downloads_dir.mkdir(parents=True, exist_ok=True)
    return settings
