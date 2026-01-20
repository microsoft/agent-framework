# Copyright (c) Microsoft. All rights reserved.

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, AgentThread, ChatMessage, Content, Role
from agent_framework.exceptions import ServiceException, ServiceInitializationError
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
    @patch("agent_framework_copilotstudio._agent.CopilotStudioSettings")
    def test_init_missing_environment_id(self, mock_settings: MagicMock, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        mock_settings.return_value.environmentid = None
        mock_settings.return_value.schemaname = "test-bot"
        mock_settings.return_value.tenantid = "test-tenant"
        mock_settings.return_value.agentappid = "test-client"

        with pytest.raises(ServiceInitializationError, match="environment ID is required"):
            CopilotStudioAgent()

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    @patch("agent_framework_copilotstudio._agent.CopilotStudioSettings")
    def test_init_missing_bot_id(self, mock_settings: MagicMock, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        mock_settings.return_value.environmentid = "test-env"
        mock_settings.return_value.schemaname = None
        mock_settings.return_value.tenantid = "test-tenant"
        mock_settings.return_value.agentappid = "test-client"

        with pytest.raises(ServiceInitializationError, match="agent identifier"):
            CopilotStudioAgent()

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    @patch("agent_framework_copilotstudio._agent.CopilotStudioSettings")
    def test_init_missing_tenant_id(self, mock_settings: MagicMock, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        mock_settings.return_value.environmentid = "test-env"
        mock_settings.return_value.schemaname = "test-bot"
        mock_settings.return_value.tenantid = None
        mock_settings.return_value.agentappid = "test-client"

        with pytest.raises(ServiceInitializationError, match="tenant ID is required"):
            CopilotStudioAgent()

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    @patch("agent_framework_copilotstudio._agent.CopilotStudioSettings")
    def test_init_missing_client_id(self, mock_settings: MagicMock, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        mock_settings.return_value.environmentid = "test-env"
        mock_settings.return_value.schemaname = "test-bot"
        mock_settings.return_value.tenantid = "test-tenant"
        mock_settings.return_value.agentappid = None

        with pytest.raises(ServiceInitializationError, match="client ID is required"):
            CopilotStudioAgent()

    def test_init_with_client(self, mock_copilot_client: MagicMock) -> None:
        agent = CopilotStudioAgent(client=mock_copilot_client)
        assert agent.client == mock_copilot_client
        assert agent.id is not None

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    def test_init_empty_environment_id(self, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        with patch("agent_framework_copilotstudio._agent.CopilotStudioSettings") as mock_settings:
            mock_settings.return_value.environmentid = ""
            mock_settings.return_value.schemaname = "test-bot"
            mock_settings.return_value.tenantid = "test-tenant"
            mock_settings.return_value.agentappid = "test-client"

            with pytest.raises(ServiceInitializationError, match="environment ID is required"):
                CopilotStudioAgent()

    @patch("agent_framework_copilotstudio._acquire_token.acquire_token")
    def test_init_empty_schema_name(self, mock_acquire_token: MagicMock) -> None:
        mock_acquire_token.return_value = "fake-token"
        with patch("agent_framework_copilotstudio._agent.CopilotStudioSettings") as mock_settings:
            mock_settings.return_value.environmentid = "test-env"
            mock_settings.return_value.schemaname = ""
            mock_settings.return_value.tenantid = "test-tenant"
            mock_settings.return_value.agentappid = "test-client"

            with pytest.raises(ServiceInitializationError, match="agent identifier"):
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
        assert response.messages[0].role == Role.ASSISTANT

    async def test_run_with_chat_message(self, mock_copilot_client: MagicMock, mock_activity: MagicMock) -> None:
        """Test run method with ChatMessage."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([mock_activity])

        chat_message = ChatMessage(role=Role.USER, contents=[Content.from_text("test message")])
        response = await agent.run(chat_message)

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1
        content = response.messages[0].contents[0]
        assert content.type == "text"
        assert content.text == "Test response"
        assert response.messages[0].role == Role.ASSISTANT

    async def test_run_with_thread(self, mock_copilot_client: MagicMock, mock_activity: MagicMock) -> None:
        """Test run method with existing thread."""
        agent = CopilotStudioAgent(client=mock_copilot_client)
        thread = AgentThread()

        conversation_activity = MagicMock()
        conversation_activity.conversation.id = "test-conversation-id"

        mock_copilot_client.start_conversation.return_value = create_async_generator([conversation_activity])
        mock_copilot_client.ask_question.return_value = create_async_generator([mock_activity])

        response = await agent.run("test message", thread=thread)

        assert isinstance(response, AgentResponse)
        assert len(response.messages) == 1
        assert thread.service_thread_id == "test-conversation-id"

    async def test_run_start_conversation_failure(self, mock_copilot_client: MagicMock) -> None:
        """Test run method when conversation start fails."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        mock_copilot_client.start_conversation.return_value = create_async_generator([])

        with pytest.raises(ServiceException, match="Failed to start a new conversation"):
            await agent.run("test message")

    async def test_run_stream_with_string_message(self, mock_copilot_client: MagicMock) -> None:
        """Test run_stream method with string message."""
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
        async for response in agent.run_stream("test message"):
            assert isinstance(response, AgentResponseUpdate)
            content = response.contents[0]
            assert content.type == "text"
            assert content.text == "Streaming response"
            response_count += 1

        assert response_count == 1

    async def test_run_stream_with_thread(self, mock_copilot_client: MagicMock) -> None:
        """Test run_stream method with existing thread."""
        agent = CopilotStudioAgent(client=mock_copilot_client)
        thread = AgentThread()

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
        async for response in agent.run_stream("test message", thread=thread):
            assert isinstance(response, AgentResponseUpdate)
            content = response.contents[0]
            assert content.type == "text"
            assert content.text == "Streaming response"
            response_count += 1

        assert response_count == 1
        assert thread.service_thread_id == "test-conversation-id"

    async def test_run_stream_no_typing_activity(self, mock_copilot_client: MagicMock) -> None:
        """Test run_stream method with non-typing activity."""
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
        async for _response in agent.run_stream("test message"):
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

    async def test_run_stream_start_conversation_failure(self, mock_copilot_client: MagicMock) -> None:
        """Test run_stream method when conversation start fails."""
        agent = CopilotStudioAgent(client=mock_copilot_client)

        mock_copilot_client.start_conversation.return_value = create_async_generator([])

        with pytest.raises(ServiceException, match="Failed to start a new conversation"):
            async for _ in agent.run_stream("test message"):
                pass
