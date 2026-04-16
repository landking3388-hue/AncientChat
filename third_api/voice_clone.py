# -*- coding: utf-8 -*-
# @Time    : 2025/5/14 15:35
# @Author  : Bin_NONG
# @FileName: voice_clone.py
# @Software: PyCharm
# @Affiliation: xxx

import os
import uuid

import requests

from config.config import Config
from env import get_app_root

_OUTPUT_DIR = os.path.join(get_app_root(), "data/cache/clone")

# 如果文件夹路径不存在，先创建
if not os.path.exists(_OUTPUT_DIR):
    os.makedirs(_OUTPUT_DIR)


def generate(
        ref_audio: str,
        gen_text: str,
) -> str:
    """
    Generate speech using the F5-TTS API.

    Args:
        ref_audio: Specify reference audio
        gen_text: Text to generate speech for

    Returns:
        bool: True on success, False on failure
    """

    ref_audio_conf = Config.get_instance().get_with_nested_params("lang-chain"
                                                                  , "audio"
                                                                  , "voice"
                                                                  , "clone"
                                                                  , ref_audio.strip())
    api_url = Config.get_instance().get_with_nested_params("third_api", "voice_clone")
    ref_audio = ref_audio_conf["audio"]
    ref_text = ref_audio_conf["text"]

    print(f"Sending TTS request to {api_url}...")
    print(f"Reference text: {ref_text}")
    print(f"Generating: {gen_text}")

    data = {
        "ref_audio": ref_audio,
        "ref_text": ref_text,
        "gen_text": gen_text
    }

    # Make the request
    response = requests.post(f"{api_url}/tts/", json=data)

    # Check response
    if response.status_code != 200:
        print(f"Error: {response.status_code}")
        print(response.text)
        return ""
    # Save the audio file
    output_path = os.path.join(_OUTPUT_DIR, f"{uuid.uuid4()}.wav")
    with open(output_path, "wb") as f:
        f.write(response.content)

    print(f"Success! Audio saved to {output_path}")
    print(f"Seed: {response.headers.get('X-Seed')}")
    return output_path


if __name__ == "__main__":

    # Set parameters directly in the code
    GEN_TEXT = "我说 你是人间的四月天；笑响点亮了四面风；轻灵在春的光艳中交舞着变。你是四月早天里的云烟，黄昏吹着风的软，星子在无意中闪，细雨点洒在花前。"

    # Change these values as needed for your specific use case

    generate(
        ref_audio="许静",
        gen_text=GEN_TEXT,
    )
