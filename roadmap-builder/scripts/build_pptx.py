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
