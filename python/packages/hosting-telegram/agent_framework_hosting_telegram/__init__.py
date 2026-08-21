# Copyright (c) Microsoft. All rights reserved.

"""Telegram Bot API-shaped helpers for app-owned Agent Framework hosting."""

import importlib.metadata

from ._parsing import (
    ResolveFileUrl,
    telegram_callback_query_id,
    telegram_chat_id,
    telegram_command,
    telegram_media_file_id,
    telegram_session_id,
    telegram_to_run,
)
from ._rendering import (
    TELEGRAM_MAX_CAPTION_LENGTH,
    TELEGRAM_MAX_TEXT_LENGTH,
    TelegramOperation,
    telegram_from_run,
    telegram_from_streaming_run,
)

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "TELEGRAM_MAX_CAPTION_LENGTH",
    "TELEGRAM_MAX_TEXT_LENGTH",
    "ResolveFileUrl",
    "TelegramOperation",
    "__version__",
    "telegram_callback_query_id",
    "telegram_chat_id",
    "telegram_command",
    "telegram_from_run",
    "telegram_from_streaming_run",
    "telegram_media_file_id",
    "telegram_session_id",
    "telegram_to_run",
]
