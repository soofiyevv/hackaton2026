"""UniResolve AI backend - public interface for the frontend.

    from backend import process_ticket, get_ticket, get_ticket_history

See BACKEND_CONTRACT.md for the exact data structures.
"""
from __future__ import annotations

from typing import Callable

from . import config, db, llm, orchestrator

__all__ = ["process_ticket", "get_ticket", "get_ticket_history", "get_dashboard_stats", "get_system_status"]


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
