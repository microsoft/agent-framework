# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._chat_client import RawTypeSafeChatClient, TypeSafeChatClient, TypeSafeChatOptions

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "RawTypeSafeChatClient",
    "TypeSafeChatClient",
    "TypeSafeChatOptions",
    "__version__",
]
