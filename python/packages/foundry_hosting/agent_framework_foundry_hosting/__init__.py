# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._history_provider import (
    FoundryHostedAgentHistoryProvider,
    bind_request_context,
    get_current_request_context,
)
from ._ids import (
    foundry_item_id,
    foundry_response_id,
    foundry_response_id_factory,
)
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
    "bind_request_context",
    "foundry_item_id",
    "foundry_response_id",
    "foundry_response_id_factory",
    "get_current_request_context",
]
