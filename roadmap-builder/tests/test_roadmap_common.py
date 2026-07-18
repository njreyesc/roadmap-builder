"""Тесты недельной сетки и клиппинга полос (roadmap_common)."""
import pytest

from roadmap_common import Timeline, monday, parse_date


def test_monday_snaps_to_week_start():
    # 2026-07-15 — среда; понедельник её недели — 2026-07-13
    assert monday(parse_date("2026-07-15")) == parse_date("2026-07-13")
    # понедельник остаётся собой
    assert monday(parse_date("2026-07-13")) == parse_date("2026-07-13")


def test_timeline_week_count_inclusive():
    tl = Timeline("2026-07-13", "2026-07-27")  # три понедельника: 13, 20, 27
    assert tl.n == 3
    assert tl.weeks[0] == parse_date("2026-07-13")
    assert tl.weeks[-1] == parse_date("2026-07-27")


def test_timeline_empty_range_raises():
    with pytest.raises(ValueError):
        Timeline("2026-07-27", "2026-07-13")


def test_week_index_raw_can_go_negative_and_past_end():
    tl = Timeline("2026-07-13", "2026-07-27")
    assert tl.week_index_raw("2026-07-06") == -1     # до начала
    assert tl.week_index_raw("2026-07-13") == 0
    assert tl.week_index_raw("2026-08-03") == 3      # за концом (n=3)


def test_week_index_clamp_vs_none():
    tl = Timeline("2026-07-13", "2026-07-27")
    assert tl.week_index("2026-07-06", clamp=True) == 0
    assert tl.week_index("2026-08-31", clamp=True) == 2
    assert tl.week_index("2026-07-06", clamp=False) is None


def test_clip_bar_fully_inside():
    tl = Timeline("2026-07-13", "2026-08-10")  # 5 недель, 0..4
    i0, i1, cut_l, cut_r = tl.clip_bar("2026-07-20", "2026-08-03")
    assert (i0, i1) == (1, 3)
    assert not cut_l and not cut_r


def test_clip_bar_marks_cuts_at_both_edges():
    tl = Timeline("2026-07-13", "2026-08-10")  # 5 недель
    i0, i1, cut_l, cut_r = tl.clip_bar("2026-07-06", "2026-08-31")
    assert (i0, i1) == (0, 4)
    assert cut_l and cut_r


def test_clip_bar_entirely_outside_returns_none():
    tl = Timeline("2026-07-13", "2026-08-10")
    assert tl.clip_bar("2026-09-01", "2026-09-15") is None


def test_clip_bar_swaps_reversed_dates(capsys):
    tl = Timeline("2026-07-13", "2026-08-10")
    res = tl.clip_bar("2026-08-03", "2026-07-20", label="X")
    assert res is not None
    i0, i1, _, _ = res
    assert i0 <= i1
    assert "поменяны местами" in capsys.readouterr().out


def test_month_spans_group_consecutive_weeks():
    tl = Timeline("2026-07-13", "2026-08-10")  # июль: 13,20,27 ; август: 3,10
    spans = tl.month_spans()
    assert spans[0] == ("Июль 2026", 0, 2)
    assert spans[1] == ("Август 2026", 3, 4)
