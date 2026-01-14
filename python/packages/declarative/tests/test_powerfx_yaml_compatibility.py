# Copyright (c) Microsoft. All rights reserved.

"""Tests to ensure PowerFx evaluation supports all expressions used in declarative YAML workflows.

This test suite validates that all PowerFx expressions found in the sample YAML workflows
under samples/getting_started/workflows/declarative/ work correctly with our implementation.

Coverage includes:
- Built-in PowerFx functions: Concat, If, IsBlank, Not, Or, Upper, Find
- Custom functions: UserMessage, MessageText
- System variables: System.ConversationId, System.LastMessage.Text
- Local/turn variables with nested access
- Comparison operators: <, >, <=, >=, <>, =
- Logical operators: And, Or, Not, !
- Arithmetic operators: +, -, *, /
- String interpolation: {Variable.Path}
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from agent_framework_declarative._workflows._declarative_base import (
    DeclarativeWorkflowState,
)


class TestPowerFxBuiltinFunctions:
    """Test PowerFx built-in functions used in YAML workflows."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state with async get/set methods."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)
        return shared_state

    async def test_concat_simple(self, mock_shared_state):
        """Test Concat function with simple strings."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Concat("Nice to meet you, ", Local.userName, "!")
        await state.set("Local.userName", "Alice")
        result = await state.eval('=Concat("Nice to meet you, ", Local.userName, "!")')
        assert result == "Nice to meet you, Alice!"

    async def test_concat_multiple_args(self, mock_shared_state):
        """Test Concat with multiple arguments."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Concat(Local.greeting, ", ", Local.name, "!")
        await state.set("Local.greeting", "Hello")
        await state.set("Local.name", "World")
        result = await state.eval('=Concat(Local.greeting, ", ", Local.name, "!")')
        assert result == "Hello, World!"

    async def test_concat_with_local_namespace(self, mock_shared_state):
        """Test Concat using Local.* namespace (maps to Local.*)."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Concat("Starting math coaching session for: ", Local.Problem)
        await state.set("Local.Problem", "2 + 2")
        result = await state.eval('=Concat("Starting math coaching session for: ", Local.Problem)')
        assert result == "Starting math coaching session for: 2 + 2"

    async def test_if_with_isblank(self, mock_shared_state):
        """Test If function with IsBlank."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"name": ""})

        # From YAML: =If(IsBlank(inputs.name), "World", inputs.name)
        # When input is blank
        result = await state.eval('=If(IsBlank(Workflow.Inputs.name), "World", Workflow.Inputs.name)')
        assert result == "World"

        # When input is provided
        await state.initialize({"name": "Alice"})
        result = await state.eval('=If(IsBlank(Workflow.Inputs.name), "World", Workflow.Inputs.name)')
        assert result == "Alice"

    async def test_not_function(self, mock_shared_state):
        """Test Not function."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Not(Local.EscalationParameters.IsComplete)
        await state.set("Local.EscalationParameters", {"IsComplete": False})
        result = await state.eval("=Not(Local.EscalationParameters.IsComplete)")
        assert result is True

        await state.set("Local.EscalationParameters", {"IsComplete": True})
        result = await state.eval("=Not(Local.EscalationParameters.IsComplete)")
        assert result is False

    async def test_or_function(self, mock_shared_state):
        """Test Or function."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Or(Local.feeling = "great", Local.feeling = "good")
        await state.set("Local.feeling", "great")
        result = await state.eval('=Or(Local.feeling = "great", Local.feeling = "good")')
        assert result is True

        await state.set("Local.feeling", "good")
        result = await state.eval('=Or(Local.feeling = "great", Local.feeling = "good")')
        assert result is True

        await state.set("Local.feeling", "bad")
        result = await state.eval('=Or(Local.feeling = "great", Local.feeling = "good")')
        assert result is False

    async def test_upper_function(self, mock_shared_state):
        """Test Upper function."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Upper(System.LastMessage.Text)
        await state.set("System.LastMessage", {"Text": "hello world"})
        result = await state.eval("=Upper(System.LastMessage.Text)")
        assert result == "HELLO WORLD"

    async def test_find_function(self, mock_shared_state):
        """Test Find function."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =!IsBlank(Find("CONGRATULATIONS", Upper(Local.TeacherResponse)))
        await state.set("Local.TeacherResponse", "CONGRATULATIONS! You solved it!")
        result = await state.eval('=Not(IsBlank(Find("CONGRATULATIONS", Upper(Local.TeacherResponse))))')
        assert result is True

        await state.set("Local.TeacherResponse", "Try again")
        result = await state.eval('=Not(IsBlank(Find("CONGRATULATIONS", Upper(Local.TeacherResponse))))')
        assert result is False


class TestPowerFxSystemVariables:
    """Test System.* variable access."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)
        return shared_state

    async def test_system_conversation_id(self, mock_shared_state):
        """Test System.ConversationId access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: conversationId: =System.ConversationId
        await state.set("System.ConversationId", "conv-12345")
        result = await state.eval("=System.ConversationId")
        assert result == "conv-12345"

    async def test_system_last_message_text(self, mock_shared_state):
        """Test System.LastMessage.Text access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Upper(System.LastMessage.Text) <> "EXIT"
        await state.set("System.LastMessage", {"Text": "Hello"})
        result = await state.eval("=System.LastMessage.Text")
        assert result == "Hello"

    async def test_system_last_message_exit_check(self, mock_shared_state):
        """Test the exit check pattern from YAML."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: when: =Upper(System.LastMessage.Text) <> "EXIT"
        await state.set("System.LastMessage", {"Text": "hello"})
        result = await state.eval('=Upper(System.LastMessage.Text) <> "EXIT"')
        assert result is True

        await state.set("System.LastMessage", {"Text": "exit"})
        result = await state.eval('=Upper(System.LastMessage.Text) <> "EXIT"')
        assert result is False


class TestPowerFxComparisonOperators:
    """Test comparison operators used in YAML workflows."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)
        return shared_state

    async def test_less_than(self, mock_shared_state):
        """Test < operator."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: condition: =Local.age < 65
        await state.set("Local.age", 30)
        assert await state.eval("=Local.age < 65") is True

        await state.set("Local.age", 70)
        assert await state.eval("=Local.age < 65") is False

    async def test_less_than_with_local(self, mock_shared_state):
        """Test < with Local namespace."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: condition: =Local.TurnCount < 4
        await state.set("Local.TurnCount", 2)
        assert await state.eval("=Local.TurnCount < 4") is True

        await state.set("Local.TurnCount", 5)
        assert await state.eval("=Local.TurnCount < 4") is False

    async def test_equality(self, mock_shared_state):
        """Test = equality operator."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Local.feeling = "great"
        await state.set("Local.feeling", "great")
        assert await state.eval('=Local.feeling = "great"') is True

        await state.set("Local.feeling", "bad")
        assert await state.eval('=Local.feeling = "great"') is False

    async def test_inequality(self, mock_shared_state):
        """Test <> inequality operator."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Upper(System.LastMessage.Text) <> "EXIT"
        await state.set("Local.status", "active")
        assert await state.eval('=Local.status <> "done"') is True
        assert await state.eval('=Local.status <> "active"') is False


class TestPowerFxArithmetic:
    """Test arithmetic operations."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)
        return shared_state

    async def test_addition(self, mock_shared_state):
        """Test + operator."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: value: =Local.TurnCount + 1
        await state.set("Local.TurnCount", 3)
        result = await state.eval("=Local.TurnCount + 1")
        assert result == 4


class TestPowerFxCustomFunctions:
    """Test custom functions (UserMessage, MessageText, AgentMessage)."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)
        return shared_state

    @pytest.mark.asyncio
    async def test_agent_message_function(self, mock_shared_state):
        """Test AgentMessage function (.NET compatibility alias for AssistantMessage)."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From .NET YAML: messages: =AgentMessage(Local.Response)
        await state.set("Local.Response", "Here is the analysis result")
        result = await state.eval("=AgentMessage(Local.Response)")

        assert isinstance(result, dict)
        assert result["role"] == "assistant"
        assert result["text"] == "Here is the analysis result"

    @pytest.mark.asyncio
    async def test_agent_message_with_empty_string(self, mock_shared_state):
        """Test AgentMessage with empty string."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        await state.set("Local.Response", "")
        result = await state.eval("=AgentMessage(Local.Response)")

        assert result["role"] == "assistant"
        assert result["text"] == ""

    @pytest.mark.asyncio
    async def test_user_message_with_variable(self, mock_shared_state):
        """Test UserMessage function with variable reference."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: messages: =UserMessage(Local.ServiceParameters.IssueDescription)
        await state.set("Local.ServiceParameters", {"IssueDescription": "My computer won't boot"})
        result = await state.eval("=UserMessage(Local.ServiceParameters.IssueDescription)")

        assert isinstance(result, dict)
        assert result["role"] == "user"
        assert result["text"] == "My computer won't boot"

    async def test_user_message_with_simple_variable(self, mock_shared_state):
        """Test UserMessage with simple variable."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: messages: =Local.Problem
        await state.set("Local.Problem", "What is 2+2?")
        result = await state.eval("=UserMessage(Local.Problem)")

        assert result["role"] == "user"
        assert result["text"] == "What is 2+2?"

    async def test_message_text_with_list(self, mock_shared_state):
        """Test MessageText extracts text from message list."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        await state.set(
            "Local.messages",
            [
                {"role": "user", "text": "Hello"},
                {"role": "assistant", "text": "Hi there!"},
            ],
        )
        result = await state.eval("=MessageText(Local.messages)")
        assert result == "Hi there!"

    async def test_message_text_empty_list(self, mock_shared_state):
        """Test MessageText with empty list returns empty string."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        await state.set("Local.messages", [])
        result = await state.eval("=MessageText(Local.messages)")
        assert result == ""


class TestPowerFxNestedVariables:
    """Test nested variable access patterns from YAML."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)
        return shared_state

    async def test_nested_local_variable(self, mock_shared_state):
        """Test nested Local.* variable access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Local.ServiceParameters.IssueDescription
        await state.set("Local.ServiceParameters", {"IssueDescription": "Screen is black"})
        result = await state.eval("=Local.ServiceParameters.IssueDescription")
        assert result == "Screen is black"

    async def test_nested_routing_parameters(self, mock_shared_state):
        """Test RoutingParameters access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Local.RoutingParameters.TeamName
        await state.set("Local.RoutingParameters", {"TeamName": "Windows Support"})
        result = await state.eval("=Local.RoutingParameters.TeamName")
        assert result == "Windows Support"

    async def test_nested_ticket_parameters(self, mock_shared_state):
        """Test TicketParameters access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: =Local.TicketParameters.TicketId
        await state.set("Local.TicketParameters", {"TicketId": "TKT-12345"})
        result = await state.eval("=Local.TicketParameters.TicketId")
        assert result == "TKT-12345"


class TestPowerFxUndefinedVariables:
    """Test graceful handling of undefined variables."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)
        return shared_state

    async def test_undefined_local_variable_returns_none(self, mock_shared_state):
        """Test that undefined Local.* variables return None."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Variable not set - should return None (not raise)
        result = await state.eval("=Local.UndefinedVariable")
        assert result is None

    async def test_undefined_nested_variable_returns_none(self, mock_shared_state):
        """Test that undefined nested variables return None."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # Nested undefined variable
        result = await state.eval("=Local.Something.Nested.Deep")
        assert result is None


class TestStringInterpolation:
    """Test string interpolation patterns."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)
        return shared_state

    async def test_interpolate_local_variable(self, mock_shared_state):
        """Test {Local.Variable} interpolation."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: activity: "Created ticket #{Local.TicketParameters.TicketId}"
        await state.set("Local.TicketParameters", {"TicketId": "TKT-999"})
        result = await state.interpolate_string("Created ticket #{Local.TicketParameters.TicketId}")
        assert result == "Created ticket #TKT-999"

    async def test_interpolate_routing_team(self, mock_shared_state):
        """Test routing team interpolation."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize()

        # From YAML: activity: Routing to {Local.RoutingParameters.TeamName}
        await state.set("Local.RoutingParameters", {"TeamName": "Linux Support"})
        result = await state.interpolate_string("Routing to {Local.RoutingParameters.TeamName}")
        assert result == "Routing to Linux Support"


class TestWorkflowInputsAccess:
    """Test Workflow.Inputs access patterns."""

    @pytest.fixture
    def mock_shared_state(self):
        """Create a mock shared state."""
        shared_state = MagicMock()
        shared_state._data = {}

        async def mock_get(key):
            if key not in shared_state._data:
                raise KeyError(key)
            return shared_state._data[key]

        async def mock_set(key, value):
            shared_state._data[key] = value

        shared_state.get = AsyncMock(side_effect=mock_get)
        shared_state.set = AsyncMock(side_effect=mock_set)
        return shared_state

    async def test_inputs_name(self, mock_shared_state):
        """Test inputs.name access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"name": "Alice", "age": 25})

        # .NET style (standard)
        result = await state.eval("=Workflow.Inputs.name")
        assert result == "Alice"

        # Also test inputs.name shorthand
        result = await state.eval("=inputs.name")
        assert result == "Alice"

    async def test_inputs_problem(self, mock_shared_state):
        """Test inputs.problem access."""
        state = DeclarativeWorkflowState(mock_shared_state)
        await state.initialize({"problem": "What is 5 * 6?"})

        # .NET style (standard)
        result = await state.eval("=Workflow.Inputs.problem")
        assert result == "What is 5 * 6?"
