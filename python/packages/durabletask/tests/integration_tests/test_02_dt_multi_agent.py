# Copyright (c) Microsoft. All rights reserved.

"""Integration tests for multi-agent functionality.

Tests operations with multiple specialized agents:
- Multiple agent registration
- Agent-specific tool usage
- Independent thread management per agent
- Concurrent agent operations
- Agent isolation and tool routing
"""

import pytest

# Agent names from the 02_multi_agent sample
WEATHER_AGENT_NAME: str = "WeatherAgent"
MATH_AGENT_NAME: str = "MathAgent"

# Module-level markers - applied to all tests in this module
pytestmark = [
    pytest.mark.flaky,
    pytest.mark.integration,
    pytest.mark.sample("02_multi_agent"),
    pytest.mark.integration_test,
    pytest.mark.requires_azure_openai,
    pytest.mark.requires_dts,
]


class TestMultiAgent:
    """Test suite for multi-agent functionality."""

    @pytest.fixture(autouse=True)
    def setup(self, agent_client_factory: type) -> None:
        """Setup test fixtures."""
        # Create agent client using the factory fixture
        _, self.agent_client = agent_client_factory.create()

    def test_multiple_agents_registered(self) -> None:
        """Test that both agents are registered and accessible."""
        weather_agent = self.agent_client.get_agent(WEATHER_AGENT_NAME)
        math_agent = self.agent_client.get_agent(MATH_AGENT_NAME)

        assert weather_agent is not None
        assert weather_agent.name == WEATHER_AGENT_NAME
        assert math_agent is not None
        assert math_agent.name == MATH_AGENT_NAME

    def test_weather_agent_with_tool(self):
        """Test weather agent with weather tool execution."""
        agent = self.agent_client.get_agent(WEATHER_AGENT_NAME)
        session = agent.create_session()

        response = agent.run("What's the weather in Seattle?", session=session)

        assert response is not None
        assert response.text is not None
        # Should contain weather information from the tool
        assert len(response.text) > 0

        # Verify that the get_weather tool was actually invoked
        tool_calls = [
            content for msg in response.messages for content in msg.contents if content.type == "function_call"
        ]
        assert len(tool_calls) > 0, "Expected at least one tool call"
        assert any(call.name == "get_weather" for call in tool_calls), "Expected get_weather tool to be called"

    def test_math_agent_with_tool(self):
        """Test math agent with calculation tool execution."""
        agent = self.agent_client.get_agent(MATH_AGENT_NAME)
        session = agent.create_session()

        response = agent.run("Calculate a 20% tip on a $50 bill.", session=session)

        assert response is not None
        assert response.text is not None
        # Should contain calculation results from the tool
        assert len(response.text) > 0

        # Verify that the calculate_tip tool was actually invoked
        tool_calls = [
            content for msg in response.messages for content in msg.contents if content.type == "function_call"
        ]
        assert len(tool_calls) > 0, "Expected at least one tool call"
        assert any(call.name == "calculate_tip" for call in tool_calls), "Expected calculate_tip tool to be called"

    def test_multiple_calls_to_same_agent(self):
        """Test multiple sequential calls to the same agent."""
        agent = self.agent_client.get_agent(WEATHER_AGENT_NAME)
        session = agent.create_session()

        # Multiple weather queries
        response1 = agent.run("What's the weather in Chicago?", session=session)
        response2 = agent.run("And what about Los Angeles?", session=session)

        assert response1 is not None
        assert response2 is not None
        assert len(response1.text) > 0
        assert len(response2.text) > 0
