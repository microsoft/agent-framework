# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._history_provider import FoundryHostedAgentHistoryProvider, foundry_response_id, foundry_response_id_factory
from ._invocations import InvocationsHostServer
from ._responses import ResponsesHostServer

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "FoundryHostedAgentHistoryProvider",
    "InvocationsHostServer",
    "ResponsesHostServer",
    "foundry_response_id",
    "foundry_response_id_factory",
]
