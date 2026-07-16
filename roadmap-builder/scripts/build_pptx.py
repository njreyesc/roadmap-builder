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

from roadmap_common import (
    STYLE,
    feature_flags_on,
    feature_span,
    flag_markers,
    flatten_rows,
    group_label,
    load_roadmap,
)

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


EMU_PER_IN = 914400


def fit_bar_text(text, w, h, sizes=(8.5, 7.5, 6.5)):
    """Подбирает размер шрифта, чтобы текст влез в плашку w×h (EMU).

    Если не влезает даже минимальным — усекает с многоточием.
    Оценка ширины символа ~0.55·size pt (кириллица), высоты строки ~1.25·size pt.
    """
    if not text:
        return text, sizes[0]
    w_in = max(0.1, w / EMU_PER_IN - 0.06)  # минус внутренние поля
    h_in = max(0.08, h / EMU_PER_IN - 0.02)
    cpl = lines = 1
    for size in sizes:
        cpl = max(1, int(w_in / (size * 0.55 / 72)))
        lines = max(1, int(h_in / (size * 1.25 / 72)))
        if len(text) <= cpl * lines:
            return text, size
    cap = max(1, cpl * lines - 1)
    return text[:cap] + "…", sizes[-1]


def text_fits(text, w, h, size):
    """Влезает ли text в плашку w×h (EMU) при кегле size без усечения."""
    if not text:
        return True
    w_in = max(0.1, w / EMU_PER_IN - 0.06)
    h_in = max(0.08, h / EMU_PER_IN - 0.02)
    cpl = max(1, int(w_in / (size * 0.55 / 72)))
    lines = max(1, int(h_in / (size * 1.25 / 72)))
    return len(text) <= cpl * lines


def add_box(slide, x, y, w, h, fill_hex=None, line_hex=None, text="", size=9,
            bold=False, color=STYLE["text"], align=PP_ALIGN.CENTER,
            shape=MSO_SHAPE.RECTANGLE, line_w=0.75, pad_right=0):
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
    tf.margin_left = Emu(18000)
    tf.margin_right = Emu(18000) + pad_right  # доп. поле справа (напр. под ромб)
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
        header_y = y  # верх полосы месяцев — сюда сажаем вымпелы флажков
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
            # подпись строки — ужимаем/усекаем по высоте дорожки, чтобы текст
            # не вылезал за границу строки и не перечёркивался линией сетки
            rlabel, rsize = fit_bar_text(row.get("label", ""), LABEL_W, ROW_H,
                                         sizes=(8, 7.5, 7))
            add_box(slide, MARGIN + GROUP_W, ry, LABEL_W, ROW_H, text=rlabel,
                    size=rsize, align=PP_ALIGN.LEFT)

            # пред-скан строки: недели, занятые полосами/вехами (куда нельзя
            # ставить выноску), и недели с вехами (там резервируем место под ромб)
            row_busy, ms_weeks = set(), set()
            for it in row.get("items", []):
                if it["type"] == "bar":
                    c = tl.clip_bar(it["start"], it["end"])
                    if c:
                        row_busy.update(range(c[0], c[1] + 1))
                elif it["type"] == "milestone":
                    mi = tl.week_index(it["date"], clamp=False)
                    if mi is not None:
                        row_busy.add(mi)
                        ms_weeks.add(mi)

            occupied = set()
            for item in row.get("items", []):
                t = item.get("type")
                if t == "bar":
                    clip = tl.clip_bar(item["start"], item["end"], item.get("label", ""))
                    if clip is None:
                        print(f"! полоса '{item.get('label')}' в строке '{row.get('label')}' "
                              f"целиком вне диапазона roadmap — пропущена")
                        continue
                    i0, i1, cut_l, cut_r = clip
                    if any(i in occupied for i in range(i0, i1 + 1)):
                        print(f"! перекрытие в строке '{row.get('label')}': "
                              f"полоса '{item.get('label')}' налезает на соседний элемент")
                    occupied.update(range(i0, i1 + 1))
                    label = item.get("label", "")
                    if cut_r:
                        label = (label + " →") if label else "→"
                    if cut_l:
                        label = ("← " + label) if label else "←"
                    style = item.get("style", "work")
                    bw = week_w * (i1 - i0 + 1) - Emu(40000)
                    bh = ROW_H - Inches(0.1)
                    # если на правой неделе полосы стоит веха — резервируем место
                    # под ромб, чтобы текст полосы его не задевал
                    d = Inches(0.16)
                    pad_r = (int(week_w / 2) + int(d / 2)) if i1 in ms_weeks else 0
                    # влезает ли имя внутрь полосы (с учётом резерва под ромб)?
                    fits = text_fits(label, bw - pad_r, bh, 6.5)
                    in_text, in_size = fit_bar_text(label, bw - pad_r, bh) if fits else ("", 9)
                    add_box(slide, week_x(i0) + Emu(20000), ry + Inches(0.05), bw, bh,
                            fill_hex=STYLE[f"bar_{style}_fill"], line_hex=STYLE[f"bar_{style}_line"],
                            text=in_text, size=in_size,
                            shape=MSO_SHAPE.ROUNDED_RECTANGLE, pad_right=pad_r)
                    if not fits and label:
                        # имя не влезает в полосу — выносим его подписью в свободные
                        # недели справа (или слева, если справа занято/нет места)
                        fr = 0
                        w = i1 + 1
                        while w < tl.n and w not in row_busy and fr < 4:
                            fr += 1
                            w += 1
                        fl = 0
                        w = i0 - 1
                        while w >= 0 and w not in row_busy and fl < 4:
                            fl += 1
                            w -= 1
                        if fr >= 1:
                            cx0 = week_x(i1 + 1) + Emu(20000)
                            cw = week_w * fr - Emu(40000)
                            ctext, csize = fit_bar_text(label, cw, ROW_H, sizes=(8, 7.5, 7))
                            add_box(slide, cx0, ry, cw, ROW_H, text=ctext, size=csize,
                                    align=PP_ALIGN.LEFT)
                            occupied.update(range(i1 + 1, i1 + 1 + fr))
                        elif fl >= 1:
                            cw = week_w * fl - Emu(40000)
                            ctext, csize = fit_bar_text(label, cw, ROW_H, sizes=(8, 7.5, 7))
                            add_box(slide, week_x(i0 - fl) + Emu(20000), ry, cw, ROW_H,
                                    text=ctext, size=csize, align=PP_ALIGN.RIGHT)
                            occupied.update(range(i0 - fl, i0))
                        else:
                            # места нет ни справа, ни слева — печатаем усечённым внутри
                            lt, ls = fit_bar_text(label, bw - pad_r, bh)
                            add_box(slide, week_x(i0) + Emu(20000), ry + Inches(0.05),
                                    bw, bh, text=lt, size=ls, color=STYLE["text"],
                                    shape=MSO_SHAPE.RECTANGLE, pad_right=pad_r)
                elif t == "milestone":
                    i0 = tl.week_index(item["date"], clamp=False)
                    if i0 is None:
                        print(f"! веха '{item.get('label', item['date'])}' в строке "
                              f"'{row.get('label')}' вне диапазона roadmap — пропущена")
                        continue
                    # веха на границе полосы (старт/финиш задачи): подпись
                    # занимает ~2 недели справа от ромба — прячем её, если ромб
                    # или зона подписи налезают на полосу, оставляя чистый
                    # ромб-маркер; свободная веха рисуется с датой
                    label_busy = any(w in occupied for w in (i0, i0 + 1))
                    occupied.add(i0)
                    status = item.get("status", "done")
                    d = Inches(0.16)
                    cx = week_x(i0) + int(week_w / 2) - int(d / 2)
                    fill_hex = STYLE["milestone_done_fill"] if status == "done" else STYLE["milestone_planned_fill"]
                    line_hex = STYLE["milestone_done_line"] if status == "done" else STYLE["milestone_planned_line"]
                    add_box(slide, cx, ry + int((ROW_H - d) / 2), d, d,
                            fill_hex=fill_hex, line_hex=line_hex, shape=MSO_SHAPE.DIAMOND,
                            line_w=1.25)
                    if item.get("label") and not label_busy:
                        lw = min(week_w * 2, week_x(tl.n) - (cx + d))
                        ltext, lsize = fit_bar_text(item["label"], lw, ROW_H, sizes=(8, 7))
                        add_box(slide, cx + d, ry, lw, ROW_H, text=ltext,
                                size=lsize, align=PP_ALIGN.LEFT)
                        # подпись занимает ~2 недели справа от ромба — резервируем,
                        # чтобы следующая полоса честно предупредила о перекрытии
                        occupied.update(range(i0, min(i0 + 2, tl.n)))
                elif t == "note":
                    i0 = tl.week_index(item["date"], clamp=False)
                    if i0 is None:
                        print(f"! выноска '{item['text'][:30]}…' вне диапазона roadmap — пропущена")
                        continue
                    w = min(week_w * 4, week_x(tl.n) - week_x(i0))
                    add_box(slide, week_x(i0), ry + Inches(0.03), w, ROW_H - Inches(0.06),
                            fill_hex=STYLE["note_fill"], line_hex=STYLE["note_line"],
                            text=item["text"], size=8,
                            shape=MSO_SHAPE.ROUNDED_RECTANGLE)

        # Названия групп слева
        for g, k0, n in group_spans:
            gname = group_label(g)
            # подгоняем шрифт под высоту блока группы (короткие группы из 2–3
            # строк не должны переполняться и налезать на соседнюю)
            gname, gsize = fit_bar_text(gname, GROUP_W, ROW_H * n, sizes=(9, 8, 7))
            add_box(slide, MARGIN, grid_top + ROW_H * k0, GROUP_W, ROW_H * n,
                    fill_hex=STYLE["group_fill"], line_hex=STYLE["grid_line"],
                    text=gname, size=gsize, bold=True, align=PP_ALIGN.LEFT)

        # Маркеры старта/финиша каждой фичи: цветной ромбик (как в легенде) на
        # левом крае первой полосы фичи (старт) и правом крае последней (финиш).
        # Выключаются `feature_flags: false`. Рисуются поверх полос.
        if feature_flags_on(data):
            dia = Inches(0.16)
            for g, k0, n in group_spans:
                span = feature_span(g, tl)
                if span is None:
                    continue
                s_i, e_i = span
                cy = grid_top + ROW_H * k0 + int((ROW_H - dia) / 2)  # центр первой строки фичи
                for kind, edge_i in (("start", s_i), ("end", e_i + 1)):
                    fx = week_x(edge_i)
                    add_box(slide, fx - int(dia / 2), cy, dia, dia,
                            fill_hex=STYLE[f"flag_{kind}_fill"],
                            line_hex=STYLE[f"flag_{kind}_line"],
                            shape=MSO_SHAPE.DIAMOND, line_w=1.25)

        # Линия "сегодня" — от верха сетки (не сквозь шапку недель, чтобы
        # не перечёркивать подпись недели; неделя уже подсвечена зелёным)
        if today_i is not None:
            x = week_x(today_i) + int(week_w / 2)
            ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x, grid_top,
                                            x, grid_top + grid_h)
            ln.line.color.rgb = rgb(STYLE["today_line"])
            ln.line.width = Pt(1.75)

        # Флажки границ: вертикальный «шест» через сетку + вымпел с подписью в
        # шапке месяцев на угловой неделе (старт — слева, финиш — справа).
        flag_w = Inches(0.62)
        for kind, flabel in flag_markers(data):
            x = week_x(0 if kind == "start" else tl.n)
            fill_hex = STYLE[f"flag_{kind}_fill"]
            line_hex = STYLE[f"flag_{kind}_line"]
            ln = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, x, header_y,
                                            x, grid_top + grid_h)
            ln.line.color.rgb = rgb(line_hex)
            ln.line.width = Pt(1.5)
            if kind == "start":
                bx, align, btext = x, PP_ALIGN.LEFT, "⚑ " + flabel
            else:
                bx, align, btext = x - flag_w, PP_ALIGN.RIGHT, flabel + " ⚑"
            add_box(slide, bx, header_y, flag_w, MONTH_H, fill_hex=fill_hex,
                    line_hex=line_hex, text=btext, size=8, bold=True,
                    color="FFFFFF", align=align)

        # Легенда внизу: цветной значок (фигура) + подпись тёмным текстом
        ly = grid_top + grid_h + Inches(0.12)
        if ly + Inches(0.25) < SLIDE_H:
            items = [
                (MSO_SHAPE.DIAMOND, STYLE["milestone_done_fill"], STYLE["milestone_done_line"], "выполнено"),
                (MSO_SHAPE.DIAMOND, STYLE["milestone_planned_fill"], STYLE["milestone_planned_line"], "план"),
                (MSO_SHAPE.ROUNDED_RECTANGLE, STYLE["bar_work_fill"], STYLE["bar_work_line"], "работы"),
                (MSO_SHAPE.ROUNDED_RECTANGLE, STYLE["bar_analytics_fill"], STYLE["bar_analytics_line"], "аналитика"),
                (MSO_SHAPE.ROUNDED_RECTANGLE, STYLE["bar_testing_fill"], STYLE["bar_testing_line"], "тестирование"),
                (MSO_SHAPE.ROUNDED_RECTANGLE, STYLE["bar_estimate_fill"], STYLE["bar_estimate_line"], "оценка т/з"),
                (MSO_SHAPE.ROUNDED_RECTANGLE, STYLE["bar_vacation_fill"], STYLE["bar_vacation_line"], "отпуск"),
                (MSO_SHAPE.PENTAGON, STYLE["flag_start_fill"], STYLE["flag_start_line"], "старт"),
                (MSO_SHAPE.PENTAGON, STYLE["flag_end_fill"], STYLE["flag_end_line"], "финиш"),
            ]
            x = MARGIN
            for shape, fill_hex, line_hex, label in items:
                sym_w = Inches(0.13) if shape == MSO_SHAPE.DIAMOND else Inches(0.24)
                add_box(slide, x, ly + Inches(0.045), sym_w, Inches(0.13),
                        fill_hex=fill_hex, line_hex=line_hex, shape=shape, line_w=1.0)
                add_box(slide, x + sym_w + Inches(0.03), ly, Inches(0.95), Inches(0.22),
                        text=label, size=8, color=STYLE["text"], align=PP_ALIGN.LEFT)
                x += sym_w + Inches(1.02)

    prs.save(out_path)
    print(f"OK: {out_path} — {len(rows)} строк, {len(pages)} слайдов, {tl.n} недель")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Использование: python build_pptx.py roadmap.json roadmap.pptx")
    main(sys.argv[1], sys.argv[2])
