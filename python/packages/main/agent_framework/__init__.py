# Copyright (c) Microsoft. All rights reserved.

import importlib
import importlib.metadata

try:
    __version__ = importlib.metadata.version(__name__)
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0"  # Fallback for development mode

from ._agents import *  # noqa: F403
from ._clients import *  # noqa: F403
from ._logging import *  # noqa: F403
from ._mcp import *  # noqa: F403
from ._memory import *  # noqa: F403
from ._threads import *  # noqa: F403
from ._tools import *  # noqa: F403
from ._types import *  # noqa: F403
