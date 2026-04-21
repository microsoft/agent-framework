# Copyright (c) Microsoft. All rights reserved.

import importlib.metadata

from ._invocations import InvocationsHostServer
from ._responses import ResponsesHostServer

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = ["InvocationsHostServer", "ResponsesHostServer"]
