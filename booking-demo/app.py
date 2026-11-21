# -*- coding: utf-8 -*-
"""予約管理デモアプリ（Python標準ライブラリのみ）

小規模店舗・教室向けの予約Web化デモ。
起動: python3 app.py  -> http://localhost:8000
"""
import html
import sqlite3
import threading
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

DB_PATH = "booking.db"
SLOTS = ["10:00", "11:00", "12:00", "13:00", "14:00", "15:00", "16:00", "17:00"]
STATUSES = ["pending", "confirmed", "cancelled", "visited"]
STATUS_LABEL = {"pending": "仮予約", "confirmed": "確定", "cancelled": "キャンセル", "visited": "来店済み"}
# 許可するステータス遷移
TRANSITIONS = {
    "pending": {"confirmed", "cancelled"},
    "confirmed": {"visited", "cancelled"},
    "cancelled": set(),
    "visited": set(),
}


def connect(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS menus(
            id INTEGER PRIMARY KEY, name TEXT, duration_min INTEGER, price INTEGER);
        CREATE TABLE IF NOT EXISTS bookings(
            id INTEGER PRIMARY KEY, menu_id INTEGER, book_date TEXT, book_time TEXT,
            customer_name TEXT, contact TEXT, status TEXT, created_at TEXT);
        """
    )
    conn.commit()


def seed(conn):
    if conn.execute("SELECT COUNT(*) FROM menus").fetchone()[0]:
        return
    menus = [
        ("カット", 60, 5000),
        ("カット＋カラー", 120, 12000),
        ("パーマ", 120, 11000),
        ("ヘッドスパ", 45, 4000),
    ]
    conn.executemany("INSERT INTO menus(name,duration_min,price) VALUES(?,?,?)", menus)
    today = date.today()
    samples = [
        (1, -1, "10:00", "サンプル花子", "090-0000-0001", "visited"),
        (2, 0, "11:00", "サンプル太郎", "090-0000-0002", "confirmed"),
        (1, 0, "13:00", "サンプル美咲", "090-0000-0003", "pending"),
        (4, 0, "15:00", "サンプル健", "090-0000-0004", "cancelled"),
        (3, 1, "10:00", "サンプル直子", "090-0000-0005", "confirmed"),
        (1, 1, "12:00", "サンプル翔太", "090-0000-0006", "pending"),
        (2, 2, "14:00", "サンプル結衣", "090-0000-0007", "pending"),
        (1, 3, "10:00", "サンプル大輔", "090-0000-0008", "pending"),
        (4, 3, "16:00", "サンプル真由", "090-0000-0009", "confirmed"),
        (1, 5, "11:00", "サンプル蓮", "090-0000-0010", "pending"),
    ]
    now = datetime.now().isoformat(timespec="seconds")
    for menu_id, offset, t, name, contact, status in samples:
        d = (today + timedelta(days=offset)).isoformat()
        conn.execute(
            "INSERT INTO bookings(menu_id,book_date,book_time,customer_name,contact,status,created_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (menu_id, d, t, name, contact, status, now),
        )
    conn.commit()


def available_slots(conn, book_date, menu_id=None):
    """指定日に予約可能な時間枠の一覧を返す（キャンセル以外で埋まっている枠を除く）。"""
    taken = {
        r["book_time"]
        for r in conn.execute(
            "SELECT book_time FROM bookings WHERE book_date=? AND status!='cancelled'",
            (book_date,),
        )
    }
    return [s for s in SLOTS if s not in taken]


def create_booking(conn, menu_id, book_date, book_time, customer_name, contact):
    if book_time not in SLOTS:
        raise ValueError("時間枠が不正です")
    if not customer_name.strip():
        raise ValueError("お名前を入力してください")
    if book_time not in available_slots(conn, book_date):
        raise ValueError("その時間枠はすでに予約が入っています")
    cur = conn.execute(
        "INSERT INTO bookings(menu_id,book_date,book_time,customer_name,contact,status,created_at)"
        " VALUES(?,?,?,?,?,'pending',?)",
        (menu_id, book_date, book_time, customer_name.strip(), contact.strip(),
         datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()
    return cur.lastrowid


def change_status(conn, booking_id, new_status):
    row = conn.execute("SELECT status FROM bookings WHERE id=?", (booking_id,)).fetchone()
    if row is None:
        raise ValueError("予約が見つかりません")
    if new_status not in TRANSITIONS.get(row["status"], set()):
        raise ValueError(f"{STATUS_LABEL[row['status']]}から{STATUS_LABEL.get(new_status, new_status)}へは変更できません")
    conn.execute("UPDATE bookings SET status=? WHERE id=?", (new_status, booking_id))
    conn.commit()


def reminder_text(booking, menu_name):
    """リマインドメールの文面（下書き）を生成する。実際の送信はしない。"""
    return (
        f"{booking['customer_name']} 様\n\n"
        "いつもご利用ありがとうございます。ご予約のリマインドです。\n\n"
        f"日時：{booking['book_date']} {booking['book_time']}〜\n"
        f"メニュー：{menu_name}\n\n"
        "ご都合が悪くなった場合は、お早めにご連絡ください。\n"
        "ご来店を心よりお待ちしております。"
    )


CSS = """
body{font-family:'Noto Sans JP',sans-serif;margin:0;background:#f4f6f5;color:#223}
header{background:#14532d;color:#fff;padding:18px 24px}header h1{margin:0;font-size:21px}
header a{color:#cdeeda;font-size:13px;margin-right:14px}
main{max-width:880px;margin:24px auto;padding:0 16px}
.card{background:#fff;border-radius:10px;padding:20px 22px;margin-bottom:18px;box-shadow:0 1px 4px rgba(0,0,0,.08)}
label{display:block;font-size:13px;margin:10px 0 4px;color:#456}
input,select{width:100%;padding:9px;border:1px solid #cbd5d1;border-radius:6px;box-sizing:border-box}
button{background:#1f7a44;color:#fff;border:0;padding:10px 22px;border-radius:6px;cursor:pointer;font-size:14px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:8px 6px;border-bottom:1px solid #e3e8e5;text-align:left}
.badge{padding:2px 9px;border-radius:10px;font-size:12px;color:#fff}
.st-pending{background:#b7791f}.st-confirmed{background:#1f7a44}.st-cancelled{background:#9aa3a7}.st-visited{background:#34548c}
.slot{display:inline-block;border:1px solid #1f7a44;color:#14532d;border-radius:6px;padding:4px 10px;margin:2px;font-size:13px}
textarea{width:100%;height:220px;padding:10px;border:1px solid #cbd5d1;border-radius:6px;box-sizing:border-box}
.msg{background:#e7f6ec;border:1px solid #9fd3ae;padding:10px 14px;border-radius:8px;margin-bottom:14px}
.err{background:#fdecec;border:1px solid #e5a3a3;padding:10px 14px;border-radius:8px;margin-bottom:14px}
"""


def page(title, body):
    return (f"<!DOCTYPE html><html lang='ja'><head><meta charset='utf-8'>"
            f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(title)}</title><style>{CSS}</style></head><body>"
            f"<header><h1>予約管理デモ（サンプル店舗）</h1>"
            f"<a href='/'>予約する</a><a href='/admin'>管理画面</a></header>"
            f"<main>{body}</main></body></html>")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body, status=200):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        conn = connect()
        try:
            if u.path == "/":
                self._send(self.customer_page(conn, q))
            elif u.path == "/admin":
                self._send(self.admin_page(conn, q))
            elif u.path == "/admin/reminder":
                self._send(self.reminder_page(conn, q))
            else:
                self._send("not found", 404)
        finally:
            conn.close()

    def do_POST(self):
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        get = lambda k: form.get(k, [""])[0]
        conn = connect()
        try:
            if u.path == "/book":
                try:
                    bid = create_booking(conn, int(get("menu_id")), get("book_date"),
                                         get("book_time"), get("customer_name"), get("contact"))
                    self._send(page("予約完了", f"<div class='card'><h2>ご予約を受け付けました</h2>"
                                    f"<p>受付番号：{bid}／日時：{html.escape(get('book_date'))} {html.escape(get('book_time'))}〜</p>"
                                    "<p>店舗からの確定連絡をお待ちください。（このデモではメール送信は行いません）</p></div>"))
                except ValueError as e:
                    self._send(page("入力エラー", f"<div class='err'>{html.escape(str(e))}</div>"
                                    "<p><a href='/'>予約フォームに戻る</a></p>"), 400)
            elif u.path == "/admin/status":
                try:
                    change_status(conn, int(get("booking_id")), get("status"))
                    msg = "ステータスを変更しました"
                except ValueError as e:
                    msg = str(e)
                self._send(self.admin_page(conn, {}, msg=msg))
            else:
                self._send("not found", 404)
        finally:
            conn.close()

    def customer_page(self, conn, q):
        menus = conn.execute("SELECT * FROM menus ORDER BY id").fetchall()
        sel_date = q.get("date", [date.today().isoformat()])[0]
        slots = available_slots(conn, sel_date)
        menu_opts = "".join(
            f"<option value='{m['id']}'>{html.escape(m['name'])}（{m['duration_min']}分／{m['price']:,}円）</option>"
            for m in menus)
        slot_html = "".join(f"<span class='slot'>{s}</span>" for s in slots) or "空き枠はありません"
        slot_opts = "".join(f"<option value='{s}'>{s}</option>" for s in slots)
        return page("予約フォーム", f"""
        <div class='card'><h2>ご予約</h2>
        <form method='get' action='/'>
          <label>日付</label><input type='date' name='date' value='{html.escape(sel_date)}'>
          <p><button type='submit'>空き枠を見る</button></p>
        </form>
        <p>{html.escape(sel_date)} の空き枠：{slot_html}</p></div>
        <div class='card'><h2>予約フォーム</h2>
        <form method='post' action='/book'>
          <label>メニュー</label><select name='menu_id'>{menu_opts}</select>
          <label>日付</label><input type='date' name='book_date' value='{html.escape(sel_date)}' required>
          <label>時間</label><select name='book_time'>{slot_opts}</select>
          <label>お名前</label><input name='customer_name' required>
          <label>連絡先（電話番号など）</label><input name='contact'>
          <p><button type='submit'>予約する</button></p>
        </form></div>""")

    def admin_page(self, conn, q, msg=None):
        sel_date = q.get("date", [date.today().isoformat()])[0]
        rows = conn.execute(
            "SELECT b.*, m.name AS menu_name FROM bookings b JOIN menus m ON m.id=b.menu_id"
            " WHERE b.book_date=? ORDER BY b.book_time", (sel_date,)).fetchall()
        trs = ""
        for r in rows:
            opts = "".join(
                f"<option value='{s}'>{STATUS_LABEL[s]}</option>"
                for s in sorted(TRANSITIONS.get(r["status"], set())))
            action = (f"<form method='post' action='/admin/status' style='display:inline'>"
                      f"<input type='hidden' name='booking_id' value='{r['id']}'>"
                      f"<select name='status'>{opts}</select><button type='submit'>変更</button></form>"
                      ) if opts else "（終了）"
            trs += (f"<tr><td>{r['book_time']}</td><td>{html.escape(r['customer_name'])}</td>"
                    f"<td>{html.escape(r['menu_name'])}</td><td>{html.escape(r['contact'])}</td>"
                    f"<td><span class='badge st-{r['status']}'>{STATUS_LABEL[r['status']]}</span></td>"
                    f"<td>{action} <a href='/admin/reminder?id={r['id']}'>リマインド文面</a></td></tr>")
        msg_html = f"<div class='msg'>{html.escape(msg)}</div>" if msg else ""
        return page("管理画面", f"""{msg_html}
        <div class='card'><h2>予約一覧（管理画面）</h2>
        <form method='get' action='/admin'><label>日付</label>
        <input type='date' name='date' value='{html.escape(sel_date)}'><p><button>表示</button></p></form>
        <table><tr><th>時間</th><th>お名前</th><th>メニュー</th><th>連絡先</th><th>状態</th><th>操作</th></tr>
        {trs or '<tr><td colspan=6>この日の予約はありません</td></tr>'}</table></div>""")

    def reminder_page(self, conn, q):
        bid = q.get("id", ["0"])[0]
        r = conn.execute(
            "SELECT b.*, m.name AS menu_name FROM bookings b JOIN menus m ON m.id=b.menu_id WHERE b.id=?",
            (bid,)).fetchone()
        if r is None:
            return page("エラー", "<div class='err'>予約が見つかりません</div>")
        text = reminder_text(r, r["menu_name"])
        return page("リマインド文面", f"""
        <div class='card'><h2>リマインドメール文面（下書き）</h2>
        <p>予約 #{r['id']}（{html.escape(r['customer_name'])} 様）向けの自動生成文面です。実際には送信されません。コピーしてメールやLINEに貼って使えます。</p>
        <textarea readonly>{html.escape(text)}</textarea>
        <p><a href='/admin'>管理画面に戻る</a></p></div>""")


def main():
    conn = connect()
    init_db(conn)
    seed(conn)
    conn.close()
    ThreadingHTTPServer(("localhost", 8000), Handler).serve_forever()


if __name__ == "__main__":
    main()
