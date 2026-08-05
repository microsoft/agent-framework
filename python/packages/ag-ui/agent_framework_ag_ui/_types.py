# Copyright (c) Microsoft. All rights reserved.

"""Type definitions for AG-UI integration."""

from __future__ import annotations

import sys
from typing import Annotated, Any, Generic

from ag_ui.core import Interrupt, ResumeEntry
from agent_framework import ChatOptions
from pydantic import AliasChoices, BaseModel, BeforeValidator, Field

if sys.version_info >= (3, 13):
    from typing import TypeVar  # pragma: no cover
else:
    from typing_extensions import TypeVar  # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import TypedDict  # pragma: no cover
else:
    from typing_extensions import TypedDict  # pragma: no cover


AGUIChatOptionsT = TypeVar("AGUIChatOptionsT", bound=TypedDict, default="AGUIChatOptions", covariant=True)  # type: ignore[valid-type]
ResponseModelT = TypeVar("ResponseModelT", bound=BaseModel | None, default=None)


def _coerce_legacy_resume_entry(value: Any) -> Any:  # noqa: ANN401
    if not isinstance(value, dict):
        return value

    interrupt_id = value.get("interruptId") or value.get("interrupt_id") or value.get("id") or value.get("toolCallId")
    if not interrupt_id:
        return value

    if "payload" in value:
        payload = value.get("payload")
    elif "value" in value:
        payload = value.get("value")
    elif "response" in value:
        payload = value.get("response")
    else:
        payload = {
            key: item
            for key, item in value.items()
            if key not in {"id", "interruptId", "interrupt_id", "toolCallId", "type", "status"}
        }

    entry: dict[str, Any] = {"interruptId": str(interrupt_id), "status": value.get("status", "resolved")}
    if payload is not None:
        entry["payload"] = payload
    return entry


def _coerce_legacy_resume(value: Any) -> Any:  # noqa: ANN401
    if value is None:
        return value
    if isinstance(value, dict):
        if "interrupts" in value:
            value = value["interrupts"]
        elif "interrupt" in value:
            value = value["interrupt"]
        elif any(key in value for key in ("interruptId", "interrupt_id", "id", "toolCallId")):
            value = [value]
        else:
            return value
    if not isinstance(value, list):
        return value
    return [_coerce_legacy_resume_entry(entry) for entry in value]


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
        validation_alias=AliasChoices("run_id", "runId"),
        description="Optional run identifier for tracking",
    )
    thread_id: str | None = Field(
        None,
        validation_alias=AliasChoices("thread_id", "threadId"),
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
        validation_alias=AliasChoices("forwarded_props", "forwardedProps"),
        description="Additional properties forwarded to the agent",
    )
    parent_run_id: str | None = Field(
        None,
        validation_alias=AliasChoices("parent_run_id", "parentRunId"),
        description="ID of the run that spawned this run",
    )
    available_interrupts: list[Interrupt] | None = Field(
        None,
        validation_alias=AliasChoices("availableInterrupts", "available_interrupts"),
        description="Canonical AG-UI interrupts that can be resumed by the server",
    )
    resume: Annotated[list[ResumeEntry], BeforeValidator(_coerce_legacy_resume)] | None = Field(
        None,
        description="Resume payload for continuing interrupted runs",
    )


# region AG-UI Chat Options TypedDict


class AGUIChatOptions(ChatOptions[ResponseModelT], Generic[ResponseModelT], total=False):
    """AG-UI protocol-specific chat options dict.

    Extends base ChatOptions for the AG-UI (Agent-UI) protocol.
    AG-UI is a streaming protocol for connecting AI agents to user interfaces.
    Options are forwarded to the remote AG-UI server.

    See: https://github.com/ag-ui/ag-ui-protocol

    Keys:
        # Inherited from ChatOptions (forwarded to remote server):
        model: The model identifier (forwarded as-is to server).
        temperature: Sampling temperature.
        top_p: Nucleus sampling parameter.
        max_tokens: Maximum tokens to generate.
        stop: Stop sequences.
        tools: List of tools - sent to server so LLM knows about client tools.
            Server executes its own tools; client tools execute locally via
            function invocation middleware.
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

    available_interrupts: list[Interrupt]
    """Canonical AG-UI interrupt descriptors available for resumption."""

    resume: list[ResumeEntry]
    """Canonical AG-UI resume entries to continue a paused run."""

    # ChatOptions fields not applicable for AG-UI
    store: None  # type: ignore[misc]
    """Not applicable for AG-UI protocol."""


AGUI_OPTION_TRANSLATIONS: dict[str, str] = {}
"""Maps ChatOptions keys to AG-UI parameter names (protocol uses standard names)."""


# endregion
