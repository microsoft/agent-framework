# Copyright (c) Microsoft. All rights reserved.

"""Conversion of Responses input_audio parts to framework audio content."""

from agent_framework import Content
from openai.types.responses import ResponseInputAudioParam
from pydantic import TypeAdapter, ValidationError

_RESPONSE_INPUT_AUDIO_ADAPTER = TypeAdapter(ResponseInputAudioParam)


def input_audio_to_content(value: object) -> Content:
    """Validate an input_audio part and preserve its audio data without transcription."""
    try:
        audio = _RESPONSE_INPUT_AUDIO_ADAPTER.validate_python(value)["input_audio"]
    except ValidationError as exc:
        raise ValueError("Invalid input_audio: expected audio data with wav or mp3 format") from exc
    if not audio["data"]:
        raise ValueError("Invalid input_audio: audio data must not be empty")

    media_type = "audio/wav" if audio["format"] == "wav" else "audio/mpeg"
    data = audio["data"]
    uri = data if data.startswith("data:") else f"data:{media_type};base64,{data}"
    return Content.from_uri(uri=uri, media_type=media_type, name=f"recording.{audio['format']}")
