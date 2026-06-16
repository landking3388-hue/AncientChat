# -*- coding: utf-8 -*-
# @Time    : 2024/4/12 22:26
# @Author  : nongbin
# @FileName: poetry_search.py
# @Software: PyCharm
# @Affiliation: tfswufe.edu.cn
import json
import os
import re
from typing import List

import requests
from icecream import ic

from logger import Logger
from lang_chain.local_poetry_search import local_search
from lang_chain.neo4j_poetry_search import neo4j_search

__logger = Logger(__name__)
_DEFAULT_POETRY_SEARCH_URL = "http://127.0.0.1:18880/api/search/nl"
_POETRY_SEARCH_URL = os.environ.get("POETRY_SEARCH_URL", _DEFAULT_POETRY_SEARCH_URL)
_POETRY_SEARCH_TIMEOUT = float(os.environ.get("POETRY_SEARCH_TIMEOUT", "10"))
_POETRY_RESULT_SIZE = 5
_MAX_REWRITE_KEYWORDS = 6


def __table2markdown(table: List[List]) -> str:
    # the first row is the header
    header = [__clean_markdown_cell(cell) for cell in table[0]]
    # the rest are the rows
    rows = table[1:]

    # create a Markdown table
    markdown_table = "| " + " | ".join(header) + " |\n| " + " | ".join(["---"] * len(header)) + " |"

    # add rows
    for row in rows:
        normalized_row = [__clean_markdown_cell(cell) for cell in row[:len(header)]]
        if len(normalized_row) < len(header):
            normalized_row.extend([""] * (len(header) - len(normalized_row)))
        markdown_table += "\n| " + " | ".join(normalized_row) + " |"

    return markdown_table


def __clean_markdown_cell(value: object) -> str:
    text = str(value).strip()
    return text.replace("|", "，").replace("\r", " ").replace("\n", " ")


def __request_poetry_search(data: dict) -> dict | None:
    try:
        resp = requests.post(
            _POETRY_SEARCH_URL,
            data=json.dumps(data, ensure_ascii=False),
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=_POETRY_SEARCH_TIMEOUT,
        )
    except requests.RequestException as exc:
        __logger.error(f"poetry search service unavailable: {_POETRY_SEARCH_URL}, error: {exc}")
        return None

    if resp.status_code != 200:
        __logger.error(f"poetry search failed, status_code: {resp.status_code}, body: {resp.text[:200]}")
        return None

    try:
        return resp.json()
    except ValueError as exc:
        __logger.error(f"poetry search returned invalid json: {exc}, body: {resp.text[:200]}")
        return None


def __service_unavailable_message() -> str:
    return (
        "古文检索服务暂时不可用，请确认 POETRY_SEARCH_URL 对应的服务已经启动并且当前网络可以访问。"
        f"\n\n当前检索服务地址：`{_POETRY_SEARCH_URL}`"
    )


def __local_search_response(data: dict) -> dict:
    text = data.get("text", "")
    conf_key = data.get("conf_key", "chinese-classical")
    size = int(data.get("size", _POETRY_RESULT_SIZE) or _POETRY_RESULT_SIZE)
    values = neo4j_search(text, conf_key, size)
    if not values:
        values = local_search(text, conf_key, size)

    return {
        "retCode": 0,
        "errMsg": None,
        "values": values,
    }


def __build_chinese_search_intro(query: str) -> str:
    return f"已根据“{query}”检索到以下相关古文，可作为理解或引用依据："


def __format_source(book: str, title: str) -> str:
    if book and title:
        return f"{book}·{title}"
    return book or title


def __parse_poetry_result(value: str) -> list[str]:
    row = value.replace("|", "，").split("##@##")
    if len(row) < 5:
        row.extend([""] * (5 - len(row)))
    return [row[0], row[1], row[2], row[3], row[4]]


def __truncate_text(text: str, limit: int = 260) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "..."


def __strip_fenced_code(text: str) -> str:
    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    return fenced_match.group(1).strip() if fenced_match else text.strip()


def __dedupe_texts(items: List[str], limit: int | None = None) -> list[str]:
    results = []
    seen = set()
    for item in items:
        value = str(item or "").strip().strip("[]()（）【】\"'“”‘’` ")
        if not value or value in seen:
            continue
        seen.add(value)
        results.append(value)
        if limit and len(results) >= limit:
            break
    return results


def __parse_rewrite_keywords(raw_text: str | None, fallback: str) -> list[str]:
    if not raw_text:
        return [fallback]

    text = __strip_fenced_code(raw_text)
    parsed_items = []

    try:
        parsed_json = json.loads(text)
        if isinstance(parsed_json, list):
            parsed_items = [str(item) for item in parsed_json]
        elif isinstance(parsed_json, dict):
            for key in ["keywords", "queries", "检索词", "关键词"]:
                value = parsed_json.get(key)
                if isinstance(value, list):
                    parsed_items = [str(item) for item in value]
                    break
                if isinstance(value, str):
                    parsed_items = re.split(r"[\n,，、;；]+", value)
                    break
    except ValueError:
        parsed_items = []

    if not parsed_items:
        cleaned_text = re.sub(r"^(输出|关键词|检索词)\s*[:：]\s*", "", text.strip())
        parsed_items = re.split(r"[\n,，、;；]+", cleaned_text)

    normalized = []
    for item in parsed_items:
        item = re.sub(r"^\s*[-*•\d.、)）]+\s*", "", str(item))
        item = re.sub(r"^(关键词|检索词)\s*[:：]\s*", "", item.strip())
        item = item.strip().strip("[]()（）【】\"'“”‘’` ")
        if item:
            normalized.append(item)

    return __dedupe_texts(normalized or [fallback], _MAX_REWRITE_KEYWORDS)


def rewrite_chinese_to_classical_queries(chinese_sentence: str) -> list[str]:
    prompt = f"""请把用户的白话问题转换成适合检索古籍、古文资料的关键词。

要求：
1. 不要回答问题，只提取检索词。
2. 优先输出能直接命中古文内容的古代制度名、礼制名、典籍常见表达、同义古代表达。
3. 关键词应短而准，避免整句白话。
4. 只输出 JSON 数组，例如 ["孝期", "守孝", "丁忧", "三年之丧", "居丧"]。

用户问题：
{chinese_sentence}
"""
    try:
        from lang_chain.client.client_factory import ClientFactory

        raw_keywords = ClientFactory().get_client().chat_with_ai(prompt)
    except Exception as exc:
        __logger.warning(f"rewrite chinese query failed, fallback to original query: {exc}")
        return [chinese_sentence]

    keywords = __parse_rewrite_keywords(raw_keywords, chinese_sentence)
    __logger.info(f"poetry rewrite query: question={chinese_sentence}, keywords={keywords}")
    return keywords


def __get_poetry_search_response(data: dict) -> dict:
    resp_json = __local_search_response(data)
    if resp_json.get("values"):
        return resp_json

    service_resp = __request_poetry_search(data)
    return service_resp or resp_json


def __build_search_request(query: str, conf_key: str, searcher: int, size: int = _POETRY_RESULT_SIZE) -> dict:
    return {
        "text": query,
        "conf_key": conf_key,
        "group": "default",
        "size": size,
        "searcher": searcher,
    }


def __search_values_by_queries(queries: List[str], conf_key: str, searcher: int) -> list[dict]:
    results_by_value: dict[str, dict] = {}
    for query in queries:
        data = __build_search_request(query, conf_key, searcher)
        ic(data)
        resp_json = __get_poetry_search_response(data)
        for item in resp_json.get("values", []):
            value = item.get("value", "")
            if not value:
                continue
            score = float(item.get("score", 0) or 0)
            if value not in results_by_value:
                results_by_value[value] = {
                    "value": value,
                    "score": score,
                    "matched_queries": [query],
                }
                continue

            cached = results_by_value[value]
            cached["score"] = max(cached["score"], score)
            if query not in cached["matched_queries"]:
                cached["matched_queries"].append(query)

    results = list(results_by_value.values())
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:_POETRY_RESULT_SIZE]


def __build_result_table(results: list[dict]) -> str:
    data_resp = [["命中词", "朝代", "作者", "古文内容", "篇名", "介绍"]]
    for item in results[:_POETRY_RESULT_SIZE]:
        row = __parse_poetry_result(item["value"])
        matched_query = "、".join(item.get("matched_queries", [])[:3])
        data_resp.append([matched_query, row[0], row[1], row[2], row[3], row[4]])

    return __table2markdown(data_resp)


def __format_sources_for_prompt(results: list[dict]) -> str:
    sources = []
    for index, item in enumerate(results[:_POETRY_RESULT_SIZE], 1):
        dynasty, author, text, title, introduction = __parse_poetry_result(item["value"])
        sources.append(
            "\n".join([
                f"[{index}] 命中词：{'、'.join(item.get('matched_queries', []))}",
                f"朝代：{dynasty}",
                f"作者：{author}",
                f"篇名：{title}",
                f"古文：{__truncate_text(text, 360)}",
                f"说明：{__truncate_text(introduction, 220)}",
            ])
        )
    return "\n\n".join(sources)


def __generate_chain_answer(question: str, keywords: list[str], results: list[dict]) -> str | None:
    if not results:
        return None

    prompt = f"""你是古代文学与古代文化问答助手。系统已经把用户白话问题转换成古文检索词，并检索到古文依据。

请根据“古文依据”完成链路回答：
1. 先说明你理解到的检索意图。
2. 将最相关的古文依据翻译或解释成白话文。
3. 再回答用户原问题。
4. 如果材料不足以确定答案，明确说明“不足以确定”，不要编造出处或结论。

要求：
- 用简洁 Markdown 输出。
- 不要重复整张表格。
- 回答要优先依据召回的古文资料。

用户问题：
{question}

LLM 转换后的检索词：
{", ".join(keywords)}

古文依据：
{__format_sources_for_prompt(results)}
"""
    try:
        from lang_chain.client.client_factory import ClientFactory

        return ClientFactory().get_client().chat_with_ai(prompt)
    except Exception as exc:
        __logger.warning(f"generate poetry chain answer failed: {exc}")
        return None


def search_by_chinese(chinese_sentence: str) -> str:
    """
    白话文搜古文
    :param chinese_sentence:
    :return:
    """
    keywords = rewrite_chinese_to_classical_queries(chinese_sentence)
    combined_query = " ".join(keywords)
    search_queries = __dedupe_texts(keywords + [combined_query], _MAX_REWRITE_KEYWORDS + 1)
    results = __search_values_by_queries(search_queries, "chinese-classical", 3)
    fallback_used = False

    if not results:
        fallback_used = True
        results = __search_values_by_queries([chinese_sentence], "chinese-poetry", 1)

    if not results:
        return "未检索到相关古文结果。"

    markdown_table = __build_result_table(results)
    chain_answer = __generate_chain_answer(chinese_sentence, keywords, results)

    chain_parts = [
        "### 检索链路",
        f"- 用户问题：{chinese_sentence}",
        f"- LLM 转换检索词：{'、'.join(keywords)}",
    ]
    if fallback_used:
        chain_parts.append("- 检索提示：转换后的古文检索词未命中结果，已回退到原白话检索。")

    chain_parts.extend([
        "",
        __build_chinese_search_intro("、".join(search_queries if not fallback_used else [chinese_sentence])),
        "",
        markdown_table,
    ])

    if chain_answer:
        chain_parts.extend(["", "### 链路回答", chain_answer])

    return "\n".join(chain_parts)


def search_by_poetry(chinese_sentence: str) -> str:
    """
    古文搜古文
    :param chinese_sentence:
    :return:
    """
    data = __build_search_request(chinese_sentence, "chinese-classical", 3)
    ic(data)
    resp_json = __get_poetry_search_response(data)

    data_resp = [["朝代", "作者", "古文内容", "篇名", "介绍"]]
    for item in resp_json.get("values", [])[:_POETRY_RESULT_SIZE]:
        data_resp.append(__parse_poetry_result(item["value"]))

    if len(data_resp) == 1:
        return "未检索到相关古文结果。"

    markdown_table = "已为你检索到以下相似古文：\n\n" + __table2markdown(data_resp)

    return markdown_table
