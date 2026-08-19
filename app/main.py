"""FastAPI 入口：视频上传 → 分析 → 返回「剪辑 DNA」JSON + 关键帧 + 导出。"""
import os
import shutil
import uuid
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .analyzer import pipeline
from . import exporter

app = FastAPI(title="Video DNA Analyzer", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # 允许所有来源，开发阶段可放开
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 跟踪最近的 session ID 以便前端访问关键帧
_last_session_id: str | None = None


@app.get("/health")
def health():
    return {"status": "ok", "service": "video-dna-analyzer", "version": "0.2.0"}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.post("/api/analyze")
async def analyze_video(file: UploadFile = File(...), detector: str = "content"):
    global _last_session_id

    if detector not in ("content", "adaptive"):
        raise HTTPException(status_code=400, detail="detector 只能是 content 或 adaptive")

    session_id = uuid.uuid4().hex
    work_dir = UPLOAD_DIR / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    video_path = work_dir / f"source{suffix}"

    try:
        with video_path.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {exc}") from exc

    try:
        result = pipeline.analyze(
            str(video_path),
            work_dir=str(work_dir),
            extract_keyframes=True,
            detector=detector,
            detect_transitions=True,
            describe_shots=True,       # 默认启用启发式描述
            keep_workdir=True,
        )
        _last_session_id = session_id
        result["_session_id"] = session_id
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"分析失败: {exc}") from exc
    finally:
        video_path.unlink(missing_ok=True)

    return result


@app.get("/api/frames/{filename}")
def serve_frame(filename: str):
    """服务最近一次分析的关键帧图片。"""
    if _last_session_id is None:
        raise HTTPException(status_code=404, detail="尚无分析结果")
    frame_path = UPLOAD_DIR / _last_session_id / "frames" / filename
    if not frame_path.exists():
        raise HTTPException(status_code=404, detail=f"关键帧未找到: {filename}")
    media_type = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
    }.get(frame_path.suffix.lower(), "image/jpeg")
    return FileResponse(str(frame_path), media_type=media_type)


@app.post("/api/export")
async def export_dna(dna: dict, fmt: str = "cutmark"):
    """接收 DNA JSON，导出指定格式并返回文件下载。"""
    if fmt not in ("edl", "fcp7xml", "cutmark", "srt", "all"):
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {fmt}")

    import tempfile
    import zipfile

    if fmt == "all":
        # 导出所有格式，打包为 ZIP
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        try:
            with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                for sub_fmt in ("edl", "fcp7xml", "cutmark", "srt"):
                    sub_tmp = tempfile.NamedTemporaryFile(suffix=f".{sub_fmt}", delete=False)
                    try:
                        if sub_fmt == "edl":
                            exporter.export_edl(dna, sub_tmp.name)
                        elif sub_fmt == "fcp7xml":
                            exporter.export_fcp7xml(dna, sub_tmp.name)
                        elif sub_fmt == "cutmark":
                            exporter.export_cutmark(dna, sub_tmp.name)
                        elif sub_fmt == "srt":
                            exporter.export_srt(dna, sub_tmp.name)
                        zf.write(sub_tmp.name, f"dna.{sub_fmt}")
                    finally:
                        os.unlink(sub_tmp.name)
            return FileResponse(tmp.name, media_type="application/zip", filename="dna_export.zip")
        except Exception:
            os.unlink(tmp.name)
            raise

    tmp = tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False)
    try:
        if fmt == "edl":
            exporter.export_edl(dna, tmp.name)
            media_type = "text/plain"
        elif fmt == "fcp7xml":
            exporter.export_fcp7xml(dna, tmp.name)
            media_type = "text/xml"
        elif fmt == "cutmark":
            exporter.export_cutmark(dna, tmp.name)
            media_type = "application/json"
        elif fmt == "srt":
            exporter.export_srt(dna, tmp.name)
            media_type = "text/plain"
        return FileResponse(tmp.name, media_type=media_type, filename=f"dna.{fmt}")
    except Exception:
        os.unlink(tmp.name)
        raise