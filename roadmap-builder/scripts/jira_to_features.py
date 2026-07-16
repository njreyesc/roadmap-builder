"""Конвертер выгрузки эпиков из Jira (CSV) → features.json.

Разбирает CSV-экспорт эпиков и собирает features.json для plan_features.py.
Колонки ищутся по ключевым словам в заголовке (регистронезависимо), поэтому
терпим к вариациям имён ("Custom field (Аналитика)", "Analytics estimate" и т.п.).

Оценки фаз читаются из ячеек вида «2 нед», «3 спринта», «3 спринта x2»:
число + единица (спринт/неделя — по слову в ячейке или заголовке) + опц.
множитель «xN» → people (ше). Пустая ячейка = фазы нет.

Использование:
  python jira_to_features.py epics.csv features.json --start 2026-07-20 \
      [--title "..."] [--sprint-weeks 2] [--today 2026-07-16] \
      [--capacity analytics:2,dev:3,testing:2] [--allow-gaps]
"""
import argparse
import csv
import json
import re
import sys

# Приоритеты Jira → числовой ранг (меньше = раньше в очереди за капасити)
PRIORITY_RANK = {
    "highest": 1, "critical": 1, "blocker": 1,
    "high": 2, "major": 2,
    "medium": 3, "normal": 3,
    "low": 4, "minor": 4,
    "lowest": 5, "trivial": 5,
}
DONE_STATUSES = {"done", "closed", "resolved", "cancelled", "canceled", "готово", "закрыт"}

# Ключевые слова для поиска колонок (в нижнем регистре, по подстроке)
COL_KEYS = {
    "type": ["issue type", "тип задачи", "тип"],
    "key": ["issue key", "key", "ключ"],
    "summary": ["summary", "название", "заголовок", "тема"],
    "status": ["status", "статус"],
    "priority": ["priority", "приоритет"],
    "assignee": ["assignee", "исполнитель", "team", "команда"],
    "components": ["component", "компонент", "сервис"],
    "analytics": ["аналит", "analy"],
    "dev": ["разраб", "develop", "dev"],
    "testing": ["тест", "test", "qa"],
    "milestone": ["веха", "milestone", "контрольн"],
    "after": ["зависит", "depends", "blocked by", "epic link"],
}


def find_col(headers, keys):
    """Первый заголовок, содержащий любое из ключевых слов."""
    for h in headers:
        low = (h or "").lower()
        for k in keys:
            if k in low:
                return h
    return None


def num_or_int(x):
    return int(x) if float(x).is_integer() else x


def parse_est(cell, header):
    """Ячейка оценки → {weeks|sprints: N, people?: M} либо None."""
    cell = (cell or "").strip()
    if not cell:
        return None
    people = 1
    m = re.search(r"[x×]\s*(\d+)", cell)
    if m:
        people = int(m.group(1))
        cell = cell[:m.start()].strip()
    num = re.search(r"(\d+(?:[.,]\d+)?)", cell)
    if not num:
        return None
    val = float(num.group(1).replace(",", "."))
    if val <= 0:
        return None
    hay = f"{cell} {header}".lower()
    unit = "sprints" if ("спринт" in hay or "sprint" in hay) else "weeks"
    est = {unit: num_or_int(val)}
    if people > 1:
        est["people"] = people
    return est


def split_multi(cell):
    return [p.strip() for p in re.split(r"[;,]", cell or "") if p.strip()]


def parse_capacity(spec):
    """'analytics:2,dev:3,testing:2' → {'analytics':2,'dev':3,'testing':2}."""
    if not spec:
        return None
    alias = {"a": "analytics", "an": "analytics", "analytics": "analytics",
             "d": "dev", "dev": "dev", "development": "dev",
             "t": "testing", "test": "testing", "testing": "testing", "qa": "testing"}
    out = {}
    for part in spec.split(","):
        k, _, v = part.partition(":")
        k = k.strip().lower()
        if k not in alias:
            sys.exit(f"capacity: неизвестный пул '{k}' (допустимо analytics/dev/testing)")
        out[alias[k]] = num_or_int(float(v))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("out_path")
    ap.add_argument("--start", required=True, help="Дата старта планирования (YYYY-MM-DD)")
    ap.add_argument("--title", default="Roadmap (из Jira)")
    ap.add_argument("--subtitle", default=None)
    ap.add_argument("--today", default=None)
    ap.add_argument("--sprint-weeks", type=int, default=2)
    ap.add_argument("--capacity", default=None, help="analytics:2,dev:3,testing:2")
    ap.add_argument("--allow-gaps", action="store_true")
    ap.add_argument("--keep-done", action="store_true", help="не отбрасывать закрытые эпики")
    args = ap.parse_args()

    with open(args.csv_path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("CSV пуст")
    headers = list(rows[0].keys())

    col = {name: find_col(headers, keys) for name, keys in COL_KEYS.items()}
    if not col["summary"]:
        sys.exit("Не нашёл колонку с названием эпика (summary/название)")
    if not any(col[p] for p in ("analytics", "dev", "testing")):
        sys.exit("Не нашёл ни одной колонки оценки фаз (аналитика/разработка/тестирование)")

    key_to_name = {}
    for r in rows:
        if col["key"] and r.get(col["key"]):
            key_to_name[r[col["key"]].strip()] = (r.get(col["summary"]) or "").strip()

    features = []
    skipped = []
    for r in rows:
        name = (r.get(col["summary"]) or "").strip()
        if not name:
            continue
        itype = (r.get(col["type"]) or "").strip().lower() if col["type"] else ""
        if col["type"] and itype and "epic" not in itype and "эпик" not in itype:
            skipped.append(f"{name} (тип '{itype}')")
            continue
        status = (r.get(col["status"]) or "").strip().lower() if col["status"] else ""
        if not args.keep_done and status in DONE_STATUSES:
            skipped.append(f"{name} (статус '{status}')")
            continue

        feat = {"name": name}
        if col["priority"] and r.get(col["priority"]):
            feat["priority"] = PRIORITY_RANK.get(r[col["priority"]].strip().lower(), 99)
        if col["assignee"] and (r.get(col["assignee"]) or "").strip():
            feat["owner"] = r[col["assignee"]].strip()
        if col["components"] and (r.get(col["components"]) or "").strip():
            svc = split_multi(r[col["components"]])
            if svc:
                feat["services"] = svc

        for phase in ("analytics", "dev", "testing"):
            if col[phase]:
                est = parse_est(r.get(col[phase]), col[phase])
                if est is not None:
                    feat[phase] = est
        if not any(p in feat for p in ("analytics", "dev", "testing")):
            skipped.append(f"{name} (нет оценок фаз)")
            continue

        if col["milestone"] and (r.get(col["milestone"]) or "").strip():
            feat["milestone"] = r[col["milestone"]].strip()
        if col["after"] and (r.get(col["after"]) or "").strip():
            dep_key = split_multi(r[col["after"]])[0]
            dep_name = key_to_name.get(dep_key)
            if dep_name and dep_name != name:
                feat["after"] = dep_name
            else:
                print(f"! '{name}': зависимость '{dep_key}' не найдена среди эпиков — пропущена")
        features.append(feat)

    if not features:
        sys.exit("После фильтрации не осталось ни одного эпика с оценками")

    out = {"title": args.title, "start": args.start, "sprint_weeks": args.sprint_weeks}
    if args.subtitle:
        out["subtitle"] = args.subtitle
    if args.today:
        out["today"] = args.today
    cap = parse_capacity(args.capacity)
    if cap:
        out["capacity"] = cap
    if args.allow_gaps:
        out["allow_gaps"] = True
    out["features"] = features

    with open(args.out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    print(f"OK: {args.out_path} — {len(features)} эпиков → фич")
    for f in features:
        phases = [p for p in ("analytics", "dev", "testing") if p in f]
        dep = f" after '{f['after']}'" if "after" in f else ""
        print(f"  [{f.get('priority', '-')}] {f['name']}: {'+'.join(phases)}{dep}")
    if skipped:
        print(f"Пропущено {len(skipped)}: " + "; ".join(skipped))


if __name__ == "__main__":
    main()
