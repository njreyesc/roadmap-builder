"""Общая логика для рендереров roadmap: недельная сетка и загрузка JSON."""
import json
from datetime import date, datetime, timedelta

RU_MONTHS = [
    "Январь", "Февраль", "Март", "Апрель", "Май", "Июнь",
    "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь",
]

STYLE = {
    "milestone_done_fill": "4CAF50",      # зелёный
    "milestone_done_line": "2E7D32",
    "milestone_planned_fill": "FFFFFF",   # белый
    "milestone_planned_line": "E53935",   # красный контур
    "bar_work_fill": "F5A623",            # оранжевый — разработка
    "bar_work_line": "C77F00",
    "bar_estimate_fill": "FBEAB6",        # бледно-жёлтый — оценка
    "bar_estimate_line": "E0C878",
    "bar_analytics_fill": "BDD7EE",       # голубой — аналитика (SDD)
    "bar_analytics_line": "5B9BD5",
    "bar_testing_fill": "E2D1F0",         # сиреневый — тестирование
    "bar_testing_line": "9B7FC7",
    "bar_vacation_fill": "FFF176",        # жёлтый — отпуск
    "bar_vacation_line": "D4C24A",
    "note_fill": "DDEBF7",                # голубой
    "note_line": "6FA8DC",
    "today_line": "2E7D32",               # зелёная линия "сегодня"
    "header_fill": "808080",              # месяц
    "header_font": "FFFFFF",
    "week_fill": "D9D9D9",                # неделя
    "grid_line": "D9D9D9",
    "group_fill": "F2F2F2",
    "text": "333333",
}


def parse_date(s):
    return datetime.strptime(s, "%Y-%m-%d").date()


def monday(d):
    return d - timedelta(days=d.weekday())


class Timeline:
    """Недельная сетка: список недель (понедельников) между start и end."""

    def __init__(self, start, end):
        self.start = monday(parse_date(start) if isinstance(start, str) else start)
        end = parse_date(end) if isinstance(end, str) else end
        self.weeks = []
        w = self.start
        while w <= end:
            self.weeks.append(w)
            w += timedelta(days=7)
        if not self.weeks:
            raise ValueError("Пустой диапазон дат roadmap")

    @property
    def n(self):
        return len(self.weeks)

    def week_index(self, d, clamp=True):
        """Индекс недели для даты (0-based). clamp — прижать к границам."""
        i = self.week_index_raw(d)
        if clamp:
            i = max(0, min(self.n - 1, i))
        elif i < 0 or i >= self.n:
            return None
        return i

    def week_index_raw(self, d):
        """Индекс недели без прижатия к границам (может быть <0 или >= n)."""
        d = parse_date(d) if isinstance(d, str) else d
        return (monday(d) - self.start).days // 7

    def clip_bar(self, start, end, label=""):
        """Видимый диапазон полосы (i0, i1) и маркеры выхода за границы.

        Возвращает (i0, i1, cut_left, cut_right) либо None, если полоса
        целиком вне диапазона roadmap.
        """
        r0, r1 = self.week_index_raw(start), self.week_index_raw(end)
        if r1 < r0:
            print(f"! у полосы '{label}' start позже end ({start} > {end}) — даты поменяны местами")
            r0, r1 = r1, r0
        if r1 < 0 or r0 >= self.n:
            return None
        return max(0, r0), min(self.n - 1, r1), r0 < 0, r1 > self.n - 1

    def week_label(self, i):
        w = self.weeks[i]
        e = w + timedelta(days=6)
        return f"{w.day:02d}-{e.day:02d}"

    def month_spans(self):
        """[(label, first_week_idx, last_week_idx)] — месяц недели определяется её понедельником."""
        spans = []
        for i, w in enumerate(self.weeks):
            label = f"{RU_MONTHS[w.month - 1]} {w.year}"
            if spans and spans[-1][0] == label:
                spans[-1] = (label, spans[-1][1], i)
            else:
                spans.append((label, i, i))
        return spans


def load_roadmap(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for key in ("title", "start", "end", "groups"):
        if key not in data:
            raise ValueError(f"В roadmap.json нет обязательного поля '{key}'")
    tl = Timeline(data["start"], data["end"])
    return data, tl


def group_label(g):
    """Подпись группы в левой колонке: фича, владелец, дорабатываемые сервисы."""
    label = g["name"]
    if g.get("owner"):
        label += f'\n({g["owner"]})'
    if g.get("services"):
        label += "\nСервисы: " + ", ".join(g["services"])
    return label


def flatten_rows(data):
    """[(group, row, is_first_row_of_group)] в порядке отрисовки."""
    out = []
    for g in data["groups"]:
        rows = g.get("rows") or [{"label": "", "items": []}]
        for j, r in enumerate(rows):
            out.append((g, r, j == 0))
    return out
