"""SQLite persistence: tickets, agent_logs, decisions."""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    ticket_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    original_input TEXT NOT NULL,
    category TEXT,
    priority TEXT,
    assigned_department TEXT,
    status TEXT,
    auditor_decision TEXT,
    revision_count INTEGER,
    execution_mode TEXT,
    total_time_ms INTEGER,
    result_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    step INTEGER,
    agent TEXT,
    action TEXT,
    status TEXT,
    provider TEXT,
    model TEXT,
    simulated INTEGER,
    duration_ms INTEGER,
    output_json TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    agent TEXT,
    decision_type TEXT,
    decision TEXT,
    reason TEXT,
    created_at TEXT
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    config.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def save_ticket(result: dict) -> None:
    with connect() as c:
        c.execute(
            """INSERT OR REPLACE INTO tickets VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                result["ticket_id"], result["created_at"], result["original_input"],
                result.get("category"), result.get("priority"), result.get("assigned_department"),
                result.get("status"), result.get("auditor_decision"), result.get("revision_count"),
                result.get("execution_mode"), result["autonomy_metrics"].get("total_execution_time_ms"),
                json.dumps(result, ensure_ascii=False),
            ),
        )
        for ev in result.get("execution_trace", []):
            if ev.get("status") == "started":
                continue
            c.execute(
                """INSERT INTO agent_logs (ticket_id, step, agent, action, status, provider, model,
                   simulated, duration_ms, output_json, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    result["ticket_id"], ev.get("step"), ev.get("agent"), ev.get("action"),
                    ev.get("status"), ev.get("provider"), ev.get("model"), int(bool(ev.get("simulated"))),
                    ev.get("duration_ms"), json.dumps(ev.get("output"), ensure_ascii=False), ev.get("timestamp"),
                ),
            )
        for d in result.get("decisions", []):
            c.execute(
                """INSERT INTO decisions (ticket_id, agent, decision_type, decision, reason, created_at)
                   VALUES (?,?,?,?,?,?)""",
                (result["ticket_id"], d["agent"], d["decision_type"], d["decision"], d["reason"], d["timestamp"]),
            )


def load_ticket(ticket_id: str) -> dict | None:
    with connect() as c:
        row = c.execute("SELECT result_json FROM tickets WHERE ticket_id=?", (ticket_id,)).fetchone()
    return json.loads(row["result_json"]) if row else None


def list_tickets(limit: int = 100) -> list[dict]:
    with connect() as c:
        rows = c.execute(
            """SELECT ticket_id, created_at, original_input, category, priority, assigned_department,
               status, auditor_decision, revision_count, execution_mode, total_time_ms
               FROM tickets ORDER BY created_at DESC, rowid DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def stats() -> dict:
    with connect() as c:
        total = c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        verified = c.execute("SELECT COUNT(*) FROM tickets WHERE status='solution_verified'").fetchone()[0]
        pending = c.execute(
            "SELECT COUNT(*) FROM tickets WHERE status IN ('awaiting_human_approval','escalated_to_human')"
        ).fetchone()[0]
        avg = c.execute("SELECT AVG(total_time_ms) FROM tickets WHERE total_time_ms IS NOT NULL").fetchone()[0]
        rejections = c.execute(
            "SELECT COUNT(*) FROM decisions WHERE decision_type='audit' AND decision='REJECT'"
        ).fetchone()[0]
    return {
        "total_tickets": total,
        "verified_solutions": verified,
        "pending_human_approval": pending,
        "avg_processing_time_ms": int(avg) if avg is not None else None,
        "total_auditor_rejections": rejections,
    }
