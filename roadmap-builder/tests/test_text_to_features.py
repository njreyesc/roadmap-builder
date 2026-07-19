"""Тесты конвертера текстового списка фич: разбор строк, метки, дубликаты."""
import json
import os

import pytest

from text_to_features import label_of, main, parse_line, split_name


def run_main(tmp_path, text, *extra):
    src, out = tmp_path / "features.txt", tmp_path / "features.json"
    src.write_text(text, encoding="utf-8")
    main([str(src), str(out), *extra])
    return json.loads(out.read_text(encoding="utf-8"))


# --- label_of ----------------------------------------------------------------

def test_label_of_words_and_letters():
    assert label_of("аналитика 2 нед") == "analytics"
    assert label_of("разработка 3 спринта") == "dev"
    assert label_of("Т 1 нед") == "testing"
    assert label_of("2 нед") is None


def test_label_of_ignores_assignee_tail():
    # «/ Фамилия» — исполнитель; «Devyatov» не делает чанк меткой dev
    assert label_of("3 спринта / Devyatov") is None
    assert label_of("2 нед / Тестов") is None
    assert label_of("разработка 3 спринта / Devyatov") == "dev"


# --- split_name / parse_line -------------------------------------------------

def test_positional_decimal_comma_not_split():
    # запятая внутри числа «0,5» — десятичная, а не разделитель фаз
    feat = parse_line("Дозвон: 0,5 нед, 1 спринт, 2", 1)
    assert feat == {"name": "Дозвон", "analytics": {"weeks": 0.5},
                    "dev": {"sprints": 1}, "testing": {"days": 2}}


def test_colon_in_feature_name():
    # имя режется по последнему «: » перед оценками, а не по первому
    feat = parse_line("Интеграция: этап 1: 5 чд, 3 чд, 2 чд", 1)
    assert feat == {"name": "Интеграция: этап 1", "analytics": {"days": 5},
                    "dev": {"days": 3}, "testing": {"days": 2}}


def test_labeled_form_with_colon_separator_still_works():
    feat = parse_line("Фича: аналитика 2 нед, разработка 3 спринта", 1)
    assert feat == {"name": "Фича", "analytics": {"weeks": 2},
                    "dev": {"sprints": 3}}


def test_surname_with_dev_substring_keeps_positional_form():
    # раньше «Devyatov» переключал строку в подписанную форму
    # и остальные фазы молча отбрасывались
    feat = parse_line("Фича: 1 нед, 3 спринта / Devyatov, 2 нед", 1)
    assert feat == {"name": "Фича", "analytics": {"weeks": 1},
                    "dev": {"sprints": 3, "who": "Devyatov"},
                    "testing": {"weeks": 2}}


def test_split_name_pipe_and_semicolon_forms():
    assert split_name("Способы вызова | | 2 спринта | 1 нед") == \
        ("Способы вызова", ["", "2 спринта", "1 нед"])
    assert split_name("Миграция; 2 нед; 4 спринта; 2 нед") == \
        ("Миграция", ["2 нед", "4 спринта", "2 нед"])


def test_single_letter_labels():
    feat = parse_line("Аудит: А 1 нед, Р 1 спринт, Т 1 нед", 1)
    assert feat == {"name": "Аудит", "analytics": {"weeks": 1},
                    "dev": {"sprints": 1}, "testing": {"weeks": 1}}


# --- main --------------------------------------------------------------------

def test_duplicate_feature_names_clean_exit(tmp_path):
    with pytest.raises(SystemExit) as e:
        run_main(tmp_path, "Фича: 1 нед, 2 спринта\nФича: 2 нед, 1 спринт\n")
    assert "уже была в строке" in str(e.value)
    assert "Фича" in str(e.value)


def test_sample_txt_converts(tmp_path):
    sample = os.path.join(os.path.dirname(__file__), "..", "examples",
                          "sample_features.txt")
    out_path = tmp_path / "features.json"
    main([sample, str(out_path)])
    out = json.loads(out_path.read_text(encoding="utf-8"))
    by_name = {f["name"]: f for f in out["features"]}
    assert len(out["features"]) == 6
    assert by_name["Интеграция с IDP"]["dev"] == \
        {"sprints": 3, "people": 2, "who": "Петров"}
    assert by_name["Способы вызова агентов"] == \
        {"name": "Способы вызова агентов", "dev": {"sprints": 2},
         "testing": {"weeks": 1}}
