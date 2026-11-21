"""UniResolve AI backend - public interface for the frontend.

    from backend import process_ticket, get_ticket, get_ticket_history

See BACKEND_CONTRACT.md for the exact data structures.
"""
from __future__ import annotations

from typing import Callable

from . import config, db, incidents, insights, llm, orchestrator

__all__ = ["process_ticket", "get_ticket", "get_ticket_history", "get_dashboard_stats", "get_system_status",
           "review_ticket", "get_pending_reviews", "check_models", "replay_ticket", "get_incidents", "close_incident",
           "get_lessons_learned", "get_analytics", "get_recorded_runs"]


def process_ticket(user_input: str, category: str | None = None, urgency: str | None = None,
                   mode: str | None = None, on_event: Callable[[dict], None] | None = None) -> dict:
    """Run the full multi-agent pipeline on a student problem and persist the case.

    category / urgency: optional hints from the form (None = let the agents decide).
    mode: "auto" (default), "live" or "offline". None = UNIRESOLVE_MODE env var.
    on_event: optional callback called synchronously with every trace event as it happens
              (use it to animate agent cards live in Streamlit).
    Never raises for pipeline errors: check result["status"] == "failed" and result["error"].
    """
    return orchestrator.process(user_input, category_hint=category or None,
                                urgency_hint=urgency or None, mode=mode, on_event=on_event)


def get_ticket(ticket_id: str) -> dict | None:
    """Full stored result (same shape as process_ticket) or None if not found."""
    return db.load_ticket(ticket_id)


def get_ticket_history(limit: int = 100) -> list[dict]:
    """Newest-first list of ticket summaries (see BACKEND_CONTRACT.md)."""
    return db.list_tickets(limit)


def get_dashboard_stats() -> dict:
    """Aggregate numbers for the dashboard, computed from the database."""
    return db.stats()


def get_system_status() -> dict:
    """Configured mode and provider readiness. Does not call any API."""
    return {"mode": config.get_mode(), "providers": llm.provider_status(),
            "llm_chain": config.LLM_CHAIN, "llm_chain_fast": config.LLM_CHAIN_FAST,
            "max_revisions": config.MAX_REVISIONS}


def review_ticket(ticket_id: str, decision: str, reviewer: str = "staff", note: str = "") -> dict:
    """Staff decision for a case in 'awaiting_human_approval' or 'escalated_to_human'.
    decision: "approve" | "reject". Returns the updated ticket (status approved_by_staff / rejected_by_staff).
    Raises KeyError (unknown ticket) or ValueError (bad decision / ticket does not need review)."""
    return orchestrator.review(ticket_id, decision, reviewer, note)


def get_pending_reviews() -> list[dict]:
    """Ticket summaries waiting for a human decision (newest first)."""
    return [t for t in db.list_tickets(500) if t["status"] in orchestrator.REVIEWABLE]


def check_models() -> list[dict]:
    """Real tiny API call to every configured model: [{provider, model, status, latency_ms, detail, cooling_down}].
    status: ok | rate_limited_or_overloaded | unavailable | error | unexpected_output. Takes a few seconds."""
    return llm.healthcheck()


def replay_ticket(ticket_id: str, on_event: Callable[[dict], None] | None = None, speed: float = 1.0) -> dict:
    """Replay a recorded run (same events, original pacing, no LLM calls) for offline demos.
    Result has replay=True and recorded_at -> the UI must show a 'RECORDED RUN' label."""
    return orchestrator.replay(ticket_id, on_event, speed)


def get_incidents(open_only: bool = True) -> list[dict]:
    """Campus incidents detected from several similar reports:
    [{incident_id, title, category, location, department, status, report_count, ticket_ids, created_at, updated_at}]"""
    return incidents.list_incidents(open_only)


def close_incident(incident_id: str) -> None:
    """Staff marks an incident as resolved (status -> closed)."""
    incidents.close(incident_id)


def get_lessons_learned(category: str | None = None) -> dict:
    """What the system learned from past auditor rejections (fed into new plans automatically):
    {category, lessons: [{check, lesson, seen_in_category, seen_overall}], recent_llm_issues: [str]}"""
    return insights.lessons(category)


def get_analytics() -> dict:
    """University-level aggregates over all stored cases (see BACKEND_CONTRACT.md)."""
    return insights.analytics()



def get_recorded_runs() -> list[dict]:
    """Recorded live runs shipped in the repo (demo/recorded_runs/), usable with replay_ticket() on any machine."""
    return orchestrator.list_recorded()
