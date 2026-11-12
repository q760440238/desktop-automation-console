"""SQLite 持久化：任务、步骤、事件、联系人。

单文件数据库 data/agent.db；所有写入走一把全局锁，避免多线程下 sqlite 报错。
"""
from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any

from .settings import DB_PATH, ensure_dirs

_lock = threading.RLock()
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id TEXT PRIMARY KEY,
    platform TEXT NOT NULL,
    action TEXT NOT NULL,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT DEFAULT '',
    extra TEXT DEFAULT '{}',
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE TABLE IF NOT EXISTS steps (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL,
    idx INTEGER NOT NULL,
    target TEXT NOT NULL,
    text TEXT DEFAULT '',
    risk TEXT DEFAULT 'low',
    reason TEXT DEFAULT '',
    status TEXT NOT NULL,
    detail TEXT DEFAULT '',
    screenshot TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_steps_job ON steps(job_id);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    level TEXT NOT NULL,
    platform TEXT,
    job_id TEXT,
    message TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS contacts (
    platform TEXT NOT NULL,
    target TEXT NOT NULL,
    last_action TEXT,
    last_status TEXT,
    last_at TEXT,
    count INTEGER DEFAULT 0,
    PRIMARY KEY (platform, target)
);
"""


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def conn() -> sqlite3.Connection:
    global _conn
    ensure_dirs()
    with _lock:
        if _conn is None:
            _conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
            _conn.row_factory = sqlite3.Row
            _conn.execute("PRAGMA journal_mode=WAL")
            _conn.execute("PRAGMA busy_timeout=15000")
            _conn.executescript(SCHEMA)
            _conn.commit()
        return _conn


# ---------------------------------------------------------------- jobs
def insert_job(
    platform: str,
    action: str,
    mode: str,
    status: str,
    message: str,
    extra: dict[str, Any] | None = None,
) -> str:
    jid = new_id("job")
    with _lock:
        c = conn()
        c.execute(
            "INSERT INTO jobs(id,platform,action,mode,status,message,extra,created_at) VALUES(?,?,?,?,?,?,?,?)",
            (jid, platform, action, mode, status, message, json.dumps(extra or {}, ensure_ascii=False), now_iso()),
        )
        c.commit()
    return jid


def set_job_status(job_id: str, status: str, *, started: bool = False, finished: bool = False) -> None:
    with _lock:
        c = conn()
        sets = ["status=?"]
        args: list[Any] = [status]
        if started:
            sets.append("started_at=COALESCE(started_at,?)")
            args.append(now_iso())
        if finished:
            sets.append("finished_at=?")
            args.append(now_iso())
        args.append(job_id)
        c.execute(f"UPDATE jobs SET {','.join(sets)} WHERE id=?", args)
        c.commit()


def insert_steps(job_id: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    with _lock:
        c = conn()
        for i, r in enumerate(rows):
            sid = new_id("stp")
            c.execute(
                "INSERT INTO steps(id,job_id,idx,target,text,risk,reason,status,created_at)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    sid,
                    job_id,
                    i,
                    r["target"],
                    r.get("text", ""),
                    r.get("risk", "low"),
                    r.get("reason", ""),
                    "pending",
                    now_iso(),
                ),
            )
            out.append({"id": sid, "index": i, "target": r["target"], "text": r.get("text", "")})
        c.commit()
    return out


def update_step(step_id: str, **fields: Any) -> None:
    if not fields:
        return
    cols = ", ".join(f"{k}=?" for k in fields)
    with _lock:
        c = conn()
        c.execute(f"UPDATE steps SET {cols} WHERE id=?", [*fields.values(), step_id])
        c.commit()


def get_job_row(job_id: str) -> dict[str, Any] | None:
    c = conn()
    row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def job_steps(job_id: str) -> list[dict[str, Any]]:
    c = conn()
    rows = c.execute("SELECT * FROM steps WHERE job_id=? ORDER BY idx", (job_id,)).fetchall()
    return [dict(r) for r in rows]


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    c = conn()
    rows = c.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        stats = c.execute(
            "SELECT status, COUNT(*) n FROM steps WHERE job_id=? GROUP BY status", (d["id"],)
        ).fetchall()
        d["stats"] = {s["status"]: s["n"] for s in stats}
        out.append(d)
    return out


# ---------------------------------------------------------------- events
def add_event(level: str, message: str, platform: str = "", job_id: str = "") -> int:
    with _lock:
        c = conn()
        cur = c.execute(
            "INSERT INTO events(ts,level,platform,job_id,message) VALUES(?,?,?,?,?)",
            (now_iso(), level, platform, job_id, message),
        )
        c.commit()
        return int(cur.lastrowid or 0)


def list_events(after: int = 0, limit: int = 200) -> list[dict[str, Any]]:
    c = conn()
    rows = c.execute(
        "SELECT * FROM events WHERE id>? ORDER BY id ASC LIMIT ?", (after, limit)
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------- contacts
def touch_contact(platform: str, target: str, action: str, status: str) -> None:
    with _lock:
        c = conn()
        c.execute(
            "INSERT INTO contacts(platform,target,last_action,last_status,last_at,count) VALUES(?,?,?,?,?,1)"
            " ON CONFLICT(platform,target) DO UPDATE SET"
            " last_action=excluded.last_action, last_status=excluded.last_status,"
            " last_at=excluded.last_at, count=contacts.count+1",
            (platform, target, action, status, now_iso()),
        )
        c.commit()


def last_contact(platform: str, target: str) -> dict[str, Any] | None:
    c = conn()
    row = c.execute(
        "SELECT * FROM contacts WHERE platform=? AND target=?", (platform, target)
    ).fetchone()
    return dict(row) if row else None


def usage_count(platform: str, hours: int) -> int:
    """统计窗口内成功动作数，用于小时/日限流。"""
    since = (datetime.now() - timedelta(hours=hours)).replace(microsecond=0).isoformat()
    c = conn()
    row = c.execute(
        "SELECT COUNT(*) n FROM steps s JOIN jobs j ON s.job_id=j.id"
        " WHERE j.platform=? AND s.status='ok' AND s.finished_at>=?",
        (platform, since),
    ).fetchone()
    return int(row["n"] if row else 0)


def audit_rows(limit: int = 100) -> list[dict[str, Any]]:
    c = conn()
    rows = c.execute(
        "SELECT s.id, s.finished_at, s.target, s.status, s.detail, s.risk, s.screenshot,"
        " j.platform, j.action FROM steps s JOIN jobs j ON s.job_id=j.id"
        " WHERE s.status IN ('ok','failed','rejected','skipped')"
        " ORDER BY s.finished_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def today_counters() -> dict[str, int]:
    today = datetime.now().strftime("%Y-%m-%d")
    c = conn()
    rows = c.execute(
        "SELECT status, COUNT(*) n FROM steps WHERE substr(finished_at,1,10)=? GROUP BY status",
        (today,),
    ).fetchall()
    return {r["status"]: r["n"] for r in rows}
