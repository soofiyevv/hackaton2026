"""Evaluation run: 20 labelled student problems through the real pipeline.
Measures routing accuracy against the expected department plus autonomy statistics.
Results -> data/eval_results.json and data/eval_report.md (numbers for the README / pitch deck).

    py demo/evaluate.py            # live LLM (default mode from .env), ~2-4 min with pauses for rate limits
    py demo/evaluate.py --offline  # quick sanity check of the script itself
"""
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend import process_ticket  # noqa: E402

# (problem, expected owning department, expect a staff decision?)
CASES = [
    ("University Wi-Fi is not working and my exam starts in one hour!", "IT Service Desk", False),
    ("Eduroam keeps disconnecting in the library reading room since this morning.", "IT Service Desk", False),
    ("I cannot log in to Neptun, it says my password is wrong but I just reset it.", "IT Service Desk", False),
    ("The printer on the second floor of the main building has a paper jam and nobody fixed it.", "IT Service Desk", False),
    ("There is a broken chair in classroom 204.", "Facilities Management", False),
    ("The heating in lecture hall A does not work and it is freezing.", "Facilities Management", False),
    ("The projector in room 112 shows no signal from my laptop, I present in 20 minutes.", "Facilities Management", False),
    ("I was sick and need to reschedule my calculus exam to a new date.", "Study Office (Faculty Registrar)", True),
    ("I need an official student status certificate for my visa office appointment.", "Study Office (Faculty Registrar)", True),
    ("My scholarship payment did not arrive this month.", "Student Finance Office", True),
    ("I paid my tuition twice by mistake and want a refund.", "Student Finance Office", True),
    ("I feel overwhelmed and anxious before exams and can't sleep.", "Student Counselling Service", True),
    ("The elevator in building C is broken and I use a wheelchair.", "Disability & Accessibility Support", True),
    ("A classmate keeps sending me insulting racist messages.", "Student Ombudsman / Equal Opportunities Office", True),
    ("There is a strong smell of gas in the chemistry lab corridor.", "Campus Security", False),
    ("The washing machines in my dormitory have been broken for a week.", "Dormitory Office", False),
    ("I lost my wallet with my student card somewhere in the medical faculty building.", "Building Reception", False),
    ("The canteen served undercooked chicken today and my friend feels sick.", "Catering Services", False),
    ("Where can I renew my library books that are due tomorrow?", "University Library", False),
    ("My private landlord in the city refuses to return my rental deposit.", None, None),  # out of scope
]


def main() -> None:
    mode = "offline" if "--offline" in sys.argv else None
    pause = 0 if mode == "offline" else float(next((a.split("=")[1] for a in sys.argv if a.startswith("--pause=")), 6))
    rows = []
    for i, (text, dept, staff) in enumerate(CASES, 1):
        r = process_ticket(text, mode=mode)
        m = r["autonomy_metrics"]
        row = {
            "case": i, "input": text, "expected_department": dept, "assigned_department": r["assigned_department"],
            "routing_correct": None if dept is None else r["assigned_department"] == dept,
            "expected_staff_decision": staff, "requires_human_approval": r["requires_human_approval"],
            "status": r["status"], "revisions": r["revision_count"], "rejections": m["auditor_rejections"],
            "time_ms": m["total_execution_time_ms"], "live_calls": m["llm_calls_live"],
            "simulated_calls": m["llm_calls_simulated"], "execution_mode": r["execution_mode"],
            "has_message_draft": bool(r.get("message_draft")), "error": r["error"],
        }
        rows.append(row)
        ok = {True: "OK ", False: "MISS", None: "n/a"}[row["routing_correct"]]
        print(f"[{i:2}/{len(CASES)}] {ok} {row['status']:<24} rev={row['revisions']} {row['time_ms']:>6} ms "
              f"{row['execution_mode']:<18} -> {row['assigned_department']}")
        if i < len(CASES):
            time.sleep(pause)

    scored = [r for r in rows if r["routing_correct"] is not None]
    staff_scored = [r for r in rows if r["expected_staff_decision"] is not None]
    n = len(rows)
    summary = {
        "cases": n,
        "mode_counts": dict(Counter(r["execution_mode"] for r in rows)),
        "routing_accuracy": round(sum(r["routing_correct"] for r in scored) / len(scored), 3),
        "staff_decision_flag_accuracy": round(
            sum(r["requires_human_approval"] == r["expected_staff_decision"] for r in staff_scored) / len(staff_scored), 3),
        "accepted_first_attempt": sum(r["rejections"] == 0 and r["status"] != "failed" for r in rows),
        "self_corrected_after_rejection": sum(r["rejections"] > 0 and r["status"] in
                                              ("solution_verified", "awaiting_human_approval") for r in rows),
        "escalated_after_failed_revisions": sum(r["status"] == "escalated_to_human" for r in rows),
        "queued_for_staff_decision": sum(r["status"] == "awaiting_human_approval" for r in rows),
        "failed": sum(r["status"] == "failed" for r in rows),
        "total_auditor_rejections": sum(r["rejections"] for r in rows),
        "median_time_ms": int(statistics.median(r["time_ms"] for r in rows)),
        "mean_time_ms": int(statistics.mean(r["time_ms"] for r in rows)),
        "live_llm_calls": sum(r["live_calls"] for r in rows),
        "simulated_llm_calls": sum(r["simulated_calls"] for r in rows),
        "message_drafts": sum(r["has_message_draft"] for r in rows),
    }
    out_dir = ROOT / "data"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "eval_results.json").write_text(json.dumps({"summary": summary, "rows": rows}, indent=2,
                                                          ensure_ascii=False), encoding="utf-8")
    misses = [r for r in scored if not r["routing_correct"]]
    report = [
        "# UniResolve AI - evaluation run",
        f"Run at {time.strftime('%Y-%m-%d %H:%M')} on {n} hand-written student problems "
        f"({summary['mode_counts']}). Expected departments were labelled by the team before the run.\n",
        "| metric | value |", "|---|---|",
        f"| Routing accuracy (19 in-scope cases) | {summary['routing_accuracy']:.0%} |",
        f"| Staff-decision flag accuracy | {summary['staff_decision_flag_accuracy']:.0%} |",
        f"| Accepted by auditor on first attempt | {summary['accepted_first_attempt']}/{n} |",
        f"| Self-corrected after auditor rejection | {summary['self_corrected_after_rejection']}/{n} |",
        f"| Escalated to human after failed revisions | {summary['escalated_after_failed_revisions']}/{n} |",
        f"| Queued for staff decision (policy) | {summary['queued_for_staff_decision']}/{n} |",
        f"| Total auditor rejections | {summary['total_auditor_rejections']} |",
        f"| Median / mean time per ticket | {summary['median_time_ms']/1000:.1f} s / {summary['mean_time_ms']/1000:.1f} s |",
        f"| Live LLM calls / simulated | {summary['live_llm_calls']} / {summary['simulated_llm_calls']} |",
        f"| Failed tickets | {summary['failed']} |",
        "\nRouting misses:" if misses else "\nNo routing misses.",
        *[f"- \"{r['input']}\" -> {r['assigned_department']} (expected {r['expected_department']})" for r in misses],
        "\nSmall hand-made test set; these numbers describe this run, not real-world performance.",
    ]
    (out_dir / "eval_report.md").write_text("\n".join(report), encoding="utf-8")
    print("\n" + "\n".join(report))


if __name__ == "__main__":
    main()
