# Copyright (c) Microsoft. All rights reserved.

"""Audio format helpers for DevUI input_audio conversion."""

from typing import Literal

from openai.types.responses import ResponseInputAudioParam
from pydantic import TypeAdapter, ValidationError
from typing_extensions import TypedDict

InputAudioFormat = Literal["wav", "mp3"]

_MP3_MEDIA_TYPES = {
    "audio/mp3",
    "audio/mpeg",
    "audio/x-mpeg",
    "audio/mpeg3",
    "audio/x-mpeg-3",
}


class _RawInputAudio(TypedDict, total=False):
    format: object


class _RawInputAudioParam(TypedDict, total=False):
    input_audio: _RawInputAudio


_RESPONSE_INPUT_AUDIO_ADAPTER = TypeAdapter(ResponseInputAudioParam)
_RAW_INPUT_AUDIO_ADAPTER = TypeAdapter(_RawInputAudioParam)


def media_type_for_input_audio_format(audio_format: object) -> str | None:
    """Return the media type for a supported Responses input_audio format."""
    if audio_format == "wav":
        return "audio/wav"
    if audio_format == "mp3":
        return "audio/mpeg"
    return None


def input_audio_format_for_media_type(media_type: str | None) -> InputAudioFormat | None:
    """Return the Responses input_audio format for a supported media type."""
    normalized_media_type = media_type.partition(";")[0].strip().lower() if media_type else ""
    if "wav" in normalized_media_type:
        return "wav"
    if normalized_media_type in _MP3_MEDIA_TYPES:
        return "mp3"
    return None


def input_audio_data_uri(audio_data: str, media_type: str) -> str:
    """Return a data URI for raw base64 audio or preserve an existing data URI."""
    return audio_data if audio_data.startswith("data:") else f"data:{media_type};base64,{audio_data}"


def parse_input_audio_param(value: object) -> ResponseInputAudioParam | None:
    """Return a validated Responses input_audio payload, if the value matches that shape."""
    try:
        audio_content = _RESPONSE_INPUT_AUDIO_ADAPTER.validate_python(value)
    except ValidationError:
        return None

    if not audio_content["input_audio"]["data"]:
        return None

    return audio_content


def input_audio_format_for_error(value: object) -> object | None:
    """Return the supplied input_audio format for error messages, if present."""
    try:
        audio_content = _RAW_INPUT_AUDIO_ADAPTER.validate_python(value)
    except ValidationError:
        return None

    return audio_content.get("input_audio", {}).get("format")
