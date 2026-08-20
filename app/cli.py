"""命令行入口：本地分析视频，输出 dna.json + 关键帧 + 可选导出。
支持单文件分析、批量目录分析、AI 短剧/漫剧优化字段。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import exporter
from .analyzer import pipeline

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def analyze_single(video: str, outdir: str, **kwargs) -> dict:
    """分析单个视频，返回完整 DNA。"""
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    result = pipeline.analyze(
        video,
        work_dir=str(outdir),
        extract_keyframes=kwargs.get("keyframes", True),
        detector=kwargs.get("detector", "content"),
        detect_transitions=kwargs.get("transitions", True),
        describe_shots=kwargs.get("describe", True),  # 默认启用启发式描述
        vlm_backend=kwargs.get("vlm_backend", "auto"),
        vlm_model=kwargs.get("vlm_model", "gpt-4o"),
        keep_workdir=True,
    )
    result["_source_path"] = str(Path(video).resolve())

    # 写入 JSON
    out_json = outdir / "dna.json"
    out_json.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def do_export(result: dict, fmt: str | None, outdir: Path) -> dict:
    """执行导出，返回 {fmt: path}。"""
    if fmt is None:
        return {}

    export_map = {
        "edl": (exporter.export_edl, "dna.edl"),
        "fcp7xml": (exporter.export_fcp7xml, "dna.xml"),
        "cutmark": (exporter.export_cutmark, "dna_cuts.json"),
        "srt": (exporter.export_srt, "dna_subtitles.srt"),
    }

    files = {}
    if fmt == "all":
        return exporter.export_all(result, outdir)

    func, fname = export_map.get(fmt, (None, None))
    if func:
        path = str(outdir / fname)
        func(result, path)
        files[fmt] = path
    return files


def print_summary(result: dict, export_files: dict):
    """打印带有 AI 短剧/漫剧优化字段的分析摘要。"""
    m = result.get("meta", {})
    a = result.get("audio", {})
    shots = result.get("shots", [])

    print("[OK] 分析完成")
    print(f"     镜头数: {m.get('total_shots', 0)}")
    print(f"     平均镜头时长: {m.get('avg_shot_duration', 0):.3f}s")
    print(f"     卡点率: {m.get('beat_alignment_ratio', 0) * 100:.0f}%")
    print(f"     BPM: {a.get('tempo_bpm')} | 节拍点: {a.get('beat_count')}")

    # AI 短剧/漫剧优化字段
    scene_types = {}
    face_total = 0
    emotions = {}
    described = 0
    for s in shots:
        st = s.get("scene_type")
        if st:
            scene_types[st] = scene_types.get(st, 0) + 1
        face_total += s.get("face_count", 0) or 0
        em = s.get("emotion")
        if em:
            emotions[em] = emotions.get(em, 0) + 1
        if s.get("content"):
            described += 1

    if scene_types:
        parts = sorted(scene_types.items(), key=lambda x: -x[1])
        print(f"     镜头类型: {', '.join(f'{k}×{v}' for k, v in parts)}")
    if described:
        print(f"     已描述: {described}/{len(shots)}")
    if face_total > 0:
        print(f"     人脸总数: {face_total}")
    if emotions:
        top_emotion = max(emotions, key=emotions.get)
        print(f"     主导情绪: {top_emotion}")

    # 音频
    sr = a.get("speech_regions", [])
    if sr:
        print(f"     语音段落: {len(sr)}")
    sfx = a.get("sfx_candidates", [])
    if sfx:
        print(f"     音效候选: {len(sfx)}")

    print(f"     摘要: {result.get('summary', '')}")
    for fmt, path in export_files.items():
        print(f"     导出 [{fmt}]: {path}")


def main():
    ap = argparse.ArgumentParser(
        description="视频剪辑结构逆向分析引擎 — AI 短剧/漫剧优化版",
        epilog=(
            "示例:\n"
            "  # 单文件分析\n"
            "  python -m app.cli test.mp4 -o output\n"
            "  python -m app.cli test.mp4 -o output --vlm-backend heuristic --export all\n"
            "  # 批量处理目录中所有视频\n"
            "  python -m app.cli --input-dir ./videos -o output --export srt\n"
            "  # 仅导出 SRT 字幕\n"
            "  python -m app.cli test.mp4 -o output --no-keyframes --no-transitions --export srt\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("video", nargs="?", help="输入视频文件路径（单个文件）")
    ap.add_argument("--input-dir", help="批量处理目录中所有 mp4/mov 文件（替代 video 参数）")
    ap.add_argument("-o", "--outdir", default="output", help="输出目录（默认 output）")
    ap.add_argument("--no-keyframes", action="store_true", help="不提取关键帧")
    ap.add_argument("--no-describe", action="store_true", help="禁用语义描述")
    ap.add_argument("--detector", default="content", choices=["content", "adaptive"],
                    help="镜头检测器（默认 content）")
    ap.add_argument("--no-transitions", action="store_true", help="跳过转场分类")
    ap.add_argument("--vlm-backend", default="auto",
                    choices=["auto", "openai", "qwen", "heuristic"],
                    help="VLM 后端（默认 auto → heuristic 降级）")
    ap.add_argument("--vlm-model", default="gpt-4o",
                    help="VLM 模型（OpenAI: gpt-4o, Qwen: qwen-vl-max）")
    ap.add_argument("--export", default=None,
                    choices=["edl", "fcp7xml", "cutmark", "srt", "all"],
                    help="导出格式（写入输出目录）")
    args = ap.parse_args()

    if not args.video and not args.input_dir:
        ap.print_help()
        sys.exit(1)

    outdir_base = Path(args.outdir)
    outdir_base.mkdir(parents=True, exist_ok=True)

    all_results = []

    if args.input_dir:
        # 批量模式
        input_dir = Path(args.input_dir)
        videos = sorted(
            p for p in input_dir.iterdir()
            if p.suffix.lower() in (".mp4", ".mov", ".mkv", ".webm", ".avi")
        )
        if not videos:
            print(f"[WARN] 目录中未找到视频文件: {input_dir}")
            sys.exit(1)

        print(f"[BATCH] 找到 {len(videos)} 个视频，开始批量处理...")
        for vi, vp in enumerate(videos, 1):
            v_outdir = outdir_base / vp.stem
            print(f"\n[{vi}/{len(videos)}] {vp.name}")
            try:
                dna = analyze_single(
                    str(vp), str(v_outdir),
                    keyframes=not args.no_keyframes,
                    detector=args.detector,
                    transitions=not args.no_transitions,
                    describe=not args.no_describe,
                    vlm_backend=args.vlm_backend,
                    vlm_model=args.vlm_model,
                )
                export_files = do_export(dna, args.export, v_outdir)
                print_summary(dna, export_files)
                all_results.append(dna)
            except Exception as e:
                print(f"      [ERROR] {e}")

        print(f"\n[BATCH] 完成 {len(all_results)}/{len(videos)} 个视频")
    else:
        # 单文件模式
        dna = analyze_single(
            args.video, args.outdir,
            keyframes=not args.no_keyframes,
            detector=args.detector,
            transitions=not args.no_transitions,
            describe=not args.no_describe,
            vlm_backend=args.vlm_backend,
            vlm_model=args.vlm_model,
        )
        export_files = do_export(dna, args.export, Path(args.outdir))
        print_summary(dna, export_files)


if __name__ == "__main__":
    main()
