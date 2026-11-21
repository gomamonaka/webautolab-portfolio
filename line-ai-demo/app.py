# -*- coding: utf-8 -*-
"""
LINE×AI返信デモ（シミュレーター）
- LINE公式アカウントの問い合わせ対応をローカルで再現するデモです。
- 実LINE・実LLMには接続していません。返信の下書きはルールベースの疑似AIが生成します。
- 流れ: お客様が送信 → 疑似AIが下書きを生成 → 管理者が確認して「送信」 → お客様に届く
Python標準ライブラリのみ。起動: python3 app.py  → http://localhost:8000
"""
import json
import os
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SHOP_NAME = "サンプルサロン"

# --- 疑似AI（ルールベース） -------------------------------------------------

CATEGORY_RULES = [
    ("営業時間", ["営業時間", "何時", "開店", "閉店", "休み", "定休日"]),
    ("料金", ["料金", "いくら", "値段", "価格", "費用", "円"]),
    ("予約", ["予約", "空き", "空いて", "行きたい", "お願いしたい"]),
    ("アクセス", ["アクセス", "場所", "行き方", "住所", "駅", "駐車場"]),
]

DRAFT_TEMPLATES = {
    "営業時間": (
        "お問い合わせありがとうございます。{shop}の営業時間は、平日10:00〜20:00、"
        "土日祝10:00〜18:00です（定休日：火曜日）。ご来店をお待ちしております。"
    ),
    "料金": (
        "お問い合わせありがとうございます。{shop}の料金は、カット 4,400円〜、"
        "カラー 6,600円〜、パーマ 7,700円〜です。詳しいメニューはお気軽にお尋ねください。"
    ),
    "予約": (
        "ご予約ありがとうございます。空き状況を確認いたしますので、"
        "ご希望の日時とメニューを教えていただけますか？"
    ),
    "アクセス": (
        "お問い合わせありがとうございます。{shop}は最寄り駅から徒歩5分の場所にあります。"
        "専用駐車場はございませんので、近隣のコインパーキングをご利用ください。"
    ),
    "その他": (
        "お問い合わせありがとうございます。内容を確認のうえ、担当者より改めてご連絡いたします。"
        "少々お待ちくださいませ。"
    ),
}


def classify(text: str) -> str:
    """キーワードで問い合わせカテゴリを判定する（疑似AI）。"""
    for category, keywords in CATEGORY_RULES:
        if any(k in text for k in keywords):
            return category
    return "その他"


def make_draft(text: str) -> tuple:
    """(カテゴリ, 返信下書き) を返す。"""
    category = classify(text)
    return category, DRAFT_TEMPLATES[category].format(shop=SHOP_NAME)


# --- デモの状態 ---------------------------------------------------------------

class Demo:
    def __init__(self):
        self.lock = threading.Lock()
        self.customer_messages = []  # {"from": "customer"|"shop", "text": str, "time": str}
        self.drafts = []             # {"id", "question", "category", "draft", "status"}
        self.log = []                # 管理者向け通知ログ
        self._next_id = 1

    def _now(self):
        return datetime.now().strftime("%H:%M")

    def customer_send(self, text: str) -> dict:
        text = (text or "").strip()
        if not text:
            raise ValueError("メッセージが空です")
        with self.lock:
            self.customer_messages.append({"from": "customer", "text": text, "time": self._now()})
            category, draft_text = make_draft(text)
            draft = {
                "id": self._next_id,
                "question": text,
                "category": category,
                "draft": draft_text,
                "status": "下書き（未送信）",
            }
            self._next_id += 1
            self.drafts.append(draft)
            self.log.append(f"{self._now()} 新しい問い合わせ（{category}）の下書きを作成しました")
            return draft

    def approve(self, draft_id: int, text: str = None) -> dict:
        """管理者が下書きを確認し、（必要なら編集して）送信する。"""
        with self.lock:
            for d in self.drafts:
                if d["id"] == draft_id:
                    if d["status"] != "下書き（未送信）":
                        raise ValueError("この下書きは既に処理済みです")
                    send_text = (text or "").strip() or d["draft"]
                    d["status"] = "送信済み"
                    d["draft"] = send_text
                    self.customer_messages.append({"from": "shop", "text": send_text, "time": self._now()})
                    self.log.append(f"{self._now()} 下書き#{draft_id} を送信しました")
                    return d
            raise KeyError(f"下書きが見つかりません: {draft_id}")

    def state(self) -> dict:
        with self.lock:
            return {
                "customer_messages": list(self.customer_messages),
                "drafts": list(self.drafts),
                "log": list(self.log),
            }


DEMO = Demo()

# --- 画面 ---------------------------------------------------------------------

HTML = """<!DOCTYPE html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LINE×AI返信デモ（シミュレーター）</title>
<style>
body{font-family:'Hiragino Sans','Noto Sans JP',sans-serif;margin:0;background:#eef1f4;color:#222}
header{background:#06c755;color:#fff;padding:14px 20px}
header h1{font-size:19px;margin:0}
header p{margin:4px 0 0;font-size:12.5px;opacity:.92}
.wrap{display:flex;gap:22px;max-width:1060px;margin:20px auto;padding:0 14px;flex-wrap:wrap}
.phone{width:330px;background:#8cabd9;border-radius:26px;padding:12px;box-shadow:0 4px 14px rgba(0,0,0,.18)}
.phone .screen{background:#8cabd9;border-radius:16px;display:flex;flex-direction:column;height:520px}
.phone .bar{background:#06c755;color:#fff;padding:10px 12px;border-radius:12px 12px 0 0;font-weight:700;font-size:14px}
.chat{flex:1;overflow-y:auto;padding:10px;display:flex;flex-direction:column;gap:8px}
.msg{max-width:78%;padding:8px 11px;border-radius:14px;font-size:13.5px;line-height:1.5;white-space:pre-wrap}
.msg.customer{align-self:flex-end;background:#a9e493;border-bottom-right-radius:4px}
.msg.shop{align-self:flex-start;background:#fff;border-bottom-left-radius:4px}
.msg .time{display:block;font-size:10px;color:#335;text-align:right;margin-top:2px}
.inputrow{display:flex;gap:6px;padding:10px;background:#f4f6f8;border-radius:0 0 12px 12px}
.inputrow input{flex:1;padding:9px;border:1px solid #ccc;border-radius:18px;font-size:13.5px}
.inputrow button{background:#06c755;color:#fff;border:none;border-radius:18px;padding:9px 14px;font-weight:700;cursor:pointer}
.samples{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.samples button{background:#fff;border:1px solid #06c755;color:#04963f;border-radius:16px;padding:6px 10px;font-size:12.5px;cursor:pointer}
.admin{flex:1;min-width:340px;background:#fff;border-radius:14px;padding:16px 18px;box-shadow:0 2px 8px rgba(0,0,0,.08)}
.admin h2{font-size:16px;margin:4px 0 10px}
.draft{border:1px solid #ddd;border-radius:10px;padding:10px 12px;margin-bottom:12px}
.draft .meta{font-size:12px;color:#666;margin-bottom:6px}
.draft textarea{width:100%;box-sizing:border-box;min-height:74px;font-size:13.5px;padding:8px;border:1px solid #ccc;border-radius:8px}
.draft button{background:#06c755;color:#fff;border:none;border-radius:8px;padding:8px 14px;font-weight:700;cursor:pointer;margin-top:8px}
.badge{display:inline-block;background:#ffefc2;border:1px solid #e3c964;border-radius:10px;padding:1px 8px;font-size:11px}
.badge.sent{background:#e2f5e6;border-color:#9ed3a8}
.log{background:#f7f8f9;border-radius:10px;padding:10px 12px;font-size:12.5px;max-height:150px;overflow-y:auto}
.log div{padding:2px 0;border-bottom:1px dotted #ddd}
.note{font-size:12px;color:#666;max-width:1060px;margin:0 auto;padding:0 14px 18px}
</style></head><body>
<header><h1>LINE×AI返信デモ（シミュレーター）</h1>
<p>※ これはデモです。実LINE・実LLMには接続しておらず、返信の下書きはルールベースの疑似AIが生成します。</p></header>
<div class="wrap">
  <div>
    <div class="phone"><div class="screen">
      <div class="bar">サンプルサロン（公式アカウント）</div>
      <div class="chat" id="chat"></div>
      <div class="inputrow">
        <input id="input" placeholder="メッセージを入力" onkeydown="if(event.key==='Enter')sendMsg()">
        <button onclick="sendMsg()">送信</button>
      </div>
    </div></div>
    <div class="samples">
      <button onclick="sample(this)">営業時間を教えてください</button>
      <button onclick="sample(this)">予約したいのですが空いていますか</button>
      <button onclick="sample(this)">カットの料金はいくらですか</button>
      <button onclick="sample(this)">お店の場所と行き方を教えてください</button>
    </div>
  </div>
  <div class="admin">
    <h2>管理者画面（返信の下書きを確認して送信）</h2>
    <div id="drafts"></div>
    <h2>通知ログ</h2>
    <div class="log" id="log"></div>
  </div>
</div>
<p class="note">流れ：お客様がメッセージを送ると、疑似AIが返信の「下書き」を作り、管理者画面に届きます。管理者が内容を確認（編集も可能）して「このまま送信」を押すと、お客様の画面に返信が届きます。実案件では、LINE Messaging API と LLM（ChatGPT等）を接続し、送信前に人の確認を挟む構成にします。</p>
<script>
async function refresh(){
  const s = await (await fetch('/api/state')).json();
  const chat = document.getElementById('chat');
  chat.innerHTML = s.customer_messages.map(m =>
    `<div class="msg ${m.from}">${escapeHtml(m.text)}<span class="time">${m.time}</span></div>`).join('');
  chat.scrollTop = chat.scrollHeight;
  const dr = document.getElementById('drafts');
  if(!s.drafts.length){ dr.innerHTML = '<p style="color:#888;font-size:13px">まだ問い合わせはありません。左の画面からメッセージを送ってみてください。</p>'; }
  else{
    dr.innerHTML = s.drafts.slice().reverse().map(d => `
      <div class="draft">
        <div class="meta">お客様：${escapeHtml(d.question)} ／ 分類：${d.category} ／ <span class="badge ${d.status==='送信済み'?'sent':''}">${d.status}</span></div>
        <textarea id="draft-${d.id}" ${d.status!=='下書き（未送信）'?'disabled':''}>${escapeHtml(d.draft)}</textarea>
        ${d.status==='下書き（未送信）' ? `<button onclick="approve(${d.id})">このまま送信</button>` : ''}
      </div>`).join('');
  }
  document.getElementById('log').innerHTML = s.log.slice().reverse().map(l => `<div>${escapeHtml(l)}</div>`).join('');
}
function escapeHtml(t){ const d=document.createElement('div'); d.textContent=t; return d.innerHTML; }
async function sendMsg(){
  const i = document.getElementById('input'); const v = i.value.trim(); if(!v) return;
  await fetch('/api/customer/send', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text: v})});
  i.value=''; refresh();
}
function sample(btn){ document.getElementById('input').value = btn.textContent; sendMsg(); }
async function approve(id){
  const text = document.getElementById('draft-'+id).value;
  await fetch('/api/admin/approve', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({id: id, text: text})});
  refresh();
}
refresh(); setInterval(refresh, 2000);
</script></body></html>
"""

# --- HTTPサーバー ---------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        if self.path == "/":
            body = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/state":
            self._json(200, DEMO.state())
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        try:
            data = self._read_body()
            if self.path == "/api/customer/send":
                self._json(200, DEMO.customer_send(data.get("text", "")))
            elif self.path == "/api/admin/approve":
                self._json(200, DEMO.approve(int(data["id"]), data.get("text")))
            else:
                self._json(404, {"error": "not found"})
        except (ValueError, KeyError) as e:
            self._json(400, {"error": str(e)})


def main():
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"LINE×AI返信デモ: http://localhost:{port} （Ctrl+Cで停止）")
    server.serve_forever()


if __name__ == "__main__":
    main()
