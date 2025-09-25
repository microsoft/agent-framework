# Copyright (c) Microsoft. All rights reserved.

"""Session management for agent execution tracking."""

import logging
import uuid
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)

# Type aliases for better readability
SessionData = dict[str, Any]
RequestRecord = dict[str, Any]
SessionSummary = dict[str, Any]


class SessionManager:
    """Manages execution sessions for tracking requests and context."""

    def __init__(self) -> None:
        """Initialize the session manager."""
        self.sessions: dict[str, SessionData] = {}

    def create_session(self, session_id: str | None = None) -> str:
        """Create a new execution session.

        Args:
            session_id: Optional session ID, if not provided a new one is generated

        Returns:
            Session ID
        """
        if not session_id:
            session_id = str(uuid.uuid4())

        self.sessions[session_id] = {
            "id": session_id,
            "created_at": datetime.now(),
            "requests": [],
            "context": {},
            "active": True,
        }

        logger.debug(f"Created session: {session_id}")
        return session_id

    def get_session(self, session_id: str) -> SessionData | None:
        """Get session information.

        Args:
            session_id: Session ID

        Returns:
            Session data or None if not found
        """
        return self.sessions.get(session_id)

    def close_session(self, session_id: str) -> None:
        """Close and cleanup a session.

        Args:
            session_id: Session ID to close
        """
        if session_id in self.sessions:
            self.sessions[session_id]["active"] = False
            logger.debug(f"Closed session: {session_id}")

    def add_request_record(
        self, session_id: str, entity_id: str, executor_name: str, request_input: Any, model: str
    ) -> str:
        """Add a request record to a session.

        Args:
            session_id: Session ID
            entity_id: ID of the entity being executed
            executor_name: Name of the executor
            request_input: Input for the request
            model: Model name

        Returns:
            Request ID
        """
        session = self.get_session(session_id)
        if not session:
            return ""

        request_record: RequestRecord = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.now(),
            "entity_id": entity_id,
            "executor": executor_name,
            "input": request_input,
            "model": model,
            "stream": True,
        }
        session["requests"].append(request_record)
        return str(request_record["id"])

    def update_request_record(self, session_id: str, request_id: str, updates: dict[str, Any]) -> None:
        """Update a request record in a session.

        Args:
            session_id: Session ID
            request_id: Request ID to update
            updates: Dictionary of updates to apply
        """
        session = self.get_session(session_id)
        if not session:
            return

        for request in session["requests"]:
            if request["id"] == request_id:
                request.update(updates)
                break

    def get_session_history(self, session_id: str) -> SessionSummary | None:
        """Get session execution history.

        Args:
            session_id: Session ID

        Returns:
            Session history or None if not found
        """
        session = self.get_session(session_id)
        if not session:
            return None

        return {
            "session_id": session_id,
            "created_at": session["created_at"].isoformat(),
            "active": session["active"],
            "request_count": len(session["requests"]),
            "requests": [
                {
                    "id": req["id"],
                    "timestamp": req["timestamp"].isoformat(),
                    "entity_id": req["entity_id"],
                    "executor": req["executor"],
                    "model": req["model"],
                    "input_length": len(str(req["input"])) if req["input"] else 0,
                    "execution_time": req.get("execution_time"),
                    "status": req.get("status", "unknown"),
                }
                for req in session["requests"]
            ],
        }

    def get_active_sessions(self) -> list[SessionSummary]:
        """Get list of active sessions.

        Returns:
            List of active session summaries
        """
        active_sessions = []

        for session_id, session in self.sessions.items():
            if session["active"]:
                active_sessions.append({
                    "session_id": session_id,
                    "created_at": session["created_at"].isoformat(),
                    "request_count": len(session["requests"]),
                    "last_activity": (
                        session["requests"][-1]["timestamp"].isoformat()
                        if session["requests"]
                        else session["created_at"].isoformat()
                    ),
                })

        return active_sessions

    def cleanup_old_sessions(self, max_age_hours: int = 24) -> None:
        """Cleanup old sessions to prevent memory leaks.

        Args:
            max_age_hours: Maximum age of sessions to keep in hours
        """
        cutoff_time = datetime.now().timestamp() - (max_age_hours * 3600)

        sessions_to_remove = []
        for session_id, session in self.sessions.items():
            if session["created_at"].timestamp() < cutoff_time:
                sessions_to_remove.append(session_id)

        for session_id in sessions_to_remove:
            del self.sessions[session_id]
            logger.debug(f"Cleaned up old session: {session_id}")

        if sessions_to_remove:
            logger.info(f"Cleaned up {len(sessions_to_remove)} old sessions")
