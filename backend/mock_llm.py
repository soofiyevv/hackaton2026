"""Deterministic OFFLINE SIMULATION of the LLM calls.

Used when UNIRESOLVE_MODE=offline, or as a fallback in auto mode when every
provider fails. Every result produced here is flagged simulated=True.

Only the *LLM text generation* is simulated. The orchestrator, the auditor's
programmatic checks, the retry/escalation logic and persistence are the real
code paths. The simulated first draft for exam-related Wi-Fi problems is
intentionally narrow (IT steps only), so the real auditor checks can be seen
rejecting it offline.
"""
from __future__ import annotations

import re

from . import kb

RULES = [
    ("safety", ["fire", "smoke", "injur", "electric shock", "gas leak", "smell gas", "danger", "unsafe"]),
    ("conduct", ["harass", "bully", "discriminat", "racis", "threaten"]),
    ("wellbeing", ["stress", "anxiety", "anxious", "depress", "lonely", "overwhelmed", "burnout", "panic", "homesick"]),
    ("finance", ["scholarship", "stipend", "tuition", "refund", "invoice", "payment", "fee"]),
    ("accessibility", ["wheelchair", "disabilit", "accessib", "elevator", "lift", "ramp", "dyslexia"]),
    ("it_network", ["wifi", "wi-fi", "eduroam", "internet", "network"]),
    ("it_accounts", ["portal", "neptun", "password", "login", "log in", "account", "moodle", "canvas"]),
    ("classroom_equipment", ["projector", "microphone", "beamer", "hdmi", "speaker"]),
    ("facilities", ["chair", "desk", "table", "broken", "door", "window", "heating", "leak", "light"]),
    ("exams_academic", ["reschedule", "postpone", "retake", "extension", "exam", "deadline", "grade"]),
    ("administration", ["certificate", "transcript", "enrol", "registration", "student status"]),
    ("health", ["fever", "doctor", "sick", "ill ", "medical"]),
    ("it_accounts", ["printer", "print", "scanner"]),
    ("campus_services", ["canteen", "cafeteria", "food", "lost", "wallet", "gym", "sport"]),
    ("transport", ["bus", "tram", "parking", "bike", "bicycle"]),
    ("housing", ["dorm", "dormitory", "roommate", "laundry"]),
    ("international", ["visa", "residence permit", "certificate"]),
    ("library", ["library", "book", "loan"]),
]


def _has(text: str, words) -> bool:
    low = text.lower()
    return any(w in low for w in words)


def mentions_exam(text: str) -> bool:
    return bool(re.search(r"\b(exam|exams|midterm|test|quiz)\b", text.lower()))


def triage(user_input: str, category_hint: str | None, urgency_hint: str | None) -> dict:
    category = category_hint or next((c for c, words in RULES if _has(user_input, words)), "other")
    exam = mentions_exam(user_input)
    safety = category == "safety"
    if safety:
        urgency = "critical"
    elif exam or _has(user_input, ["urgent", "asap", "right now", "today"]):
        urgency = "high"
    elif category in ("it_network", "it_accounts", "classroom_equipment"):
        urgency = "medium"
    else:
        urgency = "low"
    urgency = urgency_hint or urgency
    facts = []
    room = re.search(r"\b(room|classroom)\s*([A-Za-z]?\d{1,4})", user_input, re.I)
    if room:
        facts.append(f"location: {room.group(0)}")
    if exam:
        facts.append("an exam is affected or imminent")
    return {
        "summary": user_input.strip()[:160],
        "category": category,
        "urgency": urgency,
        "urgency_reason": "Exam or time pressure mentioned" if exam else f"Typical urgency for {category}",
        "time_sensitive": exam or urgency in ("high", "critical"),
        "safety_risk": safety,
        "key_facts": facts,
        "exam_involved": exam,
        "is_support_request": not re.search(
            r"\b(poem|joke|capital of|recipe|song|story|ignore (all |previous )?instructions)\b", user_input, re.I),
        "language": "English",
    }


def routing(triage_out: dict, candidates: list[dict]) -> dict:
    primary = candidates[0] if candidates else None
    secondary = [c["department"] for c in candidates[1:] if primary and c["department"] != primary["department"]]
    needs_human = bool(primary and primary.get("requires_human_decision")) and (
        primary["category"] != "exams_academic"
        or _has(triage_out["summary"], ["reschedule", "postpone", "extension", "exception", "retake", "new date"])
    )
    return {
        "workflow": primary["category"] if primary else "general_inquiry",
        "department": primary["department"] if primary else "Student Services (general)",
        "secondary_departments": secondary,
        "kb_ids": [c["id"] for c in candidates],
        "requires_human_approval": needs_human,
        "reason": (f"Category '{triage_out['category']}' maps to {primary['department']} ({primary['id']})."
                   if primary else "No matching knowledge base entry; routed to general student services."),
    }


def resolution(triage_out: dict, routing_out: dict, kb_entries: list[dict], feedback: list[str]) -> dict:
    revising = bool(feedback)
    fb = " ".join(feedback).lower()
    entries = kb_entries
    if not revising and triage_out["category"] == "it_network":
        # deliberately narrow first draft: only the IT entry
        entries = [e for e in kb_entries if e["category"] == "it_network"] or kb_entries
    if revising and "exam" in fb and not any(e["id"] == "KB-EXAM-01" for e in entries):
        entries = entries + [kb.get("KB-EXAM-01")]

    steps = []
    for e in entries:
        for proc in e["procedures"][:3]:
            steps.append({"action": proc, "owner": "student", "kb_ref": e["id"]})
    time_critical = []
    if revising and triage_out["time_sensitive"]:
        time_critical = [s["action"] for s in steps if s["kb_ref"] in ("KB-EXAM-01", "KB-SAFE-01")][:2] or \
                        [steps[0]["action"]] if steps else []
    if not entries:
        steps = [{"action": "Describe the problem to general student services.", "owner": "student", "kb_ref": None}]
    return {
        "diagnosis": f"Likely {triage_out['category'].replace('_', ' ')} issue: {triage_out['summary'][:100]}",
        "steps": steps,
        "contact_department": routing_out["department"],
        "time_critical_actions": time_critical,
        "kb_refs": [e["id"] for e in entries],
        "assumptions": [] if entries else ["No knowledge base entry covers this request."],
        "confidence": 0.8 if entries else 0.3,
    }


def audit(solution: dict) -> dict:
    grounded = bool(solution.get("kb_refs"))
    return {
        "verdict": "ACCEPT" if grounded else "REJECT",
        "scores": {"accuracy": 4 if grounded else 2, "relevance": 4, "completeness": 4 if grounded else 2,
                   "groundedness": 5 if grounded else 1},
        "issues": [] if grounded else ["Solution is not supported by any knowledge base entry."],
        "feedback": "" if grounded else "Ground every step in a knowledge base entry or escalate.",
    }


def communication(user_input: str, tri: dict, rout: dict, sol: dict, status: str) -> dict:
    dept = sol.get("contact_department") or rout["department"]
    facts = "; ".join(tri.get("key_facts") or []) or "see description"
    return {
        "to_department": dept,
        "channel": "",
        "subject": f"{tri['category'].replace('_', ' ').title()} issue - {tri['urgency']} priority",
        "body": (f"Dear {dept},\n\nI would like to report the following problem: {user_input.strip()}\n"
                 f"Details: {facts}.\n"
                 + ("This is time-sensitive. " if tri.get("time_sensitive") else "")
                 + ("I am requesting a staff decision on this matter. " if status == "awaiting_human_approval" else "")
                 + "\n\nKind regards,\n[your name]\n[student ID]"),
    }
