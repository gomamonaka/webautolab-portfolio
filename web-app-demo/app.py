#!/usr/bin/env python3
"""備品貸出管理アプリ（デモ）

中小企業の社内ツールを想定した、小規模Webアプリのサンプルです。
Python標準ライブラリのみ（http.server + sqlite3）で動作します。

起動方法:
    python3 app.py
    → http://localhost:8000
"""

import csv
import html
import io
import os
import sqlite3
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "equipment.db")
PORT = 8000


# ---------------------------------------------------------------- DB層
def get_conn(db_path=DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS items (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            category   TEXT NOT NULL DEFAULT '',
            total_qty  INTEGER NOT NULL DEFAULT 1,
            note       TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT (date('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS loans (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id     INTEGER NOT NULL REFERENCES items(id),
            borrower    TEXT NOT NULL,
            loan_date   TEXT NOT NULL,
            due_date    TEXT NOT NULL,
            return_date TEXT
        );
        """
    )
    conn.commit()


def seed_sample_data(conn):
    """初回起動時だけ、架空のサンプルデータを投入する。"""
    count = conn.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    if count:
        return
    today = date.today()
    items = [
        ("ノートPC（会議用）", "PC・周辺機器", 3, "Windowsノート、貸出用ケース付き"),
        ("プロジェクター", "会議機材", 1, "HDMIケーブル同梱"),
        ("ワイヤレスマイク", "会議機材", 2, ""),
        ("デジタルカメラ", "撮影機材", 1, "SDカードは各自で用意"),
        ("脚立（大）", "工具・備品", 1, "倉庫保管"),
        ("脚立（小）", "工具・備品", 2, ""),
        ("モバイルモニター", "PC・周辺機器", 2, "USB-C接続"),
        ("ICレコーダー", "会議機材", 2, "議事録作成用"),
        ("延長コード（5m）", "工具・備品", 4, ""),
        ("ホワイトボードマーカーセット", "事務用品", 5, "補充は総務まで"),
    ]
    conn.executemany(
        "INSERT INTO items (name, category, total_qty, note) VALUES (?, ?, ?, ?)",
        items,
    )

    def d(offset):
        return (today + timedelta(days=offset)).isoformat()

    # (備品名キーワード, 借りた人, 貸出日offset, 返却期限offset, 返却日offset or None)
    loans = [
        ("ノートPC", "山田 花子", -10, -3, None),      # 期限切れ（未返却）
        ("プロジェクター", "佐藤 健", -2, 5, None),    # 貸出中
        ("ワイヤレスマイク", "鈴木 美咲", -1, 1, None),  # 貸出中（明日が期限）
        ("デジタルカメラ", "高橋 翔", -14, -7, -6),    # 返却済み
        ("モバイルモニター", "伊藤 葵", -5, 2, None),  # 貸出中
        ("脚立（大）", "渡辺 大輔", -3, -1, None),      # 期限切れ（未返却）
        ("ノートPC", "中村 さくら", -20, -13, -12),    # 返却済み
        ("ICレコーダー", "小林 蓮", 0, 7, None),       # 本日貸出
        ("延長コード", "加藤 結衣", -7, 0, None),      # 本日が期限
        ("脚立（小）", "吉田 悠真", -30, -23, -25),    # 返却済み
    ]
    for keyword, borrower, loan_off, due_off, ret_off in loans:
        row = conn.execute(
            "SELECT id FROM items WHERE name LIKE ?", (f"%{keyword}%",)
        ).fetchone()
        if row is None:
            continue
        conn.execute(
            "INSERT INTO loans (item_id, borrower, loan_date, due_date, return_date)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                row["id"],
                borrower,
                d(loan_off),
                d(due_off),
                d(ret_off) if ret_off is not None else None,
            ),
        )
    conn.commit()


# ---------------------------------------------------------------- 業務ロジック
def loaned_count(conn, item_id):
    return conn.execute(
        "SELECT COUNT(*) FROM loans WHERE item_id = ? AND return_date IS NULL",
        (item_id,),
    ).fetchone()[0]


def available_qty(conn, item):
    return item["total_qty"] - loaned_count(conn, item["id"])


def add_item(conn, name, category, total_qty, note):
    cur = conn.execute(
        "INSERT INTO items (name, category, total_qty, note) VALUES (?, ?, ?, ?)",
        (name, category, int(total_qty), note),
    )
    conn.commit()
    return cur.lastrowid


def update_item(conn, item_id, name, category, total_qty, note):
    conn.execute(
        "UPDATE items SET name = ?, category = ?, total_qty = ?, note = ? WHERE id = ?",
        (name, category, int(total_qty), note, item_id),
    )
    conn.commit()


def delete_item(conn, item_id):
    """貸出中の備品は削除できない。"""
    if loaned_count(conn, item_id) > 0:
        return False
    conn.execute("DELETE FROM loans WHERE item_id = ?", (item_id,))
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    conn.commit()
    return True


def checkout(conn, item_id, borrower, due_date, loan_date=None):
    """貸出を記録する。在庫がなければ ValueError。"""
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        raise ValueError("備品が見つかりません")
    if available_qty(conn, item) <= 0:
        raise ValueError("貸出可能な在庫がありません")
    if not borrower.strip():
        raise ValueError("借りた人の名前を入力してください")
    loan_date = loan_date or date.today().isoformat()
    cur = conn.execute(
        "INSERT INTO loans (item_id, borrower, loan_date, due_date) VALUES (?, ?, ?, ?)",
        (item_id, borrower.strip(), loan_date, due_date),
    )
    conn.commit()
    return cur.lastrowid


def return_loan(conn, loan_id, return_date=None):
    return_date = return_date or date.today().isoformat()
    conn.execute(
        "UPDATE loans SET return_date = ? WHERE id = ? AND return_date IS NULL",
        (return_date, loan_id),
    )
    conn.commit()


def is_overdue(loan, today=None):
    """未返却かつ返却期限を過ぎていれば True。"""
    today = today or date.today()
    if loan["return_date"] is not None:
        return False
    return loan["due_date"] < today.isoformat()


def search_items(conn, keyword=""):
    if keyword:
        like = f"%{keyword}%"
        rows = conn.execute(
            "SELECT * FROM items WHERE name LIKE ? OR category LIKE ? OR note LIKE ?"
            " ORDER BY category, name",
            (like, like, like),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM items ORDER BY category, name").fetchall()
    result = []
    for item in rows:
        loaned = loaned_count(conn, item["id"])
        result.append(
            {
                "id": item["id"],
                "name": item["name"],
                "category": item["category"],
                "total_qty": item["total_qty"],
                "note": item["note"],
                "loaned": loaned,
                "available": item["total_qty"] - loaned,
            }
        )
    return result


def list_loans(conn, active_only=False):
    sql = (
        "SELECT loans.*, items.name AS item_name FROM loans"
        " JOIN items ON items.id = loans.item_id"
    )
    if active_only:
        sql += " WHERE loans.return_date IS NULL"
    sql += " ORDER BY loans.return_date IS NOT NULL, loans.due_date, loans.id"
    rows = conn.execute(sql).fetchall()
    result = []
    for loan in rows:
        entry = dict(loan)
        entry["overdue"] = is_overdue(loan)
        result.append(entry)
    return result


def loans_to_csv(conn):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["備品名", "借りた人", "貸出日", "返却期限", "返却日", "状態"])
    for loan in list_loans(conn):
        if loan["return_date"]:
            status = "返却済み"
        elif loan["overdue"]:
            status = "期限切れ"
        else:
            status = "貸出中"
        writer.writerow(
            [
                loan["item_name"],
                loan["borrower"],
                loan["loan_date"],
                loan["due_date"],
                loan["return_date"] or "",
                status,
            ]
        )
    return buf.getvalue()


# ---------------------------------------------------------------- 画面
CSS = """
* { box-sizing: border-box; }
body { margin: 0; font-family: "Hiragino Sans", "Noto Sans JP", sans-serif;
       background: #f4f6f8; color: #243b53; }
header { background: #14509e; color: #fff; padding: 16px 24px; }
header h1 { margin: 0; font-size: 20px; }
header p { margin: 4px 0 0; font-size: 12px; opacity: .85; }
main { max-width: 960px; margin: 0 auto; padding: 20px 16px 48px; }
h2 { font-size: 16px; border-left: 4px solid #14509e; padding-left: 8px; margin: 28px 0 12px; }
table { width: 100%; border-collapse: collapse; background: #fff;
        border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
th, td { padding: 9px 12px; text-align: left; font-size: 14px; border-bottom: 1px solid #e4e9ef; }
th { background: #eef3f9; font-size: 12px; color: #486581; }
tr.overdue td { background: #fdecec; }
.badge { display: inline-block; padding: 1px 8px; border-radius: 999px; font-size: 12px; }
.badge.ok { background: #e2f4e5; color: #1d7a35; }
.badge.none { background: #fdecec; color: #b3261e; }
.badge.lent { background: #fff3d6; color: #8a6d00; }
.badge.over { background: #b3261e; color: #fff; }
.badge.done { background: #e4e9ef; color: #486581; }
form.inline { display: inline; }
input, select { padding: 7px 9px; border: 1px solid #bcccdc; border-radius: 6px; font-size: 14px; }
button, .btn { display: inline-block; padding: 7px 14px; border: none; border-radius: 6px;
  background: #14509e; color: #fff; font-size: 13px; cursor: pointer; text-decoration: none; }
button.sub, .btn.sub { background: #829ab1; }
button.danger { background: #b3261e; }
button:disabled { background: #bcccdc; cursor: not-allowed; }
.panel { background: #fff; border-radius: 8px; padding: 16px;
         box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.panel label { display: block; font-size: 12px; color: #486581; margin: 10px 0 4px; }
.panel input, .panel select { width: 100%; }
.flash { background: #e2f4e5; border: 1px solid #1d7a35; color: #1d7a35;
         padding: 10px 14px; border-radius: 6px; font-size: 14px; }
.error { background: #fdecec; border: 1px solid #b3261e; color: #b3261e;
         padding: 10px 14px; border-radius: 6px; font-size: 14px; }
.toolbar { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.toolbar form { display: flex; gap: 8px; }
.muted { color: #829ab1; font-size: 12px; }
"""

PAGE = """<!DOCTYPE html>
<html lang="ja">
<head><meta charset="utf-8"><title>備品貸出管理</title><style>{css}</style></head>
<body>
<header><h1>備品貸出管理</h1><p>社内備品の貸出・返却を管理するデモアプリ（サンプルデータ使用）</p></header>
<main>{body}</main>
</body></html>"""


def esc(value):
    return html.escape(str(value), quote=True)


def render_index(conn, keyword="", message="", error=""):
    items = search_items(conn, keyword)
    loans = list_loans(conn, active_only=True)
    default_due = (date.today() + timedelta(days=7)).isoformat()

    parts = []
    if message:
        parts.append(f'<p class="flash">{esc(message)}</p>')
    if error:
        parts.append(f'<p class="error">{esc(error)}</p>')

    parts.append("<h2>備品一覧</h2>")
    parts.append(
        '<div class="toolbar">'
        '<form method="get" action="/">'
        f'<input type="search" name="q" value="{esc(keyword)}" placeholder="キーワード検索（備品名・分類・メモ）">'
        '<button type="submit">検索</button></form>'
        '<a class="btn sub" href="/items/new">＋ 備品を登録</a>'
        '<a class="btn sub" href="/export.csv">貸出一覧をCSVで出す</a>'
        "</div>"
    )
    if items:
        rows = []
        for it in items:
            if it["available"] > 0:
                badge = f'<span class="badge ok">貸出可 あと{it["available"]}点</span>'
                lend_btn = (
                    f'<a class="btn" href="/loans/new?item_id={it["id"]}">貸出する</a>'
                )
            else:
                badge = '<span class="badge none">貸出中（在庫なし）</span>'
                lend_btn = '<button disabled>貸出する</button>'
            rows.append(
                "<tr>"
                f"<td>{esc(it['name'])}</td><td>{esc(it['category'])}</td>"
                f"<td>{it['loaned']} / {it['total_qty']}</td><td>{badge}</td>"
                f"<td>{esc(it['note'])}</td>"
                f'<td>{lend_btn} <a class="btn sub" href="/items/{it["id"]}/edit">編集</a></td>'
                "</tr>"
            )
        parts.append(
            "<table><tr><th>備品名</th><th>分類</th><th>貸出中 / 総数</th>"
            "<th>状態</th><th>メモ</th><th>操作</th></tr>" + "".join(rows) + "</table>"
        )
    else:
        parts.append('<p class="muted">条件に合う備品がありません。</p>')

    parts.append("<h2>貸出中の一覧</h2>")
    if loans:
        rows = []
        for loan in loans:
            if loan["overdue"]:
                status = '<span class="badge over">期限切れ</span>'
                cls = ' class="overdue"'
            else:
                status = '<span class="badge lent">貸出中</span>'
                cls = ""
            rows.append(
                f"<tr{cls}>"
                f"<td>{esc(loan['item_name'])}</td><td>{esc(loan['borrower'])}</td>"
                f"<td>{esc(loan['loan_date'])}</td><td>{esc(loan['due_date'])}</td>"
                f"<td>{status}</td>"
                f'<td><form class="inline" method="post" action="/loans/{loan["id"]}/return">'
                '<button type="submit">返却する</button></form></td>'
                "</tr>"
            )
        parts.append(
            "<table><tr><th>備品名</th><th>借りた人</th><th>貸出日</th>"
            "<th>返却期限</th><th>状態</th><th>操作</th></tr>" + "".join(rows) + "</table>"
        )
    else:
        parts.append('<p class="muted">現在貸出中の備品はありません。</p>')

    parts.append(
        f'<p class="muted">返却期限の初期値は1週間後（{esc(default_due)}）です。'
        "貸出フォームで変更できます。</p>"
    )
    return PAGE.format(css=CSS, body="\n".join(parts))


def render_item_form(item=None):
    is_edit = item is not None
    action = f"/items/{item['id']}/edit" if is_edit else "/items/new"
    title = "備品の編集" if is_edit else "備品の登録"
    name = esc(item["name"]) if is_edit else ""
    category = esc(item["category"]) if is_edit else ""
    qty = item["total_qty"] if is_edit else 1
    note = esc(item["note"]) if is_edit else ""
    delete_form = ""
    if is_edit:
        delete_form = (
            f'<form method="post" action="/items/{item["id"]}/delete" '
            'onsubmit="return confirm(\'この備品を削除しますか？\')" style="margin-top:16px">'
            '<button class="danger" type="submit">この備品を削除</button></form>'
        )
    body = f"""
    <h2>{title}</h2>
    <div class="panel">
      <form method="post" action="{action}">
        <label>備品名</label><input name="name" required value="{name}">
        <label>分類</label><input name="category" value="{category}" placeholder="例：PC・周辺機器">
        <label>総数</label><input name="total_qty" type="number" min="1" value="{qty}" required>
        <label>メモ</label><input name="note" value="{note}">
        <p style="margin-top:16px"><button type="submit">保存する</button>
        <a class="btn sub" href="/">戻る</a></p>
      </form>
      {delete_form}
    </div>"""
    return PAGE.format(css=CSS, body=body)


def render_loan_form(conn, item_id):
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if item is None:
        return None
    default_due = (date.today() + timedelta(days=7)).isoformat()
    body = f"""
    <h2>貸出の登録</h2>
    <div class="panel">
      <p>備品：<strong>{esc(item['name'])}</strong>（貸出可能 {available_qty(conn, item)} 点）</p>
      <form method="post" action="/loans">
        <input type="hidden" name="item_id" value="{item['id']}">
        <label>借りた人</label><input name="borrower" required placeholder="例：山田 花子">
        <label>返却期限</label><input name="due_date" type="date" value="{default_due}" required>
        <p style="margin-top:16px"><button type="submit">貸出を記録する</button>
        <a class="btn sub" href="/">戻る</a></p>
      </form>
    </div>"""
    return PAGE.format(css=CSS, body=body)


# ---------------------------------------------------------------- HTTP層
class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # アクセスログを静かにする
        pass

    def _send(self, body, status=200, content_type="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location):
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def _form(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        return {k: v[0] for k, v in parse_qs(raw).items()}

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        conn = get_conn()
        try:
            if path == "/":
                keyword = query.get("q", [""])[0]
                message = query.get("msg", [""])[0]
                error = query.get("err", [""])[0]
                self._send(render_index(conn, keyword, message, error))
            elif path == "/items/new":
                self._send(render_item_form())
            elif path.startswith("/items/") and path.endswith("/edit"):
                item_id = int(path.split("/")[2])
                item = conn.execute(
                    "SELECT * FROM items WHERE id = ?", (item_id,)
                ).fetchone()
                if item is None:
                    self._send("備品が見つかりません", status=404)
                else:
                    self._send(render_item_form(item))
            elif path == "/loans/new":
                item_id = int(query.get("item_id", ["0"])[0])
                page = render_loan_form(conn, item_id)
                if page is None:
                    self._send("備品が見つかりません", status=404)
                else:
                    self._send(page)
            elif path == "/export.csv":
                body = loans_to_csv(conn)
                data = b"\xef\xbb\xbf" + body.encode("utf-8")  # Excel向けBOM
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header(
                    "Content-Disposition", "attachment; filename=loans.csv"
                )
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self._send("ページが見つかりません", status=404)
        finally:
            conn.close()

    def do_POST(self):
        path = urlparse(self.path).path
        form = self._form()
        conn = get_conn()
        try:
            if path == "/items/new":
                add_item(
                    conn,
                    form.get("name", ""),
                    form.get("category", ""),
                    form.get("total_qty", 1),
                    form.get("note", ""),
                )
                self._redirect("/?msg=" + quote("備品を登録しました"))
            elif path.startswith("/items/") and path.endswith("/edit"):
                item_id = int(path.split("/")[2])
                update_item(
                    conn,
                    item_id,
                    form.get("name", ""),
                    form.get("category", ""),
                    form.get("total_qty", 1),
                    form.get("note", ""),
                )
                self._redirect("/?msg=" + quote("備品を更新しました"))
            elif path.startswith("/items/") and path.endswith("/delete"):
                item_id = int(path.split("/")[2])
                if delete_item(conn, item_id):
                    self._redirect("/?msg=" + quote("備品を削除しました"))
                else:
                    self._redirect("/?err=" + quote("貸出中の備品は削除できません"))
            elif path == "/loans":
                try:
                    checkout(
                        conn,
                        int(form.get("item_id", 0)),
                        form.get("borrower", ""),
                        form.get("due_date", ""),
                    )
                    self._redirect("/?msg=" + quote("貸出を記録しました"))
                except ValueError as e:
                    self._redirect("/?err=" + quote(str(e)))
            elif path.startswith("/loans/") and path.endswith("/return"):
                loan_id = int(path.split("/")[2])
                return_loan(conn, loan_id)
                self._redirect("/?msg=" + quote("返却を記録しました"))
            else:
                self._send("ページが見つかりません", status=404)
        finally:
            conn.close()


def main():
    conn = get_conn()
    init_db(conn)
    seed_sample_data(conn)
    conn.close()
    server = ThreadingHTTPServer(("localhost", PORT), Handler)
    print(f"備品貸出管理アプリを起動しました → http://localhost:{PORT}")
    print("終了するには Ctrl+C を押してください")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
