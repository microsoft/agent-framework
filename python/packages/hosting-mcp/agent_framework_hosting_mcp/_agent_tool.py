# Copyright (c) Microsoft. All rights reserved.

"""Agent-backed MCP tool adapter for app-owned servers."""

from __future__ import annotations

import re
from collections.abc import Collection, Mapping
from typing import Any, Generic, TypeVar, cast

from agent_framework import AgentResponse, Message, SupportsAgentRun
from agent_framework_hosting import AgentRunArgs, AgentState
from mcp import types

from ._conversion import mcp_from_run, mcp_to_run

AgentT = TypeVar("AgentT", bound=SupportsAgentRun)


class AgentMCPTool(Generic[AgentT]):
    """Expose one Agent Framework agent through an app-owned MCP server.

    The adapter generates the native MCP tool definition and keeps its argument
    parsing aligned with agent execution. It does not create an MCP server,
    register handlers, derive trusted session identifiers, or choose a
    transport.
    """

    def __init__(
        self,
        target: AgentT | AgentState[AgentT],
        *,
        name: str | None = None,
        description: str | None = None,
        argument_name: str = "task",
        argument_description: str | None = None,
        parameters: Mapping[str, Mapping[str, Any]] | None = None,
        required_parameters: Collection[str] = (),
        chat_option_parameters: Mapping[str, Mapping[str, Any]] | None = None,
        session_id_parameter: str | None = None,
    ) -> None:
        """Create an agent-backed MCP tool adapter.

        Args:
            target: Agent target or existing ``AgentState``.

        Keyword Args:
            name: MCP tool name override. Defaults to a sanitized agent name.
            description: MCP tool description override. Defaults to the agent description.
            argument_name: Name of the main text argument.
            argument_description: Description of the main text argument.
            parameters: Additional app-owned MCP parameter schemas.
            required_parameters: Additional parameter names that are required.
            chat_option_parameters: MCP parameter schemas whose values are copied to chat options.
            session_id_parameter: Additional string parameter used as the ``AgentState`` session key.

        Raises:
            ValueError: If parameter names overlap or required/session parameters are not defined.
        """
        self.state = target if isinstance(target, AgentState) else AgentState(target)
        self._name = name
        self._description = description
        self.argument_name = argument_name
        self.argument_description = argument_description
        self.parameters = {key: dict(value) for key, value in (parameters or {}).items()}
        self.chat_option_parameters = {key: dict(value) for key, value in (chat_option_parameters or {}).items()}
        self.session_id_parameter = session_id_parameter

        parameter_names = set(self.parameters)
        chat_option_names = set(self.chat_option_parameters)
        if self.argument_name in parameter_names | chat_option_names:
            raise ValueError(f"Main argument '{self.argument_name}' must not be repeated in additional parameters.")
        if parameter_names & chat_option_names:
            raise ValueError("Additional parameters and chat option parameters must have distinct names.")
        required_names = set(required_parameters)
        if session_id_parameter is not None:
            required_names.add(session_id_parameter)
        if self.session_id_parameter is not None and self.session_id_parameter not in parameter_names:
            raise ValueError("session_id_parameter must name an additional parameter.")
        undefined_required = required_names - parameter_names - chat_option_names
        if undefined_required:
            raise ValueError(f"Required parameters are not defined: {sorted(undefined_required)}")
        self.required_parameters = tuple(
            name for name in (*self.parameters, *self.chat_option_parameters) if name in required_names
        )

    async def list_tools(self) -> list[types.Tool]:
        """Return the native MCP tool definition for the target agent."""
        target = await self.state.get_target()
        return [self._tool_for_target(target)]

    def _tool_for_target(self, target: AgentT) -> types.Tool:
        """Create the native MCP tool definition for a resolved target."""
        tool_name = self._name
        if tool_name is None:
            if target.name is None:
                raise ValueError("MCP tool name requires either an override or an agent name.")
            tool_name = re.sub(r"[^a-zA-Z0-9_.-]+", "_", target.name).strip("_") or "agent"

        properties: dict[str, Any] = {
            self.argument_name: {
                "type": "string",
                "description": self.argument_description or f"Task for {tool_name}",
            },
            **self.parameters,
            **self.chat_option_parameters,
        }
        return types.Tool(
            name=tool_name,
            description=self._description if self._description is not None else target.description or "",
            inputSchema={
                "type": "object",
                "properties": properties,
                "required": [self.argument_name, *self.required_parameters],
                "additionalProperties": False,
            },
        )

    def mcp_to_run(self, arguments: Mapping[str, Any] | None) -> AgentRunArgs:
        """Convert this tool's MCP arguments into Agent Framework run arguments."""
        return mcp_to_run(
            arguments,
            argument_name=self.argument_name,
            chat_option_arguments=self.chat_option_parameters,
        )

    def mcp_from_run(self, result: AgentResponse[Any] | Message) -> list[types.ContentBlock]:
        """Convert Agent Framework output into this tool's MCP result content."""
        return mcp_from_run(result)

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any] | None,
    ) -> list[types.ContentBlock]:
        """Run the target agent for a native MCP ``call_tool`` handler.

        Args:
            name: MCP tool name selected by the client.
            arguments: Native MCP tool arguments.

        Returns:
            Native MCP content blocks for the completed tool result.

        Raises:
            ValueError: If the tool name or configured session id is invalid.
        """
        target = await self.state.get_target()
        tool = self._tool_for_target(target)
        if name != tool.name:
            raise ValueError(f"Unknown MCP tool: {name}")

        run = self.mcp_to_run(arguments)
        if self.session_id_parameter is None:
            result = cast(
                "AgentResponse[Any]",
                await target.run(  # pyright: ignore[reportCallIssue]
                    run["messages"],
                    options=run["options"],
                    stream=False,
                ),
            )
            return self.mcp_from_run(result)

        session_id = arguments.get(self.session_id_parameter) if arguments else None
        if not isinstance(session_id, str) or not session_id:
            raise ValueError(f"MCP tool argument '{self.session_id_parameter}' must be a non-empty string.")
        session = await self.state.get_or_create_session(session_id)
        result = cast(
            "AgentResponse[Any]",
            await target.run(  # pyright: ignore[reportCallIssue]
                run["messages"],
                options=run["options"],
                session=session,
                stream=False,
            ),
        )
        await self.state.set_session(session_id, session)
        return self.mcp_from_run(result)
