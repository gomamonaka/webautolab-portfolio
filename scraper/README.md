# Webスクレイピング・データ収集ツール（books.toscrape.com サンプル）

## 概要（目的）

書籍情報サイトから商品データ（タイトル・価格・評価・在庫状況・詳細URL）を自動収集し、
CSVおよびExcel形式で出力するPython製のスクレイピングツールのポートフォリオサンプルです。

実際の案件では対象サイトのHTML構造に合わせてセレクタを調整するだけで、
同じ設計（レート制限・リトライ・整形出力）をそのまま流用できます。

本サンプルは実在のサービスサイトへの負荷やトラブルを避けるため、
スクレイピング練習用に公式に公開されているサイト
[books.toscrape.com](https://books.toscrape.com/) を対象にしています。
このサイトは「スクレイピングの練習をしてよい」ことを目的として作られたダミーの書籍通販サイトです。

> 対象サイトの利用規約・robots.txtを遵守した範囲で対応します。

## 主な機能

- **カタログページの自動巡回**: 指定ページ数分のカタログ一覧ページを順に取得
- **データ抽出**: タイトル / 価格（GBP, float） / 評価（1〜5の整数） / 在庫状況 / 詳細URL
- **レート制限（アクセス間隔の制御）**: リクエストごとに既定1秒のウェイトを挟み、対象サーバーへの負荷を抑制（`--delay`で変更可能）
- **リトライ処理**: 通信エラー・タイムアウト・HTTPエラー発生時に指数バックオフ付きで最大3回まで自動再試行
- **User-Agentの明示**: 自動化ツールであることが分かるUser-Agentを設定してアクセス
- **robots.txt遵守の方針**: 対象サイトの`robots.txt`（`https://books.toscrape.com/robots.txt`）で許可されている範囲のみアクセスする設計。実案件で他サイトに適用する場合は、事前に対象サイトの利用規約・robots.txtを確認し、許可された範囲でのみ実行してください。
- **CSV出力**: 文字化け防止のためUTF-8 with BOM（`utf-8-sig`）で出力し、Excelでもそのまま正しく開けます
- **Excel出力**: `openpyxl`によりヘッダー装飾（背景色・太字・中央揃え）と列幅自動調整を行った`.xlsx`を出力
- **サマリー表示**: 取得件数・平均価格・評価分布（★1〜★5の件数）を実行後に表示

## 動作環境

- Python 3.12
- 依存パッケージ: `requests`, `beautifulsoup4`, `openpyxl`
  （未インストールの場合は自動で `pip install` されます）

## 使い方

```bash
# 既定（先頭3ページ、outputディレクトリに出力）
python scrape_books.py

# ページ数・出力先を指定
python scrape_books.py --pages 3 --out output

# リクエスト間隔を変更（既定1.0秒）
python scrape_books.py --pages 3 --out output --delay 1.5
```

### CLI引数一覧

| 引数 | 説明 | 既定値 |
|---|---|---|
| `--pages` | 取得するカタログページ数 | `3` |
| `--out` | 出力先ディレクトリ | `output` |
| `--delay` | リクエスト間隔（秒） | `1.0` |

実行すると、指定した出力ディレクトリに以下のファイルが生成されます。

- `output/books.csv`
- `output/books.xlsx`

## サンプル出力（先頭5件）

`output/books.csv` から抜粋した実行結果の例です（実行日時により価格や在庫状況は変わりません。books.toscrape.comは固定のダミーデータを提供しています）。

| タイトル | 価格(GBP) | 評価(1-5) | 在庫状況 | 詳細URL |
|---|---|---|---|---|
| A Light in the Attic | 51.77 | 3 | In stock | https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html |
| Tipping the Velvet | 53.74 | 1 | In stock | https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html |
| Soumission | 50.10 | 1 | In stock | https://books.toscrape.com/catalogue/soumission_998/index.html |
| Sharp Objects | 47.82 | 4 | In stock | https://books.toscrape.com/catalogue/sharp-objects_997/index.html |
| Sapiens: A Brief History of Humankind | 54.23 | 5 | In stock | https://books.toscrape.com/catalogue/sapiens-a-brief-history-of-humankind_996/index.html |

## 実行結果サマリー例

実際に3ページ分（60件）を取得した際の出力例です。

```
==================================================
スクレイピング結果サマリー
==================================================
総件数: 60 件
平均価格: £35.00
評価分布:
  5つ星:  14 件
  4つ星:  10 件
  3つ星:  13 件
  2つ星:   8 件
  1つ星:  15 件
==================================================
```

## ファイル構成

```
scraper/
├── scrape_books.py    # スクレイピング本体スクリプト
├── README.md           # 本ファイル
└── output/
    ├── books.csv        # CSV出力（UTF-8 with BOM）
    └── books.xlsx       # Excel出力（ヘッダー装飾・列幅自動調整）
```

## 免責事項・ご利用にあたって

- 本サンプルはポートフォリオ・技術デモを目的としており、対象は許可されたスクレイピング練習用サイト（books.toscrape.com）です。
- 実際の案件で他サイトを対象とする場合は、対象サイトの利用規約・robots.txtを必ず事前に確認し、許可された範囲・頻度でのみ実行してください。
- 対象サイトの利用規約・robots.txtを遵守した範囲で対応します。
