# -*- coding: utf-8 -*-
# @Time    : 2024/2/19 11:07
# @Author  : nongbin
# @FileName: webui.py
# @Software: PyCharm
# @Affiliation: tfswufe.edu.cn
import os

import gradio as gr

from config.config import Config
from env import get_app_root
from qa.bot import ChatBot

__AVATAR = (os.path.join(get_app_root(), "resource/avatar/user.png"),
            os.path.join(get_app_root(), "resource/avatar/libai.jpeg"))


def run_webui():
    chat_app = gr.ChatInterface(
        ChatBot().chat,
        chatbot=gr.Chatbot(height=700, avatar_images=__AVATAR),
        textbox=gr.Textbox(placeholder="请输入你的问题", container=False, scale=7),
        title="「古人有话说」📒",
        description="你可以问古代人物、诗词典故和传统文化",
        theme="default",
        examples=["您好", "李白与高力士的关系是什么", "杜甫是谁", "李白会写代码吗", "请生成李白在江边喝酒的图片",
                  "你认为杜甫最好的一首诗是哪一首？", "请将这首诗转成语音", "请将这首诗转成语音,语种设置为陕西话","根据参考文献回答，李白在哪里出生",
                  "请根据以下白话文来搜索相应的古文，白话文的内容为，守孝期在古代是多长",
                  "请根据以下古文来搜索相应的古文，古文的内容为，床前明月光","请总结上述内容，然后生成ppt","/飞花令","/退出游戏"],
        cache_examples=False,
        retry_btn=None,
        submit_btn="发送",
        stop_btn="停止",
        undo_btn="删除当前",
        clear_btn="清除所有",
        concurrency_limit=4,
    )

    chat_app.launch(server_name=Config.get_instance().get_with_nested_params("server", "ui_host")
                    , server_port=int(Config.get_instance().get_with_nested_params("server", "ui_port"))
                    , share=Config.get_instance().get_with_nested_params("server", "ui_share")
                    , max_threads=10)


if __name__ == "__main__":
    run_webui()
