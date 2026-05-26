# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from typing import Annotated, Any
from unittest.mock import MagicMock

import pytest
from agent_framework import Agent, MCPStdioTool, tool
from agent_framework._feature_stage import ExperimentalFeature
from azure.ai.projects.models import (
    CodeInterpreterTool,
    PromptAgentDefinition,
    PromptAgentDefinitionTextOptions,
    RaiConfig,
    Reasoning,
    StructuredInputDefinition,
    ToolChoiceFunction,
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


# ---------------------------------------------------------------------------
# Core conversion: model resolution and client-type guarding
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tool conversion
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Generation parameters sourced from default_options (with kwarg overrides)
# ---------------------------------------------------------------------------


def test_to_prompt_agent_temperature_top_p_unset_by_default() -> None:
    """Without default_options or kwargs, temperature/top_p are unset on the definition."""
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent)

    assert definition.temperature is None
    assert definition.top_p is None
    payload = definition.as_dict()
    assert "temperature" not in payload
    assert "top_p" not in payload


def test_to_prompt_agent_lifts_temperature_top_p_from_default_options() -> None:
    """temperature/top_p in default_options flow through to the definition."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"temperature": 0.42, "top_p": 0.8},
    )

    definition = to_prompt_agent(agent)

    assert definition.temperature == 0.42
    assert definition.top_p == 0.8


def test_to_prompt_agent_temperature_top_p_kwargs_win_over_default_options() -> None:
    """Explicit kwargs override values present in default_options."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"temperature": 0.42, "top_p": 0.8},
    )

    definition = to_prompt_agent(agent, temperature=0.1, top_p=0.2)

    assert definition.temperature == 0.1
    assert definition.top_p == 0.2


def test_to_prompt_agent_temperature_zero_kwarg_is_honored() -> None:
    """A literal ``0.0`` kwarg is treated as explicit, not as "fall back to default_options".

    Guards against an ``if temperature:`` truthiness check that would silently drop the value.
    """
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"temperature": 0.7},
    )

    definition = to_prompt_agent(agent, temperature=0.0, top_p=0.0)

    assert definition.temperature == 0.0
    assert definition.top_p == 0.0


def test_to_prompt_agent_defaults_tool_choice_to_auto() -> None:
    """Agent.__init__ inserts tool_choice='auto' by default; the converter propagates it."""
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent)

    assert definition.tool_choice == "auto"


def test_to_prompt_agent_lifts_string_tool_choice_from_default_options() -> None:
    """A string ``tool_choice`` in default_options propagates to the definition."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"tool_choice": "required"},
    )

    definition = to_prompt_agent(agent)

    assert definition.tool_choice == "required"


def test_to_prompt_agent_ignores_non_string_tool_choice_from_default_options() -> None:
    """Non-string ``tool_choice`` values (e.g. AF ToolMode) are not auto-propagated."""
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")
    # Replace the str default with a non-str sentinel to mimic an AF ToolMode value.
    agent.default_options["tool_choice"] = object()  # type: ignore[typeddict-item]

    definition = to_prompt_agent(agent)

    assert definition.tool_choice is None


def test_to_prompt_agent_tool_choice_kwarg_wins_over_default_options() -> None:
    """An explicit ``tool_choice`` kwarg wins over a default_options entry."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"tool_choice": "auto"},
    )

    definition = to_prompt_agent(agent, tool_choice="none")

    assert definition.tool_choice == "none"


def test_to_prompt_agent_tool_choice_accepts_param_model() -> None:
    """A ``ToolChoiceParam`` instance passed as kwarg is forwarded to the definition."""
    choice = ToolChoiceFunction(name="get_weather")
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent, tool_choice=choice)

    assert definition.tool_choice is choice


# ---------------------------------------------------------------------------
# Foundry-specific kwargs (no AF ChatOptions equivalent)
# ---------------------------------------------------------------------------


def test_to_prompt_agent_kwarg_only_fields_unset_by_default() -> None:
    """reasoning, text, structured_inputs, rai_config are absent from the payload when unset."""
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    payload = to_prompt_agent(agent).as_dict()

    assert "reasoning" not in payload
    assert "text" not in payload
    assert "structured_inputs" not in payload
    assert "rai_config" not in payload


def test_to_prompt_agent_forwards_reasoning_kwarg() -> None:
    """A ``Reasoning`` kwarg is forwarded to the definition."""
    reasoning = Reasoning(effort="high")
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent, reasoning=reasoning)

    assert definition.reasoning is reasoning


def test_to_prompt_agent_forwards_text_kwarg() -> None:
    """A ``PromptAgentDefinitionTextOptions`` kwarg is forwarded to the definition."""
    text = PromptAgentDefinitionTextOptions()
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent, text=text)

    assert definition.text is text


def test_to_prompt_agent_forwards_structured_inputs_kwarg() -> None:
    """A ``structured_inputs`` mapping is forwarded (and copied to a new dict)."""
    inputs = {"city": StructuredInputDefinition(description="Target city.")}
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent, structured_inputs=inputs)

    assert definition.structured_inputs is not None
    assert set(definition.structured_inputs) == {"city"}
    assert definition.structured_inputs["city"] is inputs["city"]
    # Defensive copy: mutating the caller's mapping after the call does not leak in.
    inputs["other"] = StructuredInputDefinition(description="x")
    assert "other" not in definition.structured_inputs


def test_to_prompt_agent_forwards_rai_config_kwarg() -> None:
    """A ``RaiConfig`` kwarg is forwarded to the definition."""
    rai_config = RaiConfig()
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent, rai_config=rai_config)

    assert definition.rai_config is rai_config


def test_to_prompt_agent_combines_all_parameters() -> None:
    """Every parameter routes through to a single definition simultaneously."""
    reasoning = Reasoning(effort="medium")
    text = PromptAgentDefinitionTextOptions()
    rai_config = RaiConfig()
    structured = {"q": StructuredInputDefinition(description="query")}
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"temperature": 0.3, "top_p": 0.95, "tool_choice": "auto"},
        tools=[get_weather],
    )

    definition = to_prompt_agent(
        agent,
        temperature=0.5,
        reasoning=reasoning,
        text=text,
        structured_inputs=structured,
        rai_config=rai_config,
    )

    # Kwargs overrode default_options for temperature; top_p and tool_choice came from default_options.
    assert definition.temperature == 0.5
    assert definition.top_p == 0.95
    assert definition.tool_choice == "auto"
    assert definition.reasoning is reasoning
    assert definition.text is text
    assert definition.rai_config is rai_config
    assert definition.structured_inputs is not None and "q" in definition.structured_inputs
    assert definition.tools is not None and len(definition.tools) == 1
