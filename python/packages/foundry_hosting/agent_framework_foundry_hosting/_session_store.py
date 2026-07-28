# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from pathlib import Path
from typing import Literal

from agent_framework import ExperimentalFeature, FileSessionStore
from agent_framework._feature_stage import experimental

from ._request_context import request_user_directory_segment


@experimental(feature_id=ExperimentalFeature.SESSION_STORE)
class FoundrySessionStore(FileSessionStore):
    """Persist MAF AgentSession snapshots within a Foundry hosted session.

    A Foundry hosted session controls platform compute and filesystem lifetime;
    a MAF :class:`AgentSession` contains framework context state. They remain
    distinct concepts even though Responses hosting uses the Foundry session ID
    as the MAF session identifier and snapshot filename for correlation.

    This implementation currently persists through :class:`FileSessionStore`,
    with each validated platform user ID as a child directory. The
    Foundry-specific type leaves room to use a platform storage API later
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
        """Return the active request user's validated session directory."""
        directory_segment = request_user_directory_segment()
        return self.storage_path / directory_segment if directory_segment else self.storage_path
