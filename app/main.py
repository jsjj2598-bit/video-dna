"""FastAPI 入口：视频上传 → 分析 → 返回「剪辑 DNA」JSON + 关键帧 + 导出 + AI 组件管理。"""
import asyncio
import json as _json
import os
import shutil
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from starlette.background import BackgroundTask

from .analyzer import pipeline
from .analyzer import ffmpeg_utils
from . import exporter
from . import registry
from . import draft as draft_export

app = FastAPI(title="Video DNA Analyzer", version="0.2.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "http://127.0.0.1",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "file://",
    ],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

# 跟踪最近的 session ID 以便前端访问关键帧
_last_session_id: str | None = None
# 最近一次分析结果（供技能运行）
_last_dna: dict | None = None
# 最近一次套用模板后保留的源视频（供剪映草稿导出）
_last_source_video: str | None = None

# 各 session 的思考过程（stage / pct / logs）
_progress: dict[str, dict] = {}
_progress_lock = threading.Lock()


def _progress_state(session_id: str) -> dict:
    with _progress_lock:
        st = _progress.get(session_id)
        if st is None:
            st = {"stage": "idle", "pct": 0, "logs": []}
            _progress[session_id] = st
        return st


def _progress_cb(session_id: str, stage: str, pct: int, message: str) -> None:
    with _progress_lock:
        st = _progress.get(session_id)
        if st is None:
            st = {"stage": "idle", "pct": 0, "logs": []}
            _progress[session_id] = st
        st["stage"] = stage
        st["pct"] = max(st["pct"], int(pct))
        st["logs"].append({
            "t": time.strftime("%H:%M:%S"),
            "stage": stage,
            "pct": int(pct),
            "msg": message,
        })
        if len(st["logs"]) > 200:
            st["logs"] = st["logs"][-200:]


def _safe_join(base: Path, name: str) -> Path:
    """把 name 安全解析到 base 目录下：拒绝路径穿越与 Windows 绝对路径绕过。"""
    base = base.resolve()
    p = (base / name).resolve()
    if p == base or base not in p.parents:
        raise HTTPException(status_code=400, detail="非法参数")
    return p


def _apply_env(openai_key: str | None, qwen_key: str | None) -> dict:
    """仅对当前分析流程注入 API Key，记录原值以便恢复（不污染全局环境）。"""
    prev = {}
    for name, val in (("OPENAI_API_KEY", openai_key), ("DASHSCOPE_API_KEY", qwen_key)):
        if val:
            prev[name] = os.environ.get(name)
            os.environ[name] = val
    return prev


def _restore_env(prev: dict) -> None:
    for name, val in prev.items():
        if val is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = val


UPLOADS_MAX_BYTES = 8 * 1024 * 1024 * 1024  # uploads 总量上限 8GB，超出自动清理最旧


def _cleanup_old_uploads(keep: Path | None = None) -> None:
    """按总量上限清理历史 uploads（保留正在使用的 session）。"""
    if not UPLOAD_DIR.exists():
        return
    try:
        dirs = [d for d in UPLOAD_DIR.iterdir() if d.is_dir()]
        total = sum(sum(f.stat().st_size for f in d.rglob("*") if f.is_file()) for d in dirs)
        if total <= UPLOADS_MAX_BYTES:
            return
        dirs.sort(key=lambda d: d.stat().st_mtime)
        for d in dirs:
            if keep is not None and d.resolve() == keep.resolve():
                continue
            try:
                shutil.rmtree(d, ignore_errors=True)
                total -= sum(f.stat().st_size for f in d.rglob("*") if f.is_file())
            except Exception:
                pass
            if total <= UPLOADS_MAX_BYTES:
                break
    except Exception:
        pass


def _build_cut_plan(template_dna: dict, target_dna: dict) -> dict:
    """把示例视频的镜头节奏映射到目标视频：
    镜头边界按时长比例缩放，并吸附到目标视频最近节拍（容差 0.45s）。
    """
    t_shots = sorted(template_dna.get("shots") or [], key=lambda s: s["start"])
    t_dur = float(template_dna.get("meta", {}).get("duration") or 1.0)
    if t_shots:
        t_dur = max(t_dur, t_shots[-1].get("end") or t_dur)
    if t_dur <= 0:
        t_dur = 1.0

    target_dur = float(target_dna.get("meta", {}).get("duration") or 0.0)
    if target_dur <= 0:
        raise HTTPException(status_code=422, detail="目标视频时长无效")

    beats = sorted(target_dna.get("audio", {}).get("beats") or [])

    # 模板内部镜头边界（按比例）→ 目标时间码
    raw_bounds = [0.0]
    for s in t_shots[:-1]:
        frac = max(min(float(s.get("end", s["start"])) / t_dur, 1.0), 0.0)
        raw_bounds.append(frac)
    raw_bounds.append(1.0)

    cuts = []
    prev = 0.0
    for k, frac in enumerate(raw_bounds):
        raw = frac * target_dur
        if k == 0:
            t = 0.0
            aligned = False
        elif k == len(raw_bounds) - 1:
            t = target_dur
            aligned = False
        else:
            t = raw
            aligned = False
            # 内部边界吸附到最近节拍
            if beats:
                near = min(beats, key=lambda b: abs(b - raw))
                if abs(near - raw) <= 0.45 and near > prev + 0.2:
                    t = near
                    aligned = True
            t = max(t, prev + 0.3)
        cuts.append({
            "index": len(cuts),
            "start": round(prev, 3),
            "end": round(t, 3),
            "duration": round(t - prev, 3),
            "aligned_to_beat": aligned,
            "template_ratio": round(frac, 4),
        })
        prev = t

    cuts = [c for c in cuts if c["duration"] >= 0.25]
    # 确保末尾闭合
    if cuts and abs(cuts[-1]["end"] - target_dur) > 0.01:
        cuts[-1]["end"] = round(target_dur, 3)
        cuts[-1]["duration"] = round(cuts[-1]["end"] - cuts[-1]["start"], 3)

    return {
        "source": template_dna.get("meta", {}).get("source_file") or "示例视频",
        "template_duration": round(t_dur, 3),
        "target_duration": round(target_dur, 3),
        "cuts": cuts,
        "total": len(cuts),
        "beat_aligned_count": sum(1 for c in cuts if c["aligned_to_beat"]),
    }


@app.get("/health")
def health():
    return {"status": "ok", "service": "video-dna-analyzer", "version": "0.2.0"}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/progress/{session_id}")
def get_progress(session_id: str):
    """查询某次分析的思考过程。"""
    st = _progress_state(session_id)
    return {
        "session_id": session_id,
        "stage": st["stage"],
        "pct": st["pct"],
        "logs": st["logs"],
        "done": st["stage"] in ("done", "error"),
    }


@app.post("/api/analyze")
async def analyze_video(
    file: UploadFile = File(...),
    detector: str = "content",
    backend: str = "auto",
    openai_key: str | None = Form(None),
    qwen_key: str | None = Form(None),
    session_id: str | None = Form(None),
):
    global _last_session_id, _last_dna

    if detector not in ("content", "adaptive"):
        raise HTTPException(status_code=400, detail="detector 只能是 content 或 adaptive")
    if backend not in ("auto", "openai", "qwen", "heuristic"):
        raise HTTPException(status_code=400, detail="backend 只能是 auto / openai / qwen / heuristic")

    # 前端可在设置页配置 API Key，仅注入本次分析流程（结束后恢复，不污染全局环境）
    prev_env = _apply_env(openai_key, qwen_key)

    session_id = (session_id or uuid.uuid4().hex).strip()
    if not session_id.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="session_id 非法")
    work_dir = UPLOAD_DIR / session_id
    work_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(file.filename or "video.mp4").suffix.lower() or ".mp4"
    video_path = work_dir / f"source{suffix}"

    try:
        with video_path.open("wb") as fh:
            shutil.copyfileobj(file.file, fh)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"保存文件失败: {exc}") from exc

    st = _progress_state(session_id)
    st.update({"stage": "uploaded", "pct": 1, "logs": [{"t": time.strftime("%H:%M:%S"), "stage": "upload", "pct": 1, "msg": f"文件已上传：{Path(file.filename or 'video').name}"}]})

    def run():
        try:
            result = pipeline.analyze(
                str(video_path),
                work_dir=str(work_dir),
                extract_keyframes=True,
                detector=detector,
                detect_transitions=True,
                describe_shots=True,       # 默认启用启发式描述
                vlm_backend=backend,
                keep_workdir=True,
                progress_cb=lambda stage, pct, msg: _progress_cb(session_id, stage, pct, msg),
            )
            _last_session_id = session_id
            _last_dna = result
            result["_session_id"] = session_id
            result["_source_file"] = Path(file.filename or "video").name
            st["result"] = result
            st["stage"] = "done"
            st["pct"] = 100
            # 历史持久化：保存分析结果 JSON
            try:
                (work_dir / "result.json").write_text(
                    _json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            except Exception:
                pass
        except Exception as exc:
            st["stage"] = "error"
            st["logs"].append({"t": time.strftime("%H:%M:%S"), "stage": "error", "pct": 100, "msg": f"分析失败: {exc}"})
            st["error"] = str(exc)
        finally:
            _restore_env(prev_env)
            _cleanup_old_uploads(keep=work_dir)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()

    return {"session_id": session_id, "status": "running"}


@app.post("/api/analyze/wait")
async def analyze_wait(
    file: UploadFile = File(...),
    detector: str = "content",
    backend: str = "auto",
    openai_key: str | None = Form(None),
    qwen_key: str | None = Form(None),
):
    """同步等待分析完成（后台线程运行，事件循环不被阻塞）。"""
    global _last_session_id, _last_dna

    if detector not in ("content", "adaptive"):
        raise HTTPException(status_code=400, detail="detector 只能是 content 或 adaptive")
    if backend not in ("auto", "openai", "qwen", "heuristic"):
        raise HTTPException(status_code=400, detail="backend 只能是 auto / openai / qwen / heuristic")

    prev_env = _apply_env(openai_key, qwen_key)

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

    st = _progress_state(session_id)
    st.update({"stage": "uploaded", "pct": 1, "logs": [{"t": time.strftime("%H:%M:%S"), "stage": "upload", "pct": 1, "msg": f"文件已上传：{Path(file.filename or 'video').name}"}]})
    try:
        result = await asyncio.to_thread(
            pipeline.analyze,
            str(video_path),
            work_dir=str(work_dir),
            extract_keyframes=True,
            detector=detector,
            detect_transitions=True,
            describe_shots=True,
            vlm_backend=backend,
            keep_workdir=True,
            progress_cb=lambda stage, pct, msg: _progress_cb(session_id, stage, pct, msg),
        )
    except Exception as exc:
        st["stage"] = "error"
        st["error"] = str(exc)
        st["logs"].append({"t": time.strftime("%H:%M:%S"), "stage": "error", "pct": 100, "msg": f"分析失败: {exc}"})
        raise HTTPException(status_code=422, detail=f"分析失败: {exc}") from exc
    finally:
        _restore_env(prev_env)

    _last_session_id = session_id
    _last_dna = result
    result["_session_id"] = session_id
    result["_source_file"] = Path(file.filename or "video").name
    st["result"] = result
    st["stage"] = "done"
    st["pct"] = 100
    try:
        (work_dir / "result.json").write_text(
            _json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except Exception:
        pass
    _cleanup_old_uploads(keep=work_dir)

    return result


@app.get("/api/frames/{filename}")
def serve_frame(filename: str):
    """服务最近一次分析的关键帧图片。"""
    if _last_session_id is None:
        raise HTTPException(status_code=404, detail="尚无分析结果")
    frame_path = _safe_join(UPLOAD_DIR / _last_session_id / "frames", filename)
    if not frame_path.exists() or not frame_path.is_file():
        raise HTTPException(status_code=404, detail=f"关键帧未找到: {filename}")
    media_type = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
    }.get(frame_path.suffix.lower(), "image/jpeg")
    return FileResponse(str(frame_path), media_type=media_type)


@app.get("/api/sessions/{session_id}/frames/{filename}")
def serve_session_frame(session_id: str, filename: str):
    """服务任意 session 的关键帧（历史记录回看用）。"""
    if not session_id.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="非法参数")
    frame_path = _safe_join(UPLOAD_DIR / session_id / "frames", filename)
    if not frame_path.exists() or not frame_path.is_file():
        raise HTTPException(status_code=404, detail=f"关键帧未找到: {filename}")
    media_type = {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".gif": "image/gif",
    }.get(frame_path.suffix.lower(), "image/jpeg")
    return FileResponse(str(frame_path), media_type=media_type)


_VIDEO_MIME = {
    ".mp4": "video/mp4", ".mov": "video/quicktime", ".mkv": "video/x-matroska",
    ".webm": "video/webm", ".avi": "video/x-msvideo", ".m4v": "video/x-m4v",
    ".ts": "video/mp2t", ".flv": "video/x-flv", ".wmv": "video/x-ms-wmv",
}


def _video_chunk(path: Path, start: int, length: int, chunk_size: int = 1 << 16):
    with path.open("rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            data = fh.read(min(chunk_size, remaining))
            if not data:
                break
            remaining -= len(data)
            yield data


@app.get("/api/sessions/{session_id}/video")
def serve_session_video(session_id: str, request: Request):
    """服务任意 session 的源视频（历史回看 / 剪映草稿下载），支持 Range 请求。"""
    if not session_id.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="非法参数")
    videos = list((UPLOAD_DIR / session_id).glob("source.*"))
    if not videos:
        raise HTTPException(status_code=404, detail="源视频未找到")
    vp = videos[0]
    media_type = _VIDEO_MIME.get(vp.suffix.lower(), "application/octet-stream")
    size = vp.stat().st_size
    rng = request.headers.get("range")
    if rng and rng.lower().startswith("bytes="):
        try:
            start_s, end_s = rng[6:].split("-", 1)
            start = int(start_s) if start_s.strip() else 0
            end = int(end_s) if end_s.strip() else size - 1
            if end >= size:
                end = size - 1
            if start < 0 or start > end or start >= size:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            length = end - start + 1
            return StreamingResponse(
                _video_chunk(vp, start, length),
                status_code=206,
                media_type=media_type,
                headers={
                    "Content-Range": f"bytes {start}-{end}/{size}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(length),
                },
            )
        except (ValueError, IndexError):
            pass
    return FileResponse(str(vp), media_type=media_type, headers={"Accept-Ranges": "bytes"})


@app.get("/api/result/{session_id}")
def get_result(session_id: str):
    """返回某次分析的结果 JSON（前端轮询进度完成后获取）。"""
    if not session_id.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="非法参数")
    st = _progress_state(session_id)
    if st.get("stage") == "error":
        raise HTTPException(status_code=422, detail=st.get("error") or "分析失败")
    if "result" in st:
        return st["result"]
    # 兜底：从磁盘读取历史结果
    rp = UPLOAD_DIR / session_id / "result.json"
    if rp.exists():
        try:
            return _json.loads(rp.read_text(encoding="utf-8"))
        except Exception:
            pass
    raise HTTPException(status_code=404, detail="分析尚未完成或不存在")


@app.get("/api/history")
def list_history():
    """列出全部历史分析（uploads 下含 result.json 的 session）。"""
    items = []
    if UPLOAD_DIR.exists():
        for d in sorted(UPLOAD_DIR.iterdir(), key=lambda p: p.stat().st_mtime if p.is_dir() else 0, reverse=True):
            if not d.is_dir():
                continue
            rp = d / "result.json"
            if not rp.exists():
                continue
            try:
                result = _json.loads(rp.read_text(encoding="utf-8"))
                mtime = d.stat().st_mtime
            except Exception:
                continue
            m = result.get("meta", {})
            items.append({
                "session_id": d.name,
                "name": result.get("_source_file") or m.get("source_file") or f"分析 {d.name[:8]}",
                "time": time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime)),
                "total_shots": m.get("total_shots", 0),
                "duration": m.get("duration", 0),
                "bpm": result.get("audio", {}).get("tempo_bpm"),
                "summary": result.get("summary", ""),
                "has_video": bool(list(d.glob("source.*"))),
                "shot_count": len(result.get("shots", [])),
            })
    return {"items": items}


@app.get("/api/history/{session_id}")
def get_history_detail(session_id: str):
    """历史记录完整回看：返回结果 JSON + 视频/关键帧地址。"""
    if not session_id.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="非法参数")
    rp = UPLOAD_DIR / session_id / "result.json"
    if not rp.exists():
        raise HTTPException(status_code=404, detail="该记录不存在")
    try:
        result = _json.loads(rp.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"结果解析失败: {exc}") from exc
    result["_session_id"] = session_id
    videos = list((UPLOAD_DIR / session_id).glob("source.*"))
    result["_video_url"] = f"/api/sessions/{session_id}/video" if videos else None
    result["_frame_base"] = f"/api/sessions/{session_id}/frames/"
    return result


@app.delete("/api/history")
def clear_history():
    """清空全部历史记录。"""
    if UPLOAD_DIR.exists():
        for d in UPLOAD_DIR.iterdir():
            if d.is_dir():
                shutil.rmtree(d, ignore_errors=True)
    with _progress_lock:
        _progress.clear()
    return {"ok": True}


@app.delete("/api/history/{session_id}")
def delete_history(session_id: str):
    if not session_id.replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="非法参数")
    d = UPLOAD_DIR / session_id
    if not d.exists():
        raise HTTPException(status_code=404, detail="该记录不存在")
    shutil.rmtree(d, ignore_errors=True)
    with _progress_lock:
        _progress.pop(session_id, None)
    return {"ok": True}


@app.post("/api/export")
async def export_dna(dna: dict, fmt: str = "cutmark"):
    """接收 DNA JSON，导出指定格式并返回文件下载。

    若 dna 中含 _download_dir（设置页自定义下载目录），文件直接保存到该目录，
    返回 {path}；否则返回文件流下载。
    """
    if fmt not in ("edl", "fcp7xml", "cutmark", "srt", "all"):
        raise HTTPException(status_code=400, detail=f"不支持的导出格式: {fmt}")

    import tempfile
    import zipfile

    download_dir = str(dna.get("_download_dir") or "").strip()
    save_to_dir = None
    if download_dir:
        try:
            save_to_dir = Path(download_dir)
            save_to_dir.mkdir(parents=True, exist_ok=True)
        except Exception:
            save_to_dir = None

    def _render(sub_fmt: str, out: str) -> None:
        if sub_fmt == "edl":
            exporter.export_edl(dna, out)
        elif sub_fmt == "fcp7xml":
            exporter.export_fcp7xml(dna, out)
        elif sub_fmt == "cutmark":
            exporter.export_cutmark(dna, out)
        elif sub_fmt == "srt":
            exporter.export_srt(dna, out)

    if fmt == "all":
        # 导出所有格式，打包为 ZIP
        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()  # 仅需要路径，立即释放句柄（Windows 下否则无法再次打开）
        try:
            with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                for sub_fmt in ("edl", "fcp7xml", "cutmark", "srt"):
                    sub_tmp = tempfile.NamedTemporaryFile(suffix=f".{sub_fmt}", delete=False)
                    sub_tmp.close()  # 释放句柄，zipfile 才能打开该路径
                    try:
                        _render(sub_fmt, sub_tmp.name)
                        zf.write(sub_tmp.name, f"dna.{sub_fmt}")
                    finally:
                        os.unlink(sub_tmp.name)
            if save_to_dir is not None:
                dest = save_to_dir / "dna_export.zip"
                shutil.copyfile(tmp.name, dest)
                os.unlink(tmp.name)
                return {"path": str(dest), "fmt": "all"}
            return FileResponse(
                tmp.name,
                media_type="application/zip",
                filename="dna_export.zip",
                background=BackgroundTask(os.unlink, tmp.name),
            )
        except Exception:
            os.unlink(tmp.name)
            raise

    tmp = tempfile.NamedTemporaryFile(suffix=f".{fmt}", delete=False)
    tmp.close()  # 仅需要路径，立即释放句柄（Windows 下否则无法再次打开）
    try:
        _render(fmt, tmp.name)
        if save_to_dir is not None:
            dest = save_to_dir / f"dna.{fmt}"
            shutil.copyfile(tmp.name, dest)
            os.unlink(tmp.name)
            return {"path": str(dest), "fmt": fmt}
        media_type = {
            "edl": "text/plain",
            "fcp7xml": "text/xml",
            "cutmark": "application/json",
            "srt": "text/plain",
        }[fmt]
        return FileResponse(
            tmp.name,
            media_type=media_type,
            filename=f"dna.{fmt}",
            background=BackgroundTask(os.unlink, tmp.name),
        )
    except Exception:
        os.unlink(tmp.name)
        raise


@app.post("/api/template/apply")
async def apply_template(
    file: UploadFile = File(...),
    template: str = Form(...),
    detector: str = "content",
    backend: str = "auto",
):
    """套用示例视频分析结果：上传自己的视频 → 按模板节奏生成剪辑方案。

    template 为示例视频的 DNA JSON 字符串。返回：目标视频分析 + 剪辑方案。
    源视频保留在 uploads 目录，供 /api/draft/export 生成剪映草稿。
    """
    global _last_session_id, _last_dna, _last_source_video

    import json as _json

    try:
        template_dna = _json.loads(template)
        if not isinstance(template_dna, dict) or not template_dna.get("shots"):
            raise ValueError("模板数据无效")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"模板 JSON 无效: {exc}") from exc

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
            describe_shots=True,
            vlm_backend=backend,
            keep_workdir=True,
        )
        result["_session_id"] = session_id
        cut_plan = _build_cut_plan(template_dna, result)
        _last_session_id = session_id
        _last_dna = result
        _last_source_video = str(video_path)
        result["_cut_plan"] = cut_plan
        result["_source_file"] = Path(file.filename or "video").name
        try:
            (work_dir / "result.json").write_text(
                _json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
    except HTTPException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"分析失败: {exc}") from exc

    return {"analysis": result, "cut_plan": cut_plan}


@app.post("/api/draft/export")
async def export_draft(body: dict):
    """生成剪映工程文件夹（非 ZIP，含视频素材）。

    body: {
      project_name, cuts: [{start, end}],
      session_id?,        # 指定用某次分析的源视频（历史记录导出）
      download_dir?       # 下载目录（任务6：自定义下载地址）
    }
    返回：{path: 草稿文件夹路径, opened}
    """
    session_id = str(body.get("session_id") or "").strip() or _last_session_id
    source_video = _last_source_video
    if session_id and session_id.replace("-", "").isalnum():
        videos = list((UPLOAD_DIR / session_id).glob("source.*"))
        if videos:
            source_video = str(videos[0])
    if not source_video or not Path(source_video).exists():
        raise HTTPException(status_code=400, detail="请先上传并分析一个视频，再导出草稿")

    cuts = body.get("cuts") or []
    if not cuts:
        raise HTTPException(status_code=400, detail="缺少剪辑区间")
    project_name = str(body.get("project_name") or "VideoDNA剪辑方案")

    probe_info = ffmpeg_utils.probe(source_video)
    if not probe_info.get("duration"):
        raise HTTPException(status_code=500, detail="无法读取源视频元信息")

    # 下载目录：默认用户下载目录，可被设置页自定义（任务6）
    download_dir = str(body.get("download_dir") or "").strip()
    if not download_dir:
        try:
            import ctypes.wintypes
            buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
            ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf)  # CSIDL_MYDOCUMENTS
            download_dir = Path(buf.value) / "VideoDNA草稿"
        except Exception:
            download_dir = str(Path.cwd() / "downloads")
    download_dir = Path(download_dir)
    try:
        download_dir.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"下载目录不可写: {download_dir} ({exc})") from exc

    try:
        folder = draft_export.export_draft_folder(
            project_name=project_name,
            video_path=source_video,
            cuts=cuts,
            probe_info=probe_info,
            out_dir=download_dir,
        )
        return {"path": folder, "download_dir": str(download_dir)}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"剪映草稿生成失败: {exc}") from exc


# ── AI 创作（任务8：AI 视频生成平台通用功能） ─────────────

# 内置节奏模板（AI 视频生成平台的模板中心能力）
RHYTHM_TEMPLATES = [
    {
        "id": "beat_kardian", "name": "抖音卡点快剪",
        "desc": "0.8s 短镜卡点，BPM≥120 燃向音乐，适合变装/舞蹈/高燃混剪",
        "icon": "🔥", "bpm": 128, "shot": 0.8,
        "pattern": [1.0, 0.8, 0.8, 0.6, 0.8, 0.8, 1.2, 0.8],
    },
    {
        "id": "vlog_relax", "name": "Vlog 生活慢叙",
        "desc": "3~6s 长镜慢节奏，BGM 轻快，适合日常记录/旅行/美食",
        "icon": "🌿", "bpm": 92, "shot": 4.0,
        "pattern": [4.0, 3.5, 5.0, 3.0, 4.5, 3.0],
    },
    {
        "id": "film_cinema", "name": "电影感叙事",
        "desc": "5~8s 大景别慢镜 + 叠化转场，适合短剧/宣传片/情感向",
        "icon": "🎬", "bpm": 70, "shot": 6.0,
        "pattern": [6.0, 5.0, 8.0, 5.0, 6.0, 4.0, 7.0],
    },
    {
        "id": "game_esport", "name": "电竞高燃卡点",
        "desc": "0.4~1s 极速切镜 + 强瞬态音效，BPM≥140，适合游戏集锦",
        "icon": "🎮", "bpm": 144, "shot": 0.6,
        "pattern": [0.6, 0.4, 0.6, 0.8, 0.5, 0.4, 0.6, 0.8, 0.5, 1.0],
    },
    {
        "id": "story_bite", "name": "短剧钩子节奏",
        "desc": "开头 3s 强钩子 + 中段对话推进 + 结尾反转留白",
        "icon": "🎭", "bpm": 100, "shot": 2.5,
        "pattern": [3.0, 2.0, 2.5, 2.0, 2.5, 3.0, 2.0, 2.5, 3.5, 4.0],
    },
]


def _template_dna(tpl: dict, duration: float) -> dict:
    """把节奏模板转为「示例视频 DNA」（供 _build_cut_plan 复用）。"""
    shots = []
    t = 0.0
    idx = 0
    i = 0
    while t < duration - 0.05:
        d = float(tpl["pattern"][i % len(tpl["pattern"])])
        if t + d > duration:
            d = duration - t
        shots.append({"start": round(t, 3), "end": round(t + d, 3), "duration": round(d, 3), "index": idx})
        t += d
        idx += 1
        i += 1
    return {
        "meta": {
            "duration": round(duration, 3),
            "total_shots": len(shots),
            "source_file": tpl["name"],
            "template_id": tpl["id"],
        },
        "shots": shots,
        "audio": {"tempo_bpm": tpl["bpm"]},
    }


@app.get("/api/ai/templates")
def list_ai_templates():
    """AI 创作中心：内置节奏模板（模板库）。"""
    return {"templates": RHYTHM_TEMPLATES}


@app.post("/api/ai/storyboard")
async def ai_storyboard(body: dict):
    """AI 分镜脚本生成：输入主题/文案 → 生成分镜脚本（表格）。"""
    topic = str(body.get("topic") or "").strip()
    length = int(body.get("length") or 6)
    if not topic:
        raise HTTPException(status_code=400, detail="请输入主题或文案")
    length = max(3, min(length, 20))
    chat = registry.get_enabled_chat_model()
    if chat is None:
        # 无模型时启发式生成分镜框架
        shots = []
        beats = max(1, length)
        for i in range(beats):
            shots.append({
                "index": i,
                "duration": 3.0,
                "scene": ["开场钩子：快速吸引注意力", "主体推进：展示核心内容", "情绪强化：特写/慢镜", "高潮：节奏加快", "结尾：留白与引导"][i % 5],
                "camera": ["中景固定", "推近", "侧移跟拍", "特写", "拉远"][i % 5],
                "voiceover": "",
            })
        return {"method": "heuristic", "topic": topic, "shots": shots,
                "hint": "未配置对话模型，已生成基础框架。在「AI 组件」中添加 chat 模型可获得 AI 级脚本。"}
    try:
        prompt = (
            "你是短视频分镜脚本导演。为主题「%s」创作 %d 个镜头的分镜脚本，输出 JSON 数组，"
            "每个元素含：scene(画面描述,20字内)、camera(景别+运镜)、duration(秒)、voiceover(台词/旁白,可为空)、"
            "transition(转场建议)。只输出 JSON，不要多余文字。" % (topic, length)
        )
        text = registry.chat_complete(
            chat,
            [{"role": "system", "content": "你是专业分镜脚本导演，只输出 JSON。"},
             {"role": "user", "content": prompt}],
        )
        import re as _re
        m = _re.search(r"\[.*\]", text, _re.S)
        if not m:
            raise ValueError("模型未返回分镜数组")
        shots = _json.loads(m.group(0))
        return {"method": "llm", "model": chat["model"], "topic": topic, "shots": shots}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"分镜生成失败: {exc}") from exc


@app.post("/api/ai/bgm")
async def ai_bgm(body: dict):
    """BGM 推荐：根据视频分析结果推荐音乐风格（AI 视频平台通用功能）。"""
    dna = (body or {}).get("dna") or _last_dna
    if not dna:
        raise HTTPException(status_code=400, detail="请先分析视频")
    bpm = float(dna.get("audio", {}).get("tempo_bpm") or 0)
    avg = float(dna.get("meta", {}).get("avg_shot_duration") or 0)
    if bpm <= 0:
        raise HTTPException(status_code=400, detail="未检测到 BPM，无法推荐")
    if bpm >= 120:
        mood, genre = "高燃/活力", ["EDM", "Trap", "电子舞曲", "Bounce"]
    elif bpm >= 90:
        mood, genre = "轻快/向上", ["流行", "Future Bass", "Pop 电子", "轻摇滚"]
    elif bpm >= 60:
        mood, genre = "舒缓/叙事", ["钢琴抒情", "Lo-fi", "氛围电子", "民谣"]
    else:
        mood, genre = "低沉/悬疑", ["暗黑氛围", "Drone", "悬疑配乐", "低频垫乐"]
    return {
        "bpm": bpm, "mood": mood,
        "recommend": genre,
        "hint": f"镜头平均 {avg:.1f}s，建议切点对齐 BPM 节拍（每拍 {60 / bpm:.2f}s）",
        "search_hint": f"在剪映/BGM 平台搜索关键词：{'、'.join(genre)}",
    }


# ── AI 组件管理 ───────────────────────────────────────────

@app.post("/api/ai/apply")
async def ai_apply_template(
    file: UploadFile = File(...),
    template: str = Form(...),
    detector: str = "content",
    backend: str = "auto",
):
    """AI 创作中心：把内置节奏模板套用到自己的视频（模板库一键成片）。"""
    global _last_session_id, _last_dna, _last_source_video

    tpl = next((t for t in RHYTHM_TEMPLATES if t["id"] == template), None)
    if tpl is None:
        raise HTTPException(status_code=400, detail=f"模板不存在: {template}")

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
            describe_shots=True,
            vlm_backend=backend,
            keep_workdir=True,
        )
        result["_session_id"] = session_id
        result["_source_file"] = Path(file.filename or "video").name
        dur = float(result.get("meta", {}).get("duration") or 0.0)
        cut_plan = _build_cut_plan(_template_dna(tpl, dur), result)
        _last_session_id = session_id
        _last_dna = result
        _last_source_video = str(video_path)
        result["_cut_plan"] = cut_plan
        try:
            (work_dir / "result.json").write_text(
                _json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except Exception:
            pass
    except HTTPException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"分析失败: {exc}") from exc

    return {"analysis": result, "cut_plan": cut_plan, "template": tpl}


@app.get("/api/components")
def get_components():
    """组件 + 模型 + 插件 + 技能 一览。"""
    return {
        "components": registry.list_components(),
        "models": registry.list_models(),
        "plugins": registry.list_plugins(),
        "skills": registry.list_skills(),
        "data_dir": str(registry.DATA_DIR),
    }


@app.post("/api/components/{cid}/toggle")
def toggle_component(cid: str, body: dict):
    enabled = bool(body.get("enabled", True))
    model_id = body.get("model_id")
    comp = registry.set_component(cid, enabled, model_id=model_id)
    if comp is None:
        raise HTTPException(status_code=404, detail=f"组件不存在: {cid}")
    return comp


@app.post("/api/models")
def create_model(body: dict):
    try:
        return registry.upsert_model(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/models/{mid}")
def update_model(mid: str, body: dict):
    body["id"] = mid
    try:
        return registry.upsert_model(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/models/{mid}")
def remove_model(mid: str):
    if not registry.delete_model(mid):
        raise HTTPException(status_code=404, detail=f"模型不存在: {mid}")
    return {"ok": True}


@app.post("/api/models/{mid}/test")
def test_model(mid: str):
    m = registry.get_model(mid)
    if m is None:
        raise HTTPException(status_code=404, detail=f"模型不存在: {mid}")
    if not m.get("api_key") and m.get("provider") not in ("ollama",):
        raise HTTPException(status_code=400, detail="请先填写 API Key 再测试")
    try:
        reply = registry.test_model(m)
        return {"ok": True, "reply": reply}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"连接失败: {exc}") from exc


@app.post("/api/skills")
def create_skill(body: dict):
    try:
        return registry.add_skill(body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.delete("/api/skills/{sid}")
def remove_skill(sid: str):
    if not registry.delete_skill(sid):
        raise HTTPException(status_code=404, detail=f"技能不存在: {sid}")
    return {"ok": True}


@app.post("/api/skills/{sid}/run")
def run_skill(sid: str, body: dict | None = None):
    """对最近一次分析结果运行技能（可传入 dna 覆盖）。"""
    dna = (body or {}).get("dna") or _last_dna
    if dna is None:
        raise HTTPException(status_code=400, detail="请先分析一个视频，或传入 dna")
    skill = next((s for s in registry.list_skills() if s["id"] == sid), None)
    if skill is None:
        raise HTTPException(status_code=404, detail=f"技能不存在: {sid}")
    try:
        output = registry.run_skill(skill, dna)
        return {"ok": True, "output": output, "skill": skill["name"]}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/plugins")
def get_plugins():
    return registry.list_plugins()


@app.post("/api/plugins/install")
async def install_plugin(file: UploadFile = File(...)):
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()  # 释放句柄，zipfile 才能打开
    try:
        with open(tmp.name, "wb") as fh:
            shutil.copyfileobj(file.file, fh)
        plugin = registry.install_plugin_zip(tmp.name)
        return {"ok": True, "plugin": plugin}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"安装失败: {exc}") from exc
    finally:
        os.unlink(tmp.name)


@app.delete("/api/plugins/{pid}")
def remove_plugin(pid: str):
    if not registry.delete_plugin(pid):
        raise HTTPException(status_code=404, detail=f"插件不存在: {pid}")
    return {"ok": True}