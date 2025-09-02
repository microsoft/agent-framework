from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal, Protocol, Union

from agent_framework import ChatMessage, ChatRole


class CallbackMode(str, Enum):
    """Controls whether agent deltas are surfaced via on_event.

    STREAMING: emit AgentDeltaEvent chunks and a final AgentMessageEvent.
    NON_STREAMING: suppress deltas and only emit AgentMessageEvent.
    """

    STREAMING = "streaming"
    NON_STREAMING = "non_streaming"


@dataclass
class OrchestratorMessageEvent:
    source: Literal["orchestrator"] = "orchestrator"
    orchestrator_id: str = ""
    message: ChatMessage | None = None
    # Kind values suggested: user_task, task_ledger, instruction, notice
    kind: str = ""


@dataclass
class AgentDeltaEvent:
    source: Literal["agent"] = "agent"
    agent_id: str | None = None
    text: str | None = None
    # Optional: function/tool streaming payloads
    function_call_id: str | None = None
    function_call_name: str | None = None
    function_call_arguments: Any | None = None
    function_result_id: str | None = None
    function_result: Any | None = None
    role: ChatRole | None = None


@dataclass
class AgentMessageEvent:
    source: Literal["agent"] = "agent"
    agent_id: str = ""
    message: ChatMessage | None = None


@dataclass
class FinalResultEvent:
    source: Literal["workflow"] = "workflow"
    message: ChatMessage | None = None


CallbackEvent = Union[
    OrchestratorMessageEvent,
    AgentDeltaEvent,
    AgentMessageEvent,
    FinalResultEvent,
]


class CallbackSink(Protocol):
    async def __call__(self, event: CallbackEvent) -> None: ...


__all__ = [
    "CallbackMode",
    "OrchestratorMessageEvent",
    "AgentDeltaEvent",
    "AgentMessageEvent",
    "FinalResultEvent",
    "CallbackEvent",
    "CallbackSink",
]

