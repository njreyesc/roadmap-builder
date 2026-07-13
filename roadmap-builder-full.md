# Skill: roadmap-builder — полный текст для переноса в другую модель
Инструкция для модели-получателя: ты — генератор roadmap. Следуй SKILL.md ниже. Разбери присланный Excel-план, построй roadmap.json по схеме, затем выполни оба Python-скрипта (нужны openpyxl и python-pptx). Если среда не позволяет запускать код — сгенерируй эти скрипты и JSON пользователю для локального запуска: pip install openpyxl python-pptx; python build_xlsx.py roadmap.json roadmap.xlsx; python build_pptx.py roadmap.json roadmap.pptx

---

## SKILL.md (инструкция скилла)

```markdown
---
name: roadmap-builder
description: Строит roadmap (дорожную карту) в двух форматах — Excel (.xlsx) и PowerPoint (.pptx) — из исходного Excel-плана работ по спринтам/неделям/людям. Использовать всегда, когда пользователь просит roadmap, дорожную карту, план-график, Gantt, таймлайн по спринтам, «переложи план в презентацию», «сделай roadmap из excel», или присылает файл плана работ со спринтами и просит визуализацию. Также использовать при обновлении существующего roadmap новыми данными.
---

# Roadmap Builder

Превращает исходный Excel-план работ (спринты в колонках, люди/команды в строках, задачи в ячейках) в roadmap двух видов:

1. **roadmap.xlsx** — таймлайн-сетка: месяцы → недели в шапке, дорожки (свимлейны) по командам/направлениям, вехи-ромбы, полосы работ с подписями («6 спринтов 2 ше»), выноски-комментарии, отметка «сегодня».
2. **roadmap.pptx** — те же данные слайдами в стиле управленческой презентации: сетка недель, оранжевые/жёлтые полосы, зелёные (done) и белые с красным контуром (план) ромбы, голубые выноски, зелёная вертикальная линия «сегодня».

## Архитектура: parse → JSON → render

Никогда не рисуй roadmap «вручную» напрямую из исходника. Всегда три шага:

1. **Разбор исходника (делаешь ты).** Прочитай исходный .xlsx через openpyxl (включая заливки ячеек — цвет несёт смысл). Пойми структуру и извлеки задачи.
2. **Нормализация в `roadmap.json`.** Схема — в `references/data-schema.md`. Это единственный вход для рендереров. Покажи пользователю краткую сводку того, что распознал (сколько дорожек, задач, вех), прежде чем рендерить.
3. **Рендеринг скриптами:**
   ```bash
   python scripts/build_xlsx.py roadmap.json roadmap.xlsx
   python scripts/build_pptx.py roadmap.json roadmap.pptx
   ```
   Скрипты детерминированные — не переписывай их под конкретный файл. Если чего-то не хватает, расширяй JSON-схему и скрипты, сохраняя обратную совместимость.

## Как разбирать исходный план

Типичный исходник: шапка из 2–3 строк (месяц / «Спринт N» / диапазон дат недели «20.07-26.07»), в первой колонке (или нескольких) — человек/команда/направление, в ячейках — тексты задач, иногда с тегами вида `[SDD]`, `[Сделки_ДЗО]`.

Правила интерпретации:
- **Колонка недели** задаёт даты: неделя с понедельника. Диапазоны вида «29.06 - 05.07» парси по первой дате; год бери из контекста листа (шапки месяца) или спроси.
- **Одна и та же задача в соседних ячейках подряд** = одна полоса (bar) от первой до последней недели. Сравнивай тексты нечётко: одинаковый префикс/тикет — та же задача.
- **Цвет заливки несёт смысл** (уточни у пользователя при первом использовании и запомни): в типичном исходнике жёлтый = отпуск или «Выход на КО», зелёный = завершено/особый статус, красный текст = риск/блокер.
- **Отпуск** — рендери как полосу style `vacation`.
- **Строки-группы** (человек/команда) становятся `groups`, конкретные подзадачи — `rows` внутри группы. Если у человека все задачи в одной строке исходника, делай одну группу с одной-двумя строками — не плоди пустые дорожки.
- Однонедельные события с глаголом завершённости («Подготовлен драфт», «Выход на КО») — это **вехи** (milestone), а не полосы.

Если структура исходника непонятна (нестандартная шапка, несколько листов) — задай пользователю один компактный вопрос со своей лучшей гипотезой, не бомбардируй вопросами.

## Что уточнить у пользователя (один раз, одним вопросом)

Если не сказано явно: период roadmap (от какой до какой даты), уровень детализации (все задачи или только ключевые вехи/полосы), дата «сегодня»-линии. Разумные дефолты: весь период исходника, все задачи, сегодняшняя дата.

## Стили (зашиты в рендереры)

| Элемент | Вид |
|---|---|
| milestone `done` | зелёный ромб ◆ |
| milestone `planned` | белый ромб с красным контуром |
| bar `work` | оранжевая полоса, подпись внутри |
| bar `estimate` | бледно-жёлтая полоса (оценки «N спринтов M ше») |
| bar `vacation` | жёлтая полоса «Отпуск» |
| note | голубая выноска с текстом |
| today | зелёная вертикальная линия/подсветка недели |

## Ограничения и типичные ошибки

- В pptx на один слайд помещается ~14 строк дорожек — рендерер сам паджинирует, шапка повторяется. Не пытайся ужать всё в один слайд, уменьшая шрифт ниже 8pt.
- Русские подписи длинные: в xlsx подпись полосы кладётся в объединённый диапазон полосы; если текст длиннее полосы — сократи подпись в JSON (например, до тикета), полный текст унеси в `note`.
- Даты в JSON только ISO (`YYYY-MM-DD`). Все преобразования дат делай на этапе парсинга.
- После генерации обоих файлов открой их программно (openpyxl / python-pptx) и проверь: количество дорожек совпадает с JSON, нет полос с нулевой шириной, вехи попали в диапазон дат. Потом отдай файлы пользователю.

## Файлы скилла

- `references/data-schema.md` — полная JSON-схема с примером. Читай перед первой нормализацией.
- `scripts/build_xlsx.py` — рендерер Excel.
- `scripts/build_pptx.py` — рендерер PowerPoint.
- `examples/sample_roadmap.json` — рабочий пример входных данных.

```

---

## references/data-schema.md (схема roadmap.json)

```markdown
# Схема roadmap.json

Единственный вход для `build_xlsx.py` и `build_pptx.py`.

```json
{
  "title": "Roadmap: Агентская платформа",
  "subtitle": "MPV — синий",
  "start": "2025-08-04",
  "end": "2025-11-02",
  "today": "2025-08-14",
  "groups": [
    {
      "name": "КАФО агента (Интеграция, взаимодействие)",
      "owner": "Д. Шатыр",
      "rows": [
        {
          "label": "Подготовлен драфт",
          "items": [
            {"type": "milestone", "date": "2025-08-05", "status": "done", "label": ""}
          ]
        },
        {
          "label": "ClickHouse: безы ОК, ДКА",
          "items": [
            {"type": "milestone", "date": "2025-08-12", "status": "done"},
            {"type": "bar", "start": "2025-08-18", "end": "2025-08-24", "label": "Согласование", "style": "work"},
            {"type": "milestone", "date": "2025-08-25", "status": "planned"},
            {"type": "note", "date": "2025-09-08", "text": "Зависит от итогов Гембы"}
          ]
        }
      ]
    },
    {
      "name": "Требования к агентам. Способы вызова",
      "rows": [
        {
          "label": "По расписанию (оценка т/з)",
          "items": [
            {"type": "bar", "start": "2025-08-18", "end": "2025-10-12", "label": "6 спринтов 2 ше", "style": "estimate"}
          ]
        }
      ]
    }
  ]
}
```

## Поля

### Корень
| Поле | Обязательное | Описание |
|---|---|---|
| `title` | да | Заголовок (имя листа xlsx, заголовок слайда pptx) |
| `subtitle` | нет | Подзаголовок / легенда-пояснение |
| `start`, `end` | да | Границы таймлайна, ISO-даты. Округляются к понедельнику/воскресенью |
| `today` | нет | Дата зелёной линии «сегодня». Не рисуется, если вне диапазона |
| `groups` | да | Дорожки верхнего уровня |

### group
| Поле | Описание |
|---|---|
| `name` | Название команды/направления, показывается в левой колонке жирным |
| `owner` | Ответственный, показывается под названием в скобках |
| `rows` | Строки внутри дорожки |

### row
| Поле | Описание |
|---|---|
| `label` | Подпись строки (вторая колонка слева) |
| `items` | Элементы на таймлайне |

### item, type = "milestone"
| Поле | Описание |
|---|---|
| `date` | ISO-дата вехи |
| `status` | `done` (зелёный ромб) или `planned` (белый с красным контуром). По умолчанию `done` |
| `label` | Необязательная короткая подпись справа от ромба |

### item, type = "bar"
| Поле | Описание |
|---|---|
| `start`, `end` | ISO-даты включительно |
| `label` | Текст внутри полосы |
| `style` | `work` (оранжевая), `estimate` (бледно-жёлтая), `vacation` (жёлтая). По умолчанию `work` |

### item, type = "note"
| Поле | Описание |
|---|---|
| `date` | Где на таймлайне поставить выноску (левый край) |
| `text` | Текст выноски (голубая плашка) |

## Правила
- Все даты — `YYYY-MM-DD`. Единица сетки — неделя (пн–вс).
- Элементы одной строки не должны перекрываться по неделям (кроме note — она рисуется поверх). Если в исходнике перекрытие — разнеси по отдельным row.
- Пустая строка (без items) допустима — используется как визуальный разделитель.

```

---

## scripts/roadmap_common.py

```python
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
    "bar_work_fill": "F5A623",            # оранжевый
    "bar_work_line": "C77F00",
    "bar_estimate_fill": "FBEAB6",        # бледно-жёлтый
    "bar_estimate_line": "E0C878",
    "bar_vacation_fill": "FFF176",        # жёлтый
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
        d = parse_date(d) if isinstance(d, str) else d
        i = (monday(d) - self.start).days // 7
        if clamp:
            i = max(0, min(self.n - 1, i))
        elif i < 0 or i >= self.n:
            return None
        return i

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


def flatten_rows(data):
    """[(group, row, is_first_row_of_group)] в порядке отрисовки."""
    out = []
    for g in data["groups"]:
        rows = g.get("rows") or [{"label": "", "items": []}]
        for j, r in enumerate(rows):
            out.append((g, r, j == 0))
    return out

```

---

## scripts/build_xlsx.py

```python
#!/usr/bin/env python3
"""Рендерер roadmap в Excel.

Использование: python build_xlsx.py roadmap.json roadmap.xlsx
"""
import sys

from openpyxl import Workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from roadmap_common import STYLE, flatten_rows, load_roadmap

COL_GROUP = 1   # A — команда/направление
COL_LABEL = 2   # B — подпись строки
FIRST_WEEK_COL = 3
HEADER_ROWS = 2  # месяц, неделя
FIRST_DATA_ROW = HEADER_ROWS + 2  # +1 строка под title


def fill(hexcode):
    return PatternFill("solid", fgColor=hexcode)


def thin_border(color=STYLE["grid_line"]):
    side = Side(style="thin", color=color)
    return Border(left=side, right=side, top=side, bottom=side)


def main(json_path, out_path):
    data, tl = load_roadmap(json_path)
    wb = Workbook()
    ws = wb.active
    ws.title = "Roadmap"

    center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left = Alignment(horizontal="left", vertical="center", wrap_text=True)

    # Заголовок
    ws.cell(row=1, column=1, value=data["title"]).font = Font(bold=True, size=14)
    if data.get("subtitle"):
        c = ws.cell(row=1, column=FIRST_WEEK_COL, value=data["subtitle"])
        c.font = Font(italic=True, size=10, color="4472C4")

    # Шапка: месяцы (объединённые) и недели
    today_col = None
    if data.get("today"):
        ti = tl.week_index(data["today"], clamp=False)
        if ti is not None:
            today_col = FIRST_WEEK_COL + ti

    for label, i0, i1 in tl.month_spans():
        c0, c1 = FIRST_WEEK_COL + i0, FIRST_WEEK_COL + i1
        ws.merge_cells(start_row=2, start_column=c0, end_row=2, end_column=c1)
        cell = ws.cell(row=2, column=c0, value=label)
        cell.fill = fill(STYLE["header_fill"])
        cell.font = Font(bold=True, color=STYLE["header_font"])
        cell.alignment = center
    for i in range(tl.n):
        col = FIRST_WEEK_COL + i
        cell = ws.cell(row=3, column=col, value=tl.week_label(i))
        cell.fill = fill(STYLE["today_line"] if col == today_col else STYLE["week_fill"])
        if col == today_col:
            cell.font = Font(bold=True, color="FFFFFF")
        cell.alignment = center
        cell.border = thin_border()
        ws.column_dimensions[get_column_letter(col)].width = 8.5

    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 30

    rows = flatten_rows(data)
    # Сетка + данные
    bar_styles = {
        "work": (STYLE["bar_work_fill"], STYLE["text"]),
        "estimate": (STYLE["bar_estimate_fill"], STYLE["text"]),
        "vacation": (STYLE["bar_vacation_fill"], STYLE["text"]),
    }
    r = FIRST_DATA_ROW
    group_start = {}
    for g, row, is_first in rows:
        gname = g["name"] + (f'\n({g["owner"]})' if g.get("owner") else "")
        if is_first:
            group_start[id(g)] = r
        # фон сетки
        for i in range(tl.n):
            cell = ws.cell(row=r, column=FIRST_WEEK_COL + i)
            cell.border = thin_border()
        lab = ws.cell(row=r, column=COL_LABEL, value=row.get("label", ""))
        lab.alignment = left
        lab.font = Font(size=9)
        lab.border = thin_border()
        ws.row_dimensions[r].height = 22

        occupied = set()
        for item in row.get("items", []):
            t = item.get("type")
            if t == "bar":
                i0 = tl.week_index(item["start"])
                i1 = tl.week_index(item["end"])
                if i1 < i0:
                    i0, i1 = i1, i0
                c0, c1 = FIRST_WEEK_COL + i0, FIRST_WEEK_COL + i1
                if any(c in occupied for c in range(c0, c1 + 1)):
                    print(f"! перекрытие в строке '{row.get('label')}', полоса '{item.get('label')}' пропущена частично")
                if c1 > c0:
                    ws.merge_cells(start_row=r, start_column=c0, end_row=r, end_column=c1)
                bar_fill, font_color = bar_styles.get(item.get("style", "work"), bar_styles["work"])
                cell = ws.cell(row=r, column=c0, value=item.get("label", ""))
                cell.alignment = center
                cell.font = Font(size=9, color=font_color)
                for c in range(c0, c1 + 1):
                    ws.cell(row=r, column=c).fill = fill(bar_fill)
                    ws.cell(row=r, column=c).border = thin_border(bar_styles.get(item.get("style", "work"))[0])
                    occupied.add(c)
            elif t == "milestone":
                i0 = tl.week_index(item["date"])
                c0 = FIRST_WEEK_COL + i0
                status = item.get("status", "done")
                color = STYLE["milestone_done_fill"] if status == "done" else STYLE["milestone_planned_line"]
                text = "◆" if status == "done" else "◇"
                if item.get("label"):
                    text += " " + item["label"]
                cell = ws.cell(row=r, column=c0, value=text)
                cell.font = Font(size=12, color=color, bold=True)
                cell.alignment = center
                occupied.add(c0)
            elif t == "note":
                i0 = tl.week_index(item["date"])
                c0 = FIRST_WEEK_COL + i0
                cell = ws.cell(row=r, column=c0)
                # выноска — комментарий + голубая метка, чтобы не воевать за место с полосами
                if cell.value is None and c0 not in occupied:
                    cell.value = "🗨"
                    cell.alignment = center
                target = ws.cell(row=r, column=c0)
                target.comment = Comment(item["text"], "roadmap", height=80, width=260)
                if c0 not in occupied:
                    target.fill = fill(STYLE["note_fill"])
        r += 1

    # Объединение колонки групп
    for g in data["groups"]:
        start = group_start[id(g)]
        n = max(1, len(g.get("rows") or [1]))
        if n > 1:
            ws.merge_cells(start_row=start, start_column=COL_GROUP, end_row=start + n - 1, end_column=COL_GROUP)
        gname = g["name"] + (f'\n({g["owner"]})' if g.get("owner") else "")
        cell = ws.cell(row=start, column=COL_GROUP, value=gname)
        cell.font = Font(bold=True, size=10)
        cell.alignment = Alignment(horizontal="left", vertical="top", wrap_text=True)
        for rr in range(start, start + n):
            ws.cell(row=rr, column=COL_GROUP).fill = fill(STYLE["group_fill"])
            ws.cell(row=rr, column=COL_GROUP).border = thin_border()

    # Линия "сегодня": правая граница колонки текущей недели
    if today_col:
        side = Side(style="medium", color=STYLE["today_line"])
        for rr in range(3, r):
            cell = ws.cell(row=rr, column=today_col)
            b = cell.border
            cell.border = Border(left=b.left, right=side, top=b.top, bottom=b.bottom)

    # Легенда
    lr = r + 2
    ws.cell(row=lr, column=COL_LABEL, value="Легенда:").font = Font(bold=True, size=9)
    legend = [
        ("◆ выполнено / факт", STYLE["milestone_done_fill"], None),
        ("◇ план / под вопросом", STYLE["milestone_planned_line"], None),
        ("работы", None, STYLE["bar_work_fill"]),
        ("оценка т/з", None, STYLE["bar_estimate_fill"]),
        ("отпуск", None, STYLE["bar_vacation_fill"]),
    ]
    for k, (text, font_color, bg) in enumerate(legend):
        cell = ws.cell(row=lr + 1 + k, column=COL_LABEL, value=text)
        cell.font = Font(size=9, color=font_color or STYLE["text"])
        if bg:
            cell.fill = fill(bg)

    ws.freeze_panes = ws.cell(row=FIRST_DATA_ROW, column=FIRST_WEEK_COL)
    wb.save(out_path)
    print(f"OK: {out_path} — {len(rows)} строк, {tl.n} недель")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Использование: python build_xlsx.py roadmap.json roadmap.xlsx")
    main(sys.argv[1], sys.argv[2])

```

---

## scripts/build_pptx.py

```python
#!/usr/bin/env python3
"""Рендерер roadmap в PowerPoint (16:9).

Использование: python build_pptx.py roadmap.json roadmap.pptx
"""
import sys

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from roadmap_common import STYLE, flatten_rows, load_roadmap

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)
MARGIN = Inches(0.25)
GROUP_W = Inches(2.1)
LABEL_W = Inches(1.9)
TITLE_H = Inches(0.45)
MONTH_H = Inches(0.28)
WEEK_H = Inches(0.24)
ROW_H = Inches(0.34)
MAX_ROWS_PER_SLIDE = 15


def rgb(hexcode):
    return RGBColor.from_string(hexcode)


def add_box(slide, x, y, w, h, fill_hex=None, line_hex=None, text="", size=9,
            bold=False, color=STYLE["text"], align=PP_ALIGN.CENTER,
            shape=MSO_SHAPE.RECTANGLE, line_w=0.75):
    sp = slide.shapes.add_shape(shape, x, y, w, h)
    if fill_hex:
        sp.fill.solid()
        sp.fill.fore_color.rgb = rgb(fill_hex)
    else:
        sp.fill.background()
    if line_hex:
        sp.line.color.rgb = rgb(line_hex)
        sp.line.width = Pt(line_w)
    else:
        sp.line.fill.background()
    sp.shadow.inherit = False
    tf = sp.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Emu(18000)
    tf.margin_top = tf.margin_bottom = Emu(9000)
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]
    p.alignment = align
    if text:
        run = p.add_run()
        run.text = text
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = rgb(color)
    return sp


def main(json_path, out_path):
    data, tl = load_roadmap(json_path)
    prs = Presentation()
    prs.slide_width = SLIDE_W
    prs.slide_height = SLIDE_H
    blank = prs.slide_layouts[6]

    rows = flatten_rows(data)
    pages = [rows[i:i + MAX_ROWS_PER_SLIDE] for i in range(0, len(rows), MAX_ROWS_PER_SLIDE)]

    tl_x = MARGIN + GROUP_W + LABEL_W
    tl_w = SLIDE_W - tl_x - MARGIN
    week_w = int(tl_w / tl.n)

    def week_x(i):
        return tl_x + week_w * i

    today_i = tl.week_index(data["today"], clamp=False) if data.get("today") else None

    for page_no, page in enumerate(pages):
        slide = prs.slides.add_slide(blank)
        y = MARGIN

        # Заголовок
        title = data["title"] + (f" ({page_no + 1}/{len(pages)})" if len(pages) > 1 else "")
        add_box(slide, MARGIN, y, Inches(8), TITLE_H, text=title, size=18, bold=True,
                align=PP_ALIGN.LEFT)
        if data.get("subtitle"):
            add_box(slide, MARGIN + Inches(8), y, SLIDE_W - Inches(8) - 2 * MARGIN, TITLE_H,
                    text=data["subtitle"], size=10, color="4472C4", align=PP_ALIGN.RIGHT)
        y += TITLE_H + Inches(0.05)

        # Шапка: месяцы и недели
        for label, i0, i1 in tl.month_spans():
            add_box(slide, week_x(i0), y, week_w * (i1 - i0 + 1), MONTH_H,
                    fill_hex=STYLE["header_fill"], line_hex="FFFFFF",
                    text=label, size=10, bold=True, color=STYLE["header_font"])
        y += MONTH_H
        for i in range(tl.n):
            is_today = i == today_i
            add_box(slide, week_x(i), y, week_w, WEEK_H,
                    fill_hex=STYLE["today_line"] if is_today else STYLE["week_fill"],
                    line_hex="FFFFFF", text=tl.week_label(i), size=8,
                    bold=is_today, color="FFFFFF" if is_today else STYLE["text"])
        y += WEEK_H
        grid_top = y
        grid_h = ROW_H * len(page)

        # Фоновая сетка недель
        for i in range(tl.n + 1):
            ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, week_x(i), grid_top,
                                            week_x(i), grid_top + grid_h)
            ln.line.color.rgb = rgb(STYLE["grid_line"])
            ln.line.width = Pt(0.5)

        # Дорожки
        group_spans = []  # (group, first_row_idx, n_rows) на этой странице
        for k, (g, row, is_first) in enumerate(page):
            ry = grid_top + ROW_H * k
            if is_first or k == 0:
                group_spans.append([g, k, 0])
            group_spans[-1][2] += 1
            # горизонтальная линия
            ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, MARGIN, ry, week_x(tl.n), ry)
            ln.line.color.rgb = rgb(STYLE["grid_line"])
            ln.line.width = Pt(0.5)
            # подпись строки
            add_box(slide, MARGIN + GROUP_W, ry, LABEL_W, ROW_H, text=row.get("label", ""),
                    size=8, align=PP_ALIGN.LEFT)

            for item in row.get("items", []):
                t = item.get("type")
                if t == "bar":
                    i0 = tl.week_index(item["start"])
                    i1 = tl.week_index(item["end"])
                    if i1 < i0:
                        i0, i1 = i1, i0
                    style = item.get("style", "work")
                    add_box(slide, week_x(i0) + Emu(20000), ry + Inches(0.05),
                            week_w * (i1 - i0 + 1) - Emu(40000), ROW_H - Inches(0.1),
                            fill_hex=STYLE[f"bar_{style}_fill"], line_hex=STYLE[f"bar_{style}_line"],
                            text=item.get("label", ""), size=8.5,
                            shape=MSO_SHAPE.ROUNDED_RECTANGLE)
                elif t == "milestone":
                    i0 = tl.week_index(item["date"])
                    status = item.get("status", "done")
                    d = Inches(0.16)
                    cx = week_x(i0) + int(week_w / 2) - int(d / 2)
                    fill_hex = STYLE["milestone_done_fill"] if status == "done" else STYLE["milestone_planned_fill"]
                    line_hex = STYLE["milestone_done_line"] if status == "done" else STYLE["milestone_planned_line"]
                    add_box(slide, cx, ry + int((ROW_H - d) / 2), d, d,
                            fill_hex=fill_hex, line_hex=line_hex, shape=MSO_SHAPE.DIAMOND,
                            line_w=1.25)
                    if item.get("label"):
                        add_box(slide, cx + d, ry, week_w * 2, ROW_H, text=item["label"],
                                size=8, align=PP_ALIGN.LEFT)
                elif t == "note":
                    i0 = tl.week_index(item["date"])
                    w = min(week_w * 4, week_x(tl.n) - week_x(i0))
                    add_box(slide, week_x(i0), ry + Inches(0.03), w, ROW_H - Inches(0.06),
                            fill_hex=STYLE["note_fill"], line_hex=STYLE["note_line"],
                            text=item["text"], size=8,
                            shape=MSO_SHAPE.ROUNDED_RECTANGLE)

        # Названия групп слева
        for g, k0, n in group_spans:
            gname = g["name"] + (f'\n({g["owner"]})' if g.get("owner") else "")
            add_box(slide, MARGIN, grid_top + ROW_H * k0, GROUP_W, ROW_H * n,
                    fill_hex=STYLE["group_fill"], line_hex=STYLE["grid_line"],
                    text=gname, size=9, bold=True, align=PP_ALIGN.LEFT)

        # Линия "сегодня"
        if today_i is not None:
            x = week_x(today_i) + int(week_w / 2)
            ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x, grid_top - MONTH_H - WEEK_H,
                                            x, grid_top + grid_h)
            ln.line.color.rgb = rgb(STYLE["today_line"])
            ln.line.width = Pt(1.75)

        # Легенда внизу
        ly = grid_top + grid_h + Inches(0.12)
        if ly + Inches(0.25) < SLIDE_H:
            items = [("◆", STYLE["milestone_done_fill"], "выполнено"),
                     ("◇", STYLE["milestone_planned_line"], "план"),
                     ("▬", STYLE["bar_work_fill"], "работы"),
                     ("▬", STYLE["bar_estimate_fill"], "оценка т/з"),
                     ("▬", STYLE["bar_vacation_fill"], "отпуск")]
            x = MARGIN
            for sym, color, label in items:
                add_box(slide, x, ly, Inches(1.5), Inches(0.22),
                        text=f"{sym} {label}", size=8, color=color, align=PP_ALIGN.LEFT)
                x += Inches(1.55)

    prs.save(out_path)
    print(f"OK: {out_path} — {len(rows)} строк, {len(pages)} слайдов, {tl.n} недель")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Использование: python build_pptx.py roadmap.json roadmap.pptx")
    main(sys.argv[1], sys.argv[2])

```

---

## examples/sample_roadmap.json (пример входных данных)

```json
{
  "title": "Roadmap: Агентская платформа",
  "subtitle": "MPV — синий",
  "start": "2025-08-04",
  "end": "2025-11-02",
  "today": "2025-08-14",
  "groups": [
    {
      "name": "КАФО агента (Интеграция, взаимодействие)",
      "owner": "Д. Шатыр",
      "rows": [
        {"label": "Подготовлен драфт", "items": [
          {"type": "milestone", "date": "2025-08-05", "status": "done"}
        ]},
        {"label": "CTL", "items": [
          {"type": "milestone", "date": "2025-08-12", "status": "done"}
        ]},
        {"label": "Фронт и СберЧат", "items": [
          {"type": "milestone", "date": "2025-08-12", "status": "done"}
        ]},
        {"label": "ClickHouse: безы ОК, ДКА", "items": [
          {"type": "milestone", "date": "2025-08-12", "status": "done"},
          {"type": "bar", "start": "2025-08-18", "end": "2025-08-24", "label": "Согласование", "style": "work"},
          {"type": "milestone", "date": "2025-08-26", "status": "planned"}
        ]},
        {"label": "ЛДБР: ДКА", "items": [
          {"type": "milestone", "date": "2025-08-12", "status": "done"}
        ]},
        {"label": "IDP", "items": [
          {"type": "milestone", "date": "2025-09-01", "status": "planned"},
          {"type": "note", "date": "2025-09-08", "text": "Зависит от итогов Гембы"}
        ]}
      ]
    },
    {
      "name": "Hello world [Python]",
      "owner": "С. Славский",
      "rows": [
        {"label": "От разработки до ПРОМ", "items": [
          {"type": "bar", "start": "2025-08-04", "end": "2025-08-10", "label": "Сборки", "style": "work"},
          {"type": "milestone", "date": "2025-08-12", "status": "done"},
          {"type": "bar", "start": "2025-08-18", "end": "2025-08-24", "label": "Тест", "style": "work"},
          {"type": "milestone", "date": "2025-08-26", "status": "planned"}
        ]}
      ]
    },
    {
      "name": "Требования к агентам. Способы вызова",
      "rows": [
        {"label": "По расписанию (оценка т/з)", "items": [
          {"type": "bar", "start": "2025-08-18", "end": "2025-10-12", "label": "6 спринтов 2 ше", "style": "estimate"}
        ]},
        {"label": "С параметрами (оценка т/з)", "items": [
          {"type": "bar", "start": "2025-08-18", "end": "2025-10-12", "label": "6 спринтов 2 ше", "style": "estimate"}
        ]},
        {"label": "Оба варианта (оценка т/з)", "items": [
          {"type": "bar", "start": "2025-08-18", "end": "2025-10-26", "label": "8 спринтов 2 ше", "style": "estimate"}
        ]}
      ]
    },
    {
      "name": "Требования к агентам. Варианты ответов",
      "rows": [
        {"label": "Ответ на почту (оценка т/з)", "items": [
          {"type": "bar", "start": "2025-08-18", "end": "2025-10-05", "label": "6 спринтов 2 ше", "style": "estimate"}
        ]}
      ]
    },
    {
      "name": "DevOps",
      "owner": "Е. Макаров",
      "rows": [
        {"label": "Базовые требования", "items": [
          {"type": "milestone", "date": "2025-08-05", "status": "done"},
          {"type": "note", "date": "2025-08-18", "text": "При текущих вводных требования стандартные"}
        ]}
      ]
    },
    {
      "name": "Интеграция",
      "owner": "С. Славский ?",
      "rows": [
        {"label": "CTL", "items": [
          {"type": "bar", "start": "2025-08-25", "end": "2025-09-21", "label": "4 спринта 2 ше", "style": "work"}
        ]},
        {"label": "СберЧат / собственный (оценка т/з)", "items": [
          {"type": "bar", "start": "2025-08-25", "end": "2025-10-19", "label": "8 спринтов 2 ше", "style": "estimate"}
        ]},
        {"label": "ClickHouse", "items": [
          {"type": "bar", "start": "2025-08-25", "end": "2025-09-21", "label": "4 спринта 2 ше", "style": "work"}
        ]}
      ]
    },
    {
      "name": "Интеграция с IDP (RAG)",
      "owner": "С. Славский ?",
      "rows": [
        {"label": "Встреча-Гемба — 20.08.2025", "items": [
          {"type": "milestone", "date": "2025-08-20", "status": "planned"}
        ]},
        {"label": "Интеграция", "items": [
          {"type": "note", "date": "2025-08-25", "text": "Трудозатраты неочевидны"}
        ]},
        {"label": "оценка т/з", "items": [
          {"type": "bar", "start": "2025-08-25", "end": "2025-10-19", "label": "8 спринтов 2 ше", "style": "estimate"}
        ]},
        {"label": "Рим — отпуск", "items": [
          {"type": "bar", "start": "2025-08-04", "end": "2025-08-17", "label": "Отпуск", "style": "vacation"}
        ]}
      ]
    }
  ]
}

```
