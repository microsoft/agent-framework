# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode
from ._logging import get_logger
from .contents.author_role import AuthorRole
from .contents.base_content import BaseContent
from .contents.chat_message_content import ChatMessageContent
from .contents.const import ContentTypes
from .contents.finish_reason import FinishReason
from .contents.function_call_content import FunctionCallContent
from .contents.function_result_content import FunctionResultContent
from .contents.status import Status
from .contents.streaming_chat_message_content import StreamingChatMessageContent
from .contents.streaming_content_mixin import StreamingContentMixin
from .contents.streaming_text_content import StreamingTextContent
from .contents.text_content import TextContent

__all__ = [
    "AuthorRole",
    "BaseContent",
    "ChatMessageContent",
    "ContentTypes",
    "FinishReason",
    "FunctionCallContent",
    "FunctionResultContent",
    "Status",
    "StreamingChatMessageContent",
    "StreamingContentMixin",
    "StreamingTextContent",
    "TextContent",
    "__version__",
    "get_logger",
]
