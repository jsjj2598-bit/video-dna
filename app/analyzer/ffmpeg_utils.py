"""FFmpeg/ffprobe 工具：元信息探测、音频抽取、关键帧抽取。

注意：这里刻意用「stdout 重定向到文件」而不是管道捕获输出，
以避开 Windows 沙箱下对命名管道的限制。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from contextlib import suppress
from pathlib import Path


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg  # 兜底：捆绑的静态二进制
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("未找到 ffmpeg，请安装 ffmpeg 或 pip install imageio-ffmpeg") from exc


def find_ffprobe() -> str | None:
    return shutil.which("ffprobe")


def _parse_fraction(text: str) -> float | None:
    try:
        text = str(text).strip()
        if not text or text in ("0/0", "N/A"):
            return None
        if "/" in text:
            num, den = text.split("/", 1)
            den = float(den)
            return float(num) / den if den else None
        return float(text)
    except Exception:
        return None


def _probe_fallback(video_path: str) -> dict:
    """无 ffprobe 时用 PySceneDetect 的 open_video 兜底。"""
    from scenedetect import open_video

    video = open_video(str(video_path))
    w, h = video.frame_size if video.frame_size else (0, 0)
    return {
        "duration": round(float(video.duration.get_seconds()), 3),
        "resolution": f"{int(w)}x{int(h)}" if w and h else None,
        "width": int(w or 0),
        "height": int(h or 0),
        "fps": round(float(video.frame_rate), 3),
        "video_codec": None,
        "audio_codec": None,
        "size_bytes": 0,
    }


def probe(video_path: str) -> dict:
    ffprobe = find_ffprobe()
    if not ffprobe:
        return _probe_fallback(video_path)

    fd, out_json = tempfile.mkstemp(suffix=".json")
    os.close(fd)
    try:
        cmd = [
            ffprobe, "-v", "error", "-print_format", "json",
            "-show_format", "-show_streams", str(video_path),
        ]
        with open(out_json, "w", encoding="utf-8") as fh:
            subprocess.run(cmd, stdout=fh, stderr=subprocess.DEVNULL, check=True)
        with open(out_json, encoding="utf-8") as fh:
            data = json.load(fh)
    finally:
        with suppress(OSError):
            os.unlink(out_json)

    fmt = data.get("format", {})
    duration = _parse_fraction(fmt.get("duration")) or 0.0

    video = {}
    audio = {}
    for s in data.get("streams", []):
        if s.get("codec_type") == "video" and not video:
            video = s
        elif s.get("codec_type") == "audio" and not audio:
            audio = s

    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)
    fps = _parse_fraction(video.get("avg_frame_rate")) or _parse_fraction(video.get("r_frame_rate")) or 0.0

    return {
        "duration": round(float(duration), 3),
        "resolution": f"{width}x{height}" if width and height else None,
        "width": width,
        "height": height,
        "fps": round(float(fps), 3),
        "video_codec": video.get("codec_name"),
        "audio_codec": audio.get("codec_name"),
        "size_bytes": int(fmt.get("size") or 0),
    }


def extract_audio(video_path: str, out_dir: str, sr: int = 22050) -> str:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    wav = out_dir / "audio.wav"
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y", "-i", str(video_path),
        "-vn", "-ac", "1", "-ar", str(sr), "-f", "wav", str(wav),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return str(wav)


def extract_frame(video_path: str, time_sec: float, out_path: str) -> str:
    ffmpeg = find_ffmpeg()
    cmd = [
        ffmpeg, "-y", "-i", str(video_path),
        "-ss", f"{max(0.0, time_sec):.3f}",
        "-frames:v", "1", "-q:v", "2", str(out_path),
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return str(out_path)


def extract_window_frames(
    video_path: str,
    start_sec: float,
    duration_sec: float,
    out_dir: str,
    fps: int = 25,
    width: int = 320,
) -> list[Path]:
    """在 [start_sec, start_sec+duration_sec] 时间窗内按 fps 抽帧到 out_dir。

    `-ss` 放在 `-i` 之后保证精确起始点（短视频解码开销可忽略）。
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    pattern = str(out_dir / "f_%04d.jpg")
    cmd = [
        ffmpeg, "-y", "-i", str(video_path),
        "-ss", f"{max(0.0, start_sec):.3f}",
        "-t", f"{duration_sec:.3f}",
        "-vf", f"fps={fps},scale={width}:-2",
        "-q:v", "2", pattern,
    ]
    subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return sorted(out_dir.glob("f_*.jpg"))
