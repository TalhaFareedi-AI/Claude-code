"""SQLite storage. Same tables as section 10 and section 18; swap for PostgreSQL later."""
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
CREATE TABLE IF NOT EXISTS run_requests(
  user_id TEXT, request_id TEXT, task_id TEXT, payload_hash TEXT,
  PRIMARY KEY(user_id,request_id));
CREATE TABLE IF NOT EXISTS usage_events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, task_id TEXT, step_no INTEGER,
  role TEXT, model TEXT, input_tokens INTEGER, cached_tokens INTEGER, output_tokens INTEGER,
  reasoning_tokens INTEGER, tool_units TEXT, cost_usd REAL, cost_source TEXT,
  credits_charged INTEGER, finish_reason TEXT, created_at REAL, latency_ms INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS credit_ledger(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, delta INTEGER, reason TEXT,
  task_id TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS credit_holds(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, task_id TEXT UNIQUE, amount INTEGER,
  status TEXT DEFAULT 'active', created_at REAL);
CREATE TABLE IF NOT EXISTS model_catalog(
  id TEXT PRIMARY KEY, name TEXT, lab TEXT, region TEXT, tier TEXT,
  price_in REAL, price_out REAL, price_cached REAL, thinks INTEGER DEFAULT 0,
  reasoning_style TEXT DEFAULT 'effort', context INTEGER, available INTEGER DEFAULT 1, image_out INTEGER DEFAULT 0,
  approved INTEGER DEFAULT 1, private_route INTEGER DEFAULT 1, source TEXT, updated_at REAL);
CREATE TABLE IF NOT EXISTS model_prices(
  id INTEGER PRIMARY KEY AUTOINCREMENT, model_id TEXT, price_in REAL, price_out REAL,
  started_at REAL);
CREATE TABLE IF NOT EXISTS action_prices(
  action TEXT PRIMARY KEY, credits INTEGER, updated_at REAL);
CREATE TABLE IF NOT EXISTS eval_results(
  id INTEGER PRIMARY KEY AUTOINCREMENT, prompt_name TEXT, version INTEGER,
  question_id TEXT, score REAL, cost_usd REAL, created_at REAL);
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
CREATE TABLE IF NOT EXISTS plans(
  id TEXT PRIMARY KEY, name TEXT, kind TEXT DEFAULT 'subscription', price_usd REAL DEFAULT 0,
  credits INTEGER DEFAULT 0, period_days INTEGER DEFAULT 30, benefits TEXT, rules TEXT,
  active INTEGER DEFAULT 1, sort INTEGER DEFAULT 0, updated_at REAL);
CREATE TABLE IF NOT EXISTS purchases(
  id TEXT PRIMARY KEY, user_id TEXT, plan_id TEXT, kind TEXT, amount_usd REAL, credits INTEGER,
  status TEXT, provider TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS sessions(
  token_hash TEXT PRIMARY KEY, user_id TEXT, created_at REAL, expires_at REAL, ip TEXT, agent TEXT);
CREATE TABLE IF NOT EXISTS activity(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, kind TEXT, detail TEXT, actor TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS memories(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, kind TEXT, content TEXT, importance INTEGER DEFAULT 3,
  source TEXT, conversation_id TEXT, pinned INTEGER DEFAULT 0, use_count INTEGER DEFAULT 0,
  last_used_at REAL, created_at REAL, updated_at REAL, deleted INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS harness_versions(
  id TEXT PRIMARY KEY, user_id TEXT, parent_id TEXT, name TEXT, files TEXT,
  created_by TEXT, active INTEGER DEFAULT 1, created_at REAL);
CREATE TABLE IF NOT EXISTS improvement_records(
  id TEXT PRIMARY KEY, user_id TEXT, task_id TEXT, base_harness TEXT, new_harness TEXT,
  k INTEGER DEFAULT 1, edits TEXT, evidence TEXT, compose_decision TEXT, result_summary TEXT,
  credits INTEGER DEFAULT 0, undone INTEGER DEFAULT 0, created_at REAL);
CREATE TABLE IF NOT EXISTS lessons(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id TEXT, scope TEXT DEFAULT 'personal',
  topic TEXT DEFAULT 'general', text TEXT, evidence TEXT, helped_count INTEGER DEFAULT 0,
  hurt_count INTEGER DEFAULT 0, review_status TEXT DEFAULT 'approved',
  created_at REAL, updated_at REAL);
CREATE INDEX IF NOT EXISTS ix_activity_user ON activity(user_id, id);
CREATE INDEX IF NOT EXISTS ix_memories_user ON memories(user_id, deleted);
CREATE INDEX IF NOT EXISTS ix_purchases_user ON purchases(user_id);
CREATE INDEX IF NOT EXISTS ix_conv_user ON conversations(user_id, updated_at);
CREATE INDEX IF NOT EXISTS ix_tasks_user ON tasks(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_events_task ON run_events(task_id, seq);
CREATE INDEX IF NOT EXISTS ix_ledger_user ON credit_ledger(user_id);
CREATE INDEX IF NOT EXISTS ix_usage_task ON usage_events(task_id);
CREATE INDEX IF NOT EXISTS ix_msgs_conv ON messages(conversation_id, id);
CREATE INDEX IF NOT EXISTS ix_lessons_scope ON lessons(scope, review_status);
"""


MIGRATIONS = [
    ("usage_events", "latency_ms INTEGER DEFAULT 0"),
    ("users", "email TEXT"), ("users", "pw_hash TEXT"), ("users", "role TEXT DEFAULT 'user'"),
    ("users", "status TEXT DEFAULT 'active'"), ("users", "daily_limit INTEGER"), ("users", "monthly_limit INTEGER"),
    ("users", "memory_enabled INTEGER DEFAULT 1"), ("users", "last_seen_at REAL"), ("users", "plan_renews_at REAL"),
    ("users", "note TEXT"),
    ("conversations", "notes TEXT DEFAULT ''"),
    ("model_catalog", "image_out INTEGER DEFAULT 0"),
    ("users", "image_model TEXT"),
]

# Full-text search keeps memory recall fast: past messages and saved memories are indexed as they are written.
FTS = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(content, content='messages', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content); END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content); END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE OF content ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
  INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content); END;
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(content, content='memories', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
  INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content); END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content); END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF content ON memories BEGIN
  INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.id, old.content);
  INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content); END;
"""


class DB:
    def __init__(self, path: str):
        if path != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False)
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")  # readers do not block the writer
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.row_factory = sqlite3.Row
        self.lock = threading.RLock()
        with self.lock:
            self.conn.executescript(SCHEMA)
            for table, column in MIGRATIONS:  # older databases: add new columns
                try:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column}")
                except sqlite3.OperationalError:
                    pass
            self.fts = self._setup_fts()
            self.conn.commit()

    def _setup_fts(self) -> bool:
        try:
            fresh = self.conn.execute("SELECT name FROM sqlite_master WHERE name='messages_fts'").fetchone() is None
            self.conn.executescript(FTS)
            if fresh:  # index messages written before search existed
                self.conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
                self.conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
            return True
        except sqlite3.OperationalError:  # SQLite without FTS5: memory falls back to LIKE search
            return False

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
