"""Print the models your API keys can actually use, then test one tiny JSON call each.

    py demo/list_models.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import config, llm  # noqa: E402  (loads .env)

print("=== Gemini ===")
try:
    from google import genai

    client = genai.Client(api_key=config.gemini_api_key())
    names = []
    for m in client.models.list():
        actions = getattr(m, "supported_actions", None) or []
        if "generateContent" in actions and "flash" in m.name:
            names.append(m.name.replace("models/", ""))
    for n in sorted(names):
        print("  ", n)
    for p, m in llm.parse_chain(config.LLM_CHAIN + "," + config.LLM_CHAIN_FAST):
        if p == "gemini":
            print(f"Chain model {m}  ->  {'OK' if m in names else 'NOT IN LIST'}")
except Exception as exc:
    print("  Gemini error:", type(exc).__name__, str(exc)[:300])

print("\n=== Groq ===")
try:
    from groq import Groq

    client = Groq(api_key=config.groq_api_key())
    ids = sorted(m.id for m in client.models.list().data)
    for i in ids:
        print("  ", i)
    for p, m in llm.parse_chain(config.LLM_CHAIN + "," + config.LLM_CHAIN_FAST):
        if p == "groq":
            print(f"Chain model {m}  ->  {'OK' if m in ids else 'NOT IN LIST'}")
except Exception as exc:
    print("  Groq error:", type(exc).__name__, str(exc)[:300])
