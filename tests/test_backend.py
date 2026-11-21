"""Offline tests for the backend. Run: python -m pytest -q"""
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture(autouse=True)
def offline_db(tmp_path, monkeypatch):
    from backend import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    monkeypatch.setenv("UNIRESOLVE_MODE", "offline")
    yield


REQUIRED = ["ticket_id", "original_input", "category", "priority", "assigned_department", "agent_results",
            "execution_trace", "auditor_decision", "revision_count", "final_solution", "status",
            "autonomy_metrics", "execution_mode"]


def test_wifi_exam_rejected_then_revised_then_accepted():
    from backend import process_ticket
    r = process_ticket("University Wi-Fi is not working and my exam starts in one hour!")
    for key in REQUIRED:
        assert key in r
    assert r["category"] == "it_network"
    assert r["execution_mode"] == "offline_simulation"
    attempts = r["agent_results"]["resolution_attempts"]
    assert attempts[0]["audit"]["verdict"] == "REJECT"
    assert attempts[-1]["audit"]["verdict"] == "ACCEPT"
    assert r["revision_count"] == 1
    assert r["status"] == "solution_verified"
    assert r["autonomy_metrics"]["auditor_rejections"] == 1


def test_broken_chair_accepted_first_time():
    from backend import process_ticket
    r = process_ticket("There is a broken chair in classroom 204.")
    assert r["assigned_department"] == "Facilities Management"
    assert r["revision_count"] == 0
    assert r["status"] == "solution_verified"


def test_reschedule_requires_human_approval():
    from backend import process_ticket
    r = process_ticket("I was sick and need to reschedule my calculus exam to a new date.")
    assert r["status"] == "awaiting_human_approval"
    assert r["autonomy_metrics"]["human_escalations"] == 1


def test_unknown_problem_escalates_after_max_revisions():
    from backend import process_ticket, config
    r = process_ticket("My private landlord in the city refuses to return my rental deposit.")
    assert r["status"] == "escalated_to_human"
    assert r["revision_count"] == config.MAX_REVISIONS
    assert r["final_solution"]["verified_by_auditor"] is False


def test_persistence_and_history():
    from backend import process_ticket, get_ticket, get_ticket_history, get_dashboard_stats
    r = process_ticket("I cannot access my university portal.")
    assert get_ticket(r["ticket_id"])["ticket_id"] == r["ticket_id"]
    assert get_ticket_history()[0]["ticket_id"] == r["ticket_id"]
    assert get_dashboard_stats()["total_tickets"] == 1
    assert get_ticket("nope") is None


def test_events_streamed():
    from backend import process_ticket
    events = []
    process_ticket("There is a broken chair in classroom 204.", on_event=events.append)
    assert events[0]["status"] == "started" and events[0]["agent"] == "Triage Agent"
    assert any(e["status"] == "decision" for e in events)


def test_auditor_catches_invented_contacts_and_bad_refs():
    from backend import agents
    tri = {"time_sensitive": False, "urgency": "low", "safety_risk": False}
    rout = {"department": "Facilities Management", "secondary_departments": []}
    sol = {"diagnosis": "x", "steps": [{"action": "Email fix@uni-fake.edu now", "kb_ref": "KB-FAKE-9"},
                                       {"action": "Wait", "kb_ref": "KB-FAC-01"}],
           "time_critical_actions": [], "kb_refs": ["KB-FAC-01"], "contact_department": "Facilities Management",
           "_available_kb_ids": ["KB-FAC-01"]}
    failed = {c["id"] for c in agents.programmatic_checks("broken chair", tri, rout, sol) if not c["passed"]}
    assert "C1" in failed and "C7" in failed


def test_empty_input_rejected():
    from backend import process_ticket
    with pytest.raises(ValueError):
        process_ticket("   ")


def test_live_mode_without_keys_fails_cleanly(monkeypatch):
    from backend import process_ticket
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = process_ticket("broken chair in room 12", mode="live")
    assert r["status"] == "failed" and "providers failed" in r["error"]


def test_auto_mode_falls_back_and_is_labelled(monkeypatch):
    from backend import process_ticket
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = process_ticket("broken chair in room 12", mode="auto")
    assert r["execution_mode"] == "offline_simulation"
    assert all(e.get("simulated") for e in r["execution_trace"] if e["status"] == "completed")


def test_scholarship_goes_to_finance_and_needs_staff():
    from backend import process_ticket
    r = process_ticket("My scholarship payment did not arrive this month.")
    assert r["assigned_department"] == "Student Finance Office"
    assert r["status"] == "awaiting_human_approval"


@pytest.mark.parametrize("text,dept", [
    ("I lost my wallet in the library building", "Building Reception"),
    ("The printer on the 2nd floor has a paper jam", "IT Service Desk"),
    ("I feel very stressed and anxious about my exams", "Student Counselling Service"),
    ("The elevator is broken and I use a wheelchair", "Disability & Accessibility Support"),
])
def test_new_kb_areas_route(text, dept):
    from backend import process_ticket
    r = process_ticket(text)
    assert r["assigned_department"] == dept, r["agent_results"]["routing"]
    assert r["status"] != "failed"
