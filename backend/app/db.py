"""SQLite storage. Same tables as section 10; swap for PostgreSQL later."""
import json
import sqlite3
import threading
import time
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(
  id TEXT PRIMARY KEY, name TEXT, plan TEXT DEFAULT 'free', country TEXT,
  auto_spend INTEGER DEFAULT 20, private_route INTEGER DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS profiles(user_id TEXT PRIMARY KEY, data TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS conversations(
  id TEXT PRIMARY KEY, user_id TEXT, title TEXT, summary TEXT DEFAULT '',
  summarized_upto INTEGER DEFAULT 0, created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS messages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, conversation_id TEXT, role TEXT, content TEXT,
  meta TEXT, task_id TEXT, rating INTEGER, created_at REAL);
CREATE TABLE IF NOT EXISTS tasks(
  id TEXT PRIMARY KEY, user_id TEXT, conversation_id TEXT, mode TEXT, intent TEXT,
  status TEXT, estimate INTEGER, max_credits INTEGER, credits_used INTEGER DEFAULT 0,
  usd_used REAL DEFAULT 0, config TEXT, state TEXT, created_at REAL, finished_at REAL);
CREATE TABLE IF NOT EXISTS usage_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, task_id TEXT, step_no INTEGER,
  role TEXT, model TEXT, input_tokens INTEGER, cached_tokens INTEGER, output_tokens INTEGER,
  reasoning_tokens INTEGER, tool_units TEXT, cost_usd REAL, cost_source TEXT,
  credits_charged INTEGER, finish_reason TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS credit_ledger(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, delta INTEGER, reason TEXT,
  task_id TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS credit_holds(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, task_id TEXT UNIQUE, amount INTEGER,
  status TEXT DEFAULT 'active', created_at REAL);
CREATE TABLE IF NOT EXISTS model_catalog(
  id TEXT PRIMARY KEY, name TEXT, lab TEXT, region TEXT, tier TEXT,
  price_in REAL, price_out REAL, price_cached REAL, thinks INTEGER DEFAULT 0,
  reasoning_style TEXT DEFAULT 'effort', context INTEGER, available INTEGER DEFAULT 1,
  approved INTEGER DEFAULT 1, private_route INTEGER DEFAULT 1, source TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS model_prices(
  id INTEGER PRIMARY KEY AUTOINCREMENT, model_id TEXT, price_in REAL, price_out REAL,
  started_at REAL);
CREATE TABLE IF NOT EXISTS run_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, seq INTEGER, type TEXT, data TEXT,
  created_at REAL);
CREATE TABLE IF NOT EXISTS workspace_files(
  id TEXT PRIMARY KEY, user_id TEXT, task_id TEXT, path TEXT, kind TEXT, name TEXT,
  size INTEGER, version INTEGER DEFAULT 1, delete_after REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS artifacts(
  id TEXT PRIMARY KEY, user_id TEXT, task_id TEXT, kind TEXT, data TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS modes(
  id TEXT PRIMARY KEY, data TEXT, enabled INTEGER DEFAULT 1, sort INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS ix_events_task ON run_events(task_id, seq);
CREATE INDEX IF NOT EXISTS ix_ledger_user ON credit_ledger(user_id);
CREATE INDEX IF NOT EXISTS ix_usage_task ON usage_events(task_id);
CREATE INDEX IF NOT EXISTS ix_msgs_conv ON messages(conversation_id, id);
"""


class DB:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            self.conn.commit()

    def run(self, sql: str, params=()) -> sqlite3.Cursor:
        with self.lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def one(self, sql: str, params=()) -> dict | None:
        with self.lock:
            row = self.conn.execute(sql, params).fetchone()
        return dict(row) if row else None

    def all(self, sql: str, params=()) -> list[dict]:
        with self.lock:
            rows = self.conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]

    def scalar(self, sql: str, params=(), default=0):
        with self.lock:
            row = self.conn.execute(sql, params).fetchone()
        return default if row is None or row[0] is None else row[0]


def now() -> float:
    return time.time()


def jdump(x) -> str:
    return json.dumps(x, ensure_ascii=False)


def jload(s, default=None):
    if s is None or s == "":
        return default
    try:
        return json.loads(s)
    except (ValueError, TypeError):
        return default
