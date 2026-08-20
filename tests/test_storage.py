import os
import time

from app.core.config import Settings
from app.services.storage import StorageService


def _settings(tmp_path, history_limit=15) -> Settings:
    static = tmp_path / "static"
    static.mkdir()
    data = tmp_path / "data"
    data.mkdir()
    return Settings(
        data_dir=data,
        static_dir=static,
        max_upload_bytes=100,
        max_history_bytes=history_limit,
        task_ttl_seconds=60,
        api_token=None,
        allowed_video_suffixes=frozenset({".mp4"}),
    )


def test_cleanup_stops_after_reaching_history_limit(tmp_path):
    service = StorageService(_settings(tmp_path))
    service.uploads_dir.mkdir()
    now = time.time()
    for index in range(3):
        directory = service.uploads_dir / f"session{index}"
        directory.mkdir()
        (directory / "payload.bin").write_bytes(b"x" * 10)
        os.utime(directory, (now + index, now + index))

    removed = service.cleanup_history()

    assert removed == ["session0", "session1"]
    assert [path.name for path in service.uploads_dir.iterdir()] == ["session2"]


def test_cleanup_never_deletes_active_session(tmp_path):
    service = StorageService(_settings(tmp_path, history_limit=5))
    service.uploads_dir.mkdir()
    for name in ("active", "old"):
        directory = service.uploads_dir / name
        directory.mkdir()
        (directory / "payload.bin").write_bytes(b"x" * 10)

    removed = service.cleanup_history(keep_session_id="active")

    assert removed == ["old"]
    assert (service.uploads_dir / "active").exists()

