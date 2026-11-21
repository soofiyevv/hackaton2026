"""Console demo of the multi-agent pipeline.

    python demo/run_demo.py              # mode from .env (default auto)
    python demo/run_demo.py --offline    # deterministic simulation, no API
    python demo/run_demo.py "my own problem text"
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import get_system_status, process_ticket  # noqa: E402

SCENARIOS = [
    "University Wi-Fi is not working and my exam starts in one hour!",
    "There is a broken chair in classroom 204.",
    "I was sick and need to reschedule my calculus exam to a new date.",
    "My private landlord in the city refuses to return my rental deposit.",
]


def show(event: dict) -> None:
    if event["status"] == "started":
        print(f"  [{event['step']}] {event['agent']:<17} ... {event['action']}")
    elif event["status"] == "completed":
        tag = "SIMULATED" if event.get("simulated") else f"{event['provider']}:{event['model']}"
        print(f"      -> {event['summary']}  ({event['duration_ms']} ms, {tag})")
        for err in event.get("fallback_errors") or []:
            print(f"      ! fallback: {err}")
    elif event["status"] == "decision":
        print(f"      * {event['agent']} decided {event['decision']}: {event['summary'][:110]}")
    elif event["status"] == "error":
        print(f"      x ERROR {event['summary']}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    mode = "offline" if "--offline" in sys.argv else ("live" if "--live" in sys.argv else None)
    status = get_system_status()
    print(f"Mode: {mode or status['mode']} | providers: "
          + ", ".join(f"{k}={'ready' if v['ready'] else 'not ready'}" for k, v in status["providers"].items()))
    for text in args or SCENARIOS:
        print("\n" + "=" * 90 + f"\nSTUDENT: {text}")
        r = process_ticket(text, mode=mode, on_event=show)
        print(f"RESULT {r['ticket_id']}: status={r['status']} | {r['category']} / {r['priority']} -> "
              f"{r['assigned_department']} | revisions={r['revision_count']} | mode={r['execution_mode']}")
        if r["error"]:
            print("ERROR:", r["error"])
        print("METRICS:", r["autonomy_metrics"])
        if r.get("message_draft"):
            m = r["message_draft"]
            print(f"MESSAGE DRAFT -> {m['to_department']} via {m['channel']}\n  Subject: {m['subject']}\n  "
                  + m["body"].replace("\n", "\n  "))


if __name__ == "__main__":
    main()
