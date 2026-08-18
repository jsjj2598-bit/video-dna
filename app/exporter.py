"""剪辑 DNA → EDL / FCP7XML / Cutmark JSON 导出。

支持三种格式：
- CMX3600 EDL：通用离线编辑交换格式
- FCP7 XML：Final Cut Pro 7 兼容交换格式
- Cutmark JSON：极简切点清单
"""
from __future__ import annotations

from pathlib import Path
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def _tc(seconds: float, fps: float = 30.0) -> str:
    """秒 → SMPTE 时间码 (HH:MM:SS:FF)。"""
    total_frames = int(round(seconds * fps))
    ff = total_frames % int(fps)
    total_secs = total_frames // int(fps)
    hh = total_secs // 3600
    mm = (total_secs % 3600) // 60
    ss = total_secs % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}:{ff:02d}"


def _transition_keyword(ttype: str | None) -> str:
    """转场类型 → EDL/FCP transition hint。"""
    mapping = {
        "cut": "C",
        "dissolve": "D",
        "fade": "F",
        "white_flash": "W",
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
        trans_str = f" {trans}     " if trans != "C" else ""

        lines.append(
            f"{event_num:03d}  AX       V     C        "
            f"{src_in} {src_out} {rec_in} {rec_out}"
        )

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
            dur = sh.get("transition_confidence", 0.5) * 30  # 帧数
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


def export_fcp7xml(dna: dict, output_path: str | Path, fps: float = 30.0) -> str:
    """导出 FCP 7 XML。"""
    shots = dna.get("shots", [])
    meta = dna.get("meta", {})
    fps = meta.get("fps", fps)
    duration_sec = meta.get("duration", 0)
    duration_frames = int(round(duration_sec * fps))

    xmeml = Element("xmeml", attrib={"version": "4"})
    seq = SubElement(xmeml, "sequence")
    SubElement(seq, "duration").text = str(duration_frames)
    SubElement(seq, "rate").append(_xml_element("timebase", str(int(fps))))

    media = SubElement(seq, "media")
    video = SubElement(media, "video")

    # Format
    fmt = SubElement(video, "format")
    SubElement(fmt, "samplecharacteristics").append(
        _xml_element("rate", attrib={"ntsc": "FALSE"})
    )
    fmt.find("samplecharacteristics").append(
        _xml_element("timebase", str(int(fps)))
    )

    track = SubElement(video, "track")

    for i, sh in enumerate(shots):
        clip = SubElement(track, "clipitem")
        clip_id = f"shot_{i:03d}"
        SubElement(clip, "name").text = f"Shot {i} ({sh.get('transition', 'cut')})"

        # 时长
        dur = int(round(sh["duration"] * fps))
        SubElement(clip, "duration").text = str(dur)
        SubElement(clip, "in").text = "0"
        SubElement(clip, "out").text = str(dur)

        # 时间轴位置
        start = int(round(sh["start"] * fps))
        SubElement(clip, "start").text = str(start)
        SubElement(clip, "end").text = str(start + dur)

        # 文件引用
        file = SubElement(clip, "file")
        SubElement(file, "name").text = clip_id
        SubElement(file, "pathurl").text = f"file://shots/{clip_id}.jpg" if sh.get("keyframe") else ""

        # 转场
        if sh.get("transition") and sh["transition"] != "cut":
            trans_elem = SubElement(clip, "transition")
            # 转场长度（帧）
            trans_dur = max(1, int(round(dur * 0.1)))  # 10% of clip as transition
            SubElement(trans_elem, "start").text = str(trans_dur)
            SubElement(trans_elem, "end").text = str(trans_dur + 1)
            trans_name = SubElement(trans_elem, "effect")
            SubElement(trans_name, "name").text = sh["transition"]

        # 台词元数据
        if sh.get("transcript"):
            SubElement(clip, "comment").text = f"DIALOG: {sh['transcript'][:200]}"
        if sh.get("beat_aligned"):
            SubElement(clip, "comment").text = (
                (clip.findtext("comment") or "") + "\nBEAT_ALIGNED"
            )

    # 音频
    audio_info = dna.get("audio", {})
    audio_track = SubElement(media, "audio")
    at = SubElement(audio_track, "track")
    SubElement(at, "name").text = "DNA Audio Analysis"

    if audio_info.get("beats"):
        for b in audio_info["beats"]:
            bf = int(round(b * fps))
            clip_elem = SubElement(at, "clipitem")
            SubElement(clip_elem, "name").text = "beat"
            SubElement(clip_elem, "start").text = str(bf)
            SubElement(clip_elem, "duration").text = "1"

    if audio_info.get("sfx_candidates"):
        for sfx in audio_info["sfx_candidates"]:
            bf = int(round(sfx["time"] * fps))
            clip_elem = SubElement(at, "clipitem")
            SubElement(clip_elem, "name").text = "sfx"
            SubElement(clip_elem, "start").text = str(bf)
            SubElement(clip_elem, "duration").text = "2"
            if "class" in sfx:
                SubElement(clip_elem, "comment").text = sfx["class"]

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
        hh = int(sec // 3600)
        mm = int((sec % 3600) // 60)
        ss = int(sec % 60)
        ms = int(round((sec - int(sec)) * 1000))
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