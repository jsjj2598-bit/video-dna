"""生成含多种转场的测试视频：硬切、叠化、闪白、淡入淡出。

顺序：red —[硬切]→ green —[叠化]→ blue —[闪白]→ yellow —[淡入淡出]→ cyan，
并叠加一条 120 BPM 点击音轨供音频分析。
仅依赖系统 ffmpeg。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

FFMPEG = "ffmpeg"


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main() -> None:
    out = Path("test_data")
    out.mkdir(exist_ok=True)

    colors = ["red", "green", "blue", "yellow", "cyan"]
    segs = []
    for i, c in enumerate(colors):
        seg = out / f"tseg_{i}.mp4"
        run([
            FFMPEG, "-y", "-f", "lavfi", "-i",
            f"color=c={c}:size=640x360:rate=30:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(seg),
        ])
        segs.append(seg)

    # 1) 硬切：red + green 用 concat 过滤器（确保 PTS 连续）
    ab = out / "ab.mp4"
    run([
        FFMPEG, "-y", "-i", str(segs[0]), "-i", str(segs[1]),
        "-filter_complex", "[0][1]concat=n=2:v=1:a=0[out]",
        "-map", "[out]", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(ab),
    ])

    # 2) 叠化 green→blue：xfade fade
    # 3) 闪白 blue→yellow：xfade fadewhite
    # 4) 淡入淡出 yellow→cyan：xfade fadeblack
    fc = (
        "[0][1]xfade=transition=fade:duration=0.5:offset=3.5[v1];"
        "[v1][2]xfade=transition=fadewhite:duration=0.3:offset=5.0[v2];"
        "[v2][3]xfade=transition=fadeblack:duration=0.5:offset=6.7[v3]"
    )
    final = out / "transitions.mp4"
    run([
        FFMPEG, "-y",
        "-i", str(ab), "-i", str(segs[2]), "-i", str(segs[3]), "-i", str(segs[4]),
        "-filter_complex", fc, "-map", "[v3]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(final),
    ])

    # 120 BPM 点击音轨
    click = out / "click.wav"
    run([
        FFMPEG, "-y", "-f", "lavfi", "-i",
        "aevalsrc='0.6*sin(2*PI*1000*t)*lt(mod(t,0.5),0.05)':s=22050:d=10",
        "-c:a", "pcm_s16le", str(click),
    ])

    final_audio = out / "transitions_audio.mp4"
    run([
        FFMPEG, "-y", "-i", str(final), "-i", str(click),
        "-c:v", "copy", "-c:a", "aac", "-shortest", str(final_audio),
    ])
    print(f"[OK] 测试视频: {final_audio.resolve()}")


if __name__ == "__main__":
    main()
