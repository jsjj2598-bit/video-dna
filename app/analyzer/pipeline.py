"""编排完整分析管线，产出「剪辑 DNA」JSON。

P0：元信息 + 镜头切分 + 节拍卡点 + 节奏统计。
P1：转场类型识别 + 音频能量/静音/强瞬态。
P2：ASR 台词转写 + 语音段落检测 + 台词-镜头对齐。
P3：谐波/打击乐分离 → 更准 BPM + 更干净音效候选。
P4：多模态语义描述（VLM API / OpenCV 降级）。
P5：EDL / FCP7XML / Cutmark JSON 导出（app/exporter.py）。
"""
from __future__ import annotations

import bisect
import logging
import os
import shutil
import tempfile
from pathlib import Path

from . import audio as old_audio  # 旧版保持向后兼容
from . import ffmpeg_utils, hpss, shots, speech, transitions
from .describer import describe_all
from .. import registry

logger = logging.getLogger(__name__)


def _nearest_beat(t: float, beats: list[float], tol: float = 0.15):
    if not beats:
        return False, None
    i = bisect.bisect_left(beats, t)
    candidates = []
    if i < len(beats):
        candidates.append(beats[i])
    if i > 0:
        candidates.append(beats[i - 1])
    offset = min(abs(c - t) for c in candidates)
    return offset <= tol, round(offset, 3)


_TRANSITION_LABELS = {
    "cut": "硬切",
    "dissolve": "叠化",
    "fade": "淡入淡出",
    "white_flash": "闪白",
    "unknown": "未知",
}


def _summarize(shots_list, audio_info: dict, beat_ratio: float, transition_counts: dict) -> str:
    parts = []
    if shots_list:
        avg = sum(s["duration"] for s in shots_list) / len(shots_list)
        parts.append(f"共 {len(shots_list)} 个镜头，平均 {avg:.2f} 秒/镜")
        if avg < 2:
            pace = "极快"
        elif avg < 4:
            pace = "快"
        elif avg < 8:
            pace = "中等"
        else:
            pace = "慢"
        parts.append(f"整体节奏偏{pace}")
        parts.append(f"卡点率约 {beat_ratio * 100:.0f}%")
    if transition_counts:
        order = ["cut", "dissolve", "fade", "white_flash", "unknown"]
        seg = "、".join(
            f"{_TRANSITION_LABELS.get(k, k)}×{transition_counts[k]}" for k in order if k in transition_counts
        )
        parts.append(f"转场：{seg}")
    if audio_info.get("tempo_bpm"):
        parts.append(
            f"BGM 约 {audio_info['tempo_bpm']:.0f} BPM，"
            f"检测到 {audio_info.get('beat_count', 0)} 个节拍点"
        )
    else:
        parts.append("未检测到明显节拍（可能无音乐）")
    sfx = audio_info.get("sfx_candidates", [])
    if sfx:
        parts.append(f"检测到 {len(sfx)} 个强瞬态（音效候选）")
    sr = audio_info.get("speech_regions", [])
    if sr:
        parts.append(f"检测到 {len(sr)} 段语音")
    wc = audio_info.get("word_count", 0)
    if wc:
        parts.append(f"台词约 {wc} 字")
    # AI 短剧/漫剧优化字段
    described = sum(1 for s in shots_list if s.get("content"))
    if described:
        method = shots_list[0].get("content_method", "heuristic")
        parts.append(f"已完成 {described} 个镜头语义描述（{method}）")

    scene_types = {}
    for s in shots_list:
        st = s.get("scene_type")
        if st:
            scene_types[st] = scene_types.get(st, 0) + 1
    if scene_types:
        order = ["dialogue", "action", "establishing", "closeup", "emotional", "transition"]
        seg = "、".join(
            f"{k}×{scene_types[k]}" for k in order if k in scene_types
        )
        parts.append(f"镜头类型：{seg}")

    face_total = sum(s.get("face_count", 0) or 0 for s in shots_list)
    if face_total:
        parts.append(f"出现人脸约 {face_total} 次")

    emotions = {}
    for s in shots_list:
        em = s.get("emotion")
        if em:
            emotions[em] = emotions.get(em, 0) + 1
    if emotions:
        top = max(emotions, key=emotions.get)
        parts.append(f"主导情绪：{top}")

    return "；".join(parts) + "。"


def analyze(
    video_path: str,
    work_dir: str | None = None,
    extract_keyframes: bool = True,
    detector: str = "content",
    detect_transitions: bool = True,
    describe_shots: bool = True,   # 默认启用 OpenCV 启发式描述（无需 API）
    vlm_backend: str = "auto",
    vlm_model: str = "gpt-4o",
    keep_workdir: bool = False,
    progress_cb: callable | None = None,
) -> dict:
    """progress_cb(stage: str, pct: int, message: str) 思考过程回调。"""
    def report(stage: str, pct: int, message: str) -> None:
        try:
            if progress_cb:
                progress_cb(stage, pct, message)
        except Exception:
            pass

    video_path = Path(video_path)
    if not video_path.exists():
        raise FileNotFoundError(f"视频文件不存在: {video_path}")

    if work_dir is None:
        work_dir = Path(tempfile.mkdtemp(prefix="videodna_"))
    else:
        work_dir = Path(work_dir)
        work_dir.mkdir(parents=True, exist_ok=True)

    try:
        report("probe", 2, "读取视频元信息：分辨率 / 帧率 / 时长 / 编码")
        meta = ffmpeg_utils.probe(str(video_path))
        report("shots", 8, f"开始镜头切分：{meta.get('resolution') or '未知分辨率'} · {meta.get('fps') or '?'}fps")
        shots_list = shots.detect_shots(str(video_path), detector=detector)
        report("shots", 18, f"镜头切分完成：共 {len(shots_list)} 个镜头边界")

        comp_on = lambda cid: bool((registry.get_component(cid) or {}).get("enabled"))

        # ── 音频分析（HPSS 增强） ──
        wav = None
        if meta.get("audio_codec"):
            report("audio", 20, "提取音轨（WAV 22050Hz 单声道）")
            wav = ffmpeg_utils.extract_audio(str(video_path), str(work_dir))
            report("audio", 24, "HPSS 谐波/打击乐分离，分析 BPM 与节拍")
            audio_info = hpss.analyze_enhanced(wav)
            # ASR 台词（组件开关）
            if comp_on("asr"):
                report("asr", 30, "faster-whisper 转写台词与语音段落（首次使用需下载模型）")
                try:
                    transcript = speech.transcribe(wav)
                    audio_info.update(transcript)
                except Exception as exc:
                    logger.warning("ASR 转写失败，降级能量检测: %s", exc)
            else:
                audio_info.update(speech.transcribe(wav, use_whisper=False))
            report("audio", 38, f"音频分析完成：BPM={audio_info.get('tempo_bpm') or '未知'}")
        else:
            audio_info = old_audio.empty_audio_info()
            report("audio", 38, "视频无音轨，跳过音频分析")

        # ── 节拍卡点（组件开关） ──
        beats = audio_info.get("beats", []) if comp_on("beats") else []
        aligned_count = 0
        for sh in shots_list:
            aligned, offset = _nearest_beat(sh["start"], beats)
            sh["beat_aligned"] = aligned
            sh["beat_offset"] = offset
            sh["transition"] = None
            sh["transition_confidence"] = None
            sh["content"] = None
            sh["camera_motion"] = None
            sh["shot_scale"] = None
            sh["content_method"] = None
            if aligned:
                aligned_count += 1

        beat_ratio = (aligned_count / len(shots_list)) if shots_list else 0.0
        report("beats", 42, f"节拍对齐：{aligned_count}/{len(shots_list)} 个镜头卡点（容差 0.15s）")

        # ── 转场分类 ──
        transition_counts: dict = {}
        if detect_transitions and len(shots_list) > 1:
            report("transitions", 45, "识别镜头切换类型：硬切 / 叠化 / 淡入淡出 / 闪白")
            trans = transitions.classify_transitions(str(video_path), shots_list, str(work_dir))
            for i, t in enumerate(trans):
                if t is None:
                    continue
                shots_list[i]["transition"] = t["type"]
                shots_list[i]["transition_confidence"] = t["confidence"]
                transition_counts[t["type"]] = transition_counts.get(t["type"], 0) + 1
            report("transitions", 50, f"转场分类完成：{transition_counts}")

        # ── 台词对齐到镜头 ──
        if audio_info.get("segments"):
            for sh in shots_list:
                segs = []
                for ts in audio_info["segments"]:
                    if ts["end"] > sh["start"] and ts["start"] < sh["end"]:
                        t = ts.get("text")
                        if t:
                            segs.append(t)
                sh["transcript"] = "，".join(segs) if segs else None
        else:
            for sh in shots_list:
                sh["transcript"] = None
        report("align", 55, "台词-镜头时间轴对齐完成")

        # ── 关键帧提取 ──
        if extract_keyframes:
            report("frames", 58, f"提取 {len(shots_list)} 个镜头关键帧")
            frames_dir = work_dir / "frames"
            frames_dir.mkdir(exist_ok=True)
            for sh in shots_list:
                mid = (sh["start"] + sh["end"]) / 2
                fname = f"shot_{sh['index']:03d}.jpg"
                try:
                    ffmpeg_utils.extract_frame(str(video_path), mid, str(frames_dir / fname))
                    sh["keyframe"] = fname
                except Exception:
                    sh["keyframe"] = None
        else:
            for sh in shots_list:
                sh["keyframe"] = None
        report("frames", 64, "关键帧提取完成")

        # ── VLM 语义描述（可选，受组件开关与注册模型控制） ──
        if describe_shots and comp_on("describer") and extract_keyframes and shots_list:
            frames_dir = work_dir / "frames"
            vlm_cfg = None
            try:
                vlm_cfg = registry.get_enabled_vision_model()
            except Exception:
                vlm_cfg = None
            try:
                if vlm_cfg is not None:
                    report("describer", 66, f"多模态语义描述：{vlm_cfg.get('name') or vlm_cfg.get('model')}（镜头画面/景别/运镜/情绪）")
                    if vlm_cfg["provider"] == "dashscope":
                        os.environ["DASHSCOPE_API_KEY"] = vlm_cfg["api_key"]
                    else:
                        os.environ["OPENAI_API_KEY"] = vlm_cfg["api_key"]
                    describe_all(
                        {"shots": shots_list}, frames_dir,
                        backend=vlm_backend, model=vlm_cfg["model"],
                        model_cfg=vlm_cfg,
                    )
                else:
                    report("describer", 66, "OpenCV 启发式描述镜头画面（未配置视觉模型）")
                    describe_all(
                        {"shots": shots_list}, frames_dir,
                        backend=vlm_backend, model=vlm_model,
                    )
            except Exception as exc:
                logger.warning("镜头语义描述失败（保持未描述状态）: %s", exc)
            report("describer", 76, f"语义描述完成：{sum(1 for s in shots_list if s.get('content'))} 个镜头已描述")

        # ── 台词翻译（组件开启且配置了 chat 模型时） ──
        if comp_on("translate") and audio_info.get("text"):
            report("translate", 78, "chat 模型翻译台词为中文")
            try:
                chat = registry.get_enabled_chat_model()
                if chat is not None:
                    audio_info["translation"] = registry.chat_complete(
                        chat,
                        [
                            {"role": "system", "content": "你是专业翻译，将台词翻译为简体中文，保留口语感，按行对应输出。"},
                            {"role": "user", "content": f"请翻译以下台词：\n{audio_info['text'][:4000]}"},
                        ],
                    )
            except Exception as exc:
                logger.warning("台词翻译失败: %s", exc)
            report("translate", 82, "台词翻译完成")

        # ── 统计与摘要 ──
        avg_shot = (sum(s["duration"] for s in shots_list) / len(shots_list)) if shots_list else 0.0
        report("summary", 85, "汇总镜头节奏 / 转场 / 卡点统计")

        dna = {
            "meta": {
                **meta,
                "total_shots": len(shots_list),
                "avg_shot_duration": round(avg_shot, 3),
                "beat_alignment_ratio": round(beat_ratio, 3),
                "transitions": transition_counts,
            },
            "audio": audio_info,
            "shots": shots_list,
            "summary": _summarize(shots_list, audio_info, beat_ratio, transition_counts),
        }

        # ── 智能摘要（组件开启且配置了 chat 模型时，替换启发式摘要） ──
        if comp_on("summarize"):
            report("summarize", 88, "chat 模型生成专业智能摘要")
            try:
                chat = registry.get_enabled_chat_model()
                if chat is not None:
                    dna["summary"] = registry.run_skill(
                        {
                            "name": "智能摘要",
                            "prompt": (
                                "请基于以下视频剪辑分析数据，生成一段 150 字以内的专业分析摘要，"
                                "覆盖：整体节奏、转场风格、卡点与音乐、内容亮点、改进建议。\n\n"
                                "【元信息】{meta}\n【镜头】{shots}\n【音频】{audio}\n【台词】{transcript}"
                            ),
                        },
                        dna,
                        model_cfg=chat,
                    )
                    dna["summary_method"] = "llm"
            except Exception as exc:
                logger.warning("智能摘要失败，使用启发式摘要: %s", exc)

        # ── 插件 hooks（on_shots / on_summary） ──
        try:
            dna = registry.run_plugin_hooks(dna, {"work_dir": str(work_dir), "video_path": str(video_path)})
        except Exception as exc:
            logger.warning("插件执行失败: %s", exc)

        report("done", 100, "分析完成，剪辑 DNA 已生成")
        return dna
    finally:
        if not keep_workdir and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)