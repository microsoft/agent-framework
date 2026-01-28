# Copyright (c) Microsoft. All rights reserved.

"""Tool handling helpers."""

import logging
from typing import TYPE_CHECKING, Any

from agent_framework import BaseChatClient

if TYPE_CHECKING:
    from agent_framework import AgentProtocol

logger = logging.getLogger(__name__)


def _collect_mcp_tool_functions(mcp_tools: list[Any]) -> list[Any]:
    """Extract functions from connected MCP tools.

    Args:
        mcp_tools: List of MCP tool instances.

    Returns:
        List of functions from connected MCP tools.
    """
    functions: list[Any] = []
    for mcp_tool in mcp_tools:
        if getattr(mcp_tool, "is_connected", False) and hasattr(mcp_tool, "functions"):
            functions.extend(mcp_tool.functions)
    return functions


def collect_server_tools(agent: "AgentProtocol") -> list[Any]:
    """Collect server tools from an agent.

    This includes both regular tools from default_options and MCP tools.
    MCP tools are stored separately for lifecycle management but their
    functions need to be included for tool execution during approval flows.

    Args:
        agent: Agent instance to collect tools from. Works with ChatAgent
            or any agent with default_options and optional mcp_tools attributes.

    Returns:
        List of tools including both regular tools and connected MCP tool functions.
    """
    # Get tools from default_options
    default_options = getattr(agent, "default_options", None)
    if default_options is None:
        return []

    tools_from_agent = default_options.get("tools") if isinstance(default_options, dict) else None
    server_tools = list(tools_from_agent) if tools_from_agent else []

    # Include functions from connected MCP tools (only available on ChatAgent)
    mcp_tools = getattr(agent, "mcp_tools", None)
    if mcp_tools:
        server_tools.extend(_collect_mcp_tool_functions(mcp_tools))

    logger.info(f"[TOOLS] Agent has {len(server_tools)} configured tools")
    for tool in server_tools:
        tool_name = getattr(tool, "name", "unknown")
        approval_mode = getattr(tool, "approval_mode", None)
        logger.info(f"[TOOLS]   - {tool_name}: approval_mode={approval_mode}")
    return server_tools


def register_additional_client_tools(agent: "AgentProtocol", client_tools: list[Any] | None) -> None:
    """Register client tools as additional declaration-only tools to avoid server execution.

    Args:
        agent: Agent instance to register tools on. Works with ChatAgent
            or any agent with a chat_client attribute.
        client_tools: List of client tools to register.
    """
    if not client_tools:
        return

    chat_client = getattr(agent, "chat_client", None)
    if chat_client is None:
        return

    if isinstance(chat_client, BaseChatClient) and chat_client.function_invocation_configuration is not None:
        chat_client.function_invocation_configuration.additional_tools = client_tools
        logger.debug(f"[TOOLS] Registered {len(client_tools)} client tools as additional_tools (declaration-only)")


def _has_approval_tools(tools: list[Any]) -> bool:
    """Check if any tools require approval."""
    return any(getattr(tool, "approval_mode", None) == "always_require" for tool in tools)


def merge_tools(server_tools: list[Any], client_tools: list[Any] | None) -> list[Any] | None:
    """Combine server and client tools without overriding server metadata.

    IMPORTANT: When server tools have approval_mode="always_require", we MUST return
    them so they get passed to the streaming response handler. Otherwise, the approval
    check in _try_execute_function_calls won't find the tool and won't trigger approval.
    """
    if not client_tools:
        # Even without client tools, we must pass server tools if any require approval
        if server_tools and _has_approval_tools(server_tools):
            logger.info(
                f"[TOOLS] No client tools but server has approval tools - "
                f"passing {len(server_tools)} server tools for approval mode"
            )
            return server_tools
        logger.info("[TOOLS] No client tools - not passing tools= parameter (using agent's configured tools)")
        return None

    server_tool_names = {getattr(tool, "name", None) for tool in server_tools}
    unique_client_tools = [tool for tool in client_tools if getattr(tool, "name", None) not in server_tool_names]

    if not unique_client_tools:
        # Same check: must pass server tools if any require approval
        if server_tools and _has_approval_tools(server_tools):
            logger.info(
                f"[TOOLS] Client tools duplicate server but server has approval tools - "
                f"passing {len(server_tools)} server tools for approval mode"
            )
            return server_tools
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
