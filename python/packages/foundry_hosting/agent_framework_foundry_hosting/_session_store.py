# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from pathlib import Path
from typing import Literal

from agent_framework import ExperimentalFeature, FileSessionStore
from agent_framework._feature_stage import experimental
from azure.ai.agentserver.core import get_request_context

from ._request_context import validate_path_segment


@experimental(feature_id=ExperimentalFeature.SESSION_STORE)
class FoundrySessionStore(FileSessionStore):
    """Persist MAF AgentSession snapshots within a Foundry hosted session.

    A Foundry hosted session controls platform compute and filesystem lifetime
    and may host multiple users and Responses conversations. A MAF
    :class:`AgentSession` contains framework context state. Snapshots are keyed
    by ``conversation_id`` for stored conversations or by Responses
    ``response_id`` for response chains; these storage keys are independent of
    the MAF session's own identifier.

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

    def _session_file_path(self, session_id: str) -> Path:
        """Resolve a snapshot path within the active Foundry user's directory."""
        user_directory = self._storage_root
        if user_id := get_request_context().user_id:
            validate_path_segment(user_id, kind="user id")
            candidate_user_directory = self._storage_root / user_id
            user_directory = candidate_user_directory.resolve()
            if user_directory != candidate_user_directory or not user_directory.is_relative_to(self._storage_root):
                raise ValueError(f"User directory escaped storage directory: '{user_directory}'.")
        user_directory.mkdir(parents=True, exist_ok=True)

        session_file_name = self._session_file_name(session_id)
        candidate_session_file_path = user_directory / session_file_name
        session_file_path = candidate_session_file_path.resolve()
        if (
            session_file_path != candidate_session_file_path
            or not session_file_path.is_relative_to(user_directory)
            or not session_file_path.is_relative_to(self._storage_root)
        ):
            raise ValueError(f"Session file path escaped user directory: {session_id!r}")
        return session_file_path
