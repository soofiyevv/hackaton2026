"""Pre-demo check: which models answer right now and how fast.   py demo/check_models.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend import check_models  # noqa: E402

for r in check_models():
    print(f"{r['status']:<28} {r['latency_ms']:>6} ms  {r['provider']}:{r['model']}  {r['detail'][:80]}")
