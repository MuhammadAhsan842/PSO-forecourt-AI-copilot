"""Pilot report composition — precision must come from feedback joined by kind."""

from __future__ import annotations

from scripts.report import compose_report


def test_precision_computed_per_kind_from_feedback() -> None:
    ctx = compose_report(
        days=7,
        event_counts={"drive_off": 10, "loitering": 6},
        feedback_by_kind={
            "drive_off": {"true": 8, "false": 2},   # 80% precision
            "loitering": {"true": 1, "false": 4},   # 20% precision on 5 reviewed → tuning note
        },
        camera_rows=[{"online": True}, {"online": False}],
    )
    by_kind = {k["kind"]: k for k in ctx["per_kind"]}
    assert by_kind["drive_off"]["precision"] == 0.8
    assert by_kind["loitering"]["precision"] == 0.2
    # Overall precision = 9 true / 15 reviewed.
    assert round(ctx["precision"], 3) == round(9 / 15, 3)
    assert ctx["cameras_online"] == 1
    assert any("loitering" in n for n in ctx["tuning_notes"])


def test_before_after_shows_delta() -> None:
    ctx = compose_report(
        days=7,
        event_counts={"drive_off": 10},
        feedback_by_kind={"drive_off": {"true": 9, "false": 1}},  # 90%
        camera_rows=[],
        prev_event_counts={"drive_off": 8},
        prev_feedback_by_kind={"drive_off": {"true": 4, "false": 4}},  # 50%
    )
    metrics = {r["metric"]: r for r in ctx["before_after"]}
    assert metrics["events"]["previous"] == 8
    assert metrics["events"]["current"] == 10
    assert metrics["precision"]["delta"] == "+40 pts"


def test_no_feedback_yields_none_precision_not_zero() -> None:
    ctx = compose_report(
        days=7,
        event_counts={"queue_dwell": 3},
        feedback_by_kind={},
        camera_rows=[],
    )
    assert ctx["precision"] is None
    assert ctx["per_kind"][0]["precision"] is None
