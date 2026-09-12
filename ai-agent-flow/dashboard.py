"""Render dashboard.html from the pipeline database (no JS, no frameworks)."""
import html
import json
from datetime import datetime, timedelta, timezone

from config import ROOT, load_agents
from taskqueue import connect

STUCK_MINUTES = 30
STATUSES = ('pending', 'processing', 'done', 'failed')
LABELS = {'pending': '未処理', 'processing': '処理中', 'done': '完了', 'failed': '失敗'}


def gather():
    agents = list(load_agents())
    with connect() as db:
        rows = db.execute('SELECT stage, status, count(*) n FROM tasks GROUP BY stage, status').fetchall()
        per_stage = {stage: dict.fromkeys(STATUSES, 0) for stage in agents}
        for row in rows:
            per_stage.setdefault(row['stage'], dict.fromkeys(STATUSES, 0))[row['status']] = row['n']

        today = datetime.now(timezone.utc).date().isoformat()
        processed_today = db.execute(
            "SELECT count(*) n FROM run_history WHERE status='done' AND finished_at LIKE ?",
            (today + '%',)).fetchone()['n']

        history = db.execute('''SELECT started_at, finished_at, stage, task_id, status, error
                                FROM run_history ORDER BY id DESC LIMIT 20''').fetchall()

        limit = (datetime.now(timezone.utc) - timedelta(minutes=STUCK_MINUTES)).isoformat(timespec='seconds')
        stuck = db.execute("""SELECT id, stage, updated_at, retry_count FROM tasks
                              WHERE status='processing' AND updated_at < ? ORDER BY updated_at""",
                           (limit,)).fetchall()
        failed = db.execute("""SELECT id, stage, retry_count, last_error FROM tasks
                               WHERE status='failed' ORDER BY updated_at DESC LIMIT 20""").fetchall()
    return per_stage, processed_today, [dict(r) for r in history], [dict(r) for r in stuck], [dict(r) for r in failed]


def table(headers, rows, empty):
    if not rows:
        return f'<p class="empty">{html.escape(empty)}</p>'
    head = ''.join(f'<th>{html.escape(h)}</th>' for h in headers)
    body = ''.join('<tr>' + ''.join(f'<td>{html.escape("" if c is None else str(c))}</td>' for c in row) + '</tr>'
                   for row in rows)
    return f'<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def render():
    per_stage, processed_today, history, stuck, failed = gather()
    generated = datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    stage_rows = [[stage] + [counts[s] for s in STATUSES] for stage, counts in per_stage.items()]
    totals = [sum(c[s] for c in per_stage.values()) for s in STATUSES]
    stage_rows.append(['合計'] + totals)
    parts = [
        '<!doctype html><html lang="ja"><head><meta charset="utf-8">',
        '<title>AI業務フロー ダッシュボード</title><style>',
        'body{font-family:system-ui,"Hiragino Kaku Gothic ProN",Meiryo,sans-serif;margin:24px;color:#1b2733;background:#f7f9fb}',
        'h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 8px}',
        '.meta{color:#5b6b7b;font-size:12px}.kpi{display:inline-block;background:#fff;border:1px solid #dde5ec;',
        'border-radius:8px;padding:12px 18px;margin:12px 12px 0 0}.kpi b{display:block;font-size:24px}',
        'table{border-collapse:collapse;background:#fff;font-size:13px}',
        'th,td{border:1px solid #dde5ec;padding:6px 10px;text-align:left}th{background:#eef3f7}',
        '.empty{color:#5b6b7b;font-size:13px}.warn{color:#b3261e}</style></head><body>',
        '<h1>AI業務フロー ダッシュボード</h1>',
        f'<p class="meta">生成時刻 {html.escape(generated)} / 「処理中」が{STUCK_MINUTES}分以上続くタスクは滞留として表示します</p>',
        f'<div class="kpi">本日の完了処理<b>{processed_today}</b></div>',
        f'<div class="kpi">失敗（要対応）<b class="{"warn" if totals[3] else ""}">{totals[3]}</b></div>',
        f'<div class="kpi">滞留タスク<b class="{"warn" if stuck else ""}">{len(stuck)}</b></div>',
        '<h2>AI社員ごとの状況</h2>',
        table(['担当（ステージ）'] + [LABELS[s] for s in STATUSES], stage_rows, 'タスクがありません'),
        '<h2>滞留しているタスク</h2>',
        table(['タスクID', '担当', '最終更新', 'リトライ'], [[r['id'], r['stage'], r['updated_at'], r['retry_count']] for r in stuck], '滞留なし'),
        '<h2>失敗したタスク</h2>',
        table(['タスクID', '担当', 'リトライ', '最後のエラー'], [[r['id'], r['stage'], r['retry_count'], r['last_error']] for r in failed], '失敗なし'),
        '<h2>直近の実行履歴</h2>',
        table(['開始', '終了', '担当', 'タスクID', '結果', 'エラー'],
              [[r['started_at'], r['finished_at'], r['stage'], r['task_id'], LABELS.get(r['status'], r['status']), r['error']] for r in history],
              '履歴なし'),
        '</body></html>',
    ]
    return '\n'.join(parts)


if __name__ == '__main__':
    out = ROOT / 'dashboard.html'
    out.write_text(render(), encoding='utf-8')
    print(f'wrote {out} ({out.stat().st_size} bytes)')
