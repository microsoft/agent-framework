# Copyright (c) Microsoft. All rights reserved.

"""Tests for lightning module."""

# ruff: noqa
from unittest.mock import AsyncMock, patch

import pytest

agentlightning = pytest.importorskip("agentlightning")

from agent_framework import AgentExecutor, AgentRunEvent, ChatAgent, WorkflowBuilder, Workflow
from agent_framework_lab_lightning import AgentFrameworkTracer
from agent_framework.openai import OpenAIChatClient
from agentlightning import TracerTraceToTriplet
from openai.types.chat import ChatCompletion, ChatCompletionMessage
from openai.types.chat.chat_completion import Choice


@pytest.fixture
def workflow_two_agents():
    """Test a workflow with two OpenAI chat agents where first agent's result passes to second agent."""

    # Mock OpenAI responses
    first_agent_response = ChatCompletion(
        id="chatcmpl-123",
        object="chat.completion",
        created=1677652288,
        model="gpt-4o",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(role="assistant", content="Analyzed data shows trend upward"),
                finish_reason="stop",
            )
        ],
    )

    second_agent_response = ChatCompletion(
        id="chatcmpl-456",
        object="chat.completion",
        created=1677652289,
        model="gpt-4o",
        choices=[
            Choice(
                index=0,
                message=ChatCompletionMessage(
                    role="assistant",
                    content="Based on the analysis 'Analyzed data shows trend upward', I recommend investing",
                ),
                finish_reason="stop",
            )
        ],
    )

    # Create mock OpenAI clients
    with patch.dict(
        "os.environ",
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_CHAT_MODEL_ID": "gpt-4o",
        },
    ):
        first_chat_client = OpenAIChatClient()
        second_chat_client = OpenAIChatClient()

        # Mock the OpenAI API calls
        with (
            patch.object(
                first_chat_client.client.chat.completions,
                "create",
                new_callable=AsyncMock,
                return_value=first_agent_response,
            ),
            patch.object(
                second_chat_client.client.chat.completions,
                "create",
                new_callable=AsyncMock,
                return_value=second_agent_response,
            ),
        ):
            # Create the two agents
            analyzer_agent = ChatAgent(
                chat_client=first_chat_client,
                name="DataAnalyzer",
                instructions="You are a data analyst. Analyze the given data and provide insights.",
            )

            advisor_agent = ChatAgent(
                chat_client=second_chat_client,
                name="InvestmentAdvisor",
                instructions="You are an investment advisor. Based on analysis results, provide recommendations.",
            )

            analyzer_executor = AgentExecutor(id="analyzer", agent=analyzer_agent)
            advisor_executor = AgentExecutor(id="advisor", agent=advisor_agent)

            # Build workflow: analyzer -> advisor
            workflow = (
                WorkflowBuilder()
                .set_start_executor(analyzer_executor)
                .add_edge(analyzer_executor, advisor_executor)
                .build()
            )

            yield workflow


async def test_openai_workflow_two_agents(workflow_two_agents: Workflow):
    events = await workflow_two_agents.run("Please analyze the quarterly sales data")

    # Get all AgentRunEvent data
    agent_outputs = [event.data for event in events if isinstance(event, AgentRunEvent)]

    # Check that we have outputs from both agents
    assert len(agent_outputs) == 2
    assert any("Analyzed data shows trend upward" in str(output) for output in agent_outputs)
    assert any(
        "Based on the analysis 'Analyzed data shows trend upward', I recommend investing" in str(output)
        for output in agent_outputs
    )


async def test_observability(workflow_two_agents: Workflow):
    r"""Expected trace tree:

                    [workflow.run]
                    /      \
            [analyzer]      [advisor]
            /      \          /    \
    [DataAnalyzer] [send] [Investment] [send]
            |                    |
        [chat gpt-4o]        [chat gpt-4o]
    """
    tracer = AgentFrameworkTracer()
    try:
        tracer.init()
        tracer.init_worker(0)

        async with tracer.trace_context():
            await workflow_two_agents.run("Please analyze the quarterly sales data")

        triplets = TracerTraceToTriplet(agent_match=None, llm_call_match="chat").adapt(tracer.get_last_trace())
        assert len(triplets) == 2

        triplets = TracerTraceToTriplet(agent_match="analyzer", llm_call_match="chat").adapt(tracer.get_last_trace())
        assert len(triplets) == 1

        triplets = TracerTraceToTriplet(agent_match="advisor", llm_call_match="chat").adapt(tracer.get_last_trace())
        assert len(triplets) == 1

        # Parent agent is not matched
        triplets = TracerTraceToTriplet(agent_match="DataAnalyzer", llm_call_match="chat").adapt(
            tracer.get_last_trace()
        )
        assert len(triplets) == 0

        triplets = TracerTraceToTriplet(agent_match="InvestmentAdvisor|advisor", llm_call_match="chat").adapt(
            tracer.get_last_trace()
        )
        assert len(triplets) == 1

    finally:
        tracer.teardown_worker(0)
        tracer.teardown()
