"""Runtime configuration. All secrets come from environment variables (.env supported)."""
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent

try:  # python-dotenv is optional; plain environment variables also work
    from dotenv import load_dotenv

    load_dotenv(ROOT_DIR / ".env")
except ImportError:
    pass

VALID_MODES = ("auto", "live", "offline")


def get_mode(override: str | None = None) -> str:
    """auto = real LLM, falls back to offline simulation if every provider fails.
    live = real LLM only (errors if providers fail).
    offline = deterministic simulation, no network."""
    mode = (override or os.getenv("UNIRESOLVE_MODE", "auto")).strip().lower()
    return mode if mode in VALID_MODES else "auto"


def gemini_api_key() -> str | None:
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None


def groq_api_key() -> str | None:
    return os.getenv("GROQ_API_KEY") or None


# Ordered fallback chains "provider:model,...". Each model on Groq has its own rate limit,
# so several models spread the load. Heavy agents (resolution/audit) use LLM_CHAIN,
# light agents (triage/routing) use LLM_CHAIN_FAST.
LLM_CHAIN = os.getenv("LLM_CHAIN",
                      "groq:openai/gpt-oss-120b,groq:qwen/qwen3.8-27b,groq:openai/gpt-oss-20b,"
                      "gemini:gemini-3.5-flash,gemini:gemini-3.5-flash-lite,gemini:gemini-3.8-flash")
LLM_CHAIN_FAST = os.getenv("LLM_CHAIN_FAST",
                           "groq:openai/gpt-oss-20b,groq:qwen/qwen3.8-27b,gemini:gemini-3.5-flash-lite,"
                           "groq:openai/gpt-oss-120b,gemini:gemini-3.5-flash")
GROQ_REASONING_EFFORT = os.getenv("GROQ_REASONING_EFFORT", "low")  # low | medium | high | "" to omit
LLM_TIMEOUT_S =float(os.getenv("LLM_TIMEOUT_S", "30"))

MAX_REVISIONS = int(os.getenv("MAX_REVISIONS", "2"))

DB_PATH = Path(os.getenv("UNIRESOLVE_DB", str(ROOT_DIR / "data" / "uniresolve.db")))
KB_PATH = Path(__file__).resolve().parent / "knowledge_base.json"
