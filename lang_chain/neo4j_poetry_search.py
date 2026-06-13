# -*- coding: utf-8 -*-
"""Neo4j-backed poetry search for imported ClassicalText nodes."""

from __future__ import annotations

from typing import Any

from logger import Logger
from lang_chain.local_poetry_search import _score, value_for_chinese_search, value_for_classical_search


__logger = Logger(__name__)

try:
    from dao.graph.graph_dao import GraphDao
except Exception as exc:  # pragma: no cover - keeps search usable without py2neo/config.
    GraphDao = None
    __logger.warning(f"Neo4j search disabled: {exc}")


def _keyword_text(keywords: Any) -> str:
    if isinstance(keywords, list):
        return " ".join(str(keyword) for keyword in keywords)
    return str(keywords or "")


def _to_poem(row: dict[str, Any]) -> dict[str, str]:
    return {
        "dynasty": str(row.get("dynasty") or ""),
        "book": str(row.get("book") or ""),
        "author": str(row.get("author") or ""),
        "title": str(row.get("title") or ""),
        "text": str(row.get("text") or ""),
        "translation": str(row.get("translation") or ""),
        "keywords": _keyword_text(row.get("keywords")),
        "searchText": str(row.get("searchText") or ""),
    }


def _load_classical_texts() -> list[dict[str, Any]]:
    if GraphDao is None:
        return []

    try:
        cursor = GraphDao().run_cypher(
            """
            MATCH (poem:ClassicalText)
            RETURN
              poem.dynasty AS dynasty,
              poem.book AS book,
              poem.author AS author,
              poem.title AS title,
              poem.text AS text,
              poem.translation AS translation,
              poem.keywords AS keywords,
              poem.searchText AS searchText
            """
        )
    except Exception as exc:
        __logger.warning(f"Neo4j poetry search failed: {exc}")
        return []

    if cursor is None:
        return []

    try:
        return cursor.data()
    except Exception as exc:
        __logger.warning(f"Neo4j poetry search returned invalid cursor: {exc}")
        return []


def neo4j_search(query: str, conf_key: str, size: int) -> list[dict[str, Any]]:
    rows = _load_classical_texts()
    if not rows:
        return []

    results = []
    min_score = 0.24 if conf_key == "chinese-poetry" else 0.18
    for row in rows:
        poem = _to_poem(row)
        if conf_key == "chinese-poetry":
            target = poem["searchText"] or " ".join(
                [poem["translation"], poem["keywords"], poem["title"], poem["author"], poem["book"]]
            )
            value = value_for_chinese_search(poem)
        else:
            target = " ".join([poem["text"], poem["keywords"], poem["title"], poem["author"]])
            value = value_for_classical_search(poem)

        score = _score(query, target)
        if score >= min_score:
            results.append({"value": value, "score": float(score)})

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: max(size, 1)]
