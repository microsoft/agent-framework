# Copyright (c) Microsoft. All rights reserved.

"""Type definitions for AG-UI integration."""

import sys
from typing import Any, Generic

from agent_framework import ChatOptions
from pydantic import BaseModel, Field

if sys.version_info >= (3, 13):
    from typing import TypeVar  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypeVar  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # type: ignore # pragma: no cover
else:
    from typing_extensions import TypedDict  # type: ignore # pragma: no cover


TAGUIChatOptions = TypeVar("TAGUIChatOptions", bound=TypedDict, default="AGUIChatOptions", covariant=True)  # type: ignore[valid-type]
TResponseModel = TypeVar("TResponseModel", bound=BaseModel | None, default=None)


class PredictStateConfig(TypedDict):
    """Configuration for predictive state updates."""

    state_key: str
    tool: str
    tool_argument: str | None


class RunMetadata(TypedDict):
    """Metadata for agent run."""

    run_id: str
    thread_id: str
    predict_state: list[PredictStateConfig] | None


class AgentState(TypedDict):
    """Base state for AG-UI agents."""

    messages: list[Any] | None


class AGUIRequest(BaseModel):
    """Request model for AG-UI endpoints."""

    messages: list[dict[str, Any]] = Field(
        ...,
        description="AG-UI format messages array",
    )
    run_id: str | None = Field(
        None,
        description="Optional run identifier for tracking",
    )
    thread_id: str | None = Field(
        None,
        description="Optional thread identifier for conversation context",
    )
    state: dict[str, Any] | None = Field(
        None,
        description="Optional shared state for agentic generative UI",
    )
    tools: list[dict[str, Any]] | None = Field(
        None,
        description="Client-side tools to advertise to the LLM",
    )
    context: list[dict[str, Any]] | None = Field(
        None,
        description="List of context objects provided to the agent",
    )
    forwarded_props: dict[str, Any] | None = Field(
        None,
        description="Additional properties forwarded to the agent",
    )
    parent_run_id: str | None = Field(
        None,
        description="ID of the run that spawned this run",
    )


# region AG-UI Chat Options TypedDict


class AGUIChatOptions(ChatOptions[TResponseModel], Generic[TResponseModel], total=False):
    """AG-UI protocol-specific chat options dict.

    Extends base ChatOptions for the AG-UI (Agent-UI) protocol.
    AG-UI is a streaming protocol for connecting AI agents to user interfaces.
    Options are forwarded to the remote AG-UI server.

    See: https://github.com/ag-ui/ag-ui-protocol

    Keys:
        # Inherited from ChatOptions (forwarded to remote server):
        model_id: The model identifier (forwarded as-is to server).
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum tokens to generate.
        stop: Stop sequences.
        tools: List of tools - sent to server so LLM knows about client tools.
            Server executes its own tools; client tools execute locally via
            @use_function_invocation middleware.
        tool_choice: How the model should use tools.
        metadata: Metadata dict containing thread_id for conversation continuity.

        # Options with limited support (depends on remote server):
        frequency_penalty: Forwarded if remote server supports it.
        presence_penalty: Forwarded if remote server supports it.
        seed: Forwarded if remote server supports it.
        response_format: Forwarded if remote server supports it.
        logit_bias: Forwarded if remote server supports it.
        user: Forwarded if remote server supports it.

        # Options not typically used in AG-UI:
        store: Not applicable for AG-UI protocol.
        allow_multiple_tool_calls: Handled by underlying server.

        # AG-UI-specific options:
        forward_props: Additional properties to forward to the AG-UI server.
            Useful for passing custom parameters to specific server implementations.
        context: Shared context/state to send to the server.

    Note:
        AG-UI is a protocol bridge - actual option support depends on the
        remote server implementation. The client sends all options to the
        server, which decides how to handle them.

        Thread ID management:
        - Pass ``thread_id`` in ``metadata`` to maintain conversation continuity
        - If not provided, a new thread ID is auto-generated
    """

    # AG-UI-specific options
    forward_props: dict[str, Any]
    """Additional properties to forward to the AG-UI server."""

    context: dict[str, Any]
    """Shared context/state to send to the server."""

    # ChatOptions fields not applicable for AG-UI
    store: None  # type: ignore[misc]
    """Not applicable for AG-UI protocol."""


AGUI_OPTION_TRANSLATIONS: dict[str, str] = {}
"""Maps ChatOptions keys to AG-UI parameter names (protocol uses standard names)."""


# endregion
