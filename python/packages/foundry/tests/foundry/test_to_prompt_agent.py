# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Annotated, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_framework import Agent, MCPStdioTool, tool
from agent_framework._feature_stage import ExperimentalFeature
from azure.ai.projects.models import (
    CodeInterpreterTool,
    PromptAgentDefinition,
    WebSearchTool,
)
from azure.ai.projects.models import (
    FunctionTool as ProjectsFunctionTool,
)
from azure.ai.projects.models import (
    MCPTool as FoundryMCPTool,
)
from azure.ai.projects.models import (
    Tool as ProjectsTool,
)

from agent_framework_foundry import (
    FoundryChatClient,
    RawFoundryChatClient,
    deploy_as_prompt_agent,
    to_prompt_agent,
)


@tool
def get_weather(location: Annotated[str, "City name"]) -> str:
    """Get the weather for a location."""
    return f"sunny in {location}"


def _make_foundry_chat_client(model: str | None = "gpt-4o-mini") -> FoundryChatClient:
    """Build a FoundryChatClient backed by a mocked project client."""
    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()
    return FoundryChatClient(project_client=mock_project, model=model or "placeholder")


def _make_agent(client: Any, **agent_kwargs: Any) -> Agent:
    """Build an Agent without entering the async context manager."""
    return Agent(client=client, **agent_kwargs)


def test_to_prompt_agent_minimal() -> None:
    """An agent with only model + instructions produces a valid PromptAgentDefinition."""
    agent = _make_agent(_make_foundry_chat_client(), instructions="Be helpful.")

    definition = to_prompt_agent(agent)

    assert isinstance(definition, PromptAgentDefinition)
    assert definition.model == "gpt-4o-mini"
    assert definition.instructions == "Be helpful."
    assert definition.tools is None


def test_to_prompt_agent_serializes_cleanly() -> None:
    """The PromptAgentDefinition serializes to a dict that includes ``kind: prompt``."""
    agent = _make_agent(_make_foundry_chat_client(), instructions="Hi.")

    payload = to_prompt_agent(agent).as_dict()

    assert payload["model"] == "gpt-4o-mini"
    assert payload["instructions"] == "Hi."
    assert payload["kind"] == "prompt"


def test_to_prompt_agent_rejects_non_foundry_client() -> None:
    """A non-FoundryChatClient client raises TypeError."""

    class NotFoundryChatClient:
        """Stand-in for a different chat client implementation."""

    agent = _make_agent(NotFoundryChatClient())

    with pytest.raises(TypeError, match="FoundryChatClient"):
        to_prompt_agent(agent)


def test_to_prompt_agent_rejects_missing_model() -> None:
    """When neither default_options nor the client has a model, ValueError is raised."""
    client = _make_foundry_chat_client()
    client.model = ""  # simulate unset model on the client
    agent = _make_agent(client)
    agent.default_options.pop("model", None)  # and on the agent

    with pytest.raises(ValueError, match="Agent has no model"):
        to_prompt_agent(agent)


def test_to_prompt_agent_no_instructions() -> None:
    """A tool-only agent (no instructions) produces a definition with instructions=None.

    Agent.__init__ strips None values from default_options, so reading
    default_options.get("instructions") returns None as expected.
    """
    agent = _make_agent(
        _make_foundry_chat_client(),
        tools=[WebSearchTool()],
    )

    definition = to_prompt_agent(agent)

    assert definition.model == "gpt-4o-mini"
    assert definition.instructions is None
    payload = definition.as_dict()
    # The optional ``instructions`` field is omitted from the serialized output when unset.
    assert "instructions" not in payload


def test_to_prompt_agent_prefers_default_options_model() -> None:
    """default_options['model'] wins over the bound client's model.

    Matches Agent.__init__'s resolution order (_agents.py:740), so the value
    the agent actually runs with is the same value the converter publishes.
    """
    client = _make_foundry_chat_client(model="client-model")
    agent = _make_agent(client, instructions="x", default_options={"model": "agent-override"})

    definition = to_prompt_agent(agent)

    assert definition.model == "agent-override"


def test_to_prompt_agent_falls_back_to_client_model() -> None:
    """When the agent has no model override, the bound client's model is used."""
    agent = _make_agent(_make_foundry_chat_client(model="client-model"), instructions="x")

    definition = to_prompt_agent(agent)

    assert definition.model == "client-model"


def test_to_prompt_agent_passes_through_sdk_tool_instances() -> None:
    """Foundry SDK tool instances (e.g. WebSearchTool) are passed through unchanged."""
    ws = WebSearchTool()
    ci = CodeInterpreterTool(container={"type": "auto"})
    agent = _make_agent(_make_foundry_chat_client(), instructions="x", tools=[ws, ci])

    definition = to_prompt_agent(agent)

    assert definition.tools is not None
    assert len(definition.tools) == 2
    # Pass-through: same object identity
    assert definition.tools[0] is ws
    assert definition.tools[1] is ci


def test_to_prompt_agent_converts_function_tool() -> None:
    """An AF FunctionTool from @tool emerges as a Foundry FunctionTool declaration."""
    agent = _make_agent(_make_foundry_chat_client(), instructions="x", tools=[get_weather])

    definition = to_prompt_agent(agent)

    assert definition.tools is not None
    assert len(definition.tools) == 1
    fn = definition.tools[0]
    assert isinstance(fn, ProjectsFunctionTool)
    assert fn.name == "get_weather"
    assert fn.description == "Get the weather for a location."
    assert fn.strict is False
    parameters = fn.parameters
    assert parameters["type"] == "object"
    assert "location" in parameters["properties"]
    assert parameters["required"] == ["location"]


def test_to_prompt_agent_preserves_mixed_tool_order() -> None:
    """A mix of hosted SDK tools and function tools is preserved in definition order."""
    ws = WebSearchTool()
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        tools=[ws, get_weather],
    )

    definition = to_prompt_agent(agent)

    assert definition.tools is not None
    assert definition.tools[0] is ws
    assert isinstance(definition.tools[1], ProjectsFunctionTool)
    assert definition.tools[1].name == "get_weather"


def test_to_prompt_agent_passes_through_hosted_mcp_tool() -> None:
    """A hosted MCP tool from FoundryChatClient.get_mcp_tool() is passed through."""
    hosted_mcp = FoundryChatClient.get_mcp_tool(
        name="github",
        url="https://mcp.example.com",
    )
    agent = _make_agent(_make_foundry_chat_client(), instructions="x", tools=[hosted_mcp])

    definition = to_prompt_agent(agent)

    assert definition.tools is not None
    assert len(definition.tools) == 1
    assert isinstance(definition.tools[0], FoundryMCPTool)


def test_to_prompt_agent_rejects_local_mcp_tool() -> None:
    """A local MCP tool in agent.mcp_tools raises a ValueError pointing at get_mcp_tool."""
    local_mcp = MCPStdioTool(name="local_fs", command="echo")
    agent = _make_agent(_make_foundry_chat_client(), instructions="x", tools=[local_mcp])

    with pytest.raises(ValueError, match="get_mcp_tool"):
        to_prompt_agent(agent)


def test_to_prompt_agent_rejects_unknown_tool_type() -> None:
    """An arbitrary object in tools that isn't a known shape raises ValueError."""

    class NotATool:
        pass

    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        tools=[NotATool()],
    )

    with pytest.raises(ValueError, match="NotATool"):
        to_prompt_agent(agent)


def test_to_prompt_agent_accepts_dict_tool() -> None:
    """A dict with a 'type' discriminator is rehydrated through the SDK Tool model."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        tools=[{"type": "web_search"}],
    )

    definition = to_prompt_agent(agent)

    assert definition.tools is not None
    assert len(definition.tools) == 1
    tool_obj = definition.tools[0]
    assert isinstance(tool_obj, ProjectsTool)
    assert tool_obj.type == "web_search"


def test_to_prompt_agent_rejects_dict_tool_without_type() -> None:
    """A dict missing the 'type' field raises ValueError."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        tools=[{"name": "missing_type"}],
    )

    with pytest.raises(ValueError, match="type"):
        to_prompt_agent(agent)


def test_to_prompt_agent_works_with_raw_foundry_chat_client() -> None:
    """to_prompt_agent accepts subclasses too — RawFoundryChatClient works."""
    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()
    raw_client = RawFoundryChatClient(project_client=mock_project, model="gpt-4o")
    agent = _make_agent(raw_client, instructions="x")

    definition = to_prompt_agent(agent)

    assert definition.model == "gpt-4o"


def test_to_prompt_agent_is_marked_experimental() -> None:
    """to_prompt_agent carries the TO_PROMPT_AGENT experimental metadata."""
    assert getattr(to_prompt_agent, "__feature_stage__", None) == "experimental"
    assert getattr(to_prompt_agent, "__feature_id__", None) == ExperimentalFeature.TO_PROMPT_AGENT.value


def _make_foundry_chat_client_with_async_agents_ops(
    model: str | None = "gpt-4o-mini",
) -> tuple[FoundryChatClient, AsyncMock]:
    """Build a FoundryChatClient backed by a mocked project client whose ``agents.create_version`` is awaitable."""
    mock_project = MagicMock()
    mock_project.get_openai_client.return_value = MagicMock()
    create_version = AsyncMock(return_value=MagicMock(name="travel-agent", version="1"))
    mock_project.agents = MagicMock(create_version=create_version)
    client = FoundryChatClient(project_client=mock_project, model=model or "placeholder")
    return client, create_version


async def test_deploy_as_prompt_agent_publishes_definition() -> None:
    """deploy_as_prompt_agent calls project_client.agents.create_version with the converted definition."""
    client, create_version = _make_foundry_chat_client_with_async_agents_ops()
    agent = _make_agent(client, instructions="x", tools=[WebSearchTool()])

    result = await deploy_as_prompt_agent(agent, agent_name="travel-agent")

    create_version.assert_awaited_once()
    call_kwargs = create_version.await_args.kwargs
    assert call_kwargs["agent_name"] == "travel-agent"
    definition = call_kwargs["definition"]
    assert isinstance(definition, PromptAgentDefinition)
    assert definition.model == "gpt-4o-mini"
    assert definition.tools is not None and len(definition.tools) == 1
    assert "metadata" not in call_kwargs
    assert "description" not in call_kwargs
    assert result is create_version.return_value


async def test_deploy_as_prompt_agent_defaults_name_and_description_from_agent() -> None:
    """When the Agent has name/description, the helper lifts them so the call site stays minimal."""
    client, create_version = _make_foundry_chat_client_with_async_agents_ops()
    agent = _make_agent(
        client,
        instructions="x",
        name="travel-agent",
        description="Helps Contoso employees book travel.",
    )

    await deploy_as_prompt_agent(agent)

    call_kwargs = create_version.await_args.kwargs
    assert call_kwargs["agent_name"] == "travel-agent"
    assert call_kwargs["description"] == "Helps Contoso employees book travel."


async def test_deploy_as_prompt_agent_explicit_overrides_win() -> None:
    """Explicit agent_name and description kwargs override the values from the Agent."""
    client, create_version = _make_foundry_chat_client_with_async_agents_ops()
    agent = _make_agent(
        client,
        instructions="x",
        name="travel-agent",
        description="Agent-level description",
    )

    await deploy_as_prompt_agent(
        agent,
        agent_name="travel-agent-v2",
        description="Override description",
    )

    call_kwargs = create_version.await_args.kwargs
    assert call_kwargs["agent_name"] == "travel-agent-v2"
    assert call_kwargs["description"] == "Override description"


async def test_deploy_as_prompt_agent_requires_an_agent_name() -> None:
    """If neither agent_name nor agent.name is set, a ValueError is raised before any service call."""
    client, create_version = _make_foundry_chat_client_with_async_agents_ops()
    agent = _make_agent(client, instructions="x")
    agent.name = None  # mirror an Agent constructed without a name

    with pytest.raises(ValueError, match="agent_name"):
        await deploy_as_prompt_agent(agent)
    create_version.assert_not_awaited()


async def test_deploy_as_prompt_agent_forwards_metadata_and_description() -> None:
    """Optional metadata + description land on the create_version call."""
    client, create_version = _make_foundry_chat_client_with_async_agents_ops()
    agent = _make_agent(client, instructions="x")

    await deploy_as_prompt_agent(
        agent,
        agent_name="travel-agent",
        metadata={"env": "prod"},
        description="Production travel agent",
    )

    call_kwargs = create_version.await_args.kwargs
    assert call_kwargs["metadata"] == {"env": "prod"}
    assert call_kwargs["description"] == "Production travel agent"


async def test_deploy_as_prompt_agent_forwards_extra_kwargs() -> None:
    """Extra keyword args fall through to project_client.agents.create_version."""
    client, create_version = _make_foundry_chat_client_with_async_agents_ops()
    agent = _make_agent(client, instructions="x")

    await deploy_as_prompt_agent(agent, agent_name="travel-agent", headers={"x-trace": "abc"})

    assert create_version.await_args.kwargs["headers"] == {"x-trace": "abc"}


async def test_deploy_as_prompt_agent_rejects_non_foundry_client() -> None:
    """A non-FoundryChatClient client raises TypeError before any service call."""

    class NotFoundryChatClient:
        """Stand-in for a different chat client implementation."""

    agent = _make_agent(NotFoundryChatClient())

    with pytest.raises(TypeError, match="FoundryChatClient"):
        await deploy_as_prompt_agent(agent, agent_name="travel-agent")


def test_deploy_as_prompt_agent_is_marked_experimental() -> None:
    """deploy_as_prompt_agent carries the TO_PROMPT_AGENT experimental metadata."""
    assert getattr(deploy_as_prompt_agent, "__feature_stage__", None) == "experimental"
    assert getattr(deploy_as_prompt_agent, "__feature_id__", None) == ExperimentalFeature.TO_PROMPT_AGENT.value
