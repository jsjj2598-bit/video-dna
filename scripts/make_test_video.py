"""生成合成测试视频：5 个纯色镜头（各 2s）+ 120 BPM 节拍音轨。

纯色镜头内部帧完全相同、镜头间差异巨大，便于验证镜头切分；
50ms 的 1kHz 突发音每 0.5s 一次，便于验证节拍检测。
仅依赖系统 ffmpeg，不依赖 Python 第三方库。
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

FFMPEG = "ffmpeg"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    out_dir = Path("test_data")
    out_dir.mkdir(exist_ok=True)

    colors = ["red", "green", "blue", "yellow", "cyan"]
    segments = []
    for i, c in enumerate(colors):
        seg = out_dir / f"seg_{i}.mp4"
        run([
            FFMPEG, "-y", "-f", "lavfi", "-i",
            f"color=c={c}:size=640x360:rate=30:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(seg),
        ])
        segments.append(seg)

    # concat 过滤器确保 PTS 连续（concat 复用器 + -c copy 会破坏 PTS）
    inputs_cmd = []
    for seg in segments:
        inputs_cmd += ["-i", str(seg)]
    fc = "".join(f"[{i}]" for i in range(len(segments))) + f"concat=n={len(segments)}:v=1:a=0[out]"
    video_only = out_dir / "video_only.mp4"
    run([
        FFMPEG, "-y",
    ] + inputs_cmd + [
        "-filter_complex", fc, "-map", "[out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video_only),
    ])

    # 120 BPM：每 0.5s 一个 50ms 的 1kHz 突发音，共 10s
    click = out_dir / "click.wav"
    run([
        FFMPEG, "-y", "-f", "lavfi", "-i",
        "aevalsrc='0.6*sin(2*PI*1000*t)*lt(mod(t,0.5),0.05)':s=22050:d=10",
        "-c:a", "pcm_s16le", str(click),
    ])

    final = out_dir / "sample.mp4"
    run([
        FFMPEG, "-y", "-i", str(video_only), "-i", str(click),
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(final),
    ])
    print(f"[OK] 测试视频已生成: {final.resolve()}")


if __name__ == "__main__":
    main()
