# Copyright (c) Microsoft. All rights reserved.

"""Session management for Agent Framework debug UI."""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from agent_framework import AgentThread

from ._models import SessionInfo

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class Session:
    """Internal session representation with thread object."""

    thread_id: str
    agent_id: str
    created_at: datetime
    thread: Optional["AgentThread"] = field(default=None, repr=False)
    messages: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """Manages debug sessions and conversation threads.

    Provides lightweight session management for the debug UI,
    wrapping Agent Framework's native thread functionality.
    """

    def __init__(self, persist_sessions: bool = False, sessions_file: str = "./debug_sessions.json") -> None:
        """Initialize session manager.

        Args:
            persist_sessions: Whether to persist sessions to disk
            sessions_file: Path to sessions persistence file
        """
        self.sessions: Dict[str, Session] = {}
        self.persist_sessions = persist_sessions
        self.sessions_file = Path(sessions_file)

        if persist_sessions and self.sessions_file.exists():
            self._load_sessions()

    def create_session(self, agent_id: str, thread_id: str, thread: "AgentThread") -> SessionInfo:
        """Create a new debug session.

        Args:
            agent_id: ID of the agent this session belongs to
            thread_id: Unique thread identifier
            thread: Agent Framework thread object

        Returns:
            SessionInfo for the created session
        """
        session = Session(thread_id=thread_id, agent_id=agent_id, created_at=datetime.now(), thread=thread, messages=[])

        self.sessions[thread_id] = session

        if self.persist_sessions:
            self._save_sessions()

        logger.info(f"Created session {thread_id} for agent {agent_id}")

        return SessionInfo(
            thread_id=thread_id, agent_id=agent_id, created_at=session.created_at.isoformat(), messages=[]
        )

    def get_session(self, thread_id: str) -> Optional[SessionInfo]:
        """Get session info by thread ID.

        Args:
            thread_id: Thread identifier

        Returns:
            SessionInfo if found, None otherwise
        """
        session = self.sessions.get(thread_id)
        if not session:
            return None

        return SessionInfo(
            thread_id=session.thread_id,
            agent_id=session.agent_id,
            created_at=session.created_at.isoformat(),
            messages=session.messages,
            metadata=session.metadata,
        )

    def get_thread(self, thread_id: str) -> Optional["AgentThread"]:
        """Get the actual Agent Framework thread object.

        Args:
            thread_id: Thread identifier

        Returns:
            AgentThread if found, None otherwise
        """
        session = self.sessions.get(thread_id)
        return session.thread if session else None

    def list_sessions(self, agent_id: Optional[str] = None) -> List[SessionInfo]:
        """List all sessions, optionally filtered by agent ID.

        Args:
            agent_id: Optional agent ID filter

        Returns:
            List of SessionInfo objects
        """
        sessions = self.sessions.values()
        if agent_id:
            sessions = [s for s in sessions if s.agent_id == agent_id]

        return [
            SessionInfo(
                thread_id=s.thread_id,
                agent_id=s.agent_id,
                created_at=s.created_at.isoformat(),
                messages=s.messages,
                metadata=s.metadata,
            )
            for s in sessions
        ]

    def add_message(self, thread_id: str, message_data: Dict[str, Any]) -> None:
        """Add a message to a session.

        Args:
            thread_id: Thread identifier
            message_data: Message data to store
        """
        if thread_id in self.sessions:
            self.sessions[thread_id].messages.append(message_data)

            if self.persist_sessions:
                self._save_sessions()

    def delete_session(self, thread_id: str) -> bool:
        """Delete a session.

        Args:
            thread_id: Thread identifier

        Returns:
            True if session was deleted, False if not found
        """
        if thread_id in self.sessions:
            del self.sessions[thread_id]

            if self.persist_sessions:
                self._save_sessions()

            logger.info(f"Deleted session {thread_id}")
            return True
        return False

    def _save_sessions(self) -> None:
        """Save sessions to disk (excluding non-serializable thread objects)."""
        try:
            serializable_sessions = {}
            for thread_id, session in self.sessions.items():
                serializable_sessions[thread_id] = {
                    "thread_id": session.thread_id,
                    "agent_id": session.agent_id,
                    "created_at": session.created_at.isoformat(),
                    "messages": session.messages,
                    "metadata": session.metadata,
                }

            with open(self.sessions_file, "w") as f:
                json.dump(serializable_sessions, f, indent=2)

        except Exception as e:
            logger.error(f"Error saving sessions: {e}")

    def _load_sessions(self) -> None:
        """Load sessions from disk (threads will need to be recreated)."""
        try:
            with open(self.sessions_file, "r") as f:
                data = json.load(f)

            for thread_id, session_data in data.items():
                self.sessions[thread_id] = Session(
                    thread_id=session_data["thread_id"],
                    agent_id=session_data["agent_id"],
                    created_at=datetime.fromisoformat(session_data["created_at"]),
                    messages=session_data.get("messages", []),
                    metadata=session_data.get("metadata", {}),
                    thread=None,  # Will be recreated when accessed
                )

            logger.info(f"Loaded {len(self.sessions)} sessions from disk")

        except Exception as e:
            logger.error(f"Error loading sessions: {e}")

    async def cleanup(self) -> None:
        """Cleanup resources on shutdown."""
        if self.persist_sessions:
            self._save_sessions()

        logger.info("Session manager cleaned up")
