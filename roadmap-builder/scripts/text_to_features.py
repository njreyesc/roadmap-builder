"""Конвертер простого текстового списка фич → features.json.

Одна строка = одна фича: название, рядом текстом оценки аналитики,
разработки, тестирования. Порядок строк = приоритет (очередь за капасити).

Понимает две формы оценок в строке (можно смешивать между строками):

  Подписанная (разделители ',' или ';'):
    Интеграция с IDP: аналитика 2 нед, разработка 3 спринта x2 / Петров, тестирование 2 нед
    Аудит: А 1 нед, Р 1 спринт, Т 1 нед          # односимвольные метки А/Р/Т

  Позиционная (аналитика, разработка, тестирование по порядку; пустую пропусти):
    Лимиты ОФР: 1 нед, 2 спринта, 1 нед
    Способы вызова | | 2 спринта | 1 нед          # пустая аналитика
    Миграция; 2 нед; 4 спринта; 2 нед

Имя отделяется от оценок первым из ':' '—' '–' ' - ' '|' или таб; если их нет —
первым ';'/','. Единица оценки — «спринт», «нед» или (по умолчанию, без единицы)
человеко-дни (чд); «xN» → people, «/ Имя» → who. Строки с '#' и пустые игнорируются.

Использование:
  python text_to_features.py features.txt features.json --start 2026-07-20 \
      [--title "..."] [--sprint-weeks 2] [--today ...] \
      [--capacity analytics:2,dev:3,testing:2] [--allow-gaps]
"""
import argparse
import json
import re
import sys

from jira_to_features import num_or_int, parse_capacity, parse_est

PHASE_ORDER = ["analytics", "dev", "testing"]
PHASE_KW = [
    ("analytics", ["аналит", "analy"]),
    ("dev", ["разраб", "девелоп", "dev"]),
    ("testing", ["тест", "test", "qa"]),
]
SINGLE = {"а": "analytics", "a": "analytics", "р": "dev", "d": "dev",
          "т": "testing", "t": "testing"}


def label_of(chunk):
    """Фаза чанка по метке (слово или одиночная буква) либо None."""
    low = chunk.strip().lower()
    for ph, kws in PHASE_KW:
        if any(k in low for k in kws):
            return ph
    m = re.match(r"([а-яёa-z])[\s:.)\-–—]", low)
    if m and m.group(1) in SINGLE:
        return SINGLE[m.group(1)]
    return None


def parse_chunk(x, phase):
    """Ячейка оценки → est-dict (с who, если есть '/ Имя')."""
    who = None
    if "/" in x:
        x, who = x.rsplit("/", 1)
        who = who.strip() or None
    est = parse_est(x, phase)
    if est is not None and who:
        est["who"] = who
    return est


def split_name(line):
    """(name, [items]) — отделяет имя фичи от списка ячеек оценок."""
    if "|" in line or "\t" in line:
        parts = re.split(r"\||\t", line)
        return parts[0].strip(), [p.strip() for p in parts[1:]]
    m = re.search(r"\s—\s|\s–\s|:\s|\s-\s", line)
    if m:
        name = line[:m.start()].strip()
        rest = line[m.end():]
        return name, [p.strip() for p in re.split(r"[;,]", rest)]
    if ";" in line or "," in line:
        parts = re.split(r"[;,]", line)
        return parts[0].strip(), [p.strip() for p in parts[1:]]
    return line.strip(), []


def parse_line(line, lineno):
    name, items = split_name(line)
    if not name:
        return None
    if not any(it for it in items):
        print(f"! строка {lineno}: у фичи '{name}' нет оценок фаз — пропущена")
        return None

    feat = {"name": name}
    labeled = [(label_of(it), it) for it in items]
    if any(lab for lab, _ in labeled):                # подписанная форма
        for lab, it in labeled:
            if lab is None:
                if it.strip():
                    print(f"! строка {lineno}: чанк '{it}' без метки фазы — пропущен")
                continue
            est = parse_chunk(it, lab)
            if est is not None:
                feat[lab] = est
    else:                                             # позиционная форма
        for i, it in enumerate(items[:3]):
            if not it.strip():
                continue
            est = parse_chunk(it, PHASE_ORDER[i])
            if est is not None:
                feat[PHASE_ORDER[i]] = est

    if not any(p in feat for p in PHASE_ORDER):
        print(f"! строка {lineno}: у фичи '{name}' не распозналось ни одной оценки — пропущена")
        return None
    return feat


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("txt_path")
    ap.add_argument("out_path")
    ap.add_argument("--start", default=None,
                    help="Дата старта планирования (YYYY-MM-DD); без неё — дата запуска планировщика")
    ap.add_argument("--title", default="Roadmap")
    ap.add_argument("--subtitle", default=None)
    ap.add_argument("--today", default=None)
    ap.add_argument("--sprint-weeks", type=int, default=2)
    ap.add_argument("--capacity", default=None,
                    help="чд на пул: analytics:5,dev:10,testing:5")
    ap.add_argument("--capacity-per", choices=("week", "sprint"), default="week",
                    help="единица capacity: 'week' (чд/нед, по умолчанию) или 'sprint' (чд/спринт)")
    ap.add_argument("--allow-gaps", action="store_true")
    args = ap.parse_args()

    with open(args.txt_path, encoding="utf-8") as f:
        lines = f.readlines()

    features = []
    for i, raw in enumerate(lines, 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        feat = parse_line(line, i)
        if feat:
            features.append(feat)
    if not features:
        sys.exit("Не распозналось ни одной фичи с оценками")

    out = {"title": args.title, "sprint_weeks": args.sprint_weeks}
    if args.start:
        out["start"] = args.start
    if args.subtitle:
        out["subtitle"] = args.subtitle
    if args.today:
        out["today"] = args.today
    cap = parse_capacity(args.capacity)
    if cap:
        out["capacity"] = cap
        if args.capacity_per == "sprint":
            out["capacity_per"] = "sprint"
    if args.allow_gaps:
        out["allow_gaps"] = True
    out["features"] = features

    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"OK: {args.out_path} — {len(features)} фич")
    for f in features:
        parts = []
        for p, ru in (("analytics", "А"), ("dev", "Р"), ("testing", "Т")):
            if p in f:
                e = f[p]
                if "sprints" in e:
                    v, u = e["sprints"], "сп"
                elif "weeks" in e:
                    v, u = e["weeks"], "нед"
                else:
                    v, u = e.get("days"), "чд"
                ppl = f"x{e['people']}" if e.get("people", 1) > 1 else ""
                parts.append(f"{ru}={v}{u}{ppl}")
        print(f"  {f['name']}: {', '.join(parts)}")


if __name__ == "__main__":
    main()
