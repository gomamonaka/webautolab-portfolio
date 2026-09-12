"""One row per pipeline task. Claim/history and transitions are atomic."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from config import DB_PATH, load_agents


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


@contextmanager
def connect():
    db = sqlite3.connect(DB_PATH, timeout=30)
    db.row_factory = sqlite3.Row
    try:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS tasks (
          id INTEGER PRIMARY KEY, stage TEXT NOT NULL,
          status TEXT NOT NULL CHECK(status IN ('pending','processing','done','failed')),
          payload TEXT NOT NULL, result TEXT, agent TEXT NOT NULL,
          retry_count INTEGER NOT NULL DEFAULT 0, last_error TEXT,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS task_pick ON tasks(stage, status, id);
        CREATE TABLE IF NOT EXISTS run_history (
          id INTEGER PRIMARY KEY, started_at TEXT NOT NULL, finished_at TEXT,
          stage TEXT NOT NULL, task_id INTEGER NOT NULL, status TEXT NOT NULL, error TEXT);
        ''')
        yield db
        db.commit()
    except BaseException:
        db.rollback()
        raise
    finally:
        db.close()


def enqueue(stage, payload):
    load_agents()[stage]
    if not isinstance(payload, dict):
        raise ValueError('payload must be a JSON object')
    with connect() as db:
        return db.execute('''INSERT INTO tasks
            (stage,status,payload,agent,created_at,updated_at) VALUES (?, 'pending', ?, ?, ?, ?)''',
            (stage, json.dumps(payload, ensure_ascii=False), stage, now(), now())).lastrowid


def claim_next(stage):
    load_agents()[stage]
    with connect() as db:
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT * FROM tasks WHERE stage=? AND status='pending' ORDER BY id LIMIT 1",
                         (stage,)).fetchone()
        if row is None:
            return None
        db.execute("UPDATE tasks SET status='processing', agent=?, updated_at=? WHERE id=?",
                   (stage, now(), row['id']))
        db.execute('''INSERT INTO run_history (started_at,stage,task_id,status)
                      VALUES (?,?,?,'processing')''', (now(), stage, row['id']))
        task = dict(row)
        task['status'] = 'processing'
        return task


def processing(db, task_id):
    db.execute('BEGIN IMMEDIATE')
    task = db.execute('SELECT * FROM tasks WHERE id=?', (task_id,)).fetchone()
    if task is None or task['status'] != 'processing':
        raise ValueError('Task must be processing')
    return task


def finish_history(db, task_id, status, error=None):
    db.execute('''UPDATE run_history SET finished_at=?,status=?,error=?
                  WHERE task_id=? AND finished_at IS NULL''', (now(), status, error, task_id))


def complete(task_id, result, next_stage):
    with connect() as db:
        task = processing(db, task_id)
        agent = load_agents()[task['stage']]
        if next_stage != agent['next_stage']:
            raise ValueError('Unexpected next_stage')
        if not isinstance(result, dict) or set(agent['output_contract']) - result.keys():
            raise ValueError('Invalid output contract')
        payload = json.loads(task['payload'])
        payload.update({k: result[k] for k in agent['output_contract']})
        db.execute('''UPDATE tasks SET stage=?,status=?,payload=?,result=?,agent=?,
                      retry_count=0,last_error=NULL,updated_at=? WHERE id=?''',
                   (next_stage or task['stage'], 'pending' if next_stage else 'done',
                    json.dumps(payload, ensure_ascii=False), json.dumps(result, ensure_ascii=False),
                    next_stage or task['agent'], now(), task_id))
        finish_history(db, task_id, 'done')


def fail(task_id, error):
    with connect() as db:
        task = processing(db, task_id)
        retries = task['retry_count'] + 1
        # max_retries means additional attempts after the first failure.
        terminal = retries > load_agents()[task['stage']]['max_retries']
        status = 'failed' if terminal else 'pending'
        db.execute('UPDATE tasks SET status=?,retry_count=?,last_error=?,updated_at=? WHERE id=?',
                   (status, retries, str(error), now(), task_id))
        finish_history(db, task_id, 'failed', str(error))
    if terminal:
        from notify import notify_failure
        notify_failure(task_id, task['stage'], str(error))
    return status


def counts():
    with connect() as db:
        result = dict.fromkeys(('pending', 'processing', 'done', 'failed'), 0)
        result.update({r['status']: r['n'] for r in db.execute('SELECT status,count(*) n FROM tasks GROUP BY status')})
        return result
