# Copyright (c) Microsoft. All rights reserved.

"""Discord channel for ``agent-framework-hosting``."""

import importlib.metadata

from ._channel import DiscordChannel, DiscordIsolationKeyFactory, discord_isolation_key

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "DiscordChannel",
    "DiscordIsolationKeyFactory",
    "__version__",
    "discord_isolation_key",
]
