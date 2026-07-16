"""Планировщик: features.json (список фич с оценками фаз) → roadmap.json.

Вход — согласованный список фич с оценками аналитики/разработки/тестирования
(схема — references/features-schema.md). Фазы каждой фичи идут встык
(без разрывов); фичи параллельны в пределах капасити пулов, не влезающие
сдвигаются целиком. Результат — roadmap.json для build_xlsx.py / build_pptx.py.

Оценка фазы по умолчанию — трудозатраты в человеко-днях (чд): голое число
или {days|чд|effort}. Капасити — пропускная способность пула фазы (чд/нед
или чд/спринт, см. capacity_per): без явных people фаза потребляет весь пул
(недель = чд / пул — команда как целое), с people — недель = чд /
(people × work_days). Можно задать и длительность напрямую — {weeks} или
{sprints}; тогда чд выводятся: люди × длительность(нед) × work_days.

Использование: python plan_features.py features.json roadmap.json
"""
import json
import math
import sys
from datetime import date, timedelta

from roadmap_common import monday, parse_date

SPRINT_WEEKS_DEFAULT = 2
WORK_DAYS_DEFAULT = 5

# (ключ в features.json, подпись строки, стиль полосы)
PHASES = [
    ("analytics", "Аналитика", "analytics"),
    ("dev", "Разработка", "work"),
    ("testing", "Тестирование", "testing"),
]


def ru_plural(n, one, few, many):
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def fmt_num(x):
    return str(int(x)) if float(x).is_integer() else f"{x:g}"


def scale_capacity(capacity, factor):
    """Умножает капасити (число или {пул: N}) на factor — для перевода единиц."""
    if isinstance(capacity, (int, float)):
        return capacity * factor
    if isinstance(capacity, dict):
        return {k: (v * factor if isinstance(v, (int, float)) else v)
                for k, v in capacity.items()}
    return capacity


DAYS_KEYS = ("days", "чд", "effort")             # алиасы трудозатрат (чд) в объекте


def parse_phase(spec, sprint_weeks, work_days, feature_name, phase_key, pool_rate=None):
    """Разбор оценки фазы → (недель-грид int, подпись, загрузка чд/нед) либо None.

    Оценка задаётся одним из двух способов:
    - **трудозатраты в человеко-днях (чд)** — голое число или {days|чд|effort}.
      Длительность выводится из пропускной способности: без явных people фаза
      потребляет весь пул своей фазы (pool_rate, чд/нед — команда как целое):
      недель = чд / пул; с people — недель = чд / (people × work_days).
      Без пула и без people считается 1 человек. Загрузка пула распределяется
      равномерно: чд / недель(округлённых) — суммарно резервируется ровно чд.
    - **длительность** — {weeks} или {sprints}; трудозатраты выводятся:
      чд = people × длительность(нед, округлённая вверх) × work_days;
      загрузка пула = people × work_days.

    В подписи полосы — «N нед, M чд».
    """
    if spec is None:
        return None
    who = None
    label = None
    people = None                                 # None = не задано явно
    dur_label = None
    weeks = None                                  # длительность, если задана явно
    effort = None                                 # трудозатраты чд, если заданы явно
    if isinstance(spec, (int, float)):
        effort = float(spec)                      # голое число = человеко-дни (чд)
    elif isinstance(spec, dict):
        who = spec.get("who")
        label = spec.get("label")
        people = spec.get("people")
        if people is not None and (not isinstance(people, int) or people < 1):
            raise ValueError(
                f"Фича '{feature_name}', фаза '{phase_key}': people должно быть целым >= 1")
        if "sprints" in spec:
            s = spec["sprints"]
            weeks = float(s) * sprint_weeks
            dur_label = f"{fmt_num(s)} {ru_plural(s, 'спринт', 'спринта', 'спринтов')}"
        elif "weeks" in spec:
            weeks = float(spec["weeks"])
        else:
            key = next((k for k in DAYS_KEYS if k in spec), None)
            if key is None:
                raise ValueError(
                    f"Фича '{feature_name}', фаза '{phase_key}': нужна оценка "
                    f"days (чд) / weeks / sprints")
            effort = float(spec[key])
    else:
        raise ValueError(
            f"Фича '{feature_name}', фаза '{phase_key}': оценка должна быть числом чд "
            f"или объектом {{days|weeks|sprints, people, who, label}}, получено: {spec!r}")

    if effort is not None:                        # вход — трудозатраты (чд)
        if effort <= 0:
            raise ValueError(
                f"Фича '{feature_name}', фаза '{phase_key}': оценка (чд) должна быть > 0")
        if people is not None:
            rate = people * work_days             # явные люди — их суммарный темп
        elif pool_rate is not None:
            rate = pool_rate                      # весь пул фазы: команда как целое
        else:
            rate = work_days                      # нет пула и people — 1 человек
        dur = max(1, math.ceil(effort / rate))    # единица сетки — неделя
        load = effort / dur                       # равномерно: суммарно ровно чд
        if label is None:
            if dur_label is None:
                dur_label = f"{fmt_num(dur)} нед"
            label = f"{dur_label}, {fmt_num(effort)} чд"
    else:                                         # вход — длительность
        if weeks <= 0:
            raise ValueError(f"Фича '{feature_name}', фаза '{phase_key}': оценка должна быть > 0")
        dur = max(1, math.ceil(weeks))            # единица сетки — неделя
        load = (people or 1) * work_days          # загрузка пула, чд/нед
        effort = load * dur                       # трудозатраты фазы, чд
        if label is None:
            if dur_label is None:
                dur_label = f"{fmt_num(weeks)} нед"
            label = f"{dur_label}, {fmt_num(effort)} чд"
    if who:
        label += f" / {who}"
    return dur, label, load


class CapacityAllocator:
    """Пулы капасити в человеко-днях в неделю (чд/нед) от глобального старта.

    capacity: число — общий пул чд/нед на все фазы; объект {analytics|dev|testing:
    чд/нед} — независимые пулы (нет ключа — фаза без ограничения); None — без
    ограничений. Фаза с people людьми занимает people × work_days чд/нед.
    """

    def __init__(self, capacity, origin):
        self.origin = origin                     # понедельник глобального старта
        self.shared = isinstance(capacity, (int, float))
        if self.shared:
            self.caps = {"__shared__": capacity}
        elif isinstance(capacity, dict):
            allowed = {k for k, _, _ in PHASES}
            unknown = set(capacity) - allowed
            if unknown:
                raise ValueError(
                    f"capacity: неизвестные пулы {sorted(unknown)}; допустимы {sorted(allowed)}")
            self.caps = dict(capacity)
        elif capacity is None:
            self.caps = {}
        else:
            raise ValueError(f"capacity должно быть числом или объектом, получено: {capacity!r}")
        for k, v in self.caps.items():
            if not isinstance(v, (int, float)) or v <= 0:
                raise ValueError(f"capacity['{k}'] должно быть числом > 0 (чд/нед)")
        self.usage = {k: [] for k in self.caps}  # пул → занято чд/нед по индексам недель

    def _pool(self, phase_key):
        if self.shared:
            return "__shared__"
        return phase_key if phase_key in self.caps else None

    def rate(self, phase_key):
        """Пропускная способность пула фазы, чд/нед (None — без ограничения)."""
        pool = self._pool(phase_key)
        return None if pool is None else self.caps[pool]

    def check(self, phase_key, load, what):
        """load должен помещаться в пул в принципе — иначе фаза не стартует никогда."""
        pool = self._pool(phase_key)
        if pool is not None and load > self.caps[pool]:
            raise ValueError(
                f"{what}: нужно {fmt_num(load)} чд/нед, "
                f"а капасити пула всего {fmt_num(self.caps[pool])} чд/нед")

    def fits(self, phase_key, load, i, dur):
        """Свободен ли пул фазы на недели [i, i+dur)."""
        pool = self._pool(phase_key)
        if pool is None:
            return True
        used, cap = self.usage[pool], self.caps[pool]
        while len(used) < i + dur:
            used.append(0)
        return all(used[w] + load <= cap for w in range(i, i + dur))

    def reserve(self, phase_key, load, i, dur):
        pool = self._pool(phase_key)
        if pool is None:
            return
        used = self.usage[pool]
        while len(used) < i + dur:
            used.append(0)
        for w in range(i, i + dur):
            used[w] += load

    def week_idx(self, d):
        return max(0, (d - self.origin).days // 7)

    def week_date(self, i):
        return self.origin + timedelta(weeks=i)


def schedule_feature(feature, start, sprint_weeks, work_days, alloc, allow_gaps=False):
    """Раскладка фаз фичи от start (понедельник) с учётом капасити.

    По умолчанию фазы идут встык (фичу нельзя разрывать): вся цепочка
    аналитика → разработка → тестирование сдвигается целиком до первого окна,
    где каждый пул свободен в свои недели. allow_gaps=True — старый жадный
    режим: каждая фаза стартует в первый свободный понедельник по отдельности.

    Возвращает (rows, end, visual_end): строки roadmap, дату конца фичи
    (для after) и правую границу с запасом под подпись вехи (для end roadmap).
    """
    name = feature.get("name", "?")
    phases = []                                  # (key, row_label, style, dur, bar_label, load)
    for key, row_label, style in PHASES:
        parsed = parse_phase(feature.get(key), sprint_weeks, work_days, name, key,
                             alloc.rate(key))
        if parsed is None:
            continue
        dur, bar_label, load = parsed
        alloc.check(key, load, f"Фича '{name}', фаза '{row_label}'")
        phases.append((key, row_label, style, dur, bar_label, load))
    if not phases:
        raise ValueError(
            f"Фича '{name}': нет ни одной фазы (analytics/dev/testing) — нечего планировать")

    base = alloc.week_idx(monday(start))
    starts = []                                  # индекс недели старта каждой фазы
    if allow_gaps:
        i = base
        for key, row_label, _, dur, _, load in phases:
            j = i
            while not alloc.fits(key, load, j, dur):
                j += 1
            if j > i:
                print(f"  ~ '{name}' / {row_label}: сдвиг на {j - i} нед (капасити)")
            alloc.reserve(key, load, j, dur)
            starts.append(j)
            i = j + dur
    else:
        t = base
        while True:
            off, ok = 0, True
            for key, _, _, dur, _, load in phases:
                if not alloc.fits(key, load, t + off, dur):
                    ok = False
                    break
                off += dur
            if ok:
                break
            t += 1
        if t > base:
            print(f"  ~ '{name}': старт сдвинут на {t - base} нед (капасити, фазы без разрывов)")
        off = 0
        for key, _, _, dur, _, load in phases:
            alloc.reserve(key, load, t + off, dur)
            starts.append(t + off)
            off += dur

    rows = []
    end = None
    for (key, row_label, style, dur, bar_label, load), i0 in zip(phases, starts):
        bar_start = alloc.week_date(i0)
        bar_end = bar_start + timedelta(days=dur * 7 - 1)
        rows.append({
            "label": row_label,
            "items": [{
                "type": "bar",
                "start": bar_start.isoformat(),
                "end": bar_end.isoformat(),
                "label": bar_label,
                "style": style,
            }],
        })
        end = bar_end

    visual_end = end
    ms = feature.get("milestone")
    if ms:
        ms_date = end + timedelta(days=1)        # понедельник после последней фазы
        label = ms if isinstance(ms, str) else ""
        rows[-1]["items"].append({
            "type": "milestone",
            "date": ms_date.isoformat(),
            "status": "planned",
            "label": label,
        })
        end = ms_date
        # подпись вехи рисуется справа от ромба — оставим под неё неделю запаса
        visual_end = ms_date + timedelta(days=7 if label else 0)
    return rows, end, visual_end


def resolve_start(feature, features_by_name, global_start, finish, resolving):
    """Дата старта фичи: явный start > after: <фича> > глобальный start."""
    name = feature.get("name", "?")
    if feature.get("start"):
        return monday(parse_date(feature["start"]))
    after = feature.get("after")
    if after:
        if after not in features_by_name:
            raise ValueError(f"Фича '{name}': after ссылается на неизвестную фичу '{after}'")
        if after in resolving:
            raise ValueError(f"Цикл в after: {' -> '.join([*resolving, after])}")
        if after not in finish:
            raise ValueError(
                f"Фича '{name}': after='{after}' ещё не спланирована — "
                f"перечисли фичи так, чтобы предшественник шёл раньше")
        return monday(finish[after] + timedelta(days=1))
    return global_start


def main(in_path, out_path):
    with open(in_path, encoding="utf-8") as f:
        src = json.load(f)
    for key in ("title", "features"):
        if key not in src:
            raise ValueError(f"В {in_path} нет обязательного поля '{key}'")
    if not src["features"]:
        raise ValueError("Список features пуст")

    sprint_weeks = src.get("sprint_weeks", SPRINT_WEEKS_DEFAULT)
    if not isinstance(sprint_weeks, (int, float)) or sprint_weeks <= 0:
        raise ValueError(f"sprint_weeks должно быть числом > 0, получено: {sprint_weeks!r}")
    work_days = src.get("work_days", WORK_DAYS_DEFAULT)
    if not isinstance(work_days, (int, float)) or not (0 < work_days <= 7):
        raise ValueError(f"work_days должно быть числом в диапазоне (0, 7], получено: {work_days!r}")

    capacity = src.get("capacity")
    cap_per = src.get("capacity_per", "week")
    if cap_per not in ("week", "sprint"):
        raise ValueError(f"capacity_per должно быть 'week' или 'sprint', получено: {cap_per!r}")
    if cap_per == "sprint":
        capacity = scale_capacity(capacity, 1 / sprint_weeks)  # чд/спринт → чд/нед

    if src.get("start"):
        global_start = monday(parse_date(src["start"]))
    else:
        today = date.today()
        global_start = monday(today)
        print(f"start не задан — беру дату запуска: {today.isoformat()} "
              f"(понедельник недели: {global_start.isoformat()})")
    alloc = CapacityAllocator(capacity, global_start)
    allow_gaps = bool(src.get("allow_gaps", False))

    features = list(src["features"])
    if any("priority" in f for f in features):
        features.sort(key=lambda f: f.get("priority", math.inf))

    features_by_name = {}
    for f in features:
        if "name" not in f:
            raise ValueError(f"У фичи нет поля name: {f!r}")
        if f["name"] in features_by_name:
            raise ValueError(f"Дубликат имени фичи: '{f['name']}'")
        features_by_name[f["name"]] = f

    groups = []
    finish = {}                                  # имя фичи → дата конца (для after)
    overall_end = global_start
    for f in features:
        start = resolve_start(f, features_by_name, global_start, finish, {f["name"]})
        rows, end, visual_end = schedule_feature(
            f, start, sprint_weeks, work_days, alloc, allow_gaps)
        finish[f["name"]] = end
        overall_end = max(overall_end, visual_end)
        group = {"name": f["name"], "rows": rows}
        if f.get("owner"):
            group["owner"] = f["owner"]
        if f.get("services"):
            group["services"] = f["services"]
        groups.append(group)

    roadmap = {
        "title": src["title"],
        "start": global_start.isoformat(),
        "end": src.get("end", overall_end.isoformat()),
        "groups": groups,
    }
    if src.get("subtitle"):
        roadmap["subtitle"] = src["subtitle"]
    if src.get("today"):
        roadmap["today"] = src["today"]

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(roadmap, f, ensure_ascii=False, indent=2)

    n_rows = sum(len(g["rows"]) for g in groups)
    print(f"OK: {out_path} — {len(groups)} фич, {n_rows} строк, "
          f"{roadmap['start']} … {roadmap['end']}")
    for g in groups:
        first = g["rows"][0]["items"][0]["start"]
        print(f"  {g['name']}: {first} → {finish[g['name']].isoformat()}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Использование: python plan_features.py features.json roadmap.json")
    main(sys.argv[1], sys.argv[2])
