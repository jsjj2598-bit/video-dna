"""FastAPI 入口：视频上传 → 分析 → 返回「剪辑 DNA」JSON + 关键帧 + 导出 + AI 组件管理。"""
import os
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

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


@app.post("/api/analyze")
async def analyze_video(
    file: UploadFile = File(...),
    detector: str = "content",
    backend: str = "auto",
    openai_key: str | None = Form(None),
    qwen_key: str | None = Form(None),
):
    global _last_session_id, _last_dna

    if detector not in ("content", "adaptive"):
        raise HTTPException(status_code=400, detail="detector 只能是 content 或 adaptive")
    if backend not in ("auto", "openai", "qwen", "heuristic"):
        raise HTTPException(status_code=400, detail="backend 只能是 auto / openai / qwen / heuristic")

    # 前端可在设置页配置 API Key，仅注入本次请求进程环境（不落盘）
    if openai_key:
        os.environ["OPENAI_API_KEY"] = openai_key
    if qwen_key:
        os.environ["DASHSCOPE_API_KEY"] = qwen_key

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
            vlm_backend=backend,
            keep_workdir=True,
        )
        _last_session_id = session_id
        _last_dna = result
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
        tmp.close()  # 仅需要路径，立即释放句柄（Windows 下否则无法再次打开）
        try:
            with zipfile.ZipFile(tmp.name, "w", zipfile.ZIP_DEFLATED) as zf:
                for sub_fmt in ("edl", "fcp7xml", "cutmark", "srt"):
                    sub_tmp = tempfile.NamedTemporaryFile(suffix=f".{sub_fmt}", delete=False)
                    sub_tmp.close()  # 释放句柄，zipfile 才能打开该路径
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
    tmp.close()  # 仅需要路径，立即释放句柄（Windows 下否则无法再次打开）
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
    except HTTPException:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise
    except Exception as exc:
        shutil.rmtree(work_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail=f"分析失败: {exc}") from exc

    return {"analysis": result, "cut_plan": cut_plan}


@app.post("/api/draft/export")
async def export_draft(body: dict):
    """生成剪映专业版草稿 ZIP。body: {project_name, cuts: [{start, end}, ...]}"""
    global _last_source_video

    if not _last_source_video or not Path(_last_source_video).exists():
        raise HTTPException(status_code=400, detail="请先通过「套用模板」上传自己的视频")

    cuts = body.get("cuts") or []
    if not cuts:
        raise HTTPException(status_code=400, detail="缺少剪辑区间")
    project_name = str(body.get("project_name") or "VideoDNA剪辑方案")

    import tempfile

    probe_info = ffmpeg_utils.probe(_last_source_video)
    if not probe_info.get("duration"):
        raise HTTPException(status_code=500, detail="无法读取源视频元信息")

    tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
    tmp.close()  # 释放句柄，zipfile 才能打开（Windows）
    try:
        draft_export.export_draft_zip(
            project_name=project_name,
            video_path=_last_source_video,
            cuts=cuts,
            probe_info=probe_info,
            out_path=tmp.name,
        )
        safe_name = "".join(c for c in project_name if c not in '\\/:*?"<>|').strip() or "videodna"
        return FileResponse(tmp.name, media_type="application/zip", filename=f"{safe_name}_剪映草稿.zip")
    except Exception:
        os.unlink(tmp.name)
        raise


# ── AI 组件管理 ───────────────────────────────────────────

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