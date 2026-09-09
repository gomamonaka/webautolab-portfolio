#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape_books.py
================
books.toscrape.com (スクレイピング練習専用の合法的なサンプルサイト) の
カタログページから書籍情報を収集し、CSV / Excel 形式で出力するツール。

対象サイトの利用規約・robots.txtを遵守した範囲で対応します。
  - robots.txt: https://books.toscrape.com/robots.txt (User-agent: * / Disallow: なし)
  - リクエスト間隔: 既定 1 秒（--delay で変更可）
  - User-Agent を明示的に設定
  - タイムアウト・リトライ（指数バックオフ）付き

使い方:
    python scrape_books.py --pages 3 --out output
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

try:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
except ImportError:  # pragma: no cover
    Workbook = None


BASE_URL = "https://books.toscrape.com/"
CATALOGUE_URL_TMPL = "https://books.toscrape.com/catalogue/page-{page}.html"
USER_AGENT = (
    "Mozilla/5.0 (compatible; PortfolioScrapingBot/1.0; "
    "+https://books.toscrape.com/) "
    "PythonRequests/PortfolioSample"
)

RATING_WORDS = {
    "One": 1,
    "Two": 2,
    "Three": 3,
    "Four": 4,
    "Five": 5,
}

REQUEST_DELAY_SEC = 1.0  # サイトへの負荷軽減のためのリクエスト間隔
MAX_RETRIES = 3
TIMEOUT_SEC = 10


@dataclass
class Book:
    title: str
    price_gbp: float
    rating: int
    availability: str
    detail_url: str


def build_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    return session


def fetch_with_retry(session, url, max_retries=MAX_RETRIES):
    """指数バックオフ付きでURLを取得する。失敗した場合はNoneを返す。"""
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = session.get(url, timeout=TIMEOUT_SEC)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as exc:
            last_exc = exc
            wait = 2 ** (attempt - 1)
            print(
                f"  [警告] {url} の取得に失敗 (試行 {attempt}/{max_retries}): {exc}"
                f" -> {wait}秒後に再試行します",
                file=sys.stderr,
            )
            if attempt < max_retries:
                time.sleep(wait)
    print(f"  [エラー] {url} の取得を諦めました: {last_exc}", file=sys.stderr)
    return None


def parse_price(text: str) -> float:
    """価格文字列から float(GBP) を取り出す。"""
    cleaned = text.strip()
    for ch in ("£", "Â", "\xa0"):
        cleaned = cleaned.replace(ch, "")
    cleaned = cleaned.strip()
    try:
        return float(cleaned)
    except ValueError:
        digits = "".join(c for c in cleaned if c.isdigit() or c == ".")
        return float(digits) if digits else 0.0


def parse_rating(tag) -> int:
    classes = tag.get("class", [])
    for cls in classes:
        if cls in RATING_WORDS:
            return RATING_WORDS[cls]
    return 0


def parse_catalogue_page(html: str, page_url: str) -> list:
    soup = BeautifulSoup(html, "html.parser")
    books = []
    for article in soup.select("article.product_pod"):
        title_tag = article.select_one("h3 a")
        title = title_tag.get("title", "").strip() if title_tag else ""
        detail_href = title_tag.get("href", "") if title_tag else ""
        detail_url = urljoin(page_url, detail_href)

        price_tag = article.select_one("p.price_color")
        price = parse_price(price_tag.get_text()) if price_tag else 0.0

        rating_tag = article.select_one("p.star-rating")
        rating = parse_rating(rating_tag) if rating_tag else 0

        avail_tag = article.select_one("p.instock.availability")
        availability = avail_tag.get_text(strip=True) if avail_tag else ""

        books.append(
            Book(
                title=title,
                price_gbp=price,
                rating=rating,
                availability=availability,
                detail_url=detail_url,
            )
        )
    return books


def scrape(pages: int, delay: float) -> list:
    session = build_session()
    all_books = []

    for page in range(1, pages + 1):
        if page == 1:
            url = urljoin(BASE_URL, "catalogue/page-1.html")
        else:
            url = CATALOGUE_URL_TMPL.format(page=page)
        print(f"[{page}/{pages}] 取得中: {url}")
        resp = fetch_with_retry(session, url)
        if resp is None:
            print(f"  ページ {page} をスキップします。", file=sys.stderr)
            continue

        page_books = parse_catalogue_page(resp.text, url)
        print(f"  -> {len(page_books)} 件の書籍を取得")
        all_books.extend(page_books)

        if page < pages:
            time.sleep(delay)

    return all_books


def write_csv(books: list, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Excelで文字化けしないよう UTF-8 with BOM (utf-8-sig) を使用
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["タイトル", "価格(GBP)", "評価(1-5)", "在庫状況", "詳細URL"])
        for b in books:
            writer.writerow([b.title, b.price_gbp, b.rating, b.availability, b.detail_url])


def write_xlsx(books: list, out_path: Path) -> None:
    if Workbook is None:
        print("  [警告] openpyxlが見つからないため.xlsxの出力をスキップしました。", file=sys.stderr)
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "books"

    headers = ["タイトル", "価格(GBP)", "評価(1-5)", "在庫状況", "詳細URL"]
    ws.append(headers)

    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF")
    header_align = Alignment(horizontal="center", vertical="center")
    for col_idx, _ in enumerate(headers, start=1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_align

    for b in books:
        ws.append([b.title, b.price_gbp, b.rating, b.availability, b.detail_url])

    # 列幅の自動調整
    for col_idx, header in enumerate(headers, start=1):
        max_len = len(header)
        for row_idx in range(2, ws.max_row + 1):
            val = ws.cell(row=row_idx, column=col_idx).value
            if val is not None:
                max_len = max(max_len, len(str(val)))
        letter = get_column_letter(col_idx)
        ws.column_dimensions[letter].width = min(max_len + 2, 80)

    ws.freeze_panes = "A2"
    wb.save(out_path)


def print_summary(books: list) -> None:
    print("\n" + "=" * 50)
    print("スクレイピング結果サマリー")
    print("=" * 50)
    print(f"総件数: {len(books)} 件")

    if books:
        avg_price = sum(b.price_gbp for b in books) / len(books)
        print(f"平均価格: £{avg_price:.2f}")

        dist = {i: 0 for i in range(1, 6)}
        for b in books:
            if b.rating in dist:
                dist[b.rating] += 1
        print("評価分布:")
        for star in range(5, 0, -1):
            count = dist[star]
            bar = "*" * count
            print(f"  {star}つ星: {count:3d} 件 {bar}")
    print("=" * 50)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="books.toscrape.com から書籍情報を収集しCSV/Excelに出力します。"
    )
    parser.add_argument("--pages", type=int, default=3, help="取得するカタログページ数 (既定: 3)")
    parser.add_argument("--out", type=str, default="output", help="出力先ディレクトリ (既定: output)")
    parser.add_argument(
        "--delay", type=float, default=REQUEST_DELAY_SEC, help="リクエスト間隔(秒) (既定: 1.0)"
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    print(f"books.toscrape.com からカタログ {args.pages} ページ分を取得します...")
    print(f"(リクエスト間隔: {args.delay}秒 / User-Agent設定済み / robots.txt準拠)\n")

    books = scrape(args.pages, args.delay)

    csv_path = out_dir / "books.csv"
    xlsx_path = out_dir / "books.xlsx"
    write_csv(books, csv_path)
    write_xlsx(books, xlsx_path)

    print(f"\nCSV出力: {csv_path.resolve()}")
    print(f"Excel出力: {xlsx_path.resolve()}")

    print_summary(books)


if __name__ == "__main__":
    main()
