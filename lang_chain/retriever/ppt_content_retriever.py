# -*- coding: utf-8 -*-
# @Time    : 2024/5/12 15:22
# @Author  : nongbin
# @FileName: ppt_content_retriever.py
# @Software: PyCharm
# @Affiliation: tfswufe.edu.cn
import json
import ast
import re
from typing import List, Dict

from lang_chain.client.client_factory import ClientFactory

# 输出格式
__output_format = json.dumps({
    "title": "example title",
    "pages": [
        {
            "title": "title for page 1",
            "content": [
                {
                    "title": "title for paragraph 1",
                    "description": "detail for paragraph 1",
                },
                {
                    "title": "title for paragraph 2",
                    "description": "detail for paragraph 2",
                },
            ],
        },
        {
            "title": "title for page 2",
            "content": [
                {
                    "title": "title for paragraph 1",
                    "description": "detail for paragraph 1",
                },
                {
                    "title": "title for paragraph 2",
                    "description": "detail for paragraph 2",
                },
                {
                    "title": "title for paragraph 3",
                    "description": "detail for paragraph 3",
                },
            ],
        },
    ],
}, ensure_ascii=True)

_GENERATE_PPT_PROMPT_ = f'''请你根据用户要求生成ppt的详细内容，使用中文，不要省略内容。
必须按这个JSON格式输出{__output_format}。
只能返回严格JSON，不要用```包裹，不要返回markdown格式，不要添加解释文字。
JSON对象的属性名和字符串值必须使用英文双引号，不要使用单引号，不要添加尾随逗号。'''


def __construct_messages(question: str, history: List[List | None]) -> List[Dict[str, str]]:
    messages = [
        {"role": "system",
         "content": "你现在扮演信息抽取的角色，要求根据用户输入和AI的回答，正确提取出信息。"}]

    for user_input, ai_response in history:
        messages.append({"role": "user", "content": user_input})
        messages.append(
            {"role": "assistant", "content": repr(ai_response)})

    messages.append({"role": "user", "content": question})
    messages.append({"role": "user", "content": _GENERATE_PPT_PROMPT_})

    return messages


def generate_ppt_content(question: str,
                         history: List[List | None] | None = None) -> str:
    messages = __construct_messages(question, history or [])
    result = ClientFactory().get_client().chat_using_messages(messages)

    return result


def _extract_json_text(raw_text: str) -> str:
    text = (raw_text or "").strip()
    fenced_match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced_match:
        text = fenced_match.group(1).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        text = text[start:end + 1]

    return text


def parse_ppt_content(raw_text: str) -> Dict:
    json_text = _extract_json_text(raw_text)
    candidates = [
        json_text,
        re.sub(r",\s*([}\]])", r"\1", json_text),
    ]

    last_error = None
    for candidate in candidates:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc

    try:
        parsed = ast.literal_eval(candidates[-1])
        if isinstance(parsed, dict):
            return parsed
    except (SyntaxError, ValueError) as exc:
        last_error = exc

    preview = json_text[:200].replace("\n", "\\n")
    raise ValueError(f"PPT内容不是合法JSON，无法解析。输出片段：{preview}") from last_error
