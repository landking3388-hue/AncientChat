# -*- coding: utf-8 -*-
# @Time    : 2024/5/12 15:22
# @Author  : nongbin
# @FileName: ppt_content_retriever.py
# @Software: PyCharm
# @Affiliation: tfswufe.edu.cn
import ast
import json
import re
from typing import Any, List, Dict

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

_HISTORY_SNIPPETS_PER_PAGE = 6
_SNIPPET_MAX_LEN = 180
_FILE_MESSAGE_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aac", ".ogg",
    ".png", ".jpg", ".jpeg", ".gif", ".webp",
    ".ppt", ".pptx", ".mp4",
}
_MEDIA_LABEL_KEYWORDS = ("图片", "图像", "语音", "音频")


def __construct_messages(question: str, history: List[List | None]) -> List[Dict[str, str]]:
    messages = [
        {"role": "system",
         "content": "你现在扮演信息抽取的角色，要求根据用户输入和AI的回答，正确提取出信息。"}]

    history_snippets = _build_history_snippets("", history)
    if history_snippets:
        messages.append({
            "role": "user",
            "content": "以下是历史对话摘要，请作为生成PPT的上下文参考：\n"
                       + json.dumps(history_snippets, ensure_ascii=False),
        })

    messages.append({"role": "user", "content": question})
    messages.append({"role": "user", "content": _GENERATE_PPT_PROMPT_})

    return messages


def generate_ppt_content(question: str,
                         history: List[List | None] | None = None) -> str:
    messages = __construct_messages(question, history or [])
    result = ClientFactory().get_client().chat_using_messages(messages)

    return result


def _looks_like_file_message(text: str) -> bool:
    normalized = text.strip().lower().split("?", 1)[0].split("#", 1)[0]
    return any(normalized.endswith(ext) for ext in _FILE_MESSAGE_EXTENSIONS)


def _has_media_label(value: Any) -> bool:
    return isinstance(value, str) and any(keyword in value for keyword in _MEDIA_LABEL_KEYWORDS)


def _clip_text(text: str, limit: int = _SNIPPET_MAX_LEN) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}..."


def _message_to_text(value: Any) -> str:
    if value is None:
        return ""

    if isinstance(value, dict):
        file_path = value.get("path") or value.get("name") or value.get("url")
        if file_path and _looks_like_file_message(str(file_path)):
            return ""
        if _has_media_label(value.get("label")):
            return ""

        parts = [
            _message_to_text(value.get(key))
            for key in ("text", "content", "label", "caption")
            if value.get(key)
        ]
        return " ".join(part for part in parts if part)

    if isinstance(value, (list, tuple)):
        if value and isinstance(value[0], str) and _looks_like_file_message(value[0]):
            return ""
        if any(_has_media_label(item) for item in value[1:]):
            return ""

        parts = [_message_to_text(item) for item in value]
        return " ".join(part for part in parts if part)

    text = str(value).strip()
    if _looks_like_file_message(text):
        return ""

    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _build_history_snippets(
        question: str,
        history: List[List | None] | None = None,
) -> List[Dict[str, str]]:
    snippets = []

    for index, item in enumerate(history or [], start=1):
        if not isinstance(item, (list, tuple)) or not item:
            continue

        user_text = _message_to_text(item[0]) if len(item) > 0 else ""
        ai_text = _message_to_text(item[1]) if len(item) > 1 else ""
        parts = []
        if user_text:
            parts.append(f"用户：{_clip_text(user_text)}")
        if ai_text:
            parts.append(f"回复：{_clip_text(ai_text)}")

        if parts:
            snippets.append({
                "title": f"第 {index} 轮对话",
                "description": "；".join(parts),
            })

    if not snippets:
        current_question = _message_to_text(question)
        if current_question:
            snippets.append({
                "title": "本轮请求",
                "description": _clip_text(current_question),
            })

    return snippets


def append_history_snippets(
        ppt_content: Dict,
        question: str,
        history: List[List | None] | None = None,
) -> Dict:
    snippets = _build_history_snippets(question, history)
    if not snippets:
        return ppt_content

    if not isinstance(ppt_content.get("pages"), list):
        ppt_content["pages"] = []

    for start in range(0, len(snippets), _HISTORY_SNIPPETS_PER_PAGE):
        title = "对话内容摘要" if start == 0 else "对话内容摘要（续）"
        ppt_content["pages"].append({
            "title": title,
            "content": snippets[start:start + _HISTORY_SNIPPETS_PER_PAGE],
        })

    return ppt_content


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
