"""Tiny keyword-based knowledge base retrieval (no extra dependencies)."""
from __future__ import annotations

import json
import re
from functools import lru_cache

from . import config


@lru_cache(maxsize=1)
def _load() -> dict:
    with open(config.KB_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def all_entries() -> list[dict]:
    return _load()["entries"]


def notice() -> str:
    return _load()["_notice"]


def get(entry_id: str) -> dict | None:
    return next((e for e in all_entries() if e["id"] == entry_id), None)


def valid_ids() -> set[str]:
    return {e["id"] for e in all_entries()}


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9\-]+", text.lower()))


def search(text: str, category: str | None = None, k: int = 3) -> list[dict]:
    """Score entries by keyword overlap (+bonus for matching category)."""
    toks = _tokens(text)
    low = text.lower()
    scored = []
    for e in all_entries():
        score = sum(1 for kw in e["keywords"] if kw in toks or (" " in kw and kw in low))
        if category and e["category"] == category:
            score += 3
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda x: -x[0])
    return [e for _, e in scored[:k]]


def by_category(category: str) -> list[dict]:
    return [e for e in all_entries() if e["category"] == category]
