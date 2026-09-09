# -*- coding: utf-8 -*-
"""
build_index.py

ポートフォリオトップページ (index.html) を生成するスクリプト。

- excel-tool/output/売上レポート.xlsx から「整形済データ」先頭8行、「月別集計」、
  「クリーニングログ」を読み込み、HTMLテーブルを組み立てる
- excel-tool/input/売上データ_raw.csv から Before/After 比較用の5行を抜き出す
- scraper/output/books.csv から先頭8行 + サマリー数値を組み立てる
- index_template.html のプレースホルダに埋め込んで index.html を書き出す

実行方法:
    python build_index.py
"""

import csv
import html
import os

from openpyxl import load_workbook

ROOT = os.path.dirname(os.path.abspath(__file__))
XLSX_PATH = os.path.join(ROOT, "excel-tool", "output", "売上レポート.xlsx")
RAW_CSV_PATH = os.path.join(ROOT, "excel-tool", "input", "売上データ_raw.csv")
BOOKS_CSV_PATH = os.path.join(ROOT, "scraper", "output", "books.csv")
TEMPLATE_PATH = os.path.join(ROOT, "index_template.html")
OUTPUT_PATH = os.path.join(ROOT, "index.html")


def esc(v) -> str:
    return html.escape("" if v is None else str(v))


def table_html(headers, rows, css_class="data-table"):
    out = [f'<table class="{css_class}"><thead><tr>']
    for h in headers:
        out.append(f"<th>{esc(h)}</th>")
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>")
        for cell in row:
            out.append(f"<td>{esc(cell)}</td>")
        out.append("</tr>")
    out.append("</tbody></table>")
    return "".join(out)


# ---------------------------------------------------------------------------
# Excel自動化サンプル
# ---------------------------------------------------------------------------

def build_excel_section():
    wb = load_workbook(XLSX_PATH, data_only=True)

    # 整形済データ 先頭8行
    ws = wb["整形済データ"]
    headers = [c.value for c in ws[1]]
    rows = []
    for r in ws.iter_rows(min_row=2, max_row=9, values_only=True):
        if r[0] is None:
            continue
        formatted = list(r)
        # 日付セルを YYYY-MM-DD 文字列に
        if hasattr(formatted[0], "strftime"):
            formatted[0] = formatted[0].strftime("%Y-%m-%d")
        # 単価・売上を円表記に
        for idx in (4, 5):
            if isinstance(formatted[idx], (int, float)):
                formatted[idx] = f"{formatted[idx]:,.0f}円"
        rows.append(formatted)
    seikei_table = table_html(headers, rows)

    # 月別集計
    ws2 = wb["月別集計"]
    headers2 = [c.value for c in ws2[1]]
    rows2 = []
    for r in ws2.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        formatted = list(r)
        if isinstance(formatted[1], (int, float)):
            formatted[1] = f"{formatted[1]:,.0f}円"
        rows2.append(formatted)
    monthly_table = table_html(headers2, rows2)

    # クリーニングログ（項目・件数の表。3行目がヘッダー）
    ws3 = wb["クリーニングログ"]
    log_rows = []
    header_row_idx = None
    for i, row in enumerate(ws3.iter_rows(values_only=True), start=1):
        if row[0] == "項目" and row[1] == "件数":
            header_row_idx = i
            continue
        if header_row_idx is not None and row[0] is not None:
            log_rows.append(row)
    log_table = table_html(["項目", "件数"], log_rows, css_class="data-table log-table")

    # Before / After: raw CSV から実際に5行抜粋 (README記載の代表的な5行と対応する行)
    with open(RAW_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        raw_all = list(reader)
    raw_header = raw_all[0]
    raw_data = [r for r in raw_all[1:] if any((c or "").strip() for c in r)]

    before_rows = []
    seen_idx = set()
    for target in ["令和8年12月20日", "2026/7", "2026-12-01", "1/15", "11/25"]:
        for i, r in enumerate(raw_data):
            if i in seen_idx:
                continue
            if r and r[0].strip().startswith(target):
                before_rows.append(r)
                seen_idx.add(i)
                break
    if len(before_rows) < 5:
        for i, r in enumerate(raw_data):
            if len(before_rows) >= 5:
                break
            if i not in seen_idx:
                before_rows.append(r)
                seen_idx.add(i)

    before_table = table_html(raw_header, before_rows, css_class="data-table before-table")

    # After: 上記と同じ行を整形済データから対応日付で拾う (整形済データ全件を読む)
    all_clean_rows = []
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r[0] is None:
            continue
        all_clean_rows.append(list(r))

    after_rows = []
    before_dates_norm = []
    for r in before_rows:
        raw_d = r[0].strip()
        before_dates_norm.append(raw_d)

    # 素朴なマッチング: 日付文字列の断片(月/日 や 令和年)をキーに、整形済側の日付・顧客名で照合
    import re

    def guess_iso(raw_d):
        m = re.match(r"^(\d{4})[/\-](\d{1,2})[/\-](\d{1,2})$", raw_d)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            return f"{y:04d}-{mo:02d}-{d:02d}"
        m = re.match(r"^令和(\d{1,2})年(\d{1,2})月(\d{1,2})日$", raw_d)
        if m:
            ry, mo, d = (int(x) for x in m.groups())
            y = ry + 2018
            return f"{y:04d}-{mo:02d}-{d:02d}"
        m = re.match(r"^(\d{1,2})[/\-](\d{1,2})$", raw_d)
        if m:
            mo, d = (int(x) for x in m.groups())
            return f"2026-{mo:02d}-{d:02d}"
        return None

    for r in before_rows:
        iso = guess_iso(r[0].strip())
        customer = r[1].strip()
        match = None
        for cr in all_clean_rows:
            cr_date = cr[0]
            if hasattr(cr_date, "strftime"):
                cr_date = cr_date.strftime("%Y-%m-%d")
            if cr_date == iso and cr[1] == customer:
                match = cr
                break
        if match:
            formatted = list(match)
            if hasattr(formatted[0], "strftime"):
                formatted[0] = formatted[0].strftime("%Y-%m-%d")
            for idx in (4, 5):
                if isinstance(formatted[idx], (int, float)):
                    formatted[idx] = f"{formatted[idx]:,.0f}円"
            after_rows.append(formatted)

    after_table = table_html(headers, after_rows, css_class="data-table after-table")

    return {
        "seikei_table": seikei_table,
        "monthly_table": monthly_table,
        "log_table": log_table,
        "before_table": before_table,
        "after_table": after_table,
    }


# ---------------------------------------------------------------------------
# スクレイピングサンプル
# ---------------------------------------------------------------------------

def build_books_section():
    with open(BOOKS_CSV_PATH, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f)
        all_rows = list(reader)
    header = all_rows[0]
    data = all_rows[1:]

    display_rows = []
    for r in data[:8]:
        title, price, rating, avail, url = r
        display_rows.append([title, f"£{float(price):.2f}", f"{rating}", avail, url])

    books_table = table_html(
        ["タイトル", "価格(GBP)", "評価(1-5)", "在庫状況", "詳細URL"], display_rows,
        css_class="data-table books-table",
    )

    total = len(data)
    avg_price = sum(float(r[1]) for r in data) / total if total else 0

    return {
        "books_table": books_table,
        "books_total": f"{total}件",
        "books_avg_price": f"£{avg_price:.2f}",
    }


def main():
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    ctx = {}
    ctx.update(build_excel_section())
    ctx.update(build_books_section())

    out = template
    for key, value in ctx.items():
        out = out.replace("{{" + key + "}}", value)

    remaining = [seg for seg in out.split("{{") if "}}" in seg]
    if remaining:
        unresolved = [seg.split("}}")[0] for seg in remaining]
        raise RuntimeError(f"未解決のプレースホルダがあります: {unresolved}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write(out)

    print(f"[OK] {OUTPUT_PATH} を生成しました")


if __name__ == "__main__":
    main()
