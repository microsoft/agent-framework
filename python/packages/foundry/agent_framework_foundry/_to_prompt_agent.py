# Copyright (c) Microsoft. All rights reserved.

"""Convert an Agent Framework agent into a Foundry ``PromptAgentDefinition``.

The converter accepts an :class:`agent_framework.Agent` whose chat client is a
:class:`agent_framework_foundry.FoundryChatClient` (or a subclass) and returns a
``PromptAgentDefinition`` ready to publish via
``AIProjectClient.agents.create_version(...)``.

The model is lifted from the bound ``FoundryChatClient`` so the same ``Agent``
definition used for local execution can be published as a hosted prompt agent
without restating the model deployment name.

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
    from azure.ai.projects.models import PromptAgentDefinition, Tool


@experimental(feature_id=ExperimentalFeature.TO_PROMPT_AGENT)
def to_prompt_agent(agent: Agent) -> PromptAgentDefinition:
    """Convert an ``Agent`` into a Foundry ``PromptAgentDefinition``.

    The agent's chat client must be a :class:`FoundryChatClient` (or any
    subclass). The model deployment name is lifted from the bound client.

    Args:
        agent: An Agent Framework agent whose client is a ``FoundryChatClient``.

    Returns:
        A ``PromptAgentDefinition`` carrying the agent's model, instructions,
        and tools. Pass it to ``AIProjectClient.agents.create_version(...)``
        to publish the agent as a prompt agent.

    Raises:
        TypeError: If ``agent.client`` is not a ``FoundryChatClient``
            (or subclass).
        ValueError: If the bound ``FoundryChatClient`` has no ``model``, or if
            the agent has a local MCP tool or an unsupported tool type that
            cannot be expressed in a ``PromptAgentDefinition``.
        ImportError: If the installed ``azure-ai-projects`` does not expose
            ``PromptAgentDefinition`` or ``FunctionTool``.
    """
    if not isinstance(agent.client, RawFoundryChatClient):
        raise TypeError(
            "to_prompt_agent requires an Agent whose client is a FoundryChatClient; "
            f"got {type(agent.client).__name__!r}."
        )

    model = agent.client.model
    if not model:
        raise ValueError(
            "FoundryChatClient has no model set. Set 'model' on the FoundryChatClient "
            "(or via the FOUNDRY_MODEL environment variable) before converting."
        )

    instructions = agent.default_options.get("instructions")
    tools = _convert_tools(
        agent.default_options.get("tools", []),
        getattr(agent, "mcp_tools", []),
    )

    try:
        from azure.ai.projects.models import PromptAgentDefinition
    except ImportError as exc:  # pragma: no cover - sanity guard
        raise ImportError(
            "PromptAgentDefinition is not available in the installed azure-ai-projects. "
            "Upgrade azure-ai-projects to use to_prompt_agent."
        ) from exc

    return PromptAgentDefinition(
        model=model,
        instructions=instructions,
        tools=tools or None,
    )


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
            "FunctionTool is not available in the installed azure-ai-projects. "
            "Upgrade azure-ai-projects to use to_prompt_agent."
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
