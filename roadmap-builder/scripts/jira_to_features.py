"""Конвертер выгрузки эпиков из Jira (CSV) → features.json.

Разбирает CSV-экспорт эпиков и собирает features.json для plan_features.py.
Колонки ищутся по ключевым словам в заголовке (регистронезависимо), поэтому
терпим к вариациям имён ("Custom field (Аналитика)", "Analytics estimate" и т.п.).

Оценки фаз читаются из ячеек вида «2 нед», «3 спринта», «3 спринта x2», «20»:
число + единица (спринт/неделя — по слову в ячейке или заголовке; без единицы —
человеко-дни, чд) + опц. множитель «xN» → people. Пустая ячейка = фазы нет.

Использование:
  python jira_to_features.py epics.csv features.json --start 2026-07-20 \
      [--title "..."] [--sprint-weeks 2] [--today 2026-07-16] \
      [--capacity analytics:10,dev:15,testing:10] [--allow-gaps]
"""
import argparse
import csv
import io
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
# Однословные статусы сравниваются по основе слова, чтобы ловить грамматические
# варианты («закрыто», «отменён», «выполнена»…). Многословные («готово к
# разработке») закрытыми не считаются.
_DONE_STEM_RE = re.compile(
    r"^(?:закрыт|отмен[её]н|готов|выполнен|решен|решён|заверш[её]н"
    r"|clos|resolv|cancel)[а-яёa-z]*$|^done$")


def is_done_status(status):
    """True, если статус означает закрытый/отменённый эпик."""
    s = (status or "").strip().lower()
    return s in DONE_STATUSES or bool(_DONE_STEM_RE.match(s))

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
    """Заголовок под ключевые слова: сперва точное совпадение, потом по началу слова.

    Совпадение по произвольной подстроке не годится: «Latest comment» содержит
    «test» и захватывался как колонка тестирования. Ключ должен совпадать с
    заголовком целиком либо стоять в начале слова («аналит» → «Аналитика»).
    """
    lows = [(h, (h or "").strip().lower()) for h in headers]
    for h, low in lows:
        if low in keys:
            return h
    for h, low in lows:
        for k in keys:
            if re.search(r"(?<!\w)" + re.escape(k), low):
                return h
    return None


def num_or_int(x):
    return int(x) if float(x).is_integer() else x


def parse_est(cell, header):
    """Ячейка оценки → {days|weeks|sprints: N, people?: M} либо None (people — люди).

    Единица берётся из слова в ячейке/заголовке: «спринт» → sprints, «нед»/week →
    weeks; без единицы — трудозатраты в человеко-днях (days, чд) по умолчанию.
    """
    cell = (cell or "").strip()
    if not cell:
        return None
    people = 1
    m = re.search(r"[x×хXХ]\s*(\d+)", cell)   # латинская x/X, «×» и кириллическая х/Х
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
    if "спринт" in hay or "sprint" in hay:
        unit = "sprints"
    elif "нед" in hay or "week" in hay:
        unit = "weeks"
    else:
        unit = "days"                             # без единицы — человеко-дни (чд)
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
        try:
            val = float(v)
        except ValueError:
            sys.exit(f"capacity: у пула '{k}' ожидается число чд после ':', "
                     f"получено '{v.strip()}' (пример: dev:15)")
        out[alias[k]] = num_or_int(val)
    return out


def read_csv_rows(csv_path):
    """Строки CSV с автодетектом разделителя (',' или ';').

    Jira в русской локали выгружает CSV через ';' — при разборе запятой такой
    файл превращался в одну колонку-«кашу» без единой ошибки.
    """
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        text = f.read()
    first_line = text.splitlines()[0] if text.strip() else ""
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(first_line, delimiters=",;\t").delimiter
    except csv.Error:
        if ";" in first_line and "," not in first_line:
            delimiter = ";"
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delimiter))
    if rows and len(rows[0]) == 1 and re.search(r"[;,\t]", next(iter(rows[0]))):
        sys.exit("CSV распознался как одна колонка — не смог определить разделитель. "
                 "Пересохраните выгрузку с разделителем ',' или ';'.")
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_path")
    ap.add_argument("out_path")
    ap.add_argument("--start", default=None,
                    help="Дата старта планирования (YYYY-MM-DD); без неё — дата запуска планировщика")
    ap.add_argument("--title", default="Roadmap (из Jira)")
    ap.add_argument("--subtitle", default=None)
    ap.add_argument("--today", default=None)
    ap.add_argument("--sprint-weeks", type=int, default=2)
    ap.add_argument("--capacity", default=None,
                    help="чд на пул: analytics:5,dev:10,testing:5")
    ap.add_argument("--capacity-per", choices=("week", "sprint"), default="week",
                    help="единица capacity: 'week' (чд/нед, по умолчанию) или 'sprint' (чд/спринт)")
    ap.add_argument("--allow-gaps", action="store_true")
    ap.add_argument("--keep-done", action="store_true", help="не отбрасывать закрытые эпики")
    args = ap.parse_args(argv)

    rows = read_csv_rows(args.csv_path)
    if not rows:
        sys.exit("CSV пуст")
    headers = list(rows[0].keys())

    col = {name: find_col(headers, keys) for name, keys in COL_KEYS.items()}
    if not col["summary"]:
        sys.exit("Не нашёл колонку с названием эпика (summary/название)")
    if not any(col[p] for p in ("analytics", "dev", "testing")):
        sys.exit("Не нашёл ни одной колонки оценки фаз (аналитика/разработка/тестирование)")

    key_to_name = {}    # ключ Jira → имя, только по эпикам, попавшим в план

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
        if not args.keep_done and is_done_status(status):
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
            feat["_dep_key"] = split_multi(r[col["after"]])[0]
        if col["key"] and (r.get(col["key"]) or "").strip():
            key_to_name[r[col["key"]].strip()] = name
        features.append(feat)

    if not features:
        sys.exit("После фильтрации не осталось ни одного эпика с оценками")

    dups = {n for n in (f["name"] for f in features)
            if sum(f["name"] == n for f in features) > 1}
    if dups:
        sys.exit("Дубликаты имён эпиков: " + "; ".join(sorted(dups)) +
                 ". Планировщик различает фичи по имени — переименуйте эпики в CSV.")

    # Зависимости разрешаются после фильтрации: after на отброшенный (Done,
    # не-эпик, без оценок) эпик отбрасывается с предупреждением, а не уходит
    # в features.json битой ссылкой, роняющей plan_features.py.
    included = {f["name"] for f in features}
    for feat in features:
        dep_key = feat.pop("_dep_key", None)
        if dep_key is None:
            continue
        dep_name = key_to_name.get(dep_key)
        if dep_name and dep_name != feat["name"] and dep_name in included:
            feat["after"] = dep_name
        else:
            print(f"! '{feat['name']}': зависимость '{dep_key}' не найдена "
                  f"среди планируемых эпиков — пропущена")

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

    print(f"OK: {args.out_path} — {len(features)} эпиков → фич")
    for f in features:
        phases = [p for p in ("analytics", "dev", "testing") if p in f]
        dep = f" after '{f['after']}'" if "after" in f else ""
        print(f"  [{f.get('priority', '-')}] {f['name']}: {'+'.join(phases)}{dep}")
    if skipped:
        print(f"Пропущено {len(skipped)}: " + "; ".join(skipped))


if __name__ == "__main__":
    main()
