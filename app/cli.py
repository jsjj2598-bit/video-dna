"""命令行入口：本地分析视频，输出 dna.json + 关键帧 + 可选导出。"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from .analyzer import pipeline
from . import exporter


def main():
    ap = argparse.ArgumentParser(
        description="视频剪辑结构逆向分析引擎",
        epilog=(
            "示例:\n"
            "  python -m app.cli test.mp4 -o result\n"
            "  python -m app.cli test.mp4 --describe --vlm-backend auto\n"
            "  python -m app.cli test.mp4 --export edl\n"
            "  python -m app.cli test.mp4 --export all\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("video", help="输入视频文件路径")
    ap.add_argument("-o", "--outdir", default="output", help="输出目录（默认 output）")
    ap.add_argument("--no-keyframes", action="store_true", help="不提取关键帧")
    ap.add_argument("--detector", default="content", choices=["content", "adaptive"],
                    help="镜头检测器（默认 content）")
    ap.add_argument("--no-transitions", action="store_true", help="跳过转场分类")
    ap.add_argument("--describe", action="store_true",
                    help="启用多模态语义描述（需 API Key 或使用 OpenCV 降级）")
    ap.add_argument("--vlm-backend", default="auto", choices=["auto", "openai", "qwen", "heuristic"],
                    help="VLM 后端（默认 auto → openai → qwen → heuristic 降级）")
    ap.add_argument("--vlm-model", default="gpt-4o",
                    help="VLM 模型（OpenAI: gpt-4o, Qwen: qwen-vl-max）")
    ap.add_argument("--export", default=None,
                    choices=["edl", "fcp7xml", "cutmark", "all"],
                    help="导出格式（写入输出目录）")
    args = ap.parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    result = pipeline.analyze(
        args.video,
        work_dir=str(outdir),
        extract_keyframes=not args.no_keyframes,
        detector=args.detector,
        detect_transitions=not args.no_transitions,
        describe_shots=args.describe,
        vlm_backend=args.vlm_backend,
        vlm_model=args.vlm_model,
        keep_workdir=True,
    )

    # 写入 JSON
    out_json = outdir / "dna.json"
    out_json.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # 导出
    export_files = {}
    if args.export:
        fmt = args.export
        if fmt == "all":
            export_files = exporter.export_all(result, outdir)
        elif fmt == "edl":
            path = str(outdir / "dna.edl")
            exporter.export_edl(result, path)
            export_files["edl"] = path
        elif fmt == "fcp7xml":
            path = str(outdir / "dna.xml")
            exporter.export_fcp7xml(result, path)
            export_files["fcp7xml"] = path
        elif fmt == "cutmark":
            path = str(outdir / "dna_cuts.json")
            exporter.export_cutmark(result, path)
            export_files["cutmark"] = path

    # 打印摘要
    print(f"[OK] 分析完成 -> {out_json}")
    print(f"     镜头数: {result['meta']['total_shots']}")
    print(f"     平均镜头时长: {result['meta']['avg_shot_duration']}s")
    if result['meta'].get('transitions'):
        parts = [f"{k}={v}" for k, v in result['meta']['transitions'].items()]
        print(f"     转场: {', '.join(parts)}")
    print(f"     卡点率: {result['meta']['beat_alignment_ratio'] * 100:.0f}%")
    a = result.get("audio", {})
    print(f"     BPM: {a.get('tempo_bpm')}")
    print(f"     节拍点: {a.get('beat_count')}")
    sr = a.get("speech_regions", [])
    if sr:
        print(f"     语音段落: {len(sr)}")
    sfx = a.get("sfx_candidates", [])
    if sfx:
        print(f"     音效候选: {len(sfx)}")
    described = sum(1 for s in result.get("shots", []) if s.get("content"))
    if described:
        print(f"     已描述镜头: {described}/{len(result.get('shots', []))}")
    print(f"     摘要: {result['summary']}")
    if export_files:
        for fmt, path in export_files.items():
            print(f"     导出 [{fmt}]: {path}")


if __name__ == "__main__":
    main()