"""LLM provider layer: Gemini (primary) -> Groq (fallback) -> offline simulation.

Every call returns an LLMResult that says exactly which provider produced the
output and whether it was simulated, so the UI can never confuse the two.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Callable

from . import config


class LLMError(Exception):
    pass


@dataclass
class LLMResult:
    data: dict
    provider: str  # "gemini" | "groq" | "offline-simulation"
    model: str
    simulated: bool
    latency_ms: int
    fallback_chain: list = field(default_factory=list)  # errors from providers that failed first


def parse_json(text: str) -> dict:
    """Parse a JSON object from model output, tolerating code fences / extra prose."""
    if text is None:
        raise LLMError("empty response")
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()  # reasoning models (qwen)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned)
    try:
        obj = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if not match:
            raise LLMError(f"no JSON object in response: {cleaned[:200]}")
        try:
            obj = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise LLMError(f"invalid JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise LLMError("response JSON is not an object")
    return obj


# ---------------------------------------------------------------- providers
_clients: dict = {}


def _call_gemini(model: str, system: str, prompt: str) -> str:
    key = config.gemini_api_key()
    if not key:
        raise LLMError("GEMINI_API_KEY not set")
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise LLMError("google-genai package not installed") from exc
    if "gemini" not in _clients:
        _clients["gemini"] = genai.Client(
            api_key=key, http_options=types.HttpOptions(timeout=int(config.LLM_TIMEOUT_S * 1000))
        )
    resp = _clients["gemini"].models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0.2,
        ),
    )
    return resp.text


def _call_groq(model: str, system: str, prompt: str) -> str:
    key = config.groq_api_key()
    if not key:
        raise LLMError("GROQ_API_KEY not set")
    try:
        from groq import Groq
    except ImportError as exc:
        raise LLMError("groq package not installed") from exc
    if "groq" not in _clients:
        # max_retries=0: on 429 we switch to the next model in the chain instead of waiting
        _clients["groq"] = Groq(api_key=key, timeout=config.LLM_TIMEOUT_S, max_retries=0)
    kwargs = dict(
        model=model,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        response_format={"type": "json_object"},
        temperature=0.2,
    )
    if "gpt-oss" in model and config.GROQ_REASONING_EFFORT:
        # reasoning models burn tokens/time on hidden reasoning; keep it low for speed + rate limits
        kwargs["reasoning_effort"] = config.GROQ_REASONING_EFFORT
    try:
        resp = _clients["groq"].chat.completions.create(**kwargs)
    except TypeError:  # older SDK without this parameter
        kwargs.pop("reasoning_effort", None)
        resp = _clients["groq"].chat.completions.create(**kwargs)
    return resp.choices[0].message.content


CALLERS = {"gemini": _call_gemini, "groq": _call_groq}


def parse_chain(spec: str) -> list[tuple[str, str]]:
    """'groq:openai/gpt-oss-120b,gemini:gemini-3.5-flash' -> [(provider, model), ...]"""
    chain = []
    for item in spec.split(","):
        item = item.strip()
        if ":" not in item:
            continue
        provider, model = item.split(":", 1)
        if provider.strip() in CALLERS and model.strip():
            chain.append((provider.strip(), model.strip()))
    return chain


def provider_status() -> dict:
    """Which providers are configured (key present + SDK importable). No network call."""
    status = {}
    for name, key_fn, module in (
        ("gemini", config.gemini_api_key, "google.genai"),
        ("groq", config.groq_api_key, "groq"),
    ):
        try:
            __import__(module)
            sdk = True
        except ImportError:
            sdk = False
        models = [m for p, m in parse_chain(config.LLM_CHAIN) + parse_chain(config.LLM_CHAIN_FAST) if p == name]
        status[name] = {"api_key_set": bool(key_fn()), "sdk_installed": sdk,
                        "model": models[0] if models else None, "models": sorted(set(models)),
                        "ready": bool(key_fn()) and sdk}
    return status


_disabled: dict[str, str] = {}   # "provider:model" -> reason (wrong model / bad key); cleared on restart
_cooldown: dict[str, float] = {}  # "provider:model" -> unix time until which it is skipped
COOLDOWN_S = 60.0


def _is_permanent(exc: Exception) -> bool:
    """404 model not found, 401/403 bad key: retrying will not help."""
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    text = str(exc)
    return code in (401, 403, 404) or any(
        s in text for s in ("404", "NOT_FOUND", "model_not_found", "API_KEY_INVALID", "PERMISSION_DENIED", "401"))


def _is_overloaded(exc: Exception) -> bool:
    """503 overloaded, 429 rate limit, timeouts: switch model instead of retrying."""
    code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    text = str(exc)
    return code in (429, 500, 502, 503, 504) or "Timeout" in type(exc).__name__ or any(
        s in text for s in ("503", "504", "UNAVAILABLE", "DEADLINE", "429", "RESOURCE_EXHAUSTED",
                            "rate limit", "Rate limit", "overloaded"))


class LLMClient:
    def __init__(self, mode: str):
        self.mode = config.get_mode(mode)
        self.chains = {"default": parse_chain(config.LLM_CHAIN), "fast": parse_chain(config.LLM_CHAIN_FAST)}

    def generate_json(self, system: str, prompt: str, mock: Callable[[], dict], tier: str = "default") -> LLMResult:
        """tier="fast" for light agents (triage/routing): a different model first, so the rate limits
        of the strong model are kept for resolution/audit."""
        started = time.perf_counter()
        if self.mode == "offline":
            return LLMResult(mock(), "offline-simulation", "deterministic-mock", True,
                             int((time.perf_counter() - started) * 1000))

        system = system + "\nRespond ONLY with a single valid JSON object."
        chain = self.chains.get(tier) or self.chains["default"]
        usable = [(p, m) for p, m in chain if f"{p}:{m}" not in _disabled]
        fresh = [(p, m) for p, m in usable if _cooldown.get(f"{p}:{m}", 0) <= time.time()]
        # if everything is cooling down, try anyway (soonest-available first)
        order = fresh or sorted(usable, key=lambda pm: _cooldown.get(f"{pm[0]}:{pm[1]}", 0))
        errors = [f"{p}:{m}: skipped (cooling down after overload/rate limit)" for p, m in usable if (p, m) not in order]
        for provider, model in order:
            key = f"{provider}:{model}"
            for attempt in range(2):
                try:
                    data = parse_json(CALLERS[provider](model, system, prompt))
                    return LLMResult(data, provider, model, False,
                                     int((time.perf_counter() - started) * 1000), errors)
                except LLMError as exc:  # missing key/SDK, or unparsable output
                    errors.append(f"{key}: {exc}")
                    if "not set" in str(exc) or "not installed" in str(exc):
                        break
                except Exception as exc:  # network, timeout, quota, SDK errors
                    msg = f"{type(exc).__name__}: {str(exc)[:200]}"
                    errors.append(f"{key}: {msg}")
                    if _is_permanent(exc):
                        _disabled[key] = msg[:120]
                        break
                    if _is_overloaded(exc):
                        _cooldown[key] = time.time() + COOLDOWN_S
                        break
                    if attempt == 0:
                        time.sleep(1.0)
        if self.mode == "auto":
            return LLMResult(mock(), "offline-simulation", "deterministic-mock", True,
                             int((time.perf_counter() - started) * 1000), errors)
        raise LLMError("all LLM providers failed: " + " | ".join(errors))


def healthcheck(timeout_note: str = "") -> list[dict]:
    """Ping every model in the chains with a tiny JSON request (real API calls, ~1-3 s each).
    Use before a demo / in a 'System status' panel. Does not change cooldown state."""
    seen, out = set(), []
    for provider, model in parse_chain(config.LLM_CHAIN) + parse_chain(config.LLM_CHAIN_FAST):
        if (provider, model) in seen:
            continue
        seen.add((provider, model))
        t0 = time.perf_counter()
        try:
            data = parse_json(CALLERS[provider](model, "Reply with JSON only.", 'Return {"ok": true}'))
            status, detail = ("ok" if data.get("ok") is True else "unexpected_output"), ""
        except Exception as exc:
            status = ("rate_limited_or_overloaded" if _is_overloaded(exc)
                      else "unavailable" if _is_permanent(exc) else "error")
            detail = f"{type(exc).__name__}: {str(exc)[:120]}"
        out.append({"provider": provider, "model": model, "status": status,
                    "latency_ms": int((time.perf_counter() - t0) * 1000), "detail": detail,
                    "cooling_down": _cooldown.get(f"{provider}:{model}", 0) > time.time()})
    return out
