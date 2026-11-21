"""Orchestrator: runs the agents, owns the state, the audit/revise loop, retries,
escalation, execution trace and autonomy metrics."""
from __future__ import annotations

import time
import traceback
import uuid
from datetime import datetime
from typing import Callable

from . import agents, config, db, guard, incidents, kb
from .llm import LLMClient, LLMResult

EventCallback = Callable[[dict], None]


class _StopPipeline(Exception):
    """Internal: planned early exit (e.g. out-of-scope input)."""


class Run:
    def __init__(self, ticket_id: str, on_event: EventCallback | None):
        self.ticket_id = ticket_id
        self.on_event = on_event
        self.trace: list[dict] = []
        self.decisions: list[dict] = []
        self.step = 0
        self.agents_executed = 0
        self.providers: set[str] = set()
        self.simulated_calls = 0
        self.live_calls = 0

    def _emit(self, event: dict) -> None:
        self.trace.append(event)
        if self.on_event:
            try:
                self.on_event(event)
            except Exception:  # a UI callback must never break the pipeline
                pass

    def agent(self, name: str, action: str, fn: Callable[[], tuple[dict, LLMResult]], summarize):
        self.step += 1
        step = self.step
        self._emit({"step": step, "agent": name, "action": action, "status": "started",
                    "timestamp": db.now_iso()})
        t0 = time.perf_counter()
        try:
            out, res = fn()
        except Exception as exc:
            self._emit({"step": step, "agent": name, "action": action, "status": "error",
                        "timestamp": db.now_iso(), "duration_ms": int((time.perf_counter() - t0) * 1000),
                        "summary": f"{type(exc).__name__}: {exc}", "output": None})
            raise
        self.agents_executed += 1
        self.providers.add(res.provider)
        if res.simulated:
            self.simulated_calls += 1
        else:
            self.live_calls += 1
        self._emit({
            "step": step, "agent": name, "action": action, "status": "completed",
            "timestamp": db.now_iso(), "duration_ms": int((time.perf_counter() - t0) * 1000),
            "provider": res.provider, "model": res.model, "simulated": res.simulated,
            "fallback_errors": res.fallback_chain, "summary": summarize(out),
            "output": {k: v for k, v in out.items() if not k.startswith("_")},
        })
        return out

    def decide(self, agent: str, decision_type: str, decision: str, reason: str) -> None:
        d = {"agent": agent, "decision_type": decision_type, "decision": decision, "reason": reason,
             "timestamp": db.now_iso()}
        self.decisions.append(d)
        self._emit({"step": self.step, "agent": agent, "action": f"decision:{decision_type}",
                    "status": "decision", "timestamp": d["timestamp"], "decision": decision,
                    "summary": f"{decision} - {reason}"})


def _new_ticket_id() -> str:
    return f"UR-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:6].upper()}"


def process(user_input: str, category_hint: str | None = None, urgency_hint: str | None = None,
            mode: str | None = None, on_event: EventCallback | None = None) -> dict:
    if not user_input or not user_input.strip():
        raise ValueError("user_input must not be empty")
    started = time.perf_counter()
    check = guard.inspect(user_input)
    user_input = check["text"]
    mode = config.get_mode(mode)
    llm = LLMClient(mode)
    run = Run(_new_ticket_id(), on_event)
    result: dict = {
        "ticket_id": run.ticket_id, "created_at": db.now_iso(), "original_input": user_input.strip(),
        "requested_mode": mode, "category": None, "priority": None, "assigned_department": None,
        "workflow": None, "requires_human_approval": False, "agent_results": {},
        "execution_trace": run.trace, "decisions": run.decisions, "auditor_decision": None,
        "revision_count": 0, "final_solution": None, "message_draft": None, "human_review": None,
        "status": "processing", "error": None,
        "kb_notice": kb.notice(),
        "input_guard": {k: v for k, v in check.items() if k != "text"},
        "language": None,
        "location": None,
        "incident": None,
    }
    rejections = revisions = escalations = 0
    pending_incident = None
    try:
        if check["injection_suspected"]:
            run.decide("Orchestrator", "security", "INJECTION_FLAGGED",
                       f"Input contains instruction-like text {check['patterns']}; it is treated strictly as data")
        if check["truncated"]:
            run.decide("Orchestrator", "input", "TRUNCATED", f"Input cut to {guard.MAX_INPUT_CHARS} characters")
        tri = run.agent("Triage Agent", "Classify problem, category and urgency",
                        lambda: agents.triage(llm, user_input, category_hint, urgency_hint),
                        lambda o: f"{o['category']} / urgency {o['urgency']}")
        run.decide("Triage Agent", "classification", f"{tri['category']}|{tri['urgency']}",
                   tri["urgency_reason"] or "classified from report")
        result.update(category=tri["category"], priority=tri["urgency"], language=tri["language"],
                      location=tri["location"] or None)
        result["agent_results"]["triage"] = tri

        if not tri["is_support_request"]:
            run.decide("Orchestrator", "scope", "OUT_OF_SCOPE",
                       "Not a university support request; pipeline stopped early, no plan generated")
            result["status"] = "out_of_scope_request"
            result["final_solution"] = {
                "diagnosis": "This does not look like a university support problem.", "steps": [],
                "contact_department": None, "time_critical_actions": [], "kb_refs": [], "assumptions": [],
                "confidence": 0.0, "verified_by_auditor": False,
                "note": "UniResolve only handles student support problems (IT, facilities, exams, administration, "
                        "wellbeing...). Please describe a problem you need help with.",
            }
            raise _StopPipeline()

        # Incident Detection: only runs when there are recent similar reports (no LLM call otherwise)
        similar = incidents.recent_similar(tri["category"], tri["location"], exclude_ticket=run.ticket_id)
        if tri["location"] and len(similar) + 1 >= incidents.THRESHOLD:
            inc_check = run.agent("Incident Agent", f"Compare with {len(similar)} recent similar report(s)",
                                  lambda: agents.incident_check(llm, user_input, tri, similar),
                                  lambda o: ("SAME INCIDENT: " + o["title"]) if o["same_incident"]
                                  else "Not the same incident")
            result["agent_results"]["incident_check"] = inc_check
            if inc_check["same_incident"]:
                pending_incident = (inc_check, similar)
                old = tri["urgency"]
                if old in ("low", "medium"):
                    tri["urgency"] = "high"
                    result["priority"] = "high"
                tri["incident_note"] = (f"{len(inc_check['matching_ticket_ids']) + 1} students reported this at "
                                        f"{tri['location']} within {incidents.WINDOW_MIN} min: probable shared "
                                        "outage, not an individual problem. Say so in the plan.")
                run.decide("Incident Agent", "incident", "INCIDENT_DETECTED",
                           f"{inc_check['reason']} Urgency {old} -> {tri['urgency']}")
            else:
                run.decide("Incident Agent", "incident", "NO_INCIDENT", inc_check["reason"] or "reports differ")

        rout = run.agent("Routing Agent", "Select workflow and owning department",
                         lambda: agents.routing(llm, user_input, tri),
                         lambda o: f"{o['department']} ({', '.join(o['kb_ids']) or 'no KB match'})")
        run.decide("Routing Agent", "routing", rout["department"], rout["reason"] or "routed by KB match")
        if rout["requires_human_approval"]:
            run.decide("Routing Agent", "human_approval_required", "YES",
                       "Outcome requires a staff decision; system will not act autonomously on it")
        result.update(assigned_department=rout["department"], workflow=rout["workflow"],
                      requires_human_approval=rout["requires_human_approval"])
        result["agent_results"]["routing"] = rout

        attempts = []
        feedback: list[str] = []
        solution = audit = None
        last_signature = None
        for attempt in range(config.MAX_REVISIONS + 1):
            label = "Draft resolution plan" if attempt == 0 else f"Revise plan (revision {attempt})"
            previous = {k: v for k, v in solution.items() if not k.startswith("_")} if solution else None
            solution = run.agent("Resolution Agent", label,
                                 lambda: agents.resolution(llm, user_input, tri, rout, feedback, previous),
                                 lambda o: f"{len(o['steps'])} steps, refs {o['kb_refs']}")
            audit = run.agent("Auditor Agent", f"Verify plan (attempt {attempt + 1})",
                              lambda: agents.auditor(llm, user_input, tri, rout, solution),
                              lambda o: f"{o['verdict']} - {o['checks_passed']}/{o['checks_total']} checks passed")
            attempts.append({"attempt": attempt + 1,
                             "solution": {k: v for k, v in solution.items() if not k.startswith("_")},
                             "audit": audit})
            run.decide("Auditor Agent", "audit", audit["verdict"],
                       "; ".join(audit["feedback"])[:500] or "All checks passed")
            if audit["verdict"] == "ACCEPT":
                break
            rejections += 1
            signature = (tuple(sorted(solution["kb_refs"])),
                         tuple(sorted(c["id"] for c in audit["programmatic_checks"] if not c["passed"])),
                         audit["llm_verdict"])
            stagnated = attempt > 0 and signature == last_signature
            last_signature = signature
            if stagnated:
                escalations += 1
                run.decide("Orchestrator", "escalation", "ESCALATE_TO_HUMAN",
                           "No progress: the revised plan uses the same sources and fails the same checks as the "
                           "previous one, so further automatic revisions would not help")
                break
            if attempt < config.MAX_REVISIONS:
                revisions += 1
                feedback = audit["feedback"]
                run.decide("Orchestrator", "retry", "REVISE",
                           f"Auditor rejected; sending {len(feedback)} feedback item(s) back "
                           f"(revision {revisions}/{config.MAX_REVISIONS})")
            else:
                escalations += 1
                run.decide("Orchestrator", "escalation", "ESCALATE_TO_HUMAN",
                           f"Still rejected after {config.MAX_REVISIONS} revisions; a staff member must review")

        result["agent_results"]["resolution_attempts"] = attempts
        result["agent_results"]["auditor"] = audit
        result["auditor_decision"] = audit["verdict"]
        result["revision_count"] = revisions
        final = {k: v for k, v in solution.items() if not k.startswith("_")}
        final["verified_by_auditor"] = audit["verdict"] == "ACCEPT"

        if audit["verdict"] == "ACCEPT" and rout["requires_human_approval"]:
            escalations += 1
            result["status"] = "awaiting_human_approval"
            final["note"] = ("Plan verified by the auditor. The requested outcome needs a staff decision; "
                             "the case is queued for human approval.")
            run.decide("Orchestrator", "escalation", "AWAIT_HUMAN_APPROVAL", "Policy: staff decision required")
        elif audit["verdict"] == "ACCEPT":
            result["status"] = "solution_verified"
            final["note"] = ("Verified action plan. The student and the department still need to carry it out; "
                             "the system does not fix the problem physically.")
            run.decide("Orchestrator", "finalize", "FINALIZE", "Auditor accepted the plan")
        else:
            result["status"] = "escalated_to_human"
            final["note"] = "UNVERIFIED draft: the auditor rejected every attempt. Escalated to a human."
        result["final_solution"] = final

        if pending_incident:
            inc_check, similar = pending_incident
            inc = incidents.upsert(tri["category"], tri["location"], rout["department"], inc_check["title"],
                                   inc_check["matching_ticket_ids"] + [run.ticket_id])
            result["incident"] = {"incident_id": inc["incident_id"], "title": inc["title"],
                                  "report_count": len(inc["ticket_ids"]), "location": inc["location"],
                                  "is_new": inc["is_new"], "ticket_ids": inc["ticket_ids"]}
            run.decide("Orchestrator", "incident", "INCIDENT_OPENED" if inc["is_new"] else "INCIDENT_UPDATED",
                       f"{inc['incident_id']}: {len(inc['ticket_ids'])} linked reports, owner {rout['department']}")

        # Communication Agent: ready-to-send message draft (never sent automatically)
        try:
            msg = run.agent("Communication Agent", "Draft message to the department",
                            lambda: agents.communication(llm, user_input, tri, rout, solution, result["status"]),
                            lambda o: f"Draft to {o['to_department']}: {o['subject'][:60]}")
            result["agent_results"]["communication"] = msg
            result["message_draft"] = msg
        except Exception as exc:  # optional step: never fail the ticket because of it
            result["message_draft"] = None
            result["agent_results"]["communication_error"] = f"{type(exc).__name__}: {exc}"
    except _StopPipeline:
        pass
    except Exception as exc:
        result["status"] = "failed"
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["error_trace"] = traceback.format_exc(limit=3)

    if run.simulated_calls and run.live_calls:
        exec_mode = "mixed"
    elif run.simulated_calls:
        exec_mode = "offline_simulation"
    elif run.live_calls:
        exec_mode = "live_llm"
    else:
        exec_mode = "none"
    result["execution_mode"] = exec_mode
    result["providers_used"] = sorted(run.providers)
    result["autonomy_metrics"] = {
        "agents_executed": run.agents_executed,
        "autonomous_decisions": len(run.decisions),
        "auditor_rejections": rejections,
        "revision_attempts": revisions,
        "human_escalations": escalations,
        "incident_detected": bool(result.get("incident")),
        "llm_calls_live": run.live_calls,
        "llm_calls_simulated": run.simulated_calls,
        "total_execution_time_ms": int((time.perf_counter() - started) * 1000),
    }
    try:
        db.save_ticket(result)
    except Exception as exc:  # persistence failure should not hide the result
        result["error"] = (result["error"] or "") + f" | DB save failed: {exc}"
    return result


REVIEWABLE = ("awaiting_human_approval", "escalated_to_human")


def review(ticket_id: str, decision: str, reviewer: str = "staff", note: str = "") -> dict:
    """Human-in-the-loop: a staff member approves or rejects a case the agents could not close alone."""
    decision = decision.strip().lower()
    if decision not in ("approve", "reject"):
        raise ValueError("decision must be 'approve' or 'reject'")
    result = db.load_ticket(ticket_id)
    if result is None:
        raise KeyError(f"ticket {ticket_id} not found")
    if result.get("status") not in REVIEWABLE:
        raise ValueError(f"ticket status '{result.get('status')}' does not need a human review")
    now = db.now_iso()
    previous = result["status"]
    result["status"] = "approved_by_staff" if decision == "approve" else "rejected_by_staff"
    result["human_review"] = {"decision": decision.upper(), "reviewer": reviewer or "staff", "note": note,
                              "reviewed_at": now, "previous_status": previous}
    d = {"agent": "Human Reviewer", "decision_type": "human_review", "decision": decision.upper(),
         "reason": note or f"{reviewer} {decision}d the case", "timestamp": now}
    result["decisions"].append(d)
    result["execution_trace"].append({"step": len({e['step'] for e in result['execution_trace']}) + 1,
                                      "agent": "Human Reviewer", "action": "decision:human_review",
                                      "status": "decision", "timestamp": now, "decision": decision.upper(),
                                      "summary": f"{decision.upper()} by {reviewer}" + (f" - {note}" if note else "")})
    db.save_review(result, d)
    return result


def replay(ticket_id: str, on_event: EventCallback | None = None, speed: float = 1.0) -> dict:
    """Re-emit the trace of a previously recorded run with its original pacing (capped).
    For demos without network. The returned ticket has replay=True and recorded_at, so the UI
    must label it 'RECORDED RUN' - nothing is recomputed and no LLM is called."""
    result = db.load_ticket(ticket_id) or load_recorded(ticket_id)
    if result is None:
        raise KeyError(f"ticket {ticket_id} not found")
    for ev in result.get("execution_trace", []):
        if on_event:
            if ev.get("status") == "completed" and speed > 0:
                time.sleep(min(ev.get("duration_ms", 0) / 1000 / speed, 2.5))
            try:
                on_event({**ev, "replay": True})
            except Exception:
                pass
    return {**result, "replay": True, "recorded_at": result["created_at"]}


RECORDED_DIR = config.ROOT_DIR / "demo" / "recorded_runs"


def load_recorded(ticket_id: str) -> dict | None:
    """Recorded live runs committed to the repo (demo/recorded_runs/<id>.json), for replay on any machine."""
    f = RECORDED_DIR / f"{ticket_id}.json"
    if not f.exists():
        return None
    import json
    return json.loads(f.read_text(encoding="utf-8"))


def list_recorded() -> list[dict]:
    import json
    out = []
    for f in sorted(RECORDED_DIR.glob("UR-*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        out.append({"ticket_id": r["ticket_id"], "created_at": r["created_at"],
                    "original_input": r["original_input"], "status": r["status"],
                    "execution_mode": r.get("execution_mode"), "revision_count": r.get("revision_count")})
    return out


def feedback(ticket_id: str, rating: str, comment: str = "") -> dict:
    """Student rates the final plan. A thumbs-down comment becomes a lesson for future plans."""
    rating = rating.strip().lower()
    if rating not in ("up", "down"):
        raise ValueError("rating must be 'up' or 'down'")
    result = db.load_ticket(ticket_id)
    if result is None:
        raise KeyError(f"ticket {ticket_id} not found")
    now = db.now_iso()
    result["student_feedback"] = {"rating": rating, "comment": (comment or "").strip()[:500], "at": now}
    d = {"agent": "Student", "decision_type": "feedback", "decision": "HELPFUL" if rating == "up" else "NOT_HELPFUL",
         "reason": (comment or "").strip()[:500] or ("helpful" if rating == "up" else "not helpful"), "timestamp": now}
    result["decisions"].append(d)
    db.save_feedback(result, d)
    return result
