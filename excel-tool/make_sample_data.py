# -*- coding: utf-8 -*-
"""
make_sample_data.py

「汚い」架空の売上データ(CSV)を生成するスクリプト。
ココナラ出品用ポートフォリオ「Excel/CSVデータ整形・レポート自動化」のサンプル素材として、
実務でよくある表記ゆれ・入力ミスをわざと再現する。

生成される列:
    日付, 顧客名, 商品名, 数量, 単価, 担当者

わざと入れる「汚れ」:
    - 日付表記の混在 (2026/1/5, 2026-01-05, 令和8年1月5日, 1/5 など)
    - 全角数字 (１２００円 など)
    - 前後の余分な空白
    - 完全な重複行
    - 空行
    - 単価に「円」やカンマが付いたテキスト
    - 商品名の表記ゆれ (コーヒー豆 / 珈琲豆 / コーヒー豆(末尾空白) など)

実行方法:
    python make_sample_data.py
"""

import csv
import os
import random

random.seed(42)

OUTPUT_DIR = "input"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "売上データ_raw.csv")

HEADER = ["日付", "顧客名", "商品名", "数量", "単価", "担当者"]

# ---------------------------------------------------------------------------
# マスタデータ
# ---------------------------------------------------------------------------

CUSTOMERS = [
    "株式会社さくら商事", "有限会社みどり食品", "田中商店", "山田物産株式会社",
    "カフェ・ドゥ・ソレイユ", "はなまる工務店", "株式会社フジタ製作所",
    "こばやし青果", "スズキベーカリー", "株式会社ニシムラ",
    "たけだ薬局", "オカモト印刷株式会社", "みなと運送",
    "株式会社ヤマグチ電機", "アオキ酒店", "北海道物産センター",
    "有限会社イシダ金物店", "マツモト文具", "株式会社コンドウ商会",
    "サトウ精肉店",
]

# 商品ごとの「正しい」名称と、そのゆれバリエーション
PRODUCT_VARIANTS = {
    "コーヒー豆": ["コーヒー豆", "珈琲豆", "コーヒー豆 ", " コーヒー豆", "ｺｰﾋｰ豆"],
    "紅茶葉": ["紅茶葉", "紅茶", "紅茶葉 ", "こうちゃ葉"],
    "段ボール箱": ["段ボール箱", "ダンボール箱", "段ボール箱 ", "だんぼーる箱"],
    "印刷用紙A4": ["印刷用紙A4", "印刷用紙Ａ４", "印刷用紙A4 ", "印刷用紙(A4)"],
    "軍手": ["軍手", "軍手 ", "手袋(軍手)"],
    "接着剤": ["接着剤", "接着剤 ", "せっちゃくざい"],
    "木材(杉)": ["木材(杉)", "木材（杉）", "杉材"],
    "食パン": ["食パン", "パン(食パン)", "食パン "],
    "牛肉(国産)": ["牛肉(国産)", "国産牛肉", "牛肉（国産）"],
    "醤油": ["醤油", "しょうゆ", "醤油 "],
    "米(コシヒカリ)": ["米(コシヒカリ)", "コシヒカリ", "米（コシヒカリ）"],
    "文房具セット": ["文房具セット", "文房具セット ", "文具セット"],
}

STAFF = ["佐藤", "鈴木", "高橋", "田中", "伊藤", "渡辺", "山本", "中村"]

UNIT_PRICES = {
    "コーヒー豆": 1200,
    "紅茶葉": 900,
    "段ボール箱": 250,
    "印刷用紙A4": 450,
    "軍手": 180,
    "接着剤": 320,
    "木材(杉)": 2100,
    "食パン": 280,
    "牛肉(国産)": 3200,
    "醤油": 380,
    "米(コシヒカリ)": 4200,
    "文房具セット": 1500,
}

ZEN2HAN_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def to_fullwidth_digits(s: str) -> str:
    han2zen = str.maketrans("0123456789", "０１２３４５６７８９")
    return s.translate(han2zen)


def random_date_str(month: int, day: int, year: int = 2026) -> str:
    """4種類の日付表記からランダムに1つ返す"""
    fmt = random.choice(["slash_full", "hyphen_full", "reiwa", "slash_short"])
    if fmt == "slash_full":
        return f"{year}/{month}/{day}"
    if fmt == "hyphen_full":
        return f"{year}-{month:02d}-{day:02d}"
    if fmt == "reiwa":
        reiwa_year = year - 2018  # 2019年 = 令和元年
        return f"令和{reiwa_year}年{month}月{day}日"
    # slash_short: 年を省略 (当年扱い)
    return f"{month}/{day}"


def maybe_pad(s: str) -> str:
    """ランダムに前後空白を付与"""
    r = random.random()
    if r < 0.12:
        return f" {s}"
    if r < 0.24:
        return f"{s} "
    if r < 0.28:
        return f" {s} "
    return s


def format_price(price: int) -> str:
    """単価をランダムな表記ゆれで文字列化"""
    r = random.random()
    if r < 0.25:
        return f"{price:,}円"
    if r < 0.45:
        return f"{price}円"
    if r < 0.60:
        return f"{price:,}"
    if r < 0.72:
        return to_fullwidth_digits(str(price)) + "円"
    if r < 0.80:
        return f"¥{price:,}"
    return str(price)


def format_qty(qty: int) -> str:
    if random.random() < 0.18:
        return to_fullwidth_digits(str(qty))
    return str(qty)


def build_rows(n_target: int = 300):
    rows = []
    product_names = list(PRODUCT_VARIANTS.keys())

    months_days = []
    for month in range(1, 13):
        max_day = 28 if month == 2 else 30
        for day in (1, 5, 10, 15, 20, 25, min(28, max_day)):
            months_days.append((month, day))

    while len(rows) < int(n_target * 0.92):  # 後で重複・空行を追加して300行前後にする
        month, day = random.choice(months_days)
        date_str = random_date_str(month, day)
        customer = maybe_pad(random.choice(CUSTOMERS))
        product_key = random.choice(product_names)
        product_display = random.choice(PRODUCT_VARIANTS[product_key])
        qty = random.randint(1, 50)
        base_price = UNIT_PRICES[product_key]
        price_str = format_price(base_price)
        staff = random.choice(STAFF)

        rows.append([date_str, customer, product_display, format_qty(qty), price_str, staff])

    # --- 重複行をわざと挿入 (~18件) ---
    n_dupes = 18
    for _ in range(n_dupes):
        idx = random.randrange(len(rows))
        rows.insert(random.randrange(len(rows)), list(rows[idx]))

    # --- 空行をわざと挿入 (~10件) ---
    n_blanks = 10
    for _ in range(n_blanks):
        rows.insert(random.randrange(len(rows)), ["", "", "", "", "", ""])

    random.shuffle(rows)  # 完全シャッフルすると重複が離れて現実的になる
    return rows


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    rows = build_rows(300)

    with open(OUTPUT_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(HEADER)
        writer.writerows(rows)

    print(f"[OK] {OUTPUT_FILE} を生成しました ({len(rows)}行、ヘッダー除く)")


if __name__ == "__main__":
    main()
