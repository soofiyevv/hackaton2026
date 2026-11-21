"""Learning from history:
- lessons(): the auditor's past rejections, aggregated, fed back into the Resolution Agent's prompt
- analytics(): what the university can see across all cases"""
from __future__ import annotations

import json
from collections import Counter, defaultdict

from . import db

# what each programmatic check teaches the planner
CHECK_LESSONS = {
    "C1": "Only cite knowledge base ids that were actually provided.",
    "C2": "Back every step with a knowledge base entry; if none applies, say the case needs a human.",
    "C3": "Give at least two concrete, ordered actions.",
    "C4": "For urgent or time-sensitive cases, fill time_critical_actions with what must happen first.",
    "C5": "When an exam is mentioned, tell the student to inform the examiner/instructor before it starts.",
    "C6": "When there is a safety risk, start with safety guidance (stop using, keep others away, 112).",
    "C7": "Never write emails, phone numbers or URLs that are not in the knowledge base.",
    "C8": "contact_department must be exactly one of the routed department names.",
}


def _results(limit: int = 300) -> list[dict]:
    with db.connect() as c:
        rows = c.execute("SELECT result_json FROM tickets ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
    return [json.loads(r["result_json"]) for r in rows]


def lessons(category: str | None = None, k: int = 3) -> dict:
    """Most frequent reasons the auditor rejected plans (same category first, then global)."""
    by_cat: Counter = Counter()
    overall: Counter = Counter()
    llm_issues: list[str] = []
    student: list[str] = []
    for res in _results():
        cat = res.get("category")
        fb = res.get("student_feedback") or {}
        if (category is None or cat == category) and fb.get("rating") == "down" and fb.get("comment"):
            student.append(fb["comment"])
        for att in (res.get("agent_results") or {}).get("resolution_attempts") or []:
            audit = att.get("audit") or {}
            if audit.get("verdict") != "REJECT":
                continue
            for chk in audit.get("programmatic_checks") or []:
                if not chk.get("passed"):
                    overall[chk["id"]] += 1
                    if cat == category:
                        by_cat[chk["id"]] += 1
            if cat == category and audit.get("llm_verdict") == "REJECT":
                llm_issues += [i for i in audit.get("issues") or []][:1]
    ranked = [cid for cid, _ in by_cat.most_common()] + [cid for cid, _ in overall.most_common() if cid not in by_cat]
    items = [{"check": cid, "lesson": CHECK_LESSONS[cid], "seen_in_category": by_cat.get(cid, 0),
              "seen_overall": overall.get(cid, 0)} for cid in ranked[:k] if cid in CHECK_LESSONS]
    return {"category": category, "lessons": items, "recent_llm_issues": llm_issues[:2],
            "student_feedback": student[:3]}


def lessons_prompt(category: str) -> str:
    data = lessons(category)
    if not data["lessons"] and not data["recent_llm_issues"] and not data["student_feedback"]:
        return ""
    lines = [f"- {x['lesson']} (auditor rejected this {x['seen_overall']}x before)" for x in data["lessons"]]
    lines += [f"- Earlier auditor remark in this category: {i[:160]}" for i in data["recent_llm_issues"]]
    lines += [f"- A student said an earlier plan in this category was not helpful: {c[:160]}"
              for c in data["student_feedback"]]
    return "\n\nLESSONS FROM PAST AUDITOR REJECTIONS (avoid repeating them):\n" + "\n".join(lines)


def analytics() -> dict:
    """Aggregates for a university staff dashboard. All numbers are counted from stored cases."""
    res_all = _results(1000)
    n = len(res_all)
    by_cat, by_dept, by_status, by_loc, checks = Counter(), Counter(), Counter(), Counter(), Counter()
    revisions, times, first_try = [], [], 0
    up = down = 0
    dept_esc = defaultdict(lambda: [0, 0])
    for r in res_all:
        by_cat[r.get("category") or "unknown"] += 1
        by_status[r.get("status") or "unknown"] += 1
        if r.get("assigned_department"):
            by_dept[r["assigned_department"]] += 1
            d = dept_esc[r["assigned_department"]]
            d[0] += 1
            d[1] += r.get("status") in ("awaiting_human_approval", "escalated_to_human",
                                        "approved_by_staff", "rejected_by_staff")
        if r.get("location"):
            by_loc[r["location"].strip().lower()] += 1
        fbk = (r.get("student_feedback") or {}).get("rating")
        up += fbk == "up"
        down += fbk == "down"
        m = r.get("autonomy_metrics") or {}
        times.append(m.get("total_execution_time_ms") or 0)
        revisions.append(r.get("revision_count") or 0)
        first_try += (m.get("auditor_rejections") == 0 and r.get("status") not in ("failed", "out_of_scope_request"))
        for att in (r.get("agent_results") or {}).get("resolution_attempts") or []:
            for chk in (att.get("audit") or {}).get("programmatic_checks") or []:
                if not chk.get("passed"):
                    checks[f"{chk['id']} {chk['name']}"] += 1
    return {
        "total_cases": n,
        "by_category": dict(by_cat.most_common()),
        "by_department": dict(by_dept.most_common()),
        "by_status": dict(by_status.most_common()),
        "top_locations": dict(by_loc.most_common(8)),
        "auditor_failed_checks": dict(checks.most_common()),
        "accepted_first_attempt_rate": round(first_try / n, 3) if n else None,
        "avg_revisions": round(sum(revisions) / n, 2) if n else None,
        "avg_time_ms": int(sum(times) / n) if n else None,
        "student_feedback": {"helpful": up, "not_helpful": down},
        "human_decision_rate_by_department": {k: round(v[1] / v[0], 2) for k, v in dept_esc.items() if v[0]},
    }
