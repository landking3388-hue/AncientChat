# -*- coding: utf-8 -*-
"""Small local poetry search engine used as a fallback service."""

import json
import re
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path
from typing import Any


_DATA_PATH = Path(__file__).resolve().parents[1] / "data" / "poetry_search" / "poems.json"


@lru_cache(maxsize=1)
def load_poems() -> tuple[dict[str, str], ...]:
    with _DATA_PATH.open("r", encoding="utf-8") as fp:
        return tuple(json.load(fp))


def _normalize(text: str) -> str:
    return re.sub(r"\s+", "", text or "").lower()


def _chars(text: str) -> set[str]:
    return {ch for ch in _normalize(text) if "\u4e00" <= ch <= "\u9fff" or ch.isalnum()}


def _score(query: str, target: str) -> float:
    query_norm = _normalize(query)
    target_norm = _normalize(target)
    if not query_norm or not target_norm:
        return 0.0

    query_chars = _chars(query_norm)
    target_chars = _chars(target_norm)
    overlap = len(query_chars & target_chars) / max(len(query_chars), 1)
    sequence = SequenceMatcher(None, query_norm, target_norm).ratio()
    substring_bonus = 0.25 if query_norm in target_norm or target_norm in query_norm else 0.0
    return min(1.0, overlap * 0.58 + sequence * 0.32 + substring_bonus)


def value_for_chinese_search(poem: dict[str, str]) -> str:
    book = poem.get("book") or f"{poem['dynasty']}诗文"
    return "##@##".join([book, poem["title"], poem["text"], poem["translation"]])


def value_for_classical_search(poem: dict[str, str]) -> str:
    return "##@##".join([
        poem["dynasty"],
        poem["author"],
        poem["text"],
        poem["title"],
        poem["keywords"],
    ])


def local_search(query: str, conf_key: str, size: int) -> list[dict[str, Any]]:
    results = []
    min_score = 0.24 if conf_key == "chinese-poetry" else 0.18
    for poem in load_poems():
        if conf_key == "chinese-poetry":
            target = " ".join([poem["translation"], poem["keywords"], poem["title"], poem["author"]])
            value = value_for_chinese_search(poem)
        else:
            target = " ".join([poem["text"], poem["keywords"], poem["title"], poem["author"]])
            value = value_for_classical_search(poem)

        score = _score(query, target)
        if score >= min_score:
            results.append({"value": value, "score": float(score)})

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: max(size, 1)]
