"""Incident Detection: spots several students reporting the same problem in the same place
within a short time window, and groups them into one campus incident."""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from . import db

WINDOW_MIN = int(os.getenv("INCIDENT_WINDOW_MIN", "60"))
THRESHOLD = int(os.getenv("INCIDENT_THRESHOLD", "3"))  # reports (including the new one) that make an incident

_STOP = {"the", "a", "an", "in", "on", "at", "of", "room", "classroom", "building", "floor", "hall", "near",
         "my", "our", "university", "campus", "main", "and", "level", "corridor", "area", "next", "to"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    created_at TEXT, updated_at TEXT,
    category TEXT, location TEXT, department TEXT, title TEXT,
    status TEXT, ticket_ids TEXT
);
"""


def location_tokens(location: str) -> set[str]:
    toks = set(re.findall(r"[a-z0-9]+", (location or "").lower())) - _STOP
    return {t for t in toks if len(t) > 1 or t.isdigit()}


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def recent_similar(category: str, location: str, exclude_ticket: str | None = None) -> list[dict]:
    """Recent tickets (window) with the same category and an overlapping location."""
    mine = location_tokens(location)
    if not mine:
        return []
    since = datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MIN)
    out = []
    with db.connect() as c:
        rows = c.execute("SELECT ticket_id, created_at, result_json FROM tickets WHERE category=? "
                         "ORDER BY created_at DESC LIMIT 200", (category,)).fetchall()
    for r in rows:
        if r["ticket_id"] == exclude_ticket or _parse(r["created_at"]) < since:
            continue
        res = json.loads(r["result_json"])
        loc = (res.get("agent_results", {}).get("triage") or {}).get("location", "")
        if mine & location_tokens(loc):
            out.append({"ticket_id": r["ticket_id"], "created_at": r["created_at"], "location": loc,
                        "summary": (res.get("agent_results", {}).get("triage") or {}).get("summary", ""),
                        "incident_id": (res.get("incident") or {}).get("incident_id")})
    return out


def _ensure(c) -> None:
    c.executescript(SCHEMA)


def open_incident_for(category: str, location: str) -> dict | None:
    mine = location_tokens(location)
    since = (datetime.now(timezone.utc) - timedelta(minutes=WINDOW_MIN * 3)).isoformat(timespec="seconds")
    with db.connect() as c:
        _ensure(c)
        rows = c.execute("SELECT * FROM incidents WHERE status='open' AND category=? AND updated_at>=?",
                         (category, since)).fetchall()
    for r in rows:
        if mine & location_tokens(r["location"]):
            d = dict(r)
            d["ticket_ids"] = json.loads(d["ticket_ids"])
            return d
    return None


def upsert(category: str, location: str, department: str, title: str, ticket_ids: list[str]) -> dict:
    now = db.now_iso()
    existing = open_incident_for(category, location)
    with db.connect() as c:
        _ensure(c)
        if existing:
            ids = list(dict.fromkeys(existing["ticket_ids"] + ticket_ids))
            c.execute("UPDATE incidents SET ticket_ids=?, updated_at=? WHERE incident_id=?",
                      (json.dumps(ids), now, existing["incident_id"]))
            return {**existing, "ticket_ids": ids, "updated_at": now, "is_new": False}
        iid = f"INC-{datetime.now().strftime('%m%d')}-{uuid.uuid4().hex[:4].upper()}"
        ids = list(dict.fromkeys(ticket_ids))
        c.execute("INSERT INTO incidents VALUES (?,?,?,?,?,?,?,?,?)",
                  (iid, now, now, category, location, department, title, "open", json.dumps(ids)))
        return {"incident_id": iid, "created_at": now, "updated_at": now, "category": category,
                "location": location, "department": department, "title": title, "status": "open",
                "ticket_ids": ids, "is_new": True}


def list_incidents(open_only: bool = True) -> list[dict]:
    with db.connect() as c:
        _ensure(c)
        q = "SELECT * FROM incidents" + (" WHERE status='open'" if open_only else "") + " ORDER BY updated_at DESC"
        rows = c.execute(q).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["ticket_ids"] = json.loads(d["ticket_ids"])
        d["report_count"] = len(d["ticket_ids"])
        out.append(d)
    return out


def close(incident_id: str) -> None:
    with db.connect() as c:
        _ensure(c)
        c.execute("UPDATE incidents SET status='closed', updated_at=? WHERE incident_id=?", (db.now_iso(), incident_id))
