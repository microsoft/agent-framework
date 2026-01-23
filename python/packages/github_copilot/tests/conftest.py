# Copyright (c) Microsoft. All rights reserved.

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from copilot.generated.session_events import Data, SessionEvent, SessionEventType


def create_session_event(
    event_type: SessionEventType,
    content: str | None = None,
    delta_content: str | None = None,
    message_id: str | None = None,
    error_message: str | None = None,
) -> SessionEvent:
    """Create a mock session event for testing."""
    data = Data(
        content=content,
        delta_content=delta_content,
        message_id=message_id or str(uuid4()),
        message=error_message,
    )
    return SessionEvent(
        data=data,
        id=uuid4(),
        timestamp=datetime.now(timezone.utc),
        type=event_type,
    )


@pytest.fixture
def mock_session() -> MagicMock:
    """Create a mock CopilotSession."""
    session = MagicMock()
    session.session_id = "test-session-id"
    session.send = AsyncMock(return_value="test-message-id")
    session.send_and_wait = AsyncMock()
    session.destroy = AsyncMock()
    session.on = MagicMock(return_value=lambda: None)
    return session


@pytest.fixture
def mock_client(mock_session: MagicMock) -> MagicMock:
    """Create a mock CopilotClient."""
    client = MagicMock()
    client.start = AsyncMock()
    client.stop = AsyncMock(return_value=[])
    client.create_session = AsyncMock(return_value=mock_session)
    return client


@pytest.fixture
def assistant_message_event() -> SessionEvent:
    """Create a mock assistant message event."""
    return create_session_event(
        SessionEventType.ASSISTANT_MESSAGE,
        content="Test response",
        message_id="test-msg-id",
    )


@pytest.fixture
def assistant_delta_event() -> SessionEvent:
    """Create a mock assistant message delta event."""
    return create_session_event(
        SessionEventType.ASSISTANT_MESSAGE_DELTA,
        delta_content="Hello",
        message_id="test-msg-id",
    )


@pytest.fixture
def session_idle_event() -> SessionEvent:
    """Create a mock session idle event."""
    return create_session_event(SessionEventType.SESSION_IDLE)


@pytest.fixture
def session_error_event() -> SessionEvent:
    """Create a mock session error event."""
    return create_session_event(
        SessionEventType.SESSION_ERROR,
        error_message="Test error",
    )
