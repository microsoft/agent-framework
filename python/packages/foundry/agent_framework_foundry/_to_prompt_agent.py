# Copyright (c) Microsoft. All rights reserved.

"""Convert an Agent Framework agent into a Foundry ``PromptAgentDefinition``.

The converter accepts an :class:`agent_framework.Agent` whose chat client is a
:class:`agent_framework_foundry.FoundryChatClient` (or a subclass) and returns
a ``PromptAgentDefinition`` ready to publish via
``AIProjectClient.agents.create_version(...)``.

The model is lifted from the bound ``FoundryChatClient`` so the same ``Agent``
definition used for local execution can be published as a hosted prompt agent
without restating the model deployment name. Generation parameters
(``temperature``, ``top_p``, ``tool_choice``, ``reasoning``,
``response_format`` / ``text`` / ``verbosity``) are translated from
``agent.default_options`` by ``FoundryChatClient._prepare_prompt_agent_options``
so they stay consistent with the agent's local request path.

Parameters with no Agent Framework equivalent (``structured_inputs``,
``rai_config``) are accepted as keyword arguments only.

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
        RaiConfig,
        StructuredInputDefinition,
        Tool,
    )


@experimental(feature_id=ExperimentalFeature.TO_PROMPT_AGENT)
def to_prompt_agent(
    agent: Agent,
    *,
    structured_inputs: Mapping[str, StructuredInputDefinition] | None = None,
    rai_config: RaiConfig | None = None,
) -> PromptAgentDefinition:
    """Convert an ``Agent`` into a Foundry ``PromptAgentDefinition``.

    The agent's chat client must be a :class:`FoundryChatClient` (or any
    subclass). The model deployment name is lifted from the bound client.

    All generation parameters that have an Agent Framework equivalent
    (``temperature``, ``top_p``, ``tool_choice``, ``reasoning``,
    ``response_format`` / ``text`` / ``verbosity``) are sourced from
    ``agent.default_options`` and translated by
    ``FoundryChatClient._prepare_prompt_agent_options``. The agent is the
    single source of truth for these; configure them on the ``Agent`` (or
    pass ``default_options={...}`` to its constructor) rather than here.

    Args:
        agent: An Agent Framework agent whose client is a ``FoundryChatClient``.

    Keyword Args:
        structured_inputs: Mapping of structured input names to
            ``StructuredInputDefinition`` entries. Foundry-only; no
            ``ChatOptions`` equivalent.
        rai_config: Foundry ``RaiConfig`` to attach to the definition.
            Foundry-only; no ``ChatOptions`` equivalent.

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

    translated = agent.client._prepare_prompt_agent_options(  # pyright: ignore[reportPrivateUsage]
        agent.default_options,
        has_tools=bool(tools),
    )

    from azure.ai.projects.models import PromptAgentDefinition

    kwargs: dict[str, Any] = {"model": model}
    if instructions is not None:
        kwargs["instructions"] = instructions
    if tools:
        kwargs["tools"] = tools
    kwargs.update(translated)
    if structured_inputs is not None:
        kwargs["structured_inputs"] = dict(structured_inputs)
    if rai_config is not None:
        kwargs["rai_config"] = rai_config

    return PromptAgentDefinition(**kwargs)


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
