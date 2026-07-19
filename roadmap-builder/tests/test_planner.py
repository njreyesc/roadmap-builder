"""Тесты планировщика: разбор оценок фаз, капасити, порядок с учётом after."""
import json

import pytest

from plan_features import (
    CapacityAllocator,
    order_features,
    parse_phase,
    ru_plural,
    fmt_num,
    main,
)
from roadmap_common import parse_date

WD = 5  # work_days
SW = 2  # sprint_weeks


# ---------- parse_phase ----------

def test_bare_number_is_effort_in_person_days():
    # 10 чд без пула и без people = 1 человек → ceil(10/5)=2 недели
    dur, label, load = parse_phase(10, SW, WD, "F", "dev")
    assert dur == 2
    assert load == 5  # 10 чд равномерно на 2 недели
    assert "10 чд" in label


def test_effort_with_pool_rate_uses_whole_pool():
    # 10 чд, пул 5 чд/нед → 2 недели
    dur, _, load = parse_phase(10, SW, WD, "F", "dev", pool_rate=5)
    assert dur == 2 and load == 5


def test_effort_with_explicit_people():
    # 20 чд, 2 человека → темп 10 чд/нед → 2 недели
    dur, _, load = parse_phase({"days": 20, "people": 2}, SW, WD, "F", "dev")
    assert dur == 2 and load == 10


def test_weeks_input_derives_effort():
    # 3 недели, 1 человек → 3*5 = 15 чд
    dur, label, load = parse_phase({"weeks": 3}, SW, WD, "F", "dev")
    assert dur == 3 and load == 5
    assert "15 чд" in label


def test_sprints_input_uses_sprint_weeks():
    # 2 спринта * 2 нед/спринт = 4 недели
    dur, label, _ = parse_phase({"sprints": 2}, SW, WD, "F", "dev")
    assert dur == 4
    assert "спринт" in label


def test_effort_rounds_up_to_whole_weeks():
    # 7 чд, 1 человек (5 чд/нед) → ceil(7/5)=2 недели, нагрузка 3.5 чд/нед
    dur, _, load = parse_phase(7, SW, WD, "F", "dev")
    assert dur == 2
    assert load == pytest.approx(3.5)


def test_none_spec_returns_none():
    assert parse_phase(None, SW, WD, "F", "dev") is None


@pytest.mark.parametrize("bad", [0, -3, {"days": 0}, {"weeks": -1}])
def test_nonpositive_estimate_raises(bad):
    with pytest.raises(ValueError):
        parse_phase(bad, SW, WD, "F", "dev")


def test_people_must_be_positive_int():
    with pytest.raises(ValueError):
        parse_phase({"days": 5, "people": 0}, SW, WD, "F", "dev")
    with pytest.raises(ValueError):
        parse_phase({"days": 5, "people": 1.5}, SW, WD, "F", "dev")


def test_missing_estimate_key_raises():
    with pytest.raises(ValueError):
        parse_phase({"who": "Петров"}, SW, WD, "F", "dev")


# ---------- CapacityAllocator ----------

def test_shared_pool_across_phases():
    alloc = CapacityAllocator(6, parse_date("2026-07-13"))
    assert alloc.rate("dev") == 6
    assert alloc.rate("analytics") == 6  # общий пул на все фазы


def test_per_phase_pools_independent():
    alloc = CapacityAllocator({"dev": 3, "testing": 2}, parse_date("2026-07-13"))
    assert alloc.rate("dev") == 3
    assert alloc.rate("analytics") is None  # нет ключа = без ограничения


def test_unknown_pool_rejected():
    with pytest.raises(ValueError):
        CapacityAllocator({"frontend": 3}, parse_date("2026-07-13"))


def test_nonpositive_capacity_rejected():
    with pytest.raises(ValueError):
        CapacityAllocator({"dev": 0}, parse_date("2026-07-13"))


def test_fits_and_reserve_block_weeks():
    alloc = CapacityAllocator({"dev": 5}, parse_date("2026-07-13"))
    assert alloc.fits("dev", 5, 0, 2)
    alloc.reserve("dev", 5, 0, 2)
    assert not alloc.fits("dev", 1, 0, 1)   # неделя 0 занята полностью
    assert alloc.fits("dev", 5, 2, 1)       # неделя 2 свободна


def test_check_rejects_load_bigger_than_pool():
    alloc = CapacityAllocator({"dev": 3}, parse_date("2026-07-13"))
    with pytest.raises(ValueError):
        alloc.check("dev", 5, "Фича X")     # 5 чд/нед не влезет в пул 3


# ---------- order_features (баг: priority ломал after) ----------

def _by_name(feats):
    return {f["name"]: f for f in feats}


def test_after_predecessor_comes_first_despite_priority():
    feats = [
        {"name": "B", "after": "A", "priority": 1, "dev": 10},
        {"name": "A", "priority": 2, "dev": 10},
    ]
    order = [f["name"] for f in order_features(feats, _by_name(feats))]
    assert order == ["A", "B"]


def test_priority_orders_independent_features():
    feats = [
        {"name": "low", "priority": 3, "dev": 5},
        {"name": "high", "priority": 1, "dev": 5},
        {"name": "mid", "priority": 2, "dev": 5},
    ]
    order = [f["name"] for f in order_features(feats, _by_name(feats))]
    assert order == ["high", "mid", "low"]


def test_no_priority_preserves_input_order():
    feats = [{"name": n, "dev": 5} for n in ("first", "second", "third")]
    order = [f["name"] for f in order_features(feats, _by_name(feats))]
    assert order == ["first", "second", "third"]


def test_after_cycle_raises_with_cycle_path():
    feats = [
        {"name": "A", "after": "B", "dev": 5},
        {"name": "B", "after": "A", "dev": 5},
    ]
    with pytest.raises(ValueError, match=r"Цикл в after: A -> B -> A"):
        order_features(feats, _by_name(feats))


def test_after_self_cycle_raises():
    feats = [{"name": "A", "after": "A", "dev": 5}]
    with pytest.raises(ValueError, match=r"Цикл в after: A -> A"):
        order_features(feats, _by_name(feats))


def test_after_cycle_reported_even_when_walk_starts_outside():
    # C сама не в цикле, но ждёт его — в ошибке именно цикл A -> B -> A, не C
    feats = [
        {"name": "C", "after": "A", "dev": 5},
        {"name": "A", "after": "B", "dev": 5},
        {"name": "B", "after": "A", "dev": 5},
    ]
    with pytest.raises(ValueError, match=r"Цикл в after: A -> B -> A"):
        order_features(feats, _by_name(feats))


def test_after_chain_topologically_ordered():
    feats = [
        {"name": "C", "after": "B", "dev": 5},
        {"name": "B", "after": "A", "dev": 5},
        {"name": "A", "dev": 5},
    ]
    order = [f["name"] for f in order_features(feats, _by_name(feats))]
    assert order.index("A") < order.index("B") < order.index("C")


# ---------- end-to-end main() ----------

def test_main_priority_after_no_longer_crashes(tmp_path):
    src = {
        "title": "T", "start": "2026-07-20",
        "features": [
            {"name": "B", "after": "A", "priority": 1, "dev": 10},
            {"name": "A", "priority": 2, "dev": 10},
        ],
    }
    inp = tmp_path / "in.json"
    outp = tmp_path / "out.json"
    inp.write_text(json.dumps(src), encoding="utf-8")
    main(str(inp), str(outp))
    rm = json.loads(outp.read_text(encoding="utf-8"))
    names = [g["name"] for g in rm["groups"]]
    assert names == ["A", "B"]
    # B стартует после конца A (фазы встык, зависимость соблюдена)
    a_end = rm["groups"][0]["rows"][-1]["items"][0]["end"]
    b_start = rm["groups"][1]["rows"][0]["items"][0]["start"]
    assert b_start > a_end


def test_main_warns_on_early_start(tmp_path, capsys):
    src = {
        "title": "T", "start": "2026-07-20",
        "features": [{"name": "Legacy", "start": "2026-06-01", "dev": 5}],
    }
    inp = tmp_path / "in.json"
    outp = tmp_path / "out.json"
    inp.write_text(json.dumps(src), encoding="utf-8")
    main(str(inp), str(outp))
    out = capsys.readouterr().out
    assert "раньше начала roadmap" in out
    rm = json.loads(outp.read_text(encoding="utf-8"))
    # прижата к началу roadmap
    assert rm["groups"][0]["rows"][0]["items"][0]["start"] == "2026-07-20"


def test_main_unknown_after_raises(tmp_path):
    src = {
        "title": "T", "start": "2026-07-20",
        "features": [{"name": "A", "after": "Nope", "dev": 5}],
    }
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(src), encoding="utf-8")
    with pytest.raises(ValueError):
        main(str(inp), str(tmp_path / "out.json"))


def test_main_self_cycle_raises(tmp_path):
    src = {
        "title": "T", "start": "2026-07-20",
        "features": [{"name": "A", "after": "A", "dev": 5}],
    }
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(src), encoding="utf-8")
    with pytest.raises(ValueError, match="Цикл в after"):
        main(str(inp), str(tmp_path / "out.json"))


def test_main_after_cycle_raises_clear_error(tmp_path):
    # раньше падало с «after='B' ещё не спланирована — перечисли фичи так,
    # чтобы предшественник шёл раньше», хотя перестановка при цикле не поможет
    src = {
        "title": "T", "start": "2026-07-20",
        "features": [
            {"name": "A", "after": "B", "dev": 5},
            {"name": "B", "after": "A", "dev": 5},
        ],
    }
    inp = tmp_path / "in.json"
    inp.write_text(json.dumps(src), encoding="utf-8")
    with pytest.raises(ValueError, match=r"Цикл в after: A -> B -> A"):
        main(str(inp), str(tmp_path / "out.json"))


# ---------- мелочи ----------

@pytest.mark.parametrize("n,exp", [
    (1, "спринт"), (2, "спринта"), (4, "спринта"), (5, "спринтов"),
    (11, "спринтов"), (21, "спринт"), (12, "спринтов"),
])
def test_ru_plural(n, exp):
    assert ru_plural(n, "спринт", "спринта", "спринтов") == exp


def test_fmt_num_trims_integers():
    assert fmt_num(3.0) == "3"
    assert fmt_num(2.5) == "2.5"
