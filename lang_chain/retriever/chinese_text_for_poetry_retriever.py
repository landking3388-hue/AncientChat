# -*- coding: utf-8 -*-
# @Time    : 2024/4/13 11:50
# @Author  : nongbin
# @FileName: chinese_text_for_poetry_retriever.py
# @Software: PyCharm
# @Affiliation: tfswufe.edu.cn

import re
from typing import List, Dict, Literal

from lang_chain.client.client_factory import ClientFactory
from qa.custom_tool_calling.question_type import QuestionType

__CHINESE2POETRY_PROMPT_ = "请从上述对话中帮我提取出以白话文搜古文对应的文本内容，不要解释，不要多余的信息，只需要提取出原文中对应的内容。"
__POETRY2POETRY_PROMPT_ = "请从上述对话中帮我提取出以古文搜古文对应的文本内容，不要解释，不要多余的信息，只需要提取出原文中对应的内容。"


def __extract_direct_text(question: str,
                          choose_prompt: Literal['chinese2poetry', 'poetry2poetry']) -> str | None:
    if choose_prompt == "chinese2poetry":
        markers = [
            "白话文的内容为",
            "白话文内容为",
            "白话内容为",
            "现代文的内容为",
        ]
    else:
        markers = [
            "古文的内容为",
            "古文内容为",
            "原文的内容为",
            "原文内容为",
        ]

    for marker in markers + ["内容为", "内容是"]:
        pattern = re.escape(marker) + r"\s*[，,：:\s]*\s*(.+)$"
        match = re.search(pattern, question, flags=re.S)
        if match:
            text = match.group(1).strip()
            return text.strip("。；;，,：: \n\t") or None

    return None


def __construct_messages(question: str,
                         choose_prompt: Literal['chinese2poetry', 'poetry2poetry'],
                         history: List[List | None]) -> List[Dict[str, str]]:
    messages = [
        {"role": "system",
         "content": "你现在扮演信息抽取的角色，要求根据用户输入和AI的回答，正确提取出信息，无需包含提示文字"}]

    for user_input, ai_response in (history or [])[-3:]:
        ai_text = repr(ai_response)
        if len(ai_text) > 800:
            ai_text = ai_text[:800] + "...[已截断]"
        messages.append({"role": "user", "content": user_input})
        messages.append({"role": "assistant", "content": ai_text})

    messages.append({"role": "user", "content": question})
    messages.append({"role": "user",
                     "content": __CHINESE2POETRY_PROMPT_ if choose_prompt == "chinese2poetry"
                     else __POETRY2POETRY_PROMPT_})

    return messages


def extract_text(question: str,
                 choose_prompt: Literal['chinese2poetry', 'poetry2poetry'],
                 history: List[List | None] | None = None,
                 ) -> str:
    direct_text = __extract_direct_text(question, choose_prompt)
    if direct_text:
        return direct_text

    messages = __construct_messages(question, choose_prompt, history or [])
    result = ClientFactory().get_client().chat_using_messages(messages)

    return result
