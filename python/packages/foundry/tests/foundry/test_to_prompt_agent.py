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
    ToolChoiceAllowed,
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
from pydantic import BaseModel

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
    client.model = ""
    agent = _make_agent(client)
    agent.default_options.pop("model", None)

    with pytest.raises(ValueError, match="Agent has no model"):
        to_prompt_agent(agent)


def test_to_prompt_agent_no_instructions() -> None:
    """A tool-only agent (no instructions) produces a definition with instructions=None."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        tools=[WebSearchTool()],
    )

    definition = to_prompt_agent(agent)

    assert definition.model == "gpt-4o-mini"
    assert definition.instructions is None
    payload = definition.as_dict()
    assert "instructions" not in payload


def test_to_prompt_agent_prefers_default_options_model() -> None:
    """default_options['model'] wins over the bound client's model."""
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


def test_to_prompt_agent_does_not_mutate_default_options() -> None:
    """Conversion never mutates the translatable option values in ``agent.default_options``."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={
            "temperature": 0.3,
            "top_p": 0.5,
            "reasoning": {"effort": "low"},
            "response_format": {"type": "json_object"},
            "verbosity": "low",
        },
        tools=[get_weather],
    )
    reasoning_before = dict(agent.default_options["reasoning"])  # type: ignore[index]
    response_format_before = dict(agent.default_options["response_format"])  # type: ignore[index]
    tool_choice_before = agent.default_options.get("tool_choice")

    to_prompt_agent(agent)

    assert dict(agent.default_options["reasoning"]) == reasoning_before  # type: ignore[index]
    assert dict(agent.default_options["response_format"]) == response_format_before  # type: ignore[index]
    assert agent.default_options.get("tool_choice") == tool_choice_before
    assert "text" not in agent.default_options


# ---------------------------------------------------------------------------
# Tool conversion
# ---------------------------------------------------------------------------


def test_to_prompt_agent_passes_through_sdk_tool_instances() -> None:
    """Foundry SDK tool instances (e.g. WebSearchTool) are passed through unchanged."""
    ws = WebSearchTool()
    ci = CodeInterpreterTool({"container": {"type": "auto"}})
    agent = _make_agent(_make_foundry_chat_client(), instructions="x", tools=[ws, ci])

    definition = to_prompt_agent(agent)

    assert definition.tools is not None
    assert len(definition.tools) == 2
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
    assert fn.strict is True
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
    # The SDK discriminator on ``type`` should materialize the concrete subclass
    # (here ``WebSearchTool``), not a generic ``Tool``.
    assert isinstance(tool_obj, WebSearchTool)
    assert isinstance(tool_obj, ProjectsTool)
    assert tool_obj.type == "web_search"


def test_to_prompt_agent_accepts_dict_function_tool() -> None:
    """A dict with ``type='function'`` rehydrates to a Foundry ``FunctionTool``."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        tools=[
            {
                "type": "function",
                "name": "lookup",
                "description": "Look up a value.",
                "parameters": {"type": "object", "properties": {}},
            }
        ],
    )

    definition = to_prompt_agent(agent)

    assert definition.tools is not None
    assert len(definition.tools) == 1
    tool_obj = definition.tools[0]
    assert isinstance(tool_obj, ProjectsFunctionTool)
    assert tool_obj.name == "lookup"
    assert tool_obj.description == "Look up a value."


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
# Generation parameters sourced from default_options
# (translated by _prepare_prompt_agent_options in _to_prompt_agent)
# ---------------------------------------------------------------------------


def test_to_prompt_agent_temperature_top_p_unset_by_default() -> None:
    """Without default_options entries, temperature/top_p are unset on the definition."""
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


def test_to_prompt_agent_temperature_zero_is_honored() -> None:
    """A literal ``0.0`` in default_options is treated as explicit, not as unset."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"temperature": 0.0, "top_p": 0.0},
    )

    definition = to_prompt_agent(agent)

    assert definition.temperature == 0.0
    assert definition.top_p == 0.0


def test_to_prompt_agent_tool_choice_omitted_when_no_tools() -> None:
    """``tool_choice`` is dropped when the definition has no tools.

    Mirrors RawOpenAIChatClient._prepare_options behavior. This also keeps
    Agent.__init__'s default ``tool_choice="auto"`` from polluting tool-less
    prompt agents.
    """
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent)

    assert definition.tool_choice is None
    assert "tool_choice" not in definition.as_dict()


def test_to_prompt_agent_tool_choice_auto_with_tools() -> None:
    """When tools are present, the default ``tool_choice="auto"`` flows through."""
    agent = _make_agent(_make_foundry_chat_client(), instructions="x", tools=[get_weather])

    definition = to_prompt_agent(agent)

    assert definition.tool_choice == "auto"


def test_to_prompt_agent_tool_choice_required_string_with_tools() -> None:
    """A string ``tool_choice="required"`` flows through when tools are present."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        tools=[get_weather],
        default_options={"tool_choice": "required"},
    )

    definition = to_prompt_agent(agent)

    assert definition.tool_choice == "required"


def test_to_prompt_agent_tool_choice_required_function_dict() -> None:
    """tool_choice mode=required with a function name → ToolChoiceFunction."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        tools=[get_weather],
        default_options={
            "tool_choice": {"mode": "required", "required_function_name": "get_weather"},
        },
    )

    definition = to_prompt_agent(agent)

    assert isinstance(definition.tool_choice, ToolChoiceFunction)
    assert definition.tool_choice.name == "get_weather"


def test_to_prompt_agent_tool_choice_auto_allowed_tools() -> None:
    """tool_choice mode=auto with allowed_tools → ToolChoiceAllowed."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        tools=[get_weather],
        default_options={
            "tool_choice": {"mode": "auto", "allowed_tools": ["get_weather"]},
        },
    )

    definition = to_prompt_agent(agent)

    assert isinstance(definition.tool_choice, ToolChoiceAllowed)
    assert definition.tool_choice.mode == "auto"
    assert definition.tool_choice.tools == [{"type": "function", "name": "get_weather"}]


def test_to_prompt_agent_lifts_reasoning_dict_from_default_options() -> None:
    """A reasoning dict in default_options becomes a Foundry ``Reasoning`` model."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"reasoning": {"effort": "high", "summary": "concise"}},
    )

    definition = to_prompt_agent(agent)

    assert isinstance(definition.reasoning, Reasoning)
    assert definition.reasoning.effort == "high"
    assert definition.reasoning.summary == "concise"


def test_to_prompt_agent_lifts_reasoning_model_from_default_options() -> None:
    """A pre-built ``Reasoning`` model in default_options is passed through."""
    reasoning = Reasoning(effort="medium")
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"reasoning": reasoning},
    )

    definition = to_prompt_agent(agent)

    assert definition.reasoning is reasoning


def test_to_prompt_agent_lifts_response_format_dict_to_text() -> None:
    """A ``response_format`` dict in default_options becomes ``text.format``."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "weather",
                    "schema": {"type": "object", "properties": {"temp": {"type": "number"}}},
                },
            },
        },
    )

    definition = to_prompt_agent(agent)

    assert isinstance(definition.text, PromptAgentDefinitionTextOptions)
    format_dict = definition.text["format"]
    assert format_dict is not None
    assert format_dict["type"] == "json_schema"
    assert format_dict["name"] == "weather"
    assert format_dict["schema"] == {"type": "object", "properties": {"temp": {"type": "number"}}}


def test_to_prompt_agent_lifts_response_format_pydantic_to_text() -> None:
    """A Pydantic ``BaseModel`` response_format becomes ``text.format`` json_schema."""

    class WeatherReply(BaseModel):
        location: str
        condition: str

    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"response_format": WeatherReply},
    )

    definition = to_prompt_agent(agent)

    assert isinstance(definition.text, PromptAgentDefinitionTextOptions)
    format_dict = definition.text["format"]
    assert format_dict is not None
    assert format_dict["type"] == "json_schema"
    assert format_dict["name"] == "WeatherReply"
    assert "schema" in format_dict
    assert "location" in format_dict["schema"]["properties"]


def test_to_prompt_agent_merges_verbosity_into_text() -> None:
    """A ``verbosity`` entry merges into the ``text`` config."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"verbosity": "low"},
    )

    definition = to_prompt_agent(agent)

    assert isinstance(definition.text, PromptAgentDefinitionTextOptions)
    # PromptAgentDefinitionTextOptions only declares ``format``, but its
    # mapping-init preserves extra keys for server-side use.
    assert dict(definition.text).get("verbosity") == "low"


def test_to_prompt_agent_raises_on_conflicting_response_format_and_text_format() -> None:
    """Pydantic ``response_format`` + a different ``text.format`` mapping must fail loudly."""

    class WeatherReply(BaseModel):
        location: str

    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={
            "response_format": WeatherReply,
            "text": {"format": {"type": "json_object"}},
        },
    )

    with pytest.raises(ValueError, match="Conflicting response_format"):
        to_prompt_agent(agent)


def test_to_prompt_agent_passes_through_text_dict_from_default_options() -> None:
    """A ``text`` dict in default_options flows through to the definition."""
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={"text": {"format": {"type": "text"}, "verbosity": "high"}},
    )

    definition = to_prompt_agent(agent)

    assert isinstance(definition.text, PromptAgentDefinitionTextOptions)
    assert definition.text["format"] == {"type": "text"}
    assert dict(definition.text).get("verbosity") == "high"


# ---------------------------------------------------------------------------
# Foundry-specific kwargs (no AF ChatOptions equivalent)
# ---------------------------------------------------------------------------


def test_to_prompt_agent_kwarg_only_fields_unset_by_default() -> None:
    """structured_inputs and rai_config are absent from the payload when unset."""
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    payload = to_prompt_agent(agent).as_dict()

    assert "structured_inputs" not in payload
    assert "rai_config" not in payload


def test_to_prompt_agent_forwards_structured_inputs_kwarg() -> None:
    """A ``structured_inputs`` mapping is forwarded (and copied to a new dict)."""
    inputs = {"city": StructuredInputDefinition(description="Target city.")}
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent, structured_inputs=inputs)

    assert definition.structured_inputs is not None
    assert set(definition.structured_inputs) == {"city"}
    assert definition.structured_inputs["city"] is inputs["city"]
    inputs["other"] = StructuredInputDefinition(description="x")
    assert "other" not in definition.structured_inputs


def test_to_prompt_agent_forwards_rai_config_kwarg() -> None:
    """A ``RaiConfig`` kwarg is forwarded to the definition."""
    rai_config = RaiConfig(rai_policy_name="test-policy")
    agent = _make_agent(_make_foundry_chat_client(), instructions="x")

    definition = to_prompt_agent(agent, rai_config=rai_config)

    assert definition.rai_config is rai_config


# ---------------------------------------------------------------------------
# Combined integration
# ---------------------------------------------------------------------------


def test_to_prompt_agent_combines_all_sources() -> None:
    """Generation params from default_options + Foundry-only kwargs combine cleanly."""
    rai_config = RaiConfig(rai_policy_name="test-policy")
    structured = {"q": StructuredInputDefinition(description="query")}
    agent = _make_agent(
        _make_foundry_chat_client(),
        instructions="x",
        default_options={
            "temperature": 0.3,
            "top_p": 0.95,
            "tool_choice": "auto",
            "reasoning": {"effort": "medium"},
            "verbosity": "low",
        },
        tools=[get_weather],
    )

    definition = to_prompt_agent(
        agent,
        structured_inputs=structured,
        rai_config=rai_config,
    )

    assert definition.temperature == 0.3
    assert definition.top_p == 0.95
    assert definition.tool_choice == "auto"
    assert isinstance(definition.reasoning, Reasoning)
    assert definition.reasoning.effort == "medium"
    assert isinstance(definition.text, PromptAgentDefinitionTextOptions)
    assert dict(definition.text).get("verbosity") == "low"
    assert definition.rai_config is rai_config
    assert definition.structured_inputs is not None and "q" in definition.structured_inputs
    assert definition.tools is not None and len(definition.tools) == 1
