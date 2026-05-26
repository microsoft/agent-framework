# Copyright (c) Microsoft. All rights reserved.

"""Convert an Agent Framework agent into a Foundry ``PromptAgentDefinition``.

The converter accepts an :class:`agent_framework.Agent` whose chat client is a
:class:`agent_framework_foundry.FoundryChatClient` (or a subclass) and returns a
``PromptAgentDefinition`` ready to publish via
``AIProjectClient.agents.create_version(...)``.

The model is lifted from the bound ``FoundryChatClient`` so the same ``Agent``
definition used for local execution can be published as a hosted prompt agent
without restating the model deployment name.

Generation parameters (``temperature``, ``top_p``, ``tool_choice``) are sourced
from ``agent.default_options`` when not overridden by an explicit keyword
argument. Foundry-specific parameters that have no Agent Framework equivalent
(``reasoning``, ``text``, ``structured_inputs``, ``rai_config``) are accepted
as keyword arguments only.

Function tools derived from local Python callables are translated to Foundry
``FunctionTool`` *declarations* only. Prompt agents are server-side, so the
deployed agent will receive the schema for these tools but cannot execute the
underlying Python; wiring server-side execution is the caller's responsibility.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, cast

from agent_framework import FunctionTool
from agent_framework._feature_stage import ExperimentalFeature, experimental
from agent_framework._mcp import MCPTool

from ._chat_client import RawFoundryChatClient

if TYPE_CHECKING:
    from agent_framework import Agent
    from azure.ai.projects.models import (
        PromptAgentDefinition,
        PromptAgentDefinitionTextOptions,
        RaiConfig,
        Reasoning,
        StructuredInputDefinition,
        Tool,
        ToolChoiceParam,
    )


@experimental(feature_id=ExperimentalFeature.TO_PROMPT_AGENT)
def to_prompt_agent(
    agent: Agent,
    *,
    temperature: float | None = None,
    top_p: float | None = None,
    tool_choice: str | ToolChoiceParam | None = None,
    reasoning: Reasoning | None = None,
    text: PromptAgentDefinitionTextOptions | None = None,
    structured_inputs: Mapping[str, StructuredInputDefinition] | None = None,
    rai_config: RaiConfig | None = None,
) -> PromptAgentDefinition:
    """Convert an ``Agent`` into a Foundry ``PromptAgentDefinition``.

    The agent's chat client must be a :class:`FoundryChatClient` (or any
    subclass). The model deployment name is lifted from the bound client.

    Generation parameters that have an Agent Framework ``ChatOptions``
    equivalent are sourced from ``agent.default_options`` when not supplied as
    a keyword argument here. Precedence is: explicit keyword > default_options
    entry > unset on the resulting definition. Parameters specific to Foundry
    prompt agents are accepted as keyword arguments only.

    Args:
        agent: An Agent Framework agent whose client is a ``FoundryChatClient``.

    Keyword Args:
        temperature: Sampling temperature. Falls back to
            ``agent.default_options['temperature']`` if unset.
        top_p: Nucleus sampling parameter. Falls back to
            ``agent.default_options['top_p']`` if unset.
        tool_choice: How the model should pick tools. When unset, a *string*
            ``agent.default_options['tool_choice']`` (e.g. ``"auto"``,
            ``"required"``, ``"none"``) is propagated; non-string Agent
            Framework tool-choice values are ignored.
        reasoning: Foundry ``Reasoning`` configuration.
        text: Foundry ``PromptAgentDefinitionTextOptions`` configuration.
        structured_inputs: Mapping of structured input names to
            ``StructuredInputDefinition`` entries.
        rai_config: Foundry ``RaiConfig`` to attach to the definition.

    Returns:
        A ``PromptAgentDefinition`` carrying the agent's model, instructions,
        tools, and generation parameters. Pass it to
        ``AIProjectClient.agents.create_version(...)`` to publish.
    """
    if not isinstance(agent.client, RawFoundryChatClient):
        raise TypeError(
            "Creating a Foundry Prompt Agent requires an Agent whose client is a FoundryChatClient; "
            f"got {type(agent.client).__name__!r}."
        )

    # Match the resolution order Agent.__init__ uses when building default_options:
    # an agent-level model override in default_options wins over the bound client's model.
    model = agent.default_options.get("model") or agent.client.model
    if not model:
        raise ValueError(
            "Agent has no model. Set 'model' on the FoundryChatClient (via the FOUNDRY_MODEL "
            "environment variable or the model= argument), or pass default_options={'model': ...} "
            "to the Agent before converting."
        )

    instructions = agent.default_options.get("instructions")
    tools = _convert_tools(
        agent.default_options.get("tools", []),
        getattr(agent, "mcp_tools", []),
    )

    resolved_temperature = temperature if temperature is not None else agent.default_options.get("temperature")
    resolved_top_p = top_p if top_p is not None else agent.default_options.get("top_p")
    resolved_tool_choice = tool_choice if tool_choice is not None else _default_options_tool_choice(agent)

    from azure.ai.projects.models import PromptAgentDefinition

    kwargs: dict[str, Any] = {
        "model": model,
        "instructions": instructions,
        "tools": tools or None,
    }
    if resolved_temperature is not None:
        kwargs["temperature"] = resolved_temperature
    if resolved_top_p is not None:
        kwargs["top_p"] = resolved_top_p
    if resolved_tool_choice is not None:
        kwargs["tool_choice"] = resolved_tool_choice
    if reasoning is not None:
        kwargs["reasoning"] = reasoning
    if text is not None:
        kwargs["text"] = text
    if structured_inputs is not None:
        kwargs["structured_inputs"] = dict(structured_inputs)
    if rai_config is not None:
        kwargs["rai_config"] = rai_config

    return PromptAgentDefinition(**kwargs)


def _default_options_tool_choice(agent: Agent) -> str | None:
    """Return ``agent.default_options['tool_choice']`` only when it is a string.

    Agent Framework's ``tool_choice`` is ``ToolMode | Literal["auto", "required", "none"]``.
    Foundry's prompt-agent ``tool_choice`` accepts either a string or a
    ``ToolChoiceParam`` model; the simple string values overlap cleanly, while
    AF ``ToolMode`` instances have no canonical Foundry mapping. Anything that
    is not already a string is left to the explicit keyword argument.
    """
    value = agent.default_options.get("tool_choice")
    if isinstance(value, str):
        return value
    return None


def _convert_tools(
    tools: Iterable[Any] | None,
    mcp_tools: Iterable[MCPTool] | None,
) -> list[Tool]:
    """Map AF agent tools to Foundry ``PromptAgentDefinition`` tool entries.

    Tool sources walked, in order:

    * ``agent.default_options["tools"]`` — function tools and hosted Foundry SDK
      tool instances (returned by ``FoundryChatClient.get_*_tool()``).
    * ``agent.mcp_tools`` — local Agent Framework MCP servers (split off from
      the tools list by ``normalize_tools()``). These cannot be published as
      prompt-agent tools; the caller must use the hosted MCP factory instead.

    Hosted SDK tool instances are passed through unchanged. Mapping/dict tools
    are passed through after light validation. Anything else raises
    ``ValueError`` with a message that names the offending type.
    """
    from azure.ai.projects.models import Tool as ProjectsTool

    converted: list[Tool] = []

    for tool_item in tools or ():
        if isinstance(tool_item, ProjectsTool):
            converted.append(tool_item)
            continue
        if isinstance(tool_item, FunctionTool):
            converted.append(_function_tool_to_foundry(tool_item))
            continue
        if isinstance(tool_item, Mapping):
            converted.append(_validate_mapping_tool(cast("Mapping[str, Any]", tool_item)))
            continue
        raise ValueError(
            f"Unsupported tool type for PromptAgentDefinition: {type(tool_item).__name__}. "
            "Use FoundryChatClient.get_*_tool() helpers, a callable / FunctionTool, "
            "or a dict matching the Foundry tool schema."
        )

    for mcp_tool in mcp_tools or ():
        raise ValueError(
            f"Local MCP tool {mcp_tool.name!r} cannot be published as a prompt-agent tool. "
            "Use FoundryChatClient.get_mcp_tool(...) to register a hosted MCP server instead."
        )

    return converted


def _function_tool_to_foundry(tool_item: FunctionTool) -> Tool:
    """Build a Foundry ``FunctionTool`` declaration from an AF ``FunctionTool``.

    The result carries only the schema (name, description, parameters). It is a
    declaration of the tool the prompt agent may call; server-side execution
    must be wired separately by the caller.
    """
    try:
        from azure.ai.projects.models import FunctionTool as ProjectsFunctionTool
    except ImportError as exc:  # pragma: no cover - sanity guard
        raise ImportError(
            "FunctionTool is not available in the installed azure-ai-projects. Upgrade azure-ai-projects."
        ) from exc

    return ProjectsFunctionTool(
        name=tool_item.name,
        description=tool_item.description or "",
        parameters=tool_item.parameters(),
        strict=False,
    )


def _validate_mapping_tool(tool_item: Mapping[str, Any]) -> Tool:
    """Validate a dict-shaped tool and instantiate a Foundry ``Tool``.

    The Foundry SDK can rehydrate a tool model from its raw JSON mapping via
    the discriminator on ``type``. We require the ``type`` field so the
    failure mode is obvious; everything else is left to the SDK.
    """
    from azure.ai.projects.models import Tool as ProjectsTool

    if "type" not in tool_item:
        raise ValueError("Dict-shaped tools must include a 'type' field matching a Foundry tool discriminator.")
    return ProjectsTool(**tool_item)
