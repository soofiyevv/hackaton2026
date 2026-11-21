"""Orchestrator: runs the agents, owns the state, the audit/revise loop, retries,
escalation, execution trace and autonomy metrics."""
from __future__ import annotations

import time
import traceback
import uuid
from datetime import datetime
from typing import Callable

from . import agents, config, db, kb
from .llm import LLMClient, LLMResult

EventCallback = Callable[[dict], None]


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
    mode = config.get_mode(mode)
    llm = LLMClient(mode)
    run = Run(_new_ticket_id(), on_event)
    result: dict = {
        "ticket_id": run.ticket_id, "created_at": db.now_iso(), "original_input": user_input.strip(),
        "requested_mode": mode, "category": None, "priority": None, "assigned_department": None,
        "workflow": None, "requires_human_approval": False, "agent_results": {},
        "execution_trace": run.trace, "decisions": run.decisions, "auditor_decision": None,
        "revision_count": 0, "final_solution": None, "status": "processing", "error": None,
        "kb_notice": kb.notice(),
    }
    rejections = revisions = escalations = 0
    try:
        tri = run.agent("Triage Agent", "Classify problem, category and urgency",
                        lambda: agents.triage(llm, user_input, category_hint, urgency_hint),
                        lambda o: f"{o['category']} / urgency {o['urgency']}")
        run.decide("Triage Agent", "classification", f"{tri['category']}|{tri['urgency']}",
                   tri["urgency_reason"] or "classified from report")
        result.update(category=tri["category"], priority=tri["urgency"])
        result["agent_results"]["triage"] = tri

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
        "llm_calls_live": run.live_calls,
        "llm_calls_simulated": run.simulated_calls,
        "total_execution_time_ms": int((time.perf_counter() - started) * 1000),
    }
    try:
        db.save_ticket(result)
    except Exception as exc:  # persistence failure should not hide the result
        result["error"] = (result["error"] or "") + f" | DB save failed: {exc}"
    return result
