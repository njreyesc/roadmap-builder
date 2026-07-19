"""Тесты планировщика: нахлёст фаз (overlap) и учёт капасити при нахлёсте."""
import json

import pytest

from plan_features import CapacityAllocator, main, overlap_weeks, schedule_feature
from roadmap_common import parse_date

START = parse_date("2026-07-13")  # понедельник


def bars(rows):
    """[(label, start, end), ...] по строкам фичи."""
    return [(r["label"], r["items"][0]["start"], r["items"][0]["end"]) for r in rows]


def test_overlap_weeks_fraction_and_weeks():
    assert overlap_weeks(0, 4) == 0
    assert overlap_weeks(0.5, 4) == 2      # доля: половина 4-недельной фазы
    assert overlap_weeks(0.5, 3) == 1      # floor(1.5)
    assert overlap_weeks(2, 4) == 2        # целое = недели
    assert overlap_weeks(10, 4) == 3       # не раньше чем через неделю после старта
    assert overlap_weeks(0.9, 1) == 0      # у недельной фазы нахлёста нет


def test_no_overlap_phases_back_to_back():
    alloc = CapacityAllocator(None, START)
    rows, end, _ = schedule_feature(
        {"name": "F", "analytics": 20, "dev": 30, "testing": 40},
        START, 2, 5, alloc)
    got = bars(rows)
    # 20/30/40 чд на 1 человека = 4/6/8 нед, встык
    assert got[0][1:] == ("2026-07-13", "2026-08-09")
    assert got[1][1:] == ("2026-08-10", "2026-09-20")
    assert got[2][1:] == ("2026-09-21", "2026-11-15")
    assert end == parse_date("2026-11-15")


def test_overlap_fraction_shifts_next_phase_left():
    alloc = CapacityAllocator(None, START)
    rows, end, _ = schedule_feature(
        {"name": "F", "analytics": 20, "dev": 30, "testing": 40},
        START, 2, 5, alloc, overlap=0.5)
    got = bars(rows)
    # аналитика 4 нед; dev стартует за 2 нед до её конца (после 2 нед);
    # dev 6 нед → testing за 3 нед до конца dev
    assert got[0][1] == "2026-07-13"
    assert got[1][1] == "2026-07-27"       # +2 нед от старта аналитики
    assert got[2][1] == "2026-08-17"       # +3 нед от старта dev
    assert end == parse_date("2026-10-11")  # конец testing (8 нед)


def test_overlap_end_is_max_of_bars_not_last():
    # длинная разработка, короткое тестирование с большим нахлёстом:
    # testing кончается раньше dev — конец фичи по dev
    alloc = CapacityAllocator(None, START)
    rows, end, _ = schedule_feature(
        {"name": "F", "dev": 30, "testing": 5}, START, 2, 5, alloc, overlap=5)
    got = bars(rows)
    assert got[0][2] == "2026-08-23"       # dev 6 нед
    assert got[1][2] < got[0][2]           # testing утонул внутри dev
    assert end == parse_date("2026-08-23")


def test_overlap_shared_pool_counts_sum_of_overlapping_phases():
    # общий пул числом: в неделю нахлёста analytics+dev должны влезть вместе.
    # 2 фазы по 10 чд (2 нед × 5 чд/нед каждая), нахлёст 1 нед → в неделе
    # нахлёста нужно 10 чд/нед. Пул 8 чд/нед: жадное «по одной фазе» пропустило
    # бы, fits_all — нет; фича должна уехать? Нет — сдвиг не помогает (нахлёст
    # внутри фичи), поэтому planner двигает старт бесконечно... проверяем, что
    # с достаточным пулом (10) фича встаёт с нахлёстом без сдвига.
    alloc = CapacityAllocator(10, START)
    rows, _, _ = schedule_feature(
        {"name": "F", "analytics": {"days": 10, "people": 1},
         "dev": {"days": 10, "people": 1}},
        START, 2, 5, alloc, overlap=1)
    got = bars(rows)
    assert got[0][1:] == ("2026-07-13", "2026-07-26")
    assert got[1][1] == "2026-07-20"       # старт за неделю до конца аналитики


def _run_main(tmp_path, src):
    fin, fout = tmp_path / "f.json", tmp_path / "r.json"
    fin.write_text(json.dumps(src), encoding="utf-8")
    main(str(fin), str(fout))
    return json.loads(fout.read_text(encoding="utf-8"))


def test_main_default_overlap_is_half(tmp_path):
    # без поля overlap фазы идут с нахлёстом 0.5: dev стартует после
    # половины аналитики (аналитика 4 нед → dev с 3-й недели)
    r = _run_main(tmp_path, {
        "title": "t", "start": "2026-07-13",
        "features": [{"name": "F", "analytics": 20, "dev": 30}],
    })
    items = [row["items"][0] for row in r["groups"][0]["rows"]]
    assert items[0]["start"] == "2026-07-13"
    assert items[1]["start"] == "2026-07-27"     # +2 нед, а не +4 (встык)


def test_overlap_dict_per_receiving_phase():
    # вход в dev — 0.5 (дефолт, не назван), вход в testing — 0.3
    alloc = CapacityAllocator(None, START)
    rows, _, _ = schedule_feature(
        {"name": "F", "analytics": 20, "dev": 30, "testing": 40},
        START, 2, 5, alloc, overlap={"testing": 0.3})
    got = bars(rows)
    # аналитика 4 нед → dev через 2 нед (0.5); dev 6 нед → testing через
    # 6 - floor(6*0.3)=6-1=5 нед от старта dev
    assert got[0][1] == "2026-07-13"
    assert got[1][1] == "2026-07-27"
    assert got[2][1] == "2026-08-31"


def test_main_overlap_dict_unknown_phase_raises(tmp_path):
    with pytest.raises(ValueError, match="неизвестные фазы"):
        _run_main(tmp_path, {
            "title": "t", "start": "2026-07-13", "overlap": {"qa": 0.3},
            "features": [{"name": "F", "analytics": 10, "dev": 10}],
        })


def test_main_overlap_zero_disables_default(tmp_path):
    r = _run_main(tmp_path, {
        "title": "t", "start": "2026-07-13", "overlap": 0,
        "features": [{"name": "F", "analytics": 20, "dev": 30}],
    })
    items = [row["items"][0] for row in r["groups"][0]["rows"]]
    assert items[1]["start"] == "2026-08-10"     # встык после 4 нед аналитики


def test_overlap_infeasible_within_pool_raises():
    # неделя нахлёста просит 10 чд/нед, пул 8 — сдвиг не поможет, нужна ошибка
    alloc = CapacityAllocator(8, START)
    with pytest.raises(ValueError, match="нахлёст"):
        schedule_feature(
            {"name": "F", "analytics": {"days": 10, "people": 1},
             "dev": {"days": 10, "people": 1}},
            START, 2, 5, alloc, overlap=1)


def test_overlap_respects_busy_pool_shifts_whole_feature():
    # dev-пул занят первой фичей; вторая с нахлёстом сдвигается целиком
    alloc = CapacityAllocator({"dev": 5}, START)
    schedule_feature({"name": "A", "dev": 10}, START, 2, 5, alloc)  # dev: нед 0-1
    rows, _, _ = schedule_feature(
        {"name": "B", "analytics": 10, "dev": 10}, START, 2, 5, alloc, overlap=1)
    got = bars(rows)
    # без сдвига dev B стартовал бы в нед 1 (нахлёст) — но пул занят до нед 2;
    # фича сдвигается целиком на 1 нед: аналитика нед 1-2, dev нед 2-3
    assert got[0][1] == "2026-07-20"
    assert got[1][1] == "2026-07-27"
