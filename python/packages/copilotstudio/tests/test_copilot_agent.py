# Copyright (c) Microsoft. All rights reserved.

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, AgentSession, Content, Message
from agent_framework.exceptions import AgentException
from microsoft_agents.copilotstudio.client import CopilotClient

from agent_framework_copilotstudio import CopilotStudioAgent


def create_async_generator(items: list[Any]) -> Any:
    """Helper to create async generator mock."""

    async def async_gen() -> Any:
        for item in items:
            yield item

    return async_gen()


class TestCopilotStudioAgent:
    """Test cases for CopilotStudioAgent."""

    @pytest.fixture
    def mock_activity(self) -> MagicMock:
        activity = MagicMock()
        activity.text = "Test response"
        activity.type = "message"
        activity.id = "test-id"
        activity.from_property.name = "Test Bot"
        return activity

    @pytest.fixture
    def mock_copilot_client(self) -> MagicMock:
        return MagicMock(spec=CopilotClient)

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    @patch("agent_framework_copilotstudio._agent.load_settings")
    def test_init_missing_environment_id(self, mock_load_settings: MagicMock, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        mock_load_settings.return_value = {
            "environmentid": None,
            "schemaname": "test-bot",
            "tenantid": "test-tenant",
            "agentappid": "test-client",
        }

        with pytest.raises(ValueError, match="environment ID is required"):
            CopilotStudioAgent()

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    @patch("agent_framework_copilotstudio._agent.load_settings")
    def test_init_missing_bot_id(self, mock_load_settings: MagicMock, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        mock_load_settings.return_value = {
            "environmentid": "test-env",
            "schemaname": None,
            "tenantid": "test-tenant",
            "agentappid": "test-client",
        }

        with pytest.raises(ValueError, match="agent identifier"):
            CopilotStudioAgent()

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    @patch("agent_framework_copilotstudio._agent.load_settings")
    def test_init_missing_tenant_id(self, mock_load_settings: MagicMock, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        mock_load_settings.return_value = {
            "environmentid": "test-env",
            "schemaname": "test-bot",
            "tenantid": None,
            "agentappid": "test-client",
        }

        with pytest.raises(ValueError, match="tenant ID is required"):
            CopilotStudioAgent()

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    @patch("agent_framework_copilotstudio._agent.load_settings")
    def test_init_missing_client_id(self, mock_load_settings: MagicMock, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        mock_load_settings.return_value = {
            "environmentid": "test-env",
            "schemaname": "test-bot",
            "tenantid": "test-tenant",
            "agentappid": None,
        }

        with pytest.raises(ValueError, match="client ID is required"):
            CopilotStudioAgent()

    def test_init_with_client(self, mock_copilot_client: MagicMock) -> None:
        agent = CopilotStudioAgent(client=mock_copilot_client)
        assert agent.client == mock_copilot_client
        assert agent.id is not None

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    def test_init_empty_environment_id(self, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        with patch("agent_framework_copilotstudio._agent.load_settings") as mock_load_settings:
            mock_load_settings.return_value = {
                "environmentid": "",
                "schemaname": "test-bot",
                "tenantid": "test-tenant",
                "agentappid": "test-client",
            }

            with pytest.raises(ValueError, match="environment ID is required"):
                CopilotStudioAgent()

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    def test_init_empty_schema_name(self, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        with patch("agent_framework_copilotstudio._agent.load_settings") as mock_load_settings:
            mock_load_settings.return_value = {
                "environmentid": "test-env",
                "schemaname": "",
                "tenantid": "test-tenant",
                "agentappid": "test-client",
            }

            with pytest.raises(ValueError, match="agent identifier"):
                CopilotStudioAgent()

    async def test_run_with_string_message(self, mock_copilot_client: MagicMock, mock_activity: MagicMock) -> None:
        """Test run method with string message."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([mock_activity])

        response = await agent.run("test message")

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1
        content = response.messages[0].contents[0]
        assert content.type == "text"
        assert content.text == "Test response"
        assert response.messages[0].role == "assistant"

    async def test_run_with_chat_message(self, mock_copilot_client: MagicMock, mock_activity: MagicMock) -> None:
        """Test run method with Message."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([mock_activity])

        chat_message = Message(role="user", contents=[Content.from_text("test message")])
        response = await agent.run(chat_message)

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1
        content = response.messages[0].contents[0]
        assert content.type == "text"
        assert content.text == "Test response"
        assert response.messages[0].role == "assistant"

    async def test_run_with_session(self, mock_copilot_client: MagicMock, mock_activity: MagicMock) -> None:
        """Test run method with existing session."""
        agent = CopilotStudioAgent(client=mock_copilot_client)
        session = AgentSession()

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([mock_activity])

        response = await agent.run("test message", session=session)

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1
        assert session.service_session_id == "test-conversation-id"

    async def test_run_start_conversation_failure(self, mock_copilot_client: MagicMock) -> None:
        """Test run method when conversation start fails."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        mock_copilot_client.start_conversation.return_value = create_async_generator([])

        with pytest.raises(AgentException, match="Failed to start a new conversation"):
            await agent.run("test message")

    async def test_run_streaming_with_string_message(self, mock_copilot_client: MagicMock) -> None:
        """Test run(stream=True) method with string message."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        typing_activity = MagicMock()
        typing_activity.text = "Streaming response"
        typing_activity.type = "typing"
        typing_activity.id = "test-typing-id"
        typing_activity.from_property.name = "Test Bot"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([typing_activity])

        response_count = 0
        async for response in agent.run("test message", stream=True):
            assert isinstance(response, AgentResponseUpdate)
            content = response.contents[0]
            assert content.type == "text"
            assert content.text == "Streaming response"
            response_count += 1

        assert response_count == 1

    async def test_run_streaming_with_session(self, mock_copilot_client: MagicMock) -> None:
        """Test run(stream=True) method with existing session."""
        agent = CopilotStudioAgent(client=mock_copilot_client)
        session = AgentSession()

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        typing_activity = MagicMock()
        typing_activity.text = "Streaming response"
        typing_activity.type = "typing"
        typing_activity.id = "test-typing-id"
        typing_activity.from_property.name = "Test Bot"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([typing_activity])

        response_count = 0
        async for response in agent.run("test message", session=session, stream=True):
            assert isinstance(response, AgentResponseUpdate)
            content = response.contents[0]
            assert content.type == "text"
            assert content.text == "Streaming response"
            response_count += 1

        assert response_count == 1
        assert session.service_session_id == "test-conversation-id"

    async def test_run_streaming_no_typing_activity(self, mock_copilot_client: MagicMock) -> None:
        """Test run(stream=True) method with non-typing activity."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        message_activity = MagicMock()
        message_activity.text = "Message response"
        message_activity.type = "message"
        message_activity.id = "test-message-id"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([message_activity])

        response_count = 0
        async for _response in agent.run("test message", stream=True):
            response_count += 1

        assert response_count == 0

    async def test_run_multiple_activities(self, mock_copilot_client: MagicMock) -> None:
        """Test run method with multiple message activities."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        activity1 = MagicMock()
        activity1.text = "First response"
        activity1.type = "message"
        activity1.id = "test-id-1"
        activity1.from_property.name = "Test Bot"

        activity2 = MagicMock()
        activity2.text = "Second response"
        activity2.type = "message"
        activity2.id = "test-id-2"
        activity2.from_property.name = "Test Bot"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([activity1, activity2])

        response = await agent.run("test message")

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 2

    async def test_run_list_of_messages(self, mock_copilot_client: MagicMock, mock_activity: MagicMock) -> None:
        """Test run method with list of messages."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([mock_activity])

        messages = ["Hello", "How are you?"]
        response = await agent.run(messages)

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1

    async def test_run_streaming_start_conversation_failure(self, mock_copilot_client: MagicMock) -> None:
        """Test run(stream=True) method when conversation start fails."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        mock_copilot_client.start_conversation.return_value = create_async_generator([])

        with pytest.raises(AgentException, match="Failed to start a new conversation"):
            async for _ in agent.run("test message", stream=True):
                pass
