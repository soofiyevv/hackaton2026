"""Export recorded live runs from the local database into demo/recorded_runs/ (committed to git)
so replay_ticket() works on any machine.      py demo/export_runs.py UR-... UR-..."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend import get_ticket  # noqa: E402

out_dir = ROOT / "demo" / "recorded_runs"
out_dir.mkdir(parents=True, exist_ok=True)
for tid in sys.argv[1:]:
    t = get_ticket(tid)
    if not t:
        print("not found:", tid)
        continue
    if t.get("execution_mode") != "live_llm":
        print(f"warning: {tid} is {t.get('execution_mode')}, not a pure live run")
    (out_dir / f"{tid}.json").write_text(json.dumps(t, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"exported {tid}: {t['status']}, {len(t['execution_trace'])} events, {t.get('execution_mode')}")
