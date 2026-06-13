# -*- coding: utf-8 -*-
# @Time    : 2024/4/12 22:26
# @Author  : nongbin
# @FileName: poetry_search.py
# @Software: PyCharm
# @Affiliation: tfswufe.edu.cn
import json
import os
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
    size = int(data.get("size", 5) or 5)
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


def search_by_chinese(chinese_sentence: str) -> str:
    """
    白话文搜古文
    :param chinese_sentence:
    :return:
    """
    data = {
        "text": chinese_sentence,
        "conf_key": "chinese-poetry",
        "group": "default",
        "size": 3,
        "searcher": 1
    }
    ic(data)
    resp_json = __request_poetry_search(data)
    if resp_json is None:
        resp_json = __local_search_response(data)

    data_resp = [["来源", "相关古文", "说明"]]
    for item in resp_json.get("values", [])[:3]:
        row = item['value'].split("##@##")
        if len(row) >= 4:
            data_resp.append([__format_source(row[0], row[1]), row[2], row[3]])

    if len(data_resp) == 1:
        return "未检索到相关古文结果。"

    markdown_table = __build_chinese_search_intro(chinese_sentence) + "\n\n" + __table2markdown(data_resp)

    return markdown_table


def search_by_poetry(chinese_sentence: str) -> str:
    """
    古文搜古文
    :param chinese_sentence:
    :return:
    """
    data = {
        "text": chinese_sentence,
        "conf_key": "chinese-classical",
        "group": "default",
        "size": 10,
        "searcher": 3
    }
    ic(data)
    resp_json = __request_poetry_search(data)
    if resp_json is None:
        resp_json = __local_search_response(data)

    data_resp = [["作者", "完整诗篇", "篇名", "关键词"]]
    for item in resp_json.get("values", []):
        row = item['value'].replace("|", "，").split("##@##")[1:]
        # row.append(item['score'])
        data_resp.append(row)

    if len(data_resp) == 1:
        return "未检索到相关古文结果。"

    markdown_table = "已为你检索到以下相似古文：\n\n" + __table2markdown(data_resp)

    return markdown_table
