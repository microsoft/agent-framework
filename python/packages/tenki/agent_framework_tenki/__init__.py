# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import importlib.metadata

from ._execute_code_tool import TenkiExecuteCodeTool
from ._provider import TenkiCodeActProvider

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"

__all__ = [
    "TenkiCodeActProvider",
    "TenkiExecuteCodeTool",
    "__version__",
]
