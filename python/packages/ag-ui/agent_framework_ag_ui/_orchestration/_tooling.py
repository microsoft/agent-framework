# Copyright (c) Microsoft. All rights reserved.

"""Tool handling helpers."""

import logging
from typing import Any

from agent_framework import BaseChatClient, ChatAgent

logger = logging.getLogger(__name__)


def collect_server_tools(agent: Any) -> list[Any]:
    """Collect server tools from ChatAgent or duck-typed agent."""
    if isinstance(agent, ChatAgent):
        tools_from_agent = agent.chat_options.tools
        server_tools = list(tools_from_agent) if tools_from_agent else []
        logger.info(f"[TOOLS] Agent has {len(server_tools)} configured tools")
        for tool in server_tools:
            tool_name = getattr(tool, "name", "unknown")
            approval_mode = getattr(tool, "approval_mode", None)
            logger.info(f"[TOOLS]   - {tool_name}: approval_mode={approval_mode}")
        return server_tools

    try:
        chat_options_attr = getattr(agent, "chat_options", None)
        if chat_options_attr is not None:
            return getattr(chat_options_attr, "tools", None) or []
    except AttributeError:
        return []
    return []


def register_additional_client_tools(agent: Any, client_tools: list[Any] | None) -> None:
    """Register client tools as additional declaration-only tools to avoid server execution."""
    if not client_tools:
        return

    if isinstance(agent, ChatAgent):
        chat_client = agent.chat_client
        if isinstance(chat_client, BaseChatClient) and chat_client.function_invocation_configuration is not None:
            chat_client.function_invocation_configuration.additional_tools = client_tools
            logger.debug(f"[TOOLS] Registered {len(client_tools)} client tools as additional_tools (declaration-only)")
        return

    try:
        chat_client_attr = getattr(agent, "chat_client", None)
        if chat_client_attr is not None:
            fic = getattr(chat_client_attr, "function_invocation_configuration", None)
            if fic is not None:
                fic.additional_tools = client_tools  # type: ignore[attr-defined]
                logger.debug(
                    f"[TOOLS] Registered {len(client_tools)} client tools as additional_tools (declaration-only)"
                )
    except AttributeError:
        return


def merge_tools(server_tools: list[Any], client_tools: list[Any] | None) -> list[Any] | None:
    """Combine server and client tools without overriding server metadata."""
    if not client_tools:
        logger.info("[TOOLS] No client tools - not passing tools= parameter (using agent's configured tools)")
        return None

    server_tool_names = {getattr(tool, "name", None) for tool in server_tools}
    unique_client_tools = [tool for tool in client_tools if getattr(tool, "name", None) not in server_tool_names]

    if not unique_client_tools:
        logger.info("[TOOLS] All client tools duplicate server tools - not passing tools= parameter")
        return None

    combined_tools: list[Any] = []
    if server_tools:
        combined_tools.extend(server_tools)
    combined_tools.extend(unique_client_tools)
    logger.info(
        f"[TOOLS] Passing tools= parameter with {len(combined_tools)} tools "
        f"({len(server_tools)} server + {len(unique_client_tools)} unique client)"
    )
    return combined_tools
