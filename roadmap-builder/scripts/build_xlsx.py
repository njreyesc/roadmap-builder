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
