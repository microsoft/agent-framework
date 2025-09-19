# Copyright (c) Microsoft. All rights reserved.

import importlib
import importlib.metadata
from typing import Final

try:
    _version = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    _version = "0.0.0"  # Fallback for development mode
__version__: Final[str] = _version

from ._agents import *  # noqa: F403
from ._clients import *  # noqa: F403
from ._logging import *  # noqa: F403
from ._mcp import *  # noqa: F403
from ._memory import *  # noqa: F403
from ._middleware import *  # noqa: F403
from ._telemetry import *  # noqa: F403
from ._threads import *  # noqa: F403
from ._tools import *  # noqa: F403
from ._types import *  # noqa: F403
from ._workflow import *  # noqa: F403
