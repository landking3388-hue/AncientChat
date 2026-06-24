# -*- coding: utf-8 -*-
import json
import re
from typing import Any

from dao.graph.graph_dao import GraphDao

_NON_AUTHOR_NAMES = {"你", "您", "我", "自己", "你自己", "我自己", "大家", "我们", "AI", "ai", "机器人"}


def _cypher_string(value: str) -> str:
    return json.dumps(value or "", ensure_ascii=False)


def _clean_text(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(_clean_text(item) for item in value if item)
    return str(value or "").strip()


def _first_non_empty(*values: Any) -> str:
    for value in values:
        text = _clean_text(value)
        if text and text not in {"无相关数据", "暂无数据", "暂无", "None", "null"}:
            return text
    return ""


def _dedupe_sentences(text: str) -> str:
    text = _clean_text(text)
    if not text:
        return ""

    sentences = re.findall(r"[^。！？!?；;]+[。！？!?；;]?", text)
    if len(sentences) <= 1:
        return text

    result = []
    seen = set()
    for sentence in sentences:
        sentence = sentence.strip()
        normalized = re.sub(r"\s+", "", sentence)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(sentence)

    return "".join(result) or text


def _is_valid_author_name(name: str | None) -> bool:
    name = _clean_text(name)
    return bool(2 <= len(name) <= 4 and name not in _NON_AUTHOR_NAMES and re.fullmatch(r"[\u4e00-\u9fff]+", name))


def extract_author_name(question: str, entities: list[Any] | None = None) -> str | None:
    text = _clean_text(question)
    patterns = [
        r"(?:请)?(?:介绍一下|介绍|简介|说说|讲讲)(?:诗人|作者)?(?P<name>[\u4e00-\u9fff]{2,4})(?=$|[，。？！?、\s]|的(?:生平|简介|资料|介绍))",
        r"(?:谁是|何为)(?P<name>[\u4e00-\u9fff]{2,4})(?=$|[，。？！?、\s])",
        r"(?P<name>[\u4e00-\u9fff]{2,4})(?:是谁|是何人|是什么人)(?=$|[，。？！?、\s])",
        r"(?:诗人|作者)(?P<name>[\u4e00-\u9fff]{2,4})(?:是谁|是何人|是什么人)(?=$|[，。？！?、\s])",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match and _is_valid_author_name(match.group("name")):
            return match.group("name")

    cleaned = re.sub(
        r"(请|帮我|介绍一下|介绍|简介|说说|讲讲|谁是|是谁|是何人|是什么人|诗人|作者|一下|的资料|资料|[，。？！?、\s])",
        "",
        text,
    )
    if text != cleaned and _is_valid_author_name(cleaned):
        return cleaned
    return None


def is_author_profile_question(question: str) -> bool:
    return extract_author_name(question) is not None


def query_author_profile(name: str, dao: GraphDao | None = None) -> dict[str, str] | None:
    name = _clean_text(name)
    if not name:
        return None

    graph_dao = dao or GraphDao()
    name_literal = _cypher_string(name)
    query = f"""
    MATCH (person)
    WHERE person.name = {name_literal}
      AND any(label IN labels(person) WHERE label IN ["人物", "作者", "Author"])
    OPTIONAL MATCH (person)-[:`包含介绍`]->(intro:`介绍`)
    WITH person, intro, coalesce(intro.desc, intro.text, intro.name, person.desc, "") AS introduction
    RETURN
      person.name AS name,
      labels(person) AS labels,
      introduction AS introduction,
      coalesce(person.dynasty, "") AS dynasty,
      coalesce(person.DynastyBirth, "") AS dynastyBirth,
      coalesce(person.DynastyDeath, "") AS dynastyDeath,
      coalesce(person.birth, person.birthYear, person.BirthYear, "") AS birth,
      coalesce(person.death, person.deathYear, person.DeathYear, "") AS death,
      coalesce(person.sourceFile, "") AS sourceFile
    ORDER BY
      CASE WHEN introduction <> "" THEN 0 ELSE 1 END,
      CASE WHEN intro IS NULL THEN 1 ELSE 0 END,
      CASE WHEN "Author" IN labels(person) OR "作者" IN labels(person) THEN 0 ELSE 1 END
    LIMIT 1
    """
    cursor = graph_dao.run_cypher(query)
    if cursor is None:
        return None

    rows = cursor.data()
    if not rows:
        return None

    row = rows[0]
    return {
        "name": _first_non_empty(row.get("name"), name),
        "introduction": _dedupe_sentences(_first_non_empty(row.get("introduction"))),
        "dynasty": _first_non_empty(row.get("dynasty")),
        "dynastyBirth": _first_non_empty(row.get("dynastyBirth")),
        "dynastyDeath": _first_non_empty(row.get("dynastyDeath")),
        "birth": _first_non_empty(row.get("birth")),
        "death": _first_non_empty(row.get("death")),
        "sourceFile": _first_non_empty(row.get("sourceFile")),
    }


def format_author_profile(name: str, profile: dict[str, str] | None) -> str | None:
    if not profile:
        return None

    display_name = _first_non_empty(profile.get("name"), name)
    intro = _dedupe_sentences(_first_non_empty(profile.get("introduction")))
    dynasty = _first_non_empty(profile.get("dynasty"))
    birth = _first_non_empty(profile.get("birth"), profile.get("dynastyBirth"))
    death = _first_non_empty(profile.get("death"), profile.get("dynastyDeath"))

    lines = [f"### {display_name}"]
    meta_parts = []
    if dynasty:
        meta_parts.append(f"朝代：{dynasty}")
    if birth or death:
        meta_parts.append(f"生卒：{birth or '不详'}—{death or '不详'}")
    if meta_parts:
        lines.append("，".join(meta_parts))

    if intro:
        lines.append(intro)
    else:
        lines.append("数据库中暂未提供该作者的详细介绍。")

    return "\n\n".join(lines)


def get_author_profile_answer(name: str) -> str | None:
    return format_author_profile(name, query_author_profile(name))
