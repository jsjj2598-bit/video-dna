"""剪辑 DNA → EDL / FCP7XML / Cutmark JSON 导出。

支持三种格式：
- CMX3600 EDL：通用离线编辑交换格式
- FCP7 XML：Final Cut Pro 7 兼容交换格式
- Cutmark JSON：极简切点清单
"""
from __future__ import annotations

from pathlib import Path
from xml.dom import minidom
from xml.etree.ElementTree import Element, SubElement, tostring


def _tc(seconds: float, fps: float = 30.0) -> str:
    """秒 → SMPTE 时间码 (HH:MM:SS:FF)。"""
    fps_round = int(round(fps))
    total_frames = int(round(seconds * fps))
    ff = total_frames % fps_round
    total_secs = total_frames // fps_round
    hh = total_secs // 3600
    mm = (total_secs % 3600) // 60
    ss = total_secs % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def _transition_keyword(ttype: str | None) -> str:
    """转场类型 → EDL/FCP transition hint。"""
    mapping = {
        "cut": "C",
        "dissolve": "D",
        # CMX3600 has no portable fade/flash opcode. Export them as dissolves
        # and preserve the semantic type in comments below.
        "fade": "D",
        "white_flash": "D",
    }
    return mapping.get(ttype, "C")


def export_edl(dna: dict, output_path: str | Path, fps: float = 30.0) -> str:
    """导出 CMX3600 EDL 文件。"""
    shots = dna.get("shots", [])
    meta = dna.get("meta", {})
    fps = meta.get("fps", fps)

    lines = [
        "TITLE: Video DNA Analysis",
        "FCM: NON-DROP FRAME",
        "",
    ]

    for i, sh in enumerate(shots):
        event_num = i + 1
        src_in = _tc(sh["start"], fps)
        src_out = _tc(sh["end"], fps)
        rec_in = src_in
        rec_out = src_out

        trans = _transition_keyword(sh.get("transition"))
        if trans == "D":
            transition_frames = max(1, int(round(float(sh.get("transition_duration", 0.5)) * fps)))
            event_type = f"D {transition_frames:03d}"
        else:
            event_type = "C    "
        lines.append(f"{event_num:03d}  AX       V     {event_type}    {src_in} {src_out} {rec_in} {rec_out}")

        # 注释信息（关键帧、转场、台词）
        comments = []
        if sh.get("keyframe"):
            comments.append(f"KEYFRAME: frames/{sh['keyframe']}")
        if sh.get("transition"):
            comments.append(f"TRANSITION: {sh['transition']}")
        if sh.get("transcript"):
            # EDL 注释每行 60 字符以内
            tr = sh["transcript"][:60]
            comments.append(f"DIALOG: {tr}")
        for c in comments:
            lines.append(f"* {c}")

        # 转场详细信息
        if sh.get("transition") and sh["transition"] in ("dissolve", "fade", "white_flash"):
            dur = float(sh.get("transition_duration", 0.5)) * fps
            lines.append(f"* EFFECT NAME: {sh['transition']}")
            lines.append(f"* EFFECT DURATION: {int(dur)}")

        lines.append("")

    # 尾部统计
    lines.append(f"* TOTAL EVENTS: {len(shots)}")
    lines.append(f"* DURATION: {_tc(meta.get('duration', 0), fps)}")
    lines.append("")

    text = "\n".join(lines)
    Path(output_path).write_text(text, encoding="utf-8")
    return text


def _xml_element(name: str, text: str | None = None, attrib: dict | None = None):
    el = Element(name, attrib or {})
    if text is not None:
        el.text = text
    return el


def export_fcp7xml(
    dna: dict,
    output_path: str | Path,
    fps: float = 30.0,
    source_path: str | Path | None = None,
) -> str:
    """导出 FCP 7 XML。"""
    shots = dna.get("shots", [])
    meta = dna.get("meta", {})
    fps = meta.get("fps", fps)
    duration_sec = meta.get("duration", 0)
    duration_frames = int(round(duration_sec * fps))
    source_path = source_path or dna.get("_source_path")
    source_uri = Path(source_path).resolve().as_uri() if source_path else ""

    xmeml = Element("xmeml", attrib={"version": "4"})
    seq = SubElement(xmeml, "sequence")
    SubElement(seq, "duration").text = str(duration_frames)
    sequence_rate = SubElement(seq, "rate")
    SubElement(sequence_rate, "timebase").text = str(int(round(fps)))
    SubElement(sequence_rate, "ntsc").text = "TRUE" if abs(fps - round(fps)) > 0.01 else "FALSE"

    media = SubElement(seq, "media")
    video = SubElement(media, "video")

    # Format
    fmt = SubElement(video, "format")
    characteristics = SubElement(fmt, "samplecharacteristics")
    format_rate = SubElement(characteristics, "rate")
    SubElement(format_rate, "timebase").text = str(int(round(fps)))
    SubElement(format_rate, "ntsc").text = "TRUE" if abs(fps - round(fps)) > 0.01 else "FALSE"

    track = SubElement(video, "track")

    for i, sh in enumerate(shots):
        start = int(round(sh["start"] * fps))
        dur = int(round(sh["duration"] * fps))
        if i > 0 and sh.get("transition") and sh["transition"] != "cut":
            transition_frames = max(1, int(round(float(sh.get("transition_duration", 0.5)) * fps)))
            transition = SubElement(track, "transitionitem")
            SubElement(transition, "start").text = str(max(0, start - transition_frames // 2))
            SubElement(transition, "end").text = str(start + transition_frames // 2)
            SubElement(transition, "alignment").text = "center"
            effect = SubElement(transition, "effect")
            SubElement(effect, "name").text = sh["transition"]
            SubElement(effect, "effectid").text = "Cross Dissolve"
            SubElement(effect, "effecttype").text = "transition"
            SubElement(effect, "mediatype").text = "video"

        clip = SubElement(track, "clipitem")
        SubElement(clip, "name").text = f"Shot {i} ({sh.get('transition', 'cut')})"

        # 时长
        SubElement(clip, "duration").text = str(dur)
        source_in = int(round(sh["start"] * fps))
        source_out = int(round(sh["end"] * fps))
        SubElement(clip, "in").text = str(source_in)
        SubElement(clip, "out").text = str(source_out)

        # 时间轴位置
        SubElement(clip, "start").text = str(start)
        SubElement(clip, "end").text = str(start + dur)

        # 文件引用
        file = SubElement(clip, "file", attrib={"id": "source-media"})
        if i == 0:
            SubElement(file, "name").text = Path(source_path).name if source_path else "source-video"
            SubElement(file, "pathurl").text = source_uri
            SubElement(file, "duration").text = str(duration_frames)
            rate = SubElement(file, "rate")
            SubElement(rate, "timebase").text = str(int(round(fps)))
            SubElement(rate, "ntsc").text = "TRUE" if abs(fps - round(fps)) > 0.01 else "FALSE"

        # 台词元数据
        comments = []
        if sh.get("transcript"):
            comments.append(f"DIALOG: {sh['transcript'][:200]}")
        if sh.get("beat_aligned"):
            comments.append("BEAT_ALIGNED")
        if comments:
            SubElement(clip, "comment").text = "\n".join(comments)

    # Beats and sound effects are timeline markers, not fake audio clips.
    audio_info = dna.get("audio", {})
    markers = [("Beat", beat, "Detected beat") for beat in audio_info.get("beats", [])]
    markers.extend(
        ("SFX", item.get("time", 0), item.get("class", "Sound effect candidate"))
        for item in audio_info.get("sfx_candidates", [])
    )
    for name, seconds, comment in markers:
        frame = int(round(float(seconds) * fps))
        marker = SubElement(seq, "marker")
        SubElement(marker, "name").text = name
        SubElement(marker, "comment").text = str(comment)
        SubElement(marker, "in").text = str(frame)
        SubElement(marker, "out").text = str(frame)

    # 美化输出
    rough = tostring(xmeml, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ")
    # 去掉 XML 声明（FCP 不需要）
    lines = pretty.splitlines()
    if lines[0].startswith("<?xml"):
        lines = lines[1:]
    text = "\n".join(lines)

    Path(output_path).write_text(text, encoding="utf-8")
    return text


def export_cutmark(dna: dict, output_path: str | Path) -> dict:
    """导出极简切点清单（JSON）。"""
    shots = dna.get("shots", [])
    meta = dna.get("meta", {})
    audio = dna.get("audio", {})

    cutlist = []
    for sh in shots:
        entry = {
            "index": sh["index"],
            "start_sec": sh["start"],
            "end_sec": sh["end"],
            "duration_sec": sh["duration"],
            "transition": sh.get("transition"),
            "beat_aligned": sh.get("beat_aligned"),
        }
        if sh.get("transcript"):
            entry["transcript"] = sh["transcript"]
        if sh.get("content"):
            entry["content"] = sh["content"]
        cutlist.append(entry)

    result = {
        "format": "videodna-cutmark-v1",
        "meta": {
            "duration_sec": meta.get("duration"),
            "fps": meta.get("fps"),
            "resolution": meta.get("resolution"),
            "total_shots": len(shots),
            "avg_shot_sec": meta.get("avg_shot_duration"),
        },
        "cuts": cutlist,
        "beats": audio.get("beats", []),
        "bpm": audio.get("tempo_bpm"),
        "sfx": audio.get("sfx_candidates", []),
        "transcript": audio.get("text") or None,
    }

    import json
    text = json.dumps(result, ensure_ascii=False, indent=2)
    Path(output_path).write_text(text, encoding="utf-8")
    return result


def export_srt(dna: dict, output_path: str | Path) -> str:
    """将 speech_regions 导出为 SRT 字幕文件。"""
    output_path = Path(output_path)
    sr = dna.get("audio", {}).get("speech_regions", [])
    if not sr:
        output_path.write_text("", encoding="utf-8")
        return str(output_path)

    def _srt_ts(sec: float) -> str:
        total_ms = max(0, int(round(float(sec) * 1000)))
        hh, remainder = divmod(total_ms, 3_600_000)
        mm, remainder = divmod(remainder, 60_000)
        ss, ms = divmod(remainder, 1_000)
        return f"{hh:02d}:{mm:02d}:{ss:02d},{ms:03d}"

    lines = []
    for i, seg in enumerate(sr, 1):
        start_s = seg.get("start", 0.0)
        end_s = seg.get("end", 0.0)
        text = seg.get("text") or "[语音]"
        lines.append(str(i))
        lines.append(f"{_srt_ts(start_s)} --> {_srt_ts(end_s)}")
        lines.append(text)
        lines.append("")

    output_path.write_text("\n".join(lines), encoding="utf-8")
    return str(output_path)


def export_all(dna: dict, out_dir: str | Path, fps: float = 30.0):
    """一键导出所有格式（含 SRT 字幕）。"""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    export_edl(dna, out_dir / "dna.edl", fps=fps)
    export_fcp7xml(dna, out_dir / "dna.xml", fps=fps)
    export_cutmark(dna, out_dir / "dna_cuts.json")
    export_srt(dna, out_dir / "dna_subtitles.srt")

    return {
        "edl": str(out_dir / "dna.edl"),
        "fcp7xml": str(out_dir / "dna.xml"),
        "cutmark": str(out_dir / "dna_cuts.json"),
        "srt": str(out_dir / "dna_subtitles.srt"),
    }
