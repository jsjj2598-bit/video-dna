from app.services.templates import build_cut_plan


def test_dense_template_is_clamped_to_short_target():
    template = {
        "meta": {"duration": 10},
        "shots": [{"start": index, "end": index + 1, "duration": 1} for index in range(10)],
    }
    target = {"meta": {"duration": 1}, "audio": {"beats": []}}

    plan = build_cut_plan(template, target)

    assert plan["cuts"]
    assert plan["cuts"][0]["start"] == 0
    assert plan["cuts"][-1]["end"] == 1
    assert all(0 <= cut["start"] < cut["end"] <= 1 for cut in plan["cuts"])
    assert all(cut["duration"] >= 0.25 for cut in plan["cuts"])


def test_cut_plan_boundaries_are_contiguous():
    template = {
        "meta": {"duration": 4},
        "shots": [
            {"start": 0, "end": 1},
            {"start": 1, "end": 2},
            {"start": 2, "end": 4},
        ],
    }
    target = {"meta": {"duration": 8}, "audio": {"beats": [2.05, 4.1]}}

    cuts = build_cut_plan(template, target)["cuts"]

    assert all(left["end"] == right["start"] for left, right in zip(cuts, cuts[1:], strict=False))
    assert cuts[-1]["end"] == 8
