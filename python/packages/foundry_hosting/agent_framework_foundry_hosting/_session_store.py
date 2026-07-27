# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from pathlib import Path
from typing import Literal

from agent_framework import ExperimentalFeature, FileSessionStore
from agent_framework._feature_stage import experimental

from ._request_context import _request_user_directory_segment  # pyright: ignore[reportPrivateUsage]


@experimental(feature_id=ExperimentalFeature.SESSION_STORE)
class FoundrySessionStore(FileSessionStore):
    """File-backed session store isolated by the active Foundry request user.

    This implementation currently persists through :class:`FileSessionStore`.
    The Foundry-specific type leaves room to use a platform storage API later
    without changing :class:`ResponsesHostServer` configuration.
    """

    def __init__(
        self,
        storage_path: str | Path,
        *,
        serialization_format: Literal["json", "msgpack"] = "json",
    ) -> None:
        """Initialize a Foundry-scoped file store rooted at ``storage_path``."""
        super().__init__(storage_path, serialization_format=serialization_format)

    def get_session_directory(self) -> Path:
        """Return the active request user's session directory."""
        directory_segment = _request_user_directory_segment()
        return self.storage_path / directory_segment if directory_segment else self.storage_path
