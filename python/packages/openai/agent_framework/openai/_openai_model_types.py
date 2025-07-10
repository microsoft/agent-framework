# Copyright (c) Microsoft. All rights reserved.

from enum import Enum


class OpenAIModelTypes(Enum):
    """OpenAI model types, can be text, chat or embedding."""

    CHAT = "chat"
    EMBEDDING = "embedding"
    TEXT_TO_IMAGE = "text-to-image"
    SPEECH_TO_TEXT = "speech-to-text"
    TEXT_TO_SPEECH = "text-to-speech"
    REALTIME = "realtime"
    RESPONSE = "response"
