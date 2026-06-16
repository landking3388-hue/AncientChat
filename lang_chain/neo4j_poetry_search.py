# -*- coding: utf-8 -*-
"""Neo4j-backed poetry search for imported ClassicalText nodes."""

from __future__ import annotations

import json
from typing import Any

from logger import Logger
from lang_chain.local_poetry_search import _chars, _score, value_for_chinese_search, value_for_classical_search


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
        "introduction": _normalize_introduction(row.get("introduction")),
        "keywords": _keyword_text(row.get("keywords")),
        "searchText": str(row.get("searchText") or ""),
    }


_POEM_LABEL = "诗词名"


def _cypher_string(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _normalize_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(item) for item in value if item)
    return str(value or "")


def _normalize_introduction(value: Any) -> str:
    text = _normalize_text(value).strip()
    if text in {"无相关数据", "暂无数据", "暂无", "None", "null"}:
        return ""
    return text


def _compact_text(text: str) -> str:
    return "".join(ch for ch in _normalize_text(text) if "\u4e00" <= ch <= "\u9fff" or ch.isalnum()).lower()


def _bigrams(text: str) -> set[str]:
    compact = _compact_text(text)
    return {compact[index:index + 2] for index in range(max(len(compact) - 1, 0))}


def _lcs_ratio(query: str, target: str) -> float:
    query_text = _compact_text(query)
    target_text = _compact_text(target)
    if not query_text or not target_text:
        return 0.0

    previous = [0] * (len(target_text) + 1)
    for query_char in query_text:
        current = [0]
        for index, target_char in enumerate(target_text, 1):
            if query_char == target_char:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(previous[index], current[-1]))
        previous = current

    return previous[-1] / len(query_text)


def _classical_score(query: str, target: str) -> float:
    query_text = _compact_text(query)
    target_text = _compact_text(target)
    if not query_text or not target_text:
        return 0.0
    if query_text in target_text:
        return 1.0

    query_chars = set(query_text)
    target_chars = set(target_text)
    char_overlap = len(query_chars & target_chars) / max(len(query_chars), 1)

    query_bigrams = _bigrams(query_text)
    target_bigrams = _bigrams(target_text)
    bigram_overlap = len(query_bigrams & target_bigrams) / max(len(query_bigrams), 1)

    lcs = _lcs_ratio(query_text, target_text)
    length_bonus = min(1.0, 80 / max(len(target_text), 1))

    return min(1.0, char_overlap * 0.35 + bigram_overlap * 0.35 + lcs * 0.2 + length_bonus * 0.1)


def _query_neo4j(query: str) -> list[dict[str, Any]]:
    if GraphDao is None:
        return []

    try:
        cursor = GraphDao().run_cypher(query)
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


def _load_classical_texts() -> list[dict[str, Any]]:
    return _query_neo4j(
        """
        MATCH (poem:ClassicalText)
        RETURN
          poem.dynasty AS dynasty,
          poem.book AS book,
          poem.author AS author,
          poem.title AS title,
          poem.text AS text,
          poem.translation AS translation,
          coalesce(poem.introduction, poem.intro, poem.description, "") AS introduction,
          poem.keywords AS keywords,
          poem.searchText AS searchText
        """
    )


def _query_imported_poetry_by_exact_text(query: str, limit: int) -> list[dict[str, Any]]:
    query_literal = _cypher_string(query)
    poem_label = _cypher_string(_POEM_LABEL)
    return _query_neo4j(
        f"""
        MATCH (poem)
        WHERE {poem_label} IN labels(poem)
          AND (
            coalesce(poem.text, "") CONTAINS {query_literal}
            OR coalesce(poem.title, "") CONTAINS {query_literal}
            OR coalesce(poem.name, "") CONTAINS {query_literal}
          )
        OPTIONAL MATCH (author:`作者`)-[:`创作`]->(poem)
        OPTIONAL MATCH (author)-[:`包含介绍`]->(intro:`介绍`)
        RETURN
          coalesce(author.dynasty, intro.dynasty, "") AS dynasty,
          coalesce(author.name, "") AS author,
          coalesce(poem.title, poem.name, "") AS title,
          coalesce(poem.text, "") AS text,
          coalesce(poem.rhythmic, "") AS rhythmic,
          coalesce(poem.sourceFile, "") AS sourceFile,
          coalesce(intro.text, intro.desc, intro.name, intro.content, intro.description, "") AS introduction
        LIMIT {max(limit, 1)}
        """
    )


def _query_imported_poetry_by_chars(query: str, limit: int) -> list[dict[str, Any]]:
    chars = [ch for ch in _chars(query) if "\u4e00" <= ch <= "\u9fff"]
    if not chars:
        return []

    char_literals = "[" + ", ".join(_cypher_string(ch) for ch in chars[:8]) + "]"
    min_hits = max(2, min(3, len(chars) // 2 or 1))
    poem_label = _cypher_string(_POEM_LABEL)
    return _query_neo4j(
        f"""
        WITH {char_literals} AS chars
        MATCH (poem)
        WHERE {poem_label} IN labels(poem)
        WITH poem, chars,
             coalesce(poem.text, "") + " " + coalesce(poem.title, "") + " " + coalesce(poem.name, "") AS target
        WITH poem, size([ch IN chars WHERE target CONTAINS ch]) AS hitCount
        WHERE hitCount >= {min_hits}
        OPTIONAL MATCH (author:`作者`)-[:`创作`]->(poem)
        OPTIONAL MATCH (author)-[:`包含介绍`]->(intro:`介绍`)
        RETURN
          coalesce(author.dynasty, intro.dynasty, "") AS dynasty,
          coalesce(author.name, "") AS author,
          coalesce(poem.title, poem.name, "") AS title,
          coalesce(poem.text, "") AS text,
          coalesce(poem.rhythmic, "") AS rhythmic,
          coalesce(poem.sourceFile, "") AS sourceFile,
          coalesce(intro.text, intro.desc, intro.name, intro.content, intro.description, "") AS introduction,
          hitCount
        ORDER BY hitCount DESC
        LIMIT {max(limit, 1)}
        """
    )


def _imported_row_to_poem(row: dict[str, Any]) -> dict[str, str]:
    title = _normalize_text(row.get("title"))
    rhythmic = _normalize_text(row.get("rhythmic"))
    source_file = _normalize_text(row.get("sourceFile"))
    keywords = " ".join(part for part in [rhythmic, source_file] if part)
    return {
        "dynasty": _normalize_text(row.get("dynasty")),
        "book": "",
        "author": _normalize_text(row.get("author")),
        "title": title,
        "text": _normalize_text(row.get("text")),
        "translation": "",
        "introduction": _normalize_introduction(row.get("introduction")),
        "keywords": keywords,
        "searchText": " ".join(
            _normalize_text(row.get(key))
            for key in ["title", "text", "rhythmic", "author", "dynasty", "sourceFile", "introduction"]
        ),
    }


def _search_imported_poetry(query: str, conf_key: str, size: int) -> list[dict[str, Any]]:
    candidate_limit = max(size * 200, 1000)
    rows = _query_imported_poetry_by_exact_text(query, candidate_limit)
    if len(rows) < size:
        seen = {(row.get("title"), row.get("text"), row.get("author")) for row in rows}
        for row in _query_imported_poetry_by_chars(query, candidate_limit):
            key = (row.get("title"), row.get("text"), row.get("author"))
            if key not in seen:
                rows.append(row)
                seen.add(key)

    results = []
    min_score = 0.24 if conf_key == "chinese-poetry" else 0.18
    for row in rows:
        poem = _imported_row_to_poem(row)
        if conf_key == "chinese-poetry":
            target = " ".join([poem["searchText"], poem["title"], poem["text"], poem["author"]])
            value = value_for_chinese_search(poem)
            score = _score(query, target)
        else:
            target = " ".join([poem["text"], poem["keywords"], poem["title"], poem["author"]])
            value = value_for_classical_search(poem)
            score = _classical_score(query, target)

        if score >= min_score:
            results.append({"value": value, "score": float(score)})

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: max(size, 1)]


def _search_classical_texts(query: str, conf_key: str, size: int) -> list[dict[str, Any]]:
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
            score = _score(query, target)
        else:
            target = " ".join([poem["text"], poem["keywords"], poem["title"], poem["author"]])
            value = value_for_classical_search(poem)
            score = _classical_score(query, target)

        if score >= min_score:
            results.append({"value": value, "score": float(score)})

    results.sort(key=lambda item: item["score"], reverse=True)
    return results[: max(size, 1)]


def neo4j_search(query: str, conf_key: str, size: int) -> list[dict[str, Any]]:
    results = _search_imported_poetry(query, conf_key, size)
    if results:
        return results

    return _search_classical_texts(query, conf_key, size)
