"""Тесты конвертера Jira CSV → features.json: статусы, зависимости, разбор оценок."""
import json

import pytest

from jira_to_features import (find_col, is_done_status, main, parse_capacity,
                              parse_est, read_csv_rows)

HEADER = ("Issue Type,Issue key,Summary,Status,Priority,"
          "Custom field (Аналитика),Custom field (Разработка),"
          "Custom field (Тестирование),Custom field (Зависит от)")


def run_main(tmp_path, csv_text, *extra):
    src, out = tmp_path / "epics.csv", tmp_path / "features.json"
    src.write_text(csv_text, encoding="utf-8")
    main([str(src), str(out), *extra])
    return json.loads(out.read_text(encoding="utf-8"))


# --- parse_est ---------------------------------------------------------------

def test_parse_est_units_and_people():
    assert parse_est("2 нед", "Разработка") == {"weeks": 2}
    assert parse_est("3 спринта x2", "Разработка") == {"sprints": 3, "people": 2}
    assert parse_est("20", "Разработка") == {"days": 20}
    assert parse_est("", "Разработка") is None


def test_parse_est_cyrillic_multiplier():
    # кириллическая «х» — то же, что латинская x: people не должны теряться
    assert parse_est("3 спринта х2", "Разработка") == {"sprints": 3, "people": 2}
    assert parse_est("2 нед Х3", "Разработка") == {"weeks": 2, "people": 3}
    assert parse_est("4 спринта ×2", "Разработка") == {"sprints": 4, "people": 2}


# --- is_done_status ----------------------------------------------------------

@pytest.mark.parametrize("status", [
    "Done", "Closed", "Resolved", "Cancelled", "canceled",
    "Готово", "Закрыт", "Закрыто", "Закрыта", "Отменено", "Отменён", "Отменен",
    "Выполнено", "Решено", "Завершён",
])
def test_done_statuses_detected(status):
    assert is_done_status(status)


@pytest.mark.parametrize("status", [
    "To Do", "In Progress", "Backlog", "Открыт", "В работе",
    "Готово к разработке",       # ready-for-dev — эпик живой
    "",
])
def test_live_statuses_not_done(status):
    assert not is_done_status(status)


# --- find_col ----------------------------------------------------------------

def test_find_col_ignores_substring_inside_word():
    # «Latest» содержит «test», но это не колонка тестирования
    headers = ["Summary", "Latest comment", "Тестирование"]
    assert find_col(headers, ["тест", "test", "qa"]) == "Тестирование"
    assert find_col(["Summary", "Latest comment"], ["тест", "test", "qa"]) is None


def test_find_col_word_start_and_exact():
    assert find_col(["Custom field (Аналитика)"], ["аналит", "analy"]) == \
        "Custom field (Аналитика)"
    assert find_col(["Issue key", "Custom field (Веха)"],
                    ["issue key", "key", "ключ"]) == "Issue key"


# --- parse_capacity ----------------------------------------------------------

def test_parse_capacity_ok():
    assert parse_capacity("analytics:10,dev:15,testing:10") == \
        {"analytics": 10, "dev": 15, "testing": 10}
    assert parse_capacity(None) is None


def test_parse_capacity_unknown_pool_clean_exit():
    with pytest.raises(SystemExit) as e:
        parse_capacity("designers:5")
    assert "неизвестный пул" in str(e.value)


@pytest.mark.parametrize("spec", ["dev:abc", "dev", "dev:"])
def test_parse_capacity_bad_value_clean_exit(spec):
    # не голый ValueError-traceback, а понятное сообщение
    with pytest.raises(SystemExit) as e:
        parse_capacity(spec)
    assert "число" in str(e.value)


# --- разделитель CSV ---------------------------------------------------------

def test_read_csv_semicolon_delimiter(tmp_path):
    src = tmp_path / "epics.csv"
    src.write_text("Summary;Status;Разработка\nФича А;To Do;2 спринта\n",
                   encoding="utf-8")
    rows = read_csv_rows(str(src))
    assert rows[0]["Summary"] == "Фича А"
    assert rows[0]["Разработка"] == "2 спринта"


def test_main_semicolon_csv_end_to_end(tmp_path):
    out = run_main(tmp_path,
                   "Summary;Status;Аналитика;Разработка\n"
                   "Фича А;To Do;1 нед;2 спринта\n")
    assert out["features"] == [
        {"name": "Фича А", "analytics": {"weeks": 1}, "dev": {"sprints": 2}}]


# --- main: фильтрация, зависимости, дубликаты --------------------------------

def test_done_epic_dropped_and_dependency_on_it_warned(tmp_path, capsys):
    # живой эпик зависит от закрытого: after не должен попасть в features.json
    out = run_main(tmp_path, HEADER + "\n"
                   "Epic,PL-1,Старая фича,Закрыто,High,1 нед,2 спринта,1 нед,\n"
                   "Epic,PL-2,Новая фича,To Do,High,1 нед,2 спринта,1 нед,PL-1\n")
    names = [f["name"] for f in out["features"]]
    assert names == ["Новая фича"]
    assert "after" not in out["features"][0]
    assert "зависимость 'PL-1' не найдена" in capsys.readouterr().out


def test_dependency_between_live_epics_kept(tmp_path):
    out = run_main(tmp_path, HEADER + "\n"
                   "Epic,PL-1,База,To Do,High,1 нед,2 спринта,1 нед,\n"
                   "Epic,PL-2,Надстройка,To Do,High,1 нед,2 спринта,1 нед,PL-1\n")
    by_name = {f["name"]: f for f in out["features"]}
    assert by_name["Надстройка"]["after"] == "База"
    assert "after" not in by_name["База"]


def test_dependency_on_epic_without_estimates_dropped(tmp_path, capsys):
    # эпик без оценок отбрасывается — зависимость на него тоже
    out = run_main(tmp_path, HEADER + "\n"
                   "Epic,PL-1,Пустой,To Do,High,,,,\n"
                   "Epic,PL-2,Рабочий,To Do,High,1 нед,2 спринта,1 нед,PL-1\n")
    assert [f["name"] for f in out["features"]] == ["Рабочий"]
    assert "after" not in out["features"][0]
    assert "не найдена" in capsys.readouterr().out


def test_keep_done_restores_dependency(tmp_path):
    out = run_main(tmp_path, HEADER + "\n"
                   "Epic,PL-1,Старая фича,Закрыто,High,1 нед,2 спринта,1 нед,\n"
                   "Epic,PL-2,Новая фича,To Do,High,1 нед,2 спринта,1 нед,PL-1\n",
                   "--keep-done")
    by_name = {f["name"]: f for f in out["features"]}
    assert by_name["Новая фича"]["after"] == "Старая фича"


def test_duplicate_epic_names_clean_exit(tmp_path):
    with pytest.raises(SystemExit) as e:
        run_main(tmp_path, HEADER + "\n"
                 "Epic,PL-1,Фича,To Do,High,1 нед,2 спринта,1 нед,\n"
                 "Epic,PL-2,Фича,To Do,High,1 нед,1 спринт,1 нед,\n")
    assert "Дубликаты" in str(e.value)


def test_sample_csv_converts_and_plans(tmp_path):
    """Комплектный пример: конвертер → планировщик без падений."""
    import os
    import plan_features
    sample = os.path.join(os.path.dirname(__file__), "..", "examples",
                          "sample_jira_epics.csv")
    features_path = tmp_path / "features.json"
    main([sample, str(features_path), "--start", "2026-07-20"])
    out = json.loads(features_path.read_text(encoding="utf-8"))
    names = [f["name"] for f in out["features"]]
    assert "Логирование запросов агента" not in names      # Done — отброшен
    assert {"Интеграция с IDP", "Лимиты ОФР", "Аудит доступа"} <= set(names)
    by_name = {f["name"]: f for f in out["features"]}
    assert by_name["Способы вызова агентов"]["after"] == "Интеграция с IDP"
    assert by_name["Интеграция с IDP"]["dev"] == {"sprints": 3, "people": 2}
    roadmap_path = tmp_path / "roadmap.json"
    plan_features.main(str(features_path), str(roadmap_path))
    assert json.loads(roadmap_path.read_text(encoding="utf-8"))["groups"]
