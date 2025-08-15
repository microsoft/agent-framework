"""Tests for agent-actor integration"""

import pytest

from agent_runtime.agent_actor import (
    ActorId,
    ActorMessageType,
    ActorRequestMessage,
    ActorResponseMessage,
    AgentActor,
    ChatMessage,
    ChatRole,
    RequestStatus,
)

from .mock_agents import EchoAgent, MockAIAgent


class MockActorContext:
    """Mock actor runtime context for testing"""

    def __init__(self, actor_id: ActorId):
        self._actor_id = actor_id
        self._state = {}
        self._completed_requests = {}

    @property
    def actor_id(self) -> ActorId:
        return self._actor_id

    async def read_state(self, key: str):
        return self._state.get(key)

    async def write_state(self, key: str, value):
        self._state[key] = value

    def complete_request(self, message_id: str, response: ActorResponseMessage):
        self._completed_requests[message_id] = response


class TestEchoAgent:
    def test_echo_agent_creation(self):
        agent = EchoAgent()
        assert agent is not None

    @pytest.mark.asyncio
    async def test_echo_agent_run(self):
        agent = EchoAgent()
        messages = [ChatMessage(role=ChatRole.USER, text="Hello, echo!")]

        response = await agent.run(messages)

        assert len(response.messages) == 1
        assert response.messages[0].role == ChatRole.ASSISTANT
        assert "Echo: Hello, echo!" in str(response.messages[0].text)


class TestMockAIAgent:
    def test_mock_ai_agent_creation(self):
        agent = MockAIAgent()
        assert agent is not None
        assert len(agent._responses) > 0

    @pytest.mark.asyncio
    async def test_mock_ai_agent_run(self):
        agent = MockAIAgent()
        messages = [ChatMessage(role=ChatRole.USER, text="Hello!")]

        response = await agent.run(messages)

        assert len(response.messages) == 1
        assert response.messages[0].role == ChatRole.ASSISTANT
        assert str(response.messages[0].text) in agent._responses

    @pytest.mark.asyncio
    async def test_mock_ai_agent_conversation(self):
        agent = MockAIAgent()

        # First message
        response1 = await agent.run([ChatMessage(role=ChatRole.USER, text="Hello!")])

        # Second message with context
        response2 = await agent.run([
            ChatMessage(role=ChatRole.USER, text="Hello!"),
            response1.messages[0],
            ChatMessage(role=ChatRole.USER, text="How are you?"),
        ])

        assert len(response2.messages) == 1
        assert response2.messages[0].role == ChatRole.ASSISTANT


class TestAgentActorWrapper:
    @pytest.fixture
    def actor_id(self):
        return ActorId(type_name="echo", instance_id="test-123")

    @pytest.fixture
    def mock_context(self, actor_id):
        return MockActorContext(actor_id)

    @pytest.fixture
    def echo_actor(self, actor_id):
        return AgentActor(EchoAgent())

    @pytest.mark.asyncio
    async def test_agent_actor_creation(self, echo_actor, actor_id):
        """Ensure the wrapped agent is an EchoAgent instance."""
        assert isinstance(echo_actor._agent, EchoAgent)

    @pytest.mark.asyncio
    async def test_agent_actor_run_request(self, echo_actor, mock_context):
        # Create run request
        request = ActorRequestMessage(
            message_id="test-123",
            message_type=ActorMessageType.REQUEST,
            method="run",
            params={
                "agent_name": "echo_agent",
                "messages": [ChatMessage(role=ChatRole.USER, text="Test message", message_id="user-msg-1")]
            },
        )

        # Process message by simulating the actor handling
        await echo_actor._handle_agent_request(request, mock_context)

        # Check response was completed
        assert "test-123" in mock_context._completed_requests
        response = mock_context._completed_requests["test-123"]

        assert response.status == RequestStatus.COMPLETED
        assert "messages" in response.data
        assert len(response.data["messages"]) == 1
        assert response.data["messages"][0]["role"]["value"] == "assistant"
        # ChatMessage has contents list with text content
        contents = response.data["messages"][0]["contents"]
        assert len(contents) > 0
        assert "Echo: Test message" in contents[0]["text"]

    @pytest.mark.asyncio
    async def test_agent_actor_invalid_method(self, echo_actor, mock_context):
        # Create invalid request
        request = ActorRequestMessage(
            message_id="test-456", message_type=ActorMessageType.REQUEST, method="invalid_method", params={}
        )

        # Process message by simulating the actor handling
        await echo_actor._handle_agent_request(request, mock_context)

        # Check error response
        assert "test-456" in mock_context._completed_requests
        response = mock_context._completed_requests["test-456"]

        assert response.status == RequestStatus.FAILED
        assert "error" in response.data

    @pytest.mark.asyncio
    async def test_agent_actor_malformed_request(self, echo_actor, mock_context):
        # Create request with malformed messages
        request = ActorRequestMessage(
            message_id="test-789",
            message_type=ActorMessageType.REQUEST,
            method="run",
            params={
                "agent_name": "echo_agent", 
                "messages": "not_a_list"  # Invalid format
            },
        )

        # Process message by simulating the actor handling
        await echo_actor._handle_agent_request(request, mock_context)

        # Check error response
        assert "test-789" in mock_context._completed_requests
        response = mock_context._completed_requests["test-789"]

        assert response.status == RequestStatus.FAILED
        assert "error" in response.data

    @pytest.mark.asyncio
    async def test_agent_actor_state_persistence(self, echo_actor, mock_context):
        # Send first message
        request1 = ActorRequestMessage(
            message_id="msg-1",
            message_type=ActorMessageType.REQUEST,
            method="run",
            params={
                "agent_name": "echo_agent",
                "messages": [ChatMessage(role=ChatRole.USER, text="First message")]
            },
        )

        await echo_actor._handle_agent_request(request1, mock_context)

        # Check thread state was saved
        thread_state = await mock_context.read_state(AgentActor.THREAD_STATE_KEY)
        assert thread_state is not None
        assert "messages" in thread_state
        assert len(thread_state["messages"]) == 2  # User + assistant message

        # Send second message
        request2 = ActorRequestMessage(
            message_id="msg-2",
            message_type=ActorMessageType.REQUEST,
            method="run",
            params={
                "agent_name": "echo_agent",
                "messages": [ChatMessage(role=ChatRole.USER, text="Second message")]
            },
        )

        await echo_actor._handle_agent_request(request2, mock_context)

        # Check thread state includes conversation history
        thread_state = await mock_context.read_state(AgentActor.THREAD_STATE_KEY)
        assert len(thread_state["messages"]) == 4  # 2 user + 2 assistant messages
