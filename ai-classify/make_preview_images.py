# -*- coding: utf-8 -*-
"""
make_preview_images.py

output/result.xlsx から代表的な6行を選び、「スクリーンショット代わり」の
Before/After比較画像を PIL で生成する（output/preview_before.png / preview_after.png）。
"""

import os

from openpyxl import load_workbook
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.abspath(__file__))
XLSX_PATH = os.path.join(ROOT, "output", "result.xlsx")
FONT_R = "C:/Windows/Fonts/BIZ-UDGothicR.ttc"
FONT_B = "C:/Windows/Fonts/BIZ-UDGothicB.ttc"

WIDTH = 1400
BG = (250, 249, 246)
HEADER_BG = (47, 84, 150)
HEADER_FG = (255, 255, 255)
ROW_BG_A = (255, 255, 255)
ROW_BG_B = (243, 245, 249)
BORDER = (214, 219, 226)
TEXT_COLOR = (35, 38, 45)
URGENT_BG = (255, 224, 226)
URGENT_FG = (176, 30, 40)


def truncate(s: str, n: int) -> str:
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def wrap_text(draw, text, font, max_width):
    lines = []
    cur = ""
    for ch in str(text):
        test = cur + ch
        if draw.textlength(test, font=font) > max_width and cur:
            lines.append(cur)
            cur = ch
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines or [""]


def render_table(title, subtitle, headers, col_widths, rows, out_path, urgent_col=None):
    font_title = ImageFont.truetype(FONT_B, 28)
    font_sub = ImageFont.truetype(FONT_R, 16)
    font_header = ImageFont.truetype(FONT_B, 16)
    font_cell = ImageFont.truetype(FONT_R, 15)

    pad_x, pad_y = 14, 10
    line_h = 21
    header_h = 44
    top_margin = 90
    bottom_margin = 24
    side_margin = 30

    total_w = sum(col_widths)
    scale = (WIDTH - side_margin * 2) / total_w
    col_widths = [int(w * scale) for w in col_widths]
    table_w = sum(col_widths)

    # 各行の必要行数(折り返し考慮)を先に計算
    tmp_img = Image.new("RGB", (10, 10))
    tmp_draw = ImageDraw.Draw(tmp_img)
    row_heights = []
    row_lines = []
    for row in rows:
        cell_lines = []
        max_lines = 1
        for val, w in zip(row, col_widths):
            lines = wrap_text(tmp_draw, val, font_cell, w - pad_x * 2)
            cell_lines.append(lines)
            max_lines = max(max_lines, len(lines))
        row_lines.append(cell_lines)
        row_heights.append(max_lines * line_h + pad_y * 2)

    table_h = header_h + sum(row_heights)
    total_h = top_margin + table_h + bottom_margin

    img = Image.new("RGB", (WIDTH, total_h), BG)
    draw = ImageDraw.Draw(img)

    draw.text((side_margin, 24), title, font=font_title, fill=TEXT_COLOR)
    draw.text((side_margin, 60), subtitle, font=font_sub, fill=(110, 114, 122))

    x0 = side_margin
    y = top_margin

    # ヘッダー行
    draw.rectangle([x0, y, x0 + table_w, y + header_h], fill=HEADER_BG)
    cx = x0
    for h, w in zip(headers, col_widths):
        draw.text((cx + pad_x, y + (header_h - line_h) // 2), h, font=font_header, fill=HEADER_FG)
        cx += w
    y += header_h

    # データ行
    for ridx, (row, cell_lines, rh) in enumerate(zip(rows, row_lines, row_heights)):
        bg = ROW_BG_A if ridx % 2 == 0 else ROW_BG_B
        is_urgent = urgent_col is not None and row[urgent_col] == "高"
        draw.rectangle([x0, y, x0 + table_w, y + rh], fill=URGENT_BG if is_urgent else bg)
        cx = x0
        for lines, w in zip(cell_lines, col_widths):
            ty = y + pad_y
            fill = URGENT_FG if is_urgent else TEXT_COLOR
            for line in lines:
                draw.text((cx + pad_x, ty), line, font=font_cell, fill=fill)
                ty += line_h
            cx += w
        y += rh

    # 罫線
    cx = x0
    for w in col_widths:
        draw.line([cx, top_margin, cx, top_margin + table_h], fill=BORDER)
        cx += w
    draw.line([x0 + table_w, top_margin, x0 + table_w, top_margin + table_h], fill=BORDER)
    draw.line([x0, top_margin, x0 + table_w, top_margin], fill=BORDER)
    draw.line([x0, top_margin + table_h, x0 + table_w, top_margin + table_h], fill=BORDER)
    y2 = top_margin + header_h
    for rh in row_heights:
        draw.line([x0, y2, x0 + table_w, y2], fill=BORDER)
        y2 += rh

    img.save(out_path)
    print(f"Wrote {out_path} ({WIDTH}x{total_h})")


def main():
    wb = load_workbook(XLSX_PATH, data_only=True)
    ws = wb["分類結果"]
    header = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(header)}
    all_rows = [list(r) for r in ws.iter_rows(min_row=2, values_only=True)]

    # 見栄えのするデモになるよう、カテゴリ・緊急度がなるべく異なる6行を選ぶ
    picked = []
    seen_cats = set()
    for r in all_rows:
        cat = r[idx["カテゴリ"]]
        if cat not in seen_cats:
            picked.append(r)
            seen_cats.add(cat)
        if len(picked) >= 6:
            break
    if len(picked) < 6:
        for r in all_rows:
            if r not in picked:
                picked.append(r)
            if len(picked) >= 6:
                break

    # Before: 日時 / 顧客名(架空) / 問い合わせ本文
    before_headers = ["日時", "顧客名(架空)", "問い合わせ本文"]
    before_rows = [
        [r[idx["日時"]], r[idx["顧客名(架空)"]], truncate(r[idx["問い合わせ本文"]], 60)] for r in picked
    ]
    render_table(
        "Before：問い合わせ一覧（そのまま）",
        "日時・顧客名・本文が並んでいるだけで、内容の把握や優先順位付けは目視作業",
        before_headers,
        [130, 110, 520],
        before_rows,
        os.path.join(ROOT, "output", "preview_before.png"),
    )

    # After: 8列
    after_headers = ["日時", "顧客名", "問い合わせ本文", "カテゴリ", "要約", "緊急度", "返信要否", "返信案"]
    after_rows = []
    for r in picked:
        after_rows.append(
            [
                r[idx["日時"]],
                r[idx["顧客名(架空)"]],
                truncate(r[idx["問い合わせ本文"]], 34),
                r[idx["カテゴリ"]],
                truncate(r[idx["要約"]], 22),
                r[idx["緊急度"]],
                r[idx["返信要否"]],
                truncate(r[idx["返信案"]], 42),
            ]
        )
    render_table(
        "After：AI分類 + 要約 + 返信案つき",
        "カテゴリ・緊急度で並び替え/フィルタでき、返信案があるのでそのまま返信作業に着手できる",
        after_headers,
        [110, 90, 300, 110, 190, 70, 80, 320],
        after_rows,
        os.path.join(ROOT, "output", "preview_after.png"),
        urgent_col=5,
    )


if __name__ == "__main__":
    main()
