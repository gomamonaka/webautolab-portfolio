# 復旧診断レポート: books.toscrape.com 巡回スクレイパー

- 対象ツール: `scraper_v1.py`(Python / requests + BeautifulSoup)
- 対象サイト: https://books.toscrape.com/
- 調査日: 2026-09-10
- 調査担当: リペアチーム(サービスメール: service.goma.monaka@gmail.com)

---

## 1. 症状

- スクレイパーを実行すると、コンソールに `Scraping https://books.toscrape.com/ ...` とだけ表示された直後に
  `AttributeError` の Traceback が出て異常終了する。
- 出力ファイル `books.csv` は一切生成されない(=1件も取得できていない)。
- 依頼者からの申告:「昨年AIに書いてもらって動いていたツールだが、久しぶりに使おうとしたら動かなくなった。
  作った担当者はすでに退職しており、社内に直せる人がいない」。

## 2. 再現手順

```bash
$ cd before
$ python scraper_v1.py
Scraping https://books.toscrape.com/ ...
Traceback (most recent call last):
  ...
  File ".../before/scraper_v1.py", line 26, in scrape_page
    price = pod.select_one("p.price .price_color").text
AttributeError: 'NoneType' object has no attribute 'text'
$ echo $?
1
```

- 実機(Windows 11 / Python 3.12.10)でそのまま実行し、実際に上記の例外で落ちることを確認済み。
- 全ログは `before/error.log` に保存。`books.csv` が生成されないため、依頼者側で「サイレントに壊れている」
  のではなく「毎回必ず落ちている」ことも合わせて確認した。

## 3. 原因

### 3.1 直接原因(実際に例外を投げている箇所)

`before/scraper_v1.py` 26行目:

```python
price = pod.select_one("p.price .price_color").text
```

`before/error.log` の該当行:

```
  File ".../before/scraper_v1.py", line 26, in scrape_page
    price = pod.select_one("p.price .price_color").text
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
AttributeError: 'NoneType' object has no attribute 'text'
```

`pod.select_one("p.price .price_color")` が `None` を返し、`.text` を呼んだ瞬間に落ちている。

### 3.2 何がどう変わって壊れたのか

実際のページ(2026-09-10 時点)のDOMを確認したところ、商品1件分のHTMLは以下の構造だった。

```html
<article class="product_pod">
  ...
  <div class="product_price">
    <p class="price_color">£51.77</p>
    <p class="instock availability">
      <i class="icon-ok"></i>
      In stock
    </p>
    ...
  </div>
</article>
```

つまり:

- 価格は `div.product_price` の**直下**に `<p class="price_color">` として存在しており、
  `p.price` という要素そのものが存在しない。v1 は `"p.price .price_color"` という
  (存在しない `p.price` の子孫に `.price_color` がある、という)前提のセレクタを使っており、
  常にヒットせず `None` になる。
- 在庫表示も同様で、実際は `<p class="instock availability">` というクラス構成であり、
  v1 が期待していた `.stock-badge` というクラスはそもそも存在しない(こちらは価格取得で先に
  例外が出るため未到達だが、同じ考え方の問題が埋め込まれていた)。

つまり「サイトの構造がある時点で変わった」というより、**そもそも一度も存在しなかったDOM構造を
前提にセレクタが書かれていた**可能性が高い(=AIが生成した際に、他サイトのパターンや古いサンプルを
参照して書いたセレクタが、このサイトの実際の構造と食い違っていた)。加えて実行時のBeautifulSoupの
挙動上、`select_one` はマッチしなければ静かに `None` を返すため、書いた本人がローカルで一度も
成功実行を確認しないまま「動くはず」として納品・放置されていた可能性がある。

### 3.3 潜在的な二次要因(調査中に別途発見)

修正版の実機テスト中に、`requests` が `Content-Type: text/html`(charset指定なし)のレスポンスを
デフォルトの `ISO-8859-1` として解釈してしまい、`£` のような非ASCII文字が `Â£` のように文字化けする
問題も確認した。v1ではそもそも価格取得の時点で落ちるため症状としては表面化していなかったが、
放置していれば「動くようになった後にCSVの中身が化ける」新たな不具合として顕在化していたはずのため、
今回まとめて修正した(詳細は4.4)。

## 4. 修正内容(diffの要点)

全文は `before_after.diff` を参照。主な変更点は以下の5つ。

### 4.1 セレクタの修正(直接の修正)

| 項目 | v1(誤) | v2(正) |
|---|---|---|
| 価格 | `p.price .price_color` | `p.price_color` |
| 在庫 | `.stock-badge` | `p.instock.availability` |

### 4.2 防御的パース

- 各項目(タイトル/価格/評価/在庫/URL)を個別に `None` チェックし、欠損時は
  `logger.warning(...)` を出したうえで値を `"N/A"` として処理を継続する設計に変更。
- 1冊のパース失敗で全体が落ちる構造(v1)から、1冊単位で縮退しつつ最後まで走り切る構造(v2)に変更。

### 4.3 通信まわりの堅牢化

- `requests.get()` にタイムアウト(10秒)・カスタム `User-Agent` を追加。
- 最大3回・指数バックオフ(1.5秒→2.25秒→3.4秒)のリトライを追加。
- ページ間に1秒の待機を追加(サイト側への配慮、連続アクセスによるブロック回避)。

### 4.4 文字コードの修正

- `fetch()` 内で、サーバーがcharsetを明示しない場合に `requests` が誤って `ISO-8859-1` と
  判定してしまう問題に対応し、`resp.apparent_encoding` で上書きするよう修正(3.3参照)。

### 4.5 運用性の向上

- `--check` セルフテストモードを追加(5章参照)。
- `logging` モジュールで `after/run.log` に実行ログ(取得件数・警告・エラー)を記録。
- CLI引数化(`--pages`, `--out`, `--check`, `--verbose`)により、ページ数や出力先を指定可能に。
- 出力仕様(CSVカラム: `title, price, rating, availability, url`)はv1の意図を踏襲しつつ、
  v1では未実装だった `rating` と `url` を追加(依頼内容に合わせて仕様を明確化)。

## 5. 動作確認結果

### 5.1 セルフチェック(`--check`)

```
$ python scraper_v2.py --check
[--check] https://books.toscrape.com/index.html のページ構造を検証します...
  [OK] 商品カード      selector='article.product_pod'          matched=20
  [OK] タイトル       selector='h3 a'                         matched=20
  [OK] 価格         selector='p.price_color'                matched=20
  [OK] 評価         selector='p.star-rating'                matched=20
  [OK] 在庫状況       selector='p.instock.availability'       matched=20
  [OK] 次ページリンク    selector='li.next a'                    matched=1
=> すべてのセレクタが正常にマッチしました。ページ構造は健全です。
```

### 5.2 実データでの本番実行(2ページ分)

```
$ python scraper_v2.py --pages 2 --out output/books.csv
完了: 40件を output\books.csv に書き出しました (4.53秒)
```

- 出力: `after/output/books.csv`(40件、ヘッダー含め41行)
- 文字化け(`£` → `Â£`)が発生しないことを再確認済み。
- 実行ログ: `after/run.log`(自己診断+本番実行の全履歴)

## 6. 再発防止策

1. **`--check` の定期実行**: `python scraper_v2.py --check` を日次でcron/タスクスケジューラに登録し、
   終了コード(0=正常 / 2=セレクタ不一致)で構造変化を検知する。
2. **失敗時の通知**: `--check` の終了コードが2、または本番実行が非0で終了した場合に、
   Slack Webhook やメールで担当者に通知する仕組みを追加することを推奨(現状は未実装)。
3. **CSVの中身の軽い監視**: 取得件数が0件、または前回実行より大きく減った場合にアラートを出す
   (サイト構造は壊れていなくても、ページが空になっている・ブロックされている等のケースを検知できる)。
4. **実行環境の固定**: `requirements.txt` 等でrequests/beautifulsoup4のバージョンを固定し、
   ライブラリ更新による挙動変化(charset判定など)も再発ポイントとして意識する。

## 7. 今後の注意点

- 今回の直接原因は「サイト構造の変化」ではなく「最初から実サイトの構造と食い違っていたセレクタ」
  だった可能性が高い。AI生成ツールを受け入れる際は、**納品前に一度は成功実行のログ・出力を
  確認してから引き渡す**運用を徹底することをお勧めする。
- サイト側の仕様変更(クラス名の変更、ページネーション構造の変更など)は将来的にも起こり得るため、
  `--check` モードのセレクタ一覧(`after/scraper_v2.py` 内 `CHECK_SELECTORS`)は、
  対象サイトの構造が分かる人がいなくなっても「どこを見れば壊れた箇所が分かるか」が一目で分かるように
  意図的にシンプルな辞書として実装している。
- 本ツールは学習用サンドバックサイト(books.toscrape.com)を対象としているが、実際の商用サイトを
  対象にする場合は利用規約・robots.txt・アクセス頻度制限を別途確認すること。
