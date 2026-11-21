# UniResolve AI - Backend Contract

Owner: backend (`backend/`). The frontend imports **only** these functions and must not modify backend files.

```python
from backend import (process_ticket, get_ticket, get_ticket_history,
                     get_dashboard_stats, get_system_status)
```

Run Streamlit from the repository root (`streamlit run frontend/app.py`). If `import backend` fails, add the repo root to `sys.path` at the top of `app.py`:

```python
import sys, pathlib; sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
```

---

## Functions

### `process_ticket(user_input, category=None, urgency=None, mode=None, on_event=None) -> dict`
Runs the full pipeline (Triage -> Routing -> Resolution <-> Auditor loop -> finalize / escalate) and saves the case to SQLite.

| arg | type | meaning |
|---|---|---|
| `user_input` | `str` | Student's problem text. Empty -> `ValueError`. |
| `category` | `str \| None` | Optional hint from the form. One of the **categories** below. `None` = agents decide. |
| `urgency` | `str \| None` | Optional hint: `low`, `medium`, `high`, `critical`. |
| `mode` | `str \| None` | `"auto"` (real LLM, falls back to simulation if all providers fail), `"live"` (real LLM only), `"offline"` (deterministic simulation, no network). `None` = `UNIRESOLVE_MODE` from `.env` (default `auto`). |
| `on_event` | `callable(dict) \| None` | Called **synchronously** with every trace event as it happens. Use it to update agent cards live (`st.empty()` placeholders). Exceptions inside the callback are ignored. |

Pipeline errors never raise: check `result["status"] == "failed"` and `result["error"]`.
A live run takes ~5-40 s (4-8 LLM calls). Offline is instant.

### `get_ticket(ticket_id: str) -> dict | None`
Full stored result, same shape as `process_ticket`. `None` if not found.

### `get_ticket_history(limit: int = 100) -> list[dict]`
Newest first. Each item:
```json
{"ticket_id": "UR-20261121-0A50CF", "created_at": "2026-11-21T09:34:47+00:00",
 "original_input": "...", "category": "it_network", "priority": "high",
 "assigned_department": "IT Service Desk", "status": "solution_verified",
 "auditor_decision": "ACCEPT", "revision_count": 1,
 "execution_mode": "live_llm", "total_time_ms": 8123}
```

### `get_dashboard_stats() -> dict`
```json
{"total_tickets": 5, "verified_solutions": 3, "pending_human_approval": 2,
 "avg_processing_time_ms": 7400, "total_auditor_rejections": 5}
```
`avg_processing_time_ms` is `null` when there are no tickets.

### `get_system_status() -> dict`
No API call; just configuration.
```json
{"mode": "auto", "max_revisions": 2,
 "llm_chain": "groq:openai/gpt-oss-120b,groq:openai/gpt-oss-20b,gemini:gemini-3.5-flash,gemini:gemini-3.8-flash",
 "llm_chain_fast": "groq:openai/gpt-oss-20b,gemini:gemini-3.5-flash-lite,...",
 "providers": {"gemini": {"api_key_set": true, "sdk_installed": true, "model": "gemini-3.5-flash",
                          "models": ["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.8-flash"], "ready": true},
               "groq":   {"api_key_set": true, "sdk_installed": true, "model": "openai/gpt-oss-120b",
                          "models": ["openai/gpt-oss-120b", "openai/gpt-oss-20b"], "ready": true}}}
```
The trace event `model` field shows which model actually answered each step (show it on the agent card).

---

## Enumerations

- **category**: `it_network`, `it_accounts`, `facilities`, `classroom_equipment`, `exams_academic`, `administration`, `finance`, `safety`, `health`, `wellbeing`, `accessibility`, `conduct`, `housing`, `international`, `library`, `campus_services`, `transport`, `other`
- **priority** (urgency): `low`, `medium`, `high`, `critical`
- **status**:
  - `solution_verified` - auditor accepted the plan (it is a *plan*; nothing was physically fixed)
  - `awaiting_human_approval` - plan accepted, but the outcome needs a staff decision (e.g. exam reschedule)
  - `escalated_to_human` - auditor rejected every attempt (1 draft + `max_revisions` revisions)
  - `failed` - pipeline error, see `error`
- **auditor_decision**: `ACCEPT` / `REJECT` (final audit)
- **execution_mode**: `live_llm` (all calls real), `offline_simulation` (all simulated), `mixed` (some calls fell back to simulation in auto mode), `none` (failed before any call)
  -> **The UI must show a clear "OFFLINE SIMULATION" badge when this is not `live_llm`.**

---

## `process_ticket` result

```jsonc
{
  "ticket_id": "UR-20261121-0A50CF",
  "created_at": "2026-11-21T09:34:47+00:00",       // UTC ISO
  "original_input": "University Wi-Fi is not working and my exam starts in one hour!",
  "requested_mode": "auto",
  "category": "it_network",
  "priority": "high",
  "assigned_department": "IT Service Desk",
  "workflow": "it_network",
  "requires_human_approval": false,
  "status": "solution_verified",
  "auditor_decision": "ACCEPT",
  "revision_count": 1,
  "execution_mode": "live_llm",
  "providers_used": ["gemini"],                      // or ["offline-simulation"], ["groq"], ...
  "error": null,
  "kb_notice": "DEMO DATA. ...",                     // show small disclaimer in UI

  "agent_results": {
    "triage": {
      "summary": "...", "category": "it_network", "urgency": "high", "urgency_reason": "...",
      "time_sensitive": true, "safety_risk": false, "key_facts": ["an exam is affected or imminent"]
    },
    "routing": {
      "workflow": "it_network", "department": "IT Service Desk",
      "secondary_departments": ["Study Office (Faculty Registrar)"],
      "kb_ids": ["KB-IT-01", "KB-EXAM-01"], "requires_human_approval": false, "reason": "..."
    },
    "resolution_attempts": [                          // one entry per Resolution -> Auditor round
      {
        "attempt": 1,
        "solution": { /* same shape as final_solution, without verified_by_auditor/note */ },
        "audit": {
          "verdict": "REJECT",                        // final verdict for this attempt
          "llm_verdict": "ACCEPT",                    // what the LLM auditor said on its own
          "programmatic_checks": [
            {"id": "C4", "name": "Urgency handled", "passed": false,
             "detail": "Urgency is 'high' / time-sensitive but no time-critical actions were given"}
            // C1..C8, see below
          ],
          "checks_passed": 5, "checks_total": 7,
          "scores": {"accuracy": 4, "relevance": 4, "completeness": 3, "groundedness": 5},  // may be {}
          "issues": ["..."],                          // LLM auditor's issues
          "feedback": ["[C4] ...", "[C5] ..."]        // exactly what was sent back to the Resolution Agent
        }
      },
      { "attempt": 2, "solution": {...}, "audit": {"verdict": "ACCEPT", ...} }
    ],
    "auditor": { /* = audit of the last attempt */ }
  },

  "final_solution": {
    "diagnosis": "...",
    "steps": [{"action": "...", "owner": "student|department|staff", "kb_ref": "KB-IT-01"}],
    "contact_department": "IT Service Desk",
    "time_critical_actions": ["..."],
    "kb_refs": ["KB-IT-01", "KB-EXAM-01"],
    "assumptions": [],
    "confidence": 0.8,                                // model self-estimate, 0-1 (not a measured accuracy)
    "verified_by_auditor": true,
    "note": "Verified action plan. ..."               // show this under the plan
  },

  "execution_trace": [ /* events, see below, in order */ ],
  "decisions": [
    {"agent": "Auditor Agent", "decision_type": "audit", "decision": "REJECT", "reason": "...",
     "timestamp": "..."}
    // decision_type: classification | routing | human_approval_required | audit | retry | escalation | finalize
  ],

  "autonomy_metrics": {
    "agents_executed": 6,
    "autonomous_decisions": 6,
    "auditor_rejections": 1,
    "revision_attempts": 1,
    "human_escalations": 0,
    "llm_calls_live": 6,
    "llm_calls_simulated": 0,
    "total_execution_time_ms": 8123
  }
}
```

If `status == "failed"`, fields after the failure point may be `null` / missing (`final_solution` is `null`). Always use `.get()`.

### Trace event (`execution_trace[i]` and `on_event` argument)

```jsonc
// started
{"step": 3, "agent": "Resolution Agent", "action": "Draft resolution plan", "status": "started", "timestamp": "..."}
// completed
{"step": 3, "agent": "Resolution Agent", "action": "Draft resolution plan", "status": "completed",
 "timestamp": "...", "duration_ms": 2140, "provider": "gemini", "model": "gemini-3.8-flash",
 "simulated": false, "fallback_errors": [], "summary": "3 steps, refs ['KB-IT-01']", "output": {...}}
// decision (agent can also be "Orchestrator")
{"step": 4, "agent": "Orchestrator", "action": "decision:retry", "status": "decision",
 "timestamp": "...", "decision": "REVISE", "summary": "REVISE - Auditor rejected; ..."}
// error
{"step": 3, "agent": "Resolution Agent", "status": "error", "summary": "LLMError: ...", "output": null}
```

Agents: `Triage Agent`, `Routing Agent`, `Resolution Agent`, `Auditor Agent`, `Orchestrator` (decisions only).
`step` is shared by a started/completed pair. Resolution and Auditor appear once per attempt.
`fallback_errors` non-empty = the primary provider failed and another provider (or the simulation) answered.

### Auditor programmatic checks
| id | check |
|---|---|
| C1 | Every KB reference exists among the entries given to the resolver |
| C2 | At least one step is grounded in a KB entry |
| C3 | At least 2 actionable steps |
| C4 | Time-sensitive / high urgency -> `time_critical_actions` not empty |
| C5 | *(only if an exam is mentioned)* plan tells the student what to do about the exam |
| C6 | *(only if safety risk)* safety guidance present |
| C7 | No emails / phone numbers / URLs that are not in the KB |
| C8 | Contact department consistent with routing |

Final verdict = ACCEPT only if **all** checks pass **and** the LLM auditor accepts.

---

## Offline demo scenarios (`mode="offline"`, deterministic)

| input | expected |
|---|---|
| `University Wi-Fi is not working and my exam starts in one hour!` | REJECT (C4, C5) -> revise -> ACCEPT, `solution_verified` |
| `There is a broken chair in classroom 204.` | ACCEPT first time, Facilities Management |
| `I was sick and need to reschedule my calculus exam to a new date.` | `awaiting_human_approval` |
| `My private landlord in the city refuses to return my rental deposit.` | outside university scope -> 3 rejections -> `escalated_to_human` |
| `My scholarship payment did not arrive this month.` | Student Finance Office, `awaiting_human_approval` |

Offline mode simulates only the LLM text. Orchestration, auditor checks, retries, escalation and the database are the real code.
