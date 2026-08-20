from app import exporter


def _dna() -> dict:
    return {
        "meta": {"duration": 2, "fps": 30, "resolution": "640x360"},
        "audio": {"beats": [], "sfx_candidates": [], "speech_regions": []},
        "shots": [
            {"index": 0, "start": 0, "end": 1, "duration": 1, "transition": "cut", "keyframe": "shot_000.jpg"},
            {"index": 1, "start": 1, "end": 2, "duration": 1, "transition": "dissolve", "keyframe": "shot_001.jpg"},
        ],
    }


def test_edl_preserves_dissolve_opcode(tmp_path):
    output = tmp_path / "timeline.edl"

    text = exporter.export_edl(_dna(), output)

    event = next(line for line in text.splitlines() if line.startswith("002"))
    assert " V     D " in event


def test_srt_timestamp_carries_rounded_milliseconds(tmp_path):
    dna = _dna()
    dna["audio"]["speech_regions"] = [{"start": 1.9996, "end": 2.5, "text": "字幕"}]
    output = tmp_path / "subtitles.srt"

    exporter.export_srt(dna, output)

    assert "00:00:02,000 --> 00:00:02,500" in output.read_text(encoding="utf-8")
    assert ",1000" not in output.read_text(encoding="utf-8")


def test_fcp_xml_references_source_video(tmp_path):
    source = tmp_path / "source video.mp4"
    source.touch()
    output = tmp_path / "timeline.xml"

    text = exporter.export_fcp7xml(_dna(), output, source_path=source)

    assert source.resolve().as_uri() in text
    assert "file://shots/" not in text
