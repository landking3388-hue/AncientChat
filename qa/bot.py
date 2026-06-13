# -*- coding: utf-8 -*-
# @Time    : 2024/8/21 17:56
# @Author  : nongbin
# @FileName: bot.py
# @Software: PyCharm
# @Affiliation: tfswufe.edu.cn
from pathlib import Path
from typing import Any, Literal, TypeAlias, List

from config.config import Config
from lang_chain.poetry_game import GameMode, PoetryGame
from qa.custom_tool_calling.interaction import chat_libai as chat_libai_by_custom_agent
from qa.supported_tool_calling.interaction import chat_libai as chat_libai_by_supported_agent
from utils.singleton import Singleton

Parser: TypeAlias = Literal['custom', 'tool_calling']

_FILE_MESSAGE_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ppt", ".pptx", ".png", ".jpg", ".jpeg", ".gif", ".mp4"}


def _is_missing_local_file(value: Any) -> bool:
    if not isinstance(value, str) or value.startswith(("http://", "https://")):
        return False

    path = Path(value)
    if path.suffix.lower() not in _FILE_MESSAGE_EXTENSIONS:
        return False

    return not path.exists()


def _sanitize_cached_file_message(value: Any) -> Any:
    if isinstance(value, tuple) and len(value) >= 1 and _is_missing_local_file(value[0]):
        label = str(value[1]) if len(value) > 1 and value[1] else "文件"
        return f"{label}缓存文件已被清理，请重新生成。"

    if isinstance(value, dict):
        path = value.get("path") or value.get("name")
        if _is_missing_local_file(path):
            return "缓存文件已被清理，请重新生成。"

    return value


def _sanitize_history(history: List[List[Any] | None] | None) -> List[List[Any] | None] | None:
    if not history:
        return history

    for item in history:
        if isinstance(item, list) and len(item) >= 2:
            item[1] = _sanitize_cached_file_message(item[1])

    return history


class ChatBot(object, metaclass=Singleton):
    """
    聊天机器人,供gradio调用
    """

    __GAME_INSTRUCTION_DISPLAY = {"/飞花令": GameMode.FOG_MODEL}
    __GAME_EXIT_INSTRUCTION = {"/退出游戏", "/游戏结束", "/结束游戏"}

    def __init__(self):
        self.question_parser: Parser = (
            Config.get_instance().get_with_nested_params("lang-chain", "question_parse"))
        self.game_mode = None

    def chat(self,
             message: str,
             history: List[List[str] | None] | None = None,
             ):
        history = _sanitize_history(history)

        if message.strip() in self.__GAME_EXIT_INSTRUCTION:
            self.game_mode = None
            yield from PoetryGame().end_game()

        elif self.game_mode is not None:
            yield from PoetryGame().play(message, history, self.game_mode)

        elif message.strip() in self.__GAME_INSTRUCTION_DISPLAY:
            self.game_mode = self.__GAME_INSTRUCTION_DISPLAY[message]
            game = PoetryGame()
            yield from game.start_game(self.game_mode)

        elif self.question_parser == 'custom':
            yield from chat_libai_by_custom_agent(message, history)

        elif self.question_parser == 'tool_calling':
            yield from chat_libai_by_supported_agent(message, history)

        else:
            raise ValueError(f"{self.question_parser} is not supported for question parser")
