# Copyright (c) Microsoft. All rights reserved.

"""Test multi-turn conversations with function tools in Azure AI."""

from typing import Annotated
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import tool
from azure.ai.projects.models import PromptAgentDefinition
from pydantic import Field

from agent_framework_azure_ai import AzureAIProjectAgentProvider


@tool(approval_mode="never_require")
def calculate_tip(
    bill_amount: Annotated[float, Field(description="Bill amount in dollars")],
    tip_percent: Annotated[float, Field(description="Tip percentage")],
) -> str:
    """Calculate tip amount for a bill."""
    tip = bill_amount * (tip_percent / 100)
    return f"Tip: ${tip:.2f}, Total: ${bill_amount + tip:.2f}"


@pytest.mark.asyncio
async def test_multi_turn_function_tools_does_not_resubmit_old_results():
    """Test that multi-turn conversations don't re-submit old function call results."""
    # Setup mock project client
    mock_project_client = AsyncMock()
    mock_agents = AsyncMock()
    mock_project_client.agents = mock_agents

    # Mock agent creation
    mock_agent_version = MagicMock()
    mock_agent_version.id = "agent_id_123"
    mock_agent_version.name = "tip-calculator"
    mock_agent_version.version = "v1"
    mock_agent_version.description = None
    mock_agent_version.definition = PromptAgentDefinition(
        model="gpt-4",
        instructions="Use the calculate_tip tool to help with calculations.",
        tools=[],
    )
    mock_agents.create_version = AsyncMock(return_value=mock_agent_version)

    # Mock OpenAI client that tracks requests
    requests_made = []

    def mock_create_response(**kwargs):
        """Mock response creation that tracks inputs."""
        requests_made.append(kwargs)

        # Simulate a response with function call on turn 1
        if len(requests_made) == 1:
            mock_response = MagicMock()
            mock_response.id = "resp_turn1"
            mock_response.created_at = 1234567890
            mock_response.model = "gpt-4"
            mock_response.usage = None
            mock_response.metadata = {}

            # Return a function call
            mock_function_call = MagicMock()
            mock_function_call.type = "function_call"
            mock_function_call.id = "fc_call_123"
            mock_function_call.call_id = "call_123"
            mock_function_call.name = "calculate_tip"
            mock_function_call.arguments = '{"bill_amount": 85, "tip_percent": 15}'

            mock_response.output = [mock_function_call]
            return mock_response
        # Turn 2: Return a text response
        mock_response = MagicMock()
        mock_response.id = "resp_turn2"
        mock_response.created_at = 1234567891
        mock_response.model = "gpt-4"
        mock_response.usage = None
        mock_response.metadata = {}

        mock_message = MagicMock()
        mock_message.type = "message"
        mock_text = MagicMock()
        mock_text.type = "output_text"
        mock_text.text = "The 20% tip is calculated."
        mock_message.content = [mock_text]

        mock_response.output = [mock_message]
        return mock_response

    mock_openai_client = MagicMock()
    mock_openai_client.responses = MagicMock()
    mock_openai_client.responses.create = AsyncMock(side_effect=mock_create_response)
    mock_project_client.get_openai_client = MagicMock(return_value=mock_openai_client)

    # Create provider and agent
    provider = AzureAIProjectAgentProvider(project_client=mock_project_client, model="gpt-4")
    agent = await provider.create_agent(
        name="tip-calculator",
        instructions="Use the calculate_tip tool to help with calculations.",
        tools=[calculate_tip],
    )

    # Single thread for multi-turn (BUG TRIGGER)
    thread = agent.get_new_thread()

    # Turn 1: Should work fine
    result1 = await agent.run("Calculate 15% tip on an $85 bill", thread=thread)
    assert result1 is not None

    # Check Turn 1 request - should have the user message
    turn1_request = requests_made[0]
    turn1_input = turn1_request["input"]
    assert any(item.get("role") == "user" for item in turn1_input if isinstance(item, dict))

    # Turn 2: Should NOT re-submit function call results from Turn 1
    result2 = await agent.run("Now calculate 20% tip on the same $85 bill", thread=thread)
    assert result2 is not None

    # Check Turn 2 request - should NOT have function_call_output from Turn 1
    turn2_request = requests_made[-1]  # Last request made (after function execution)
    turn2_input = turn2_request["input"]

    # The key assertion: Turn 2 should only have NEW function outputs (from turn 2's function calls)
    # If it has function outputs from turn 1, that's the bug we're fixing
    # Since turn 2 likely also has a function call, we need to check that old outputs aren't there

    # A more robust check: verify that turn 2's input doesn't contain the call_id from turn 1
    turn1_call_id = "call_123"
    has_old_function_output = any(
        item.get("type") == "function_call_output" and item.get("call_id") == turn1_call_id
        for item in turn2_input
        if isinstance(item, dict)
    )

    assert not has_old_function_output, (
        "Turn 2 should not re-submit function_call_output from Turn 1. "
        "Found old function output with call_id from Turn 1."
    )


@pytest.mark.asyncio
async def test_multi_turn_with_previous_response_id_filters_old_messages():
    """Test that when using previous_response_id, old function results are filtered."""
    # Setup mock project client
    mock_project_client = AsyncMock()
    mock_agents = AsyncMock()
    mock_project_client.agents = mock_agents

    # Mock agent creation
    mock_agent_version = MagicMock()
    mock_agent_version.id = "agent_id_123"
    mock_agent_version.name = "test-agent"
    mock_agent_version.version = "v1"
    mock_agent_version.description = None
    mock_agent_version.definition = PromptAgentDefinition(
        model="gpt-4",
        instructions="You are a helpful assistant.",
        tools=[],
    )
    mock_agents.create_version = AsyncMock(return_value=mock_agent_version)

    # Mock OpenAI client
    requests_made = []

    def mock_create_response(**kwargs):
        """Mock response creation."""
        requests_made.append(kwargs)
        mock_response = MagicMock()
        mock_response.id = f"resp_turn{len(requests_made)}"
        mock_response.created_at = 1234567890 + len(requests_made)
        mock_response.model = "gpt-4"
        mock_response.usage = None
        mock_response.metadata = {}
        mock_message = MagicMock()
        mock_message.type = "message"
        mock_text = MagicMock()
        mock_text.type = "output_text"
        mock_text.text = f"Response {len(requests_made)}"
        mock_message.content = [mock_text]
        mock_response.output = [mock_message]
        return mock_response

    mock_openai_client = MagicMock()
    mock_openai_client.responses = MagicMock()
    mock_openai_client.responses.create = AsyncMock(side_effect=mock_create_response)
    mock_project_client.get_openai_client = MagicMock(return_value=mock_openai_client)

    # Create provider and agent
    provider = AzureAIProjectAgentProvider(project_client=mock_project_client, model="gpt-4")
    agent = await provider.create_agent(
        name="test-agent",
        instructions="You are a helpful assistant.",
        tools=[calculate_tip],
    )

    # Create a thread starting with a service_thread_id (simulating a previous response)
    # This avoids the message_store/service_thread_id conflict
    thread = agent.get_new_thread()
    # Simulate that turn 1 has already completed and returned resp_turn1
    # We manually set the internal state to simulate this

    # Use the internal property to bypass the setter validation
    thread._service_thread_id = "resp_turn1"

    # Turn 2: New user message
    # This turn should only send the new user message, not any messages from turn 1
    result2 = await agent.run("Now calculate 20% tip", thread=thread)
    assert result2 is not None

    # Check that turn 2 request has previous_response_id set
    turn2_request = requests_made[0]
    assert "previous_response_id" in turn2_request
    assert turn2_request["previous_response_id"] == "resp_turn1"

    # Check that turn 2 input doesn't contain old function results
    # Since we're using service_thread_id, the messages are managed server-side
    # and only the new user message should be in the request
    turn2_input = turn2_request["input"]

    # Turn 2 should only have the NEW user message
    user_messages = [item for item in turn2_input if isinstance(item, dict) and item.get("role") == "user"]
    assert len(user_messages) == 1, "Turn 2 should only have the NEW user message"
