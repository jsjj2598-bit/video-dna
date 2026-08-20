"""Professional interchange and subtitle export endpoints."""

from __future__ import annotations

import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ... import exporter
from ...container import storage
from ...core.security import require_api_token
from ...services.storage import StorageError

router = APIRouter(prefix="/api", tags=["exports"], dependencies=[Depends(require_api_token)])

EXTENSIONS = {"edl": ".edl", "fcp7xml": ".xml", "cutmark": ".json", "srt": ".srt"}
MEDIA_TYPES = {"edl": "text/plain", "fcp7xml": "application/xml", "cutmark": "application/json", "srt": "application/x-subrip"}


def _source_path(dna: dict) -> Path | None:
    session_id = dna.get("_session_id")
    if not session_id:
        return None
    try:
        return storage.source_video(str(session_id))
    except StorageError:
        return None


def _render(dna: dict, fmt: str, output: Path) -> None:
    if fmt == "edl":
        exporter.export_edl(dna, output)
    elif fmt == "fcp7xml":
        exporter.export_fcp7xml(dna, output, source_path=_source_path(dna))
    elif fmt == "cutmark":
        exporter.export_cutmark(dna, output)
    elif fmt == "srt":
        exporter.export_srt(dna, output)
    else:
        raise ValueError(f"不支持的导出格式: {fmt}")


@router.post("/export")
async def export_dna(dna: dict, fmt: str = "cutmark"):
    if fmt not in {*EXTENSIONS, "all"}:
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {fmt}")
    requested_dir = str(dna.pop("_download_dir", "") or "").strip()
    save_dir = Path(requested_dir).expanduser() if requested_dir else None
    if save_dir:
        try:
            save_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise HTTPException(status_code=400, detail=f"导出目录不可写: {exc}") from exc

    if fmt == "all":
        handle, archive_name = tempfile.mkstemp(suffix=".zip")
        os.close(handle)
        archive = Path(archive_name)
        try:
            with tempfile.TemporaryDirectory(prefix="video-dna-export-") as temp_dir:
                temp_root = Path(temp_dir)
                with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
                    for sub_format, extension in EXTENSIONS.items():
                        output = temp_root / f"dna{extension}"
                        _render(dna, sub_format, output)
                        bundle.write(output, output.name)
            if save_dir:
                destination = save_dir / "dna_export.zip"
                shutil.move(archive, destination)
                return {"path": str(destination), "fmt": "all"}
            return FileResponse(archive, media_type="application/zip", filename="dna_export.zip", background=BackgroundTask(archive.unlink, missing_ok=True))
        except Exception:
            archive.unlink(missing_ok=True)
            raise

    handle, output_name = tempfile.mkstemp(suffix=EXTENSIONS[fmt])
    os.close(handle)
    output = Path(output_name)
    try:
        _render(dna, fmt, output)
        filename = f"dna{EXTENSIONS[fmt]}"
        if save_dir:
            destination = save_dir / filename
            shutil.move(output, destination)
            return {"path": str(destination), "fmt": fmt}
        return FileResponse(output, media_type=MEDIA_TYPES[fmt], filename=filename, background=BackgroundTask(output.unlink, missing_ok=True))
    except Exception:
        output.unlink(missing_ok=True)
        raise

