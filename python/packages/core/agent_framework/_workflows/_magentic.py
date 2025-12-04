# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import json
import logging
import re
import sys
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, TypeVar, cast
from uuid import uuid4

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatMessage,
    FunctionApprovalRequestContent,
    FunctionResultContent,
    Role,
)

from ._base_group_chat_orchestrator import BaseGroupChatOrchestrator
from ._checkpoint import CheckpointStorage, WorkflowCheckpoint
from ._const import EXECUTOR_STATE_KEY
from ._events import AgentRunUpdateEvent, WorkflowEvent
from ._executor import Executor, handler
from ._group_chat import (
    GroupChatBuilder,
    _GroupChatConfig,  # type: ignore[reportPrivateUsage]
    _GroupChatParticipantPipeline,  # type: ignore[reportPrivateUsage]
    _GroupChatRequestMessage,  # type: ignore[reportPrivateUsage]
    _GroupChatResponseMessage,  # type: ignore[reportPrivateUsage]
    group_chat_orchestrator,
)
from ._message_utils import normalize_messages_input
from ._model_utils import DictConvertible, encode_value
from ._participant_utils import GroupChatParticipantSpec, participant_description
from ._request_info_mixin import response_handler
from ._workflow import Workflow, WorkflowRunResult
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self

if sys.version_info >= (3, 12):
    from typing import override
else:
    from typing_extensions import override


logger = logging.getLogger(__name__)

# Consistent author name for messages produced by the Magentic manager/orchestrator
MAGENTIC_MANAGER_NAME = "magentic_manager"

# Optional kinds for generic orchestrator message callback
ORCH_MSG_KIND_USER_TASK = "user_task"
ORCH_MSG_KIND_TASK_LEDGER = "task_ledger"
# Newly surfaced kinds for unified callback consumers
ORCH_MSG_KIND_INSTRUCTION = "instruction"
ORCH_MSG_KIND_NOTICE = "notice"


def _message_to_payload(message: ChatMessage) -> Any:
    if hasattr(message, "to_dict") and callable(getattr(message, "to_dict", None)):
        with contextlib.suppress(Exception):
            return message.to_dict()  # type: ignore[attr-defined]
    if hasattr(message, "to_json") and callable(getattr(message, "to_json", None)):
        with contextlib.suppress(Exception):
            json_payload = message.to_json()  # type: ignore[attr-defined]
            if isinstance(json_payload, str):
                with contextlib.suppress(Exception):
                    return json.loads(json_payload)
            return json_payload
    if hasattr(message, "__dict__"):
        return encode_value(message.__dict__)
    return message


def _message_from_payload(payload: Any) -> ChatMessage:
    if isinstance(payload, ChatMessage):
        return payload
    if hasattr(ChatMessage, "from_dict") and isinstance(payload, dict):
        with contextlib.suppress(Exception):
            return ChatMessage.from_dict(payload)  # type: ignore[attr-defined,no-any-return]
    if hasattr(ChatMessage, "from_json") and isinstance(payload, str):
        with contextlib.suppress(Exception):
            return ChatMessage.from_json(payload)  # type: ignore[attr-defined,no-any-return]
    if isinstance(payload, dict):
        with contextlib.suppress(Exception):
            return ChatMessage(**payload)  # type: ignore[arg-type]
    if isinstance(payload, str):
        with contextlib.suppress(Exception):
            decoded = json.loads(payload)
            if isinstance(decoded, dict):
                return _message_from_payload(decoded)
    raise TypeError("Unable to reconstruct ChatMessage from payload")


# region Magentic event metadata constants

# Event type identifiers for magentic_event_type in additional_properties
MAGENTIC_EVENT_TYPE_ORCHESTRATOR = "orchestrator_message"
MAGENTIC_EVENT_TYPE_AGENT_DELTA = "agent_delta"

# endregion Magentic event metadata constants

# region Magentic One Prompts

ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT = """Below I will present you a request.

Before we begin addressing the request, please answer the following pre-survey to the best of your ability.
Keep in mind that you are Ken Jennings-level with trivia, and Mensa-level with puzzles, so there should be
a deep well to draw from.

Here is the request:

{task}

Here is the pre-survey:

    1. Please list any specific facts or figures that are GIVEN in the request itself. It is possible that
       there are none.
    2. Please list any facts that may need to be looked up, and WHERE SPECIFICALLY they might be found.
       In some cases, authoritative sources are mentioned in the request itself.
    3. Please list any facts that may need to be derived (e.g., via logical deduction, simulation, or computation)
    4. Please list any facts that are recalled from memory, hunches, well-reasoned guesses, etc.

When answering this survey, keep in mind that "facts" will typically be specific names, dates, statistics, etc.
Your answer should use headings:

    1. GIVEN OR VERIFIED FACTS
    2. FACTS TO LOOK UP
    3. FACTS TO DERIVE
    4. EDUCATED GUESSES

DO NOT include any other headings or sections in your response. DO NOT list next steps or plans until asked to do so.
"""

ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT = """Fantastic. To address this request we have assembled the following team:

{team}

Based on the team composition, and known and unknown facts, please devise a short bullet-point plan for addressing the
original request. Remember, there is no requirement to involve all team members. A team member's particular expertise
may not be needed for this task.
"""

# Added to render the ledger in a single assistant message, mirroring the original behavior.
ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT = """
We are working to address the following user request:

{task}


To answer this request we have assembled the following team:

{team}


Here is an initial fact sheet to consider:

{facts}


Here is the plan to follow as best as possible:

{plan}
"""

ORCHESTRATOR_TASK_LEDGER_FACTS_UPDATE_PROMPT = """As a reminder, we are working to solve the following task:

{task}

It is clear we are not making as much progress as we would like, but we may have learned something new.
Please rewrite the following fact sheet, updating it to include anything new we have learned that may be helpful.

Example edits can include (but are not limited to) adding new guesses, moving educated guesses to verified facts
if appropriate, etc. Updates may be made to any section of the fact sheet, and more than one section of the fact
sheet can be edited. This is an especially good time to update educated guesses, so please at least add or update
one educated guess or hunch, and explain your reasoning.

Here is the old fact sheet:

{old_facts}
"""

ORCHESTRATOR_TASK_LEDGER_PLAN_UPDATE_PROMPT = """Please briefly explain what went wrong on this last run
(the root cause of the failure), and then come up with a new plan that takes steps and includes hints to overcome prior
challenges and especially avoids repeating the same mistakes. As before, the new plan should be concise, expressed in
bullet-point form, and consider the following team composition:

{team}
"""

ORCHESTRATOR_PROGRESS_LEDGER_PROMPT = """
Recall we are working on the following request:

{task}

And we have assembled the following team:

{team}

To make progress on the request, please answer the following questions, including necessary reasoning:

    - Is the request fully satisfied? (True if complete, or False if the original request has yet to be
      SUCCESSFULLY and FULLY addressed)
    - Are we in a loop where we are repeating the same requests and or getting the same responses as before?
      Loops can span multiple turns, and can include repeated actions like scrolling up or down more than a
      handful of times.
    - Are we making forward progress? (True if just starting, or recent messages are adding value. False if recent
      messages show evidence of being stuck in a loop or if there is evidence of significant barriers to success
      such as the inability to read from a required file)
    - Who should speak next? (select from: {names})
    - What instruction or question would you give this team member? (Phrase as if speaking directly to them, and
      include any specific information they may need)

Please output an answer in pure JSON format according to the following schema. The JSON object must be parsable as-is.
DO NOT OUTPUT ANYTHING OTHER THAN JSON, AND DO NOT DEVIATE FROM THIS SCHEMA:

{{
    "is_request_satisfied": {{

        "reason": string,
        "answer": boolean
    }},
    "is_in_loop": {{
        "reason": string,
        "answer": boolean
    }},
    "is_progress_being_made": {{
        "reason": string,
        "answer": boolean
    }},
    "next_speaker": {{
        "reason": string,
        "answer": string (select from: {names})
    }},
    "instruction_or_question": {{
        "reason": string,
        "answer": string
    }}
}}
"""

ORCHESTRATOR_FINAL_ANSWER_PROMPT = """
We are working on the following task:
{task}

We have completed the task.

The above messages contain the conversation that took place to complete the task.

Based on the information gathered, provide the final answer to the original request.
The answer should be phrased as if you were speaking to the user.
"""


# region Messages and Types


def _new_chat_history() -> list[ChatMessage]:
    """Typed default factory for chat history list to satisfy type checkers."""
    return []


def _new_participant_descriptions() -> dict[str, str]:
    """Typed default factory for participant descriptions dict to satisfy type checkers."""
    return {}


def _new_chat_message_list() -> list[ChatMessage]:
    """Typed default factory for ChatMessage list to satisfy type checkers."""
    return []


@dataclass
class _MagenticStartMessage(DictConvertible):
    """Internal: A message to start a magentic workflow."""

    messages: list[ChatMessage] = field(default_factory=_new_chat_message_list)

    def __init__(
        self,
        messages: str | ChatMessage | Sequence[str] | Sequence[ChatMessage] | None = None,
        *,
        task: ChatMessage | None = None,
    ) -> None:
        normalized = normalize_messages_input(messages)
        if task is not None:
            normalized += normalize_messages_input(task)
        if not normalized:
            raise ValueError("MagenticStartMessage requires at least one message input.")
        self.messages: list[ChatMessage] = normalized

    @property
    def task(self) -> ChatMessage:
        """Final user message for the task."""
        return self.messages[-1]

    @classmethod
    def from_string(cls, task_text: str) -> "_MagenticStartMessage":
        """Create a MagenticStartMessage from a simple string."""
        return cls(task_text)

    def to_dict(self) -> dict[str, Any]:
        """Create a dict representation of the message."""
        return {
            "messages": [message.to_dict() for message in self.messages],
            "task": self.task.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_MagenticStartMessage":
        """Create from a dict."""
        if "messages" in data:
            raw_messages = data["messages"]
            if not isinstance(raw_messages, Sequence) or isinstance(raw_messages, (str, bytes)):
                raise TypeError("MagenticStartMessage 'messages' must be a sequence.")
            messages: list[ChatMessage] = [ChatMessage.from_dict(raw) for raw in raw_messages]  # type: ignore[arg-type]
            return cls(messages)
        if "task" in data:
            task = ChatMessage.from_dict(data["task"])
            return cls(task)
        raise KeyError("Expected 'messages' or 'task' in MagenticStartMessage payload.")


@dataclass
class _MagenticRequestMessage(_GroupChatRequestMessage):
    """Internal: A request message type for agents in a magentic workflow."""

    task_context: str = ""


class _MagenticResponseMessage(_GroupChatResponseMessage):
    """Internal: A response message type.

    When emitted by the orchestrator you can mark it as a broadcast to all agents,
    or target a specific agent by name.
    """

    def __init__(
        self,
        body: ChatMessage,
        target_agent: str | None = None,  # deliver only to this agent if set
        broadcast: bool = False,  # deliver to all agents if True
    ) -> None:
        agent_name = body.author_name or ""
        super().__init__(
            agent_name=agent_name,
            message=body,
        )
        self.body = body
        self.target_agent = target_agent
        self.broadcast = broadcast

    def to_dict(self) -> dict[str, Any]:
        """Create a dict representation of the message."""
        return {"body": self.body.to_dict(), "target_agent": self.target_agent, "broadcast": self.broadcast}

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "_MagenticResponseMessage":
        """Create from a dict."""
        body = ChatMessage.from_dict(value["body"])
        target_agent = value.get("target_agent")
        broadcast = value.get("broadcast", False)
        return cls(body=body, target_agent=target_agent, broadcast=broadcast)


# region Human Intervention Types


class MagenticHumanInterventionKind(str, Enum):
    """The kind of human intervention being requested."""

    PLAN_REVIEW = "plan_review"  # Review and approve/revise the initial plan
    TOOL_APPROVAL = "tool_approval"  # Approve a tool/function call
    STALL = "stall"  # Workflow has stalled and needs guidance


class MagenticHumanInterventionDecision(str, Enum):
    """Decision options for human intervention responses."""

    APPROVE = "approve"  # Approve (plan review, tool approval)
    REVISE = "revise"  # Request revision with feedback (plan review)
    REJECT = "reject"  # Reject/deny (tool approval)
    CONTINUE = "continue"  # Continue with current state (stall)
    REPLAN = "replan"  # Trigger replanning (stall)
    GUIDANCE = "guidance"  # Provide guidance text (stall, tool approval)


@dataclass
class _MagenticHumanInterventionRequest:
    """Unified request for human intervention in a Magentic workflow.

    This request is emitted when the workflow needs human input. The `kind` field
    indicates what type of intervention is needed, and the relevant fields are
    populated based on the kind.

    Attributes:
        request_id: Unique identifier for correlating responses
        kind: The type of intervention needed (plan_review, tool_approval, stall)

        # Plan review fields
        task_text: The task description (plan_review)
        facts_text: Extracted facts from the task (plan_review)
        plan_text: The proposed or current plan (plan_review, stall)
        round_index: Number of review rounds so far (plan_review)

        # Tool approval fields
        agent_id: The agent requesting input (tool_approval)
        prompt: Description of what input is needed (tool_approval)
        context: Additional context (tool_approval)
        conversation_snapshot: Recent conversation history (tool_approval)

        # Stall intervention fields
        stall_count: Number of consecutive stall rounds (stall)
        max_stall_count: Threshold that triggered intervention (stall)
        stall_reason: Description of why progress stalled (stall)
        last_agent: Last active agent (stall)
    """

    request_id: str = field(default_factory=lambda: str(uuid4()))
    kind: MagenticHumanInterventionKind = MagenticHumanInterventionKind.PLAN_REVIEW

    # Plan review fields
    task_text: str = ""
    facts_text: str = ""
    plan_text: str = ""
    round_index: int = 0

    # Tool approval fields
    agent_id: str = ""
    prompt: str = ""
    context: str | None = None
    conversation_snapshot: list[ChatMessage] = field(default_factory=list)  # type: ignore

    # Stall intervention fields
    stall_count: int = 0
    max_stall_count: int = 3
    stall_reason: str = ""
    last_agent: str = ""


@dataclass
class _MagenticHumanInterventionReply:
    """Unified reply to a human intervention request.

    The relevant fields depend on the original request kind and the decision made.

    Attributes:
        decision: The human's decision (approve, revise, continue, replan, guidance)
        edited_plan_text: New plan text if directly editing (plan_review with approve/revise)
        comments: Feedback for revision or guidance text (plan_review, stall with guidance)
        response_text: Free-form response text (tool_approval)
    """

    decision: MagenticHumanInterventionDecision
    edited_plan_text: str | None = None
    comments: str | None = None
    response_text: str | None = None


# endregion Human Intervention Types


@dataclass
class _MagenticTaskLedger(DictConvertible):
    """Internal: Task ledger for the Standard Magentic manager."""

    facts: ChatMessage
    plan: ChatMessage

    def to_dict(self) -> dict[str, Any]:
        return {"facts": _message_to_payload(self.facts), "plan": _message_to_payload(self.plan)}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_MagenticTaskLedger":
        return cls(
            facts=_message_from_payload(data.get("facts")),
            plan=_message_from_payload(data.get("plan")),
        )


@dataclass
class _MagenticProgressLedgerItem(DictConvertible):
    """Internal: A progress ledger item."""

    reason: str
    answer: str | bool

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason, "answer": self.answer}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_MagenticProgressLedgerItem":
        answer_value = data.get("answer")
        if not isinstance(answer_value, (str, bool)):
            answer_value = ""  # Default to empty string if not str or bool
        return cls(reason=data.get("reason", ""), answer=answer_value)


@dataclass
class _MagenticProgressLedger(DictConvertible):
    """Internal: A progress ledger for tracking workflow progress."""

    is_request_satisfied: _MagenticProgressLedgerItem
    is_in_loop: _MagenticProgressLedgerItem
    is_progress_being_made: _MagenticProgressLedgerItem
    next_speaker: _MagenticProgressLedgerItem
    instruction_or_question: _MagenticProgressLedgerItem

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_request_satisfied": self.is_request_satisfied.to_dict(),
            "is_in_loop": self.is_in_loop.to_dict(),
            "is_progress_being_made": self.is_progress_being_made.to_dict(),
            "next_speaker": self.next_speaker.to_dict(),
            "instruction_or_question": self.instruction_or_question.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "_MagenticProgressLedger":
        return cls(
            is_request_satisfied=_MagenticProgressLedgerItem.from_dict(data.get("is_request_satisfied", {})),
            is_in_loop=_MagenticProgressLedgerItem.from_dict(data.get("is_in_loop", {})),
            is_progress_being_made=_MagenticProgressLedgerItem.from_dict(data.get("is_progress_being_made", {})),
            next_speaker=_MagenticProgressLedgerItem.from_dict(data.get("next_speaker", {})),
            instruction_or_question=_MagenticProgressLedgerItem.from_dict(data.get("instruction_or_question", {})),
        )


@dataclass
class MagenticContext(DictConvertible):
    """Context for the Magentic manager."""

    task: ChatMessage
    chat_history: list[ChatMessage] = field(default_factory=_new_chat_history)
    participant_descriptions: dict[str, str] = field(default_factory=_new_participant_descriptions)
    round_count: int = 0
    stall_count: int = 0
    reset_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": _message_to_payload(self.task),
            "chat_history": [_message_to_payload(msg) for msg in self.chat_history],
            "participant_descriptions": dict(self.participant_descriptions),
            "round_count": self.round_count,
            "stall_count": self.stall_count,
            "reset_count": self.reset_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MagenticContext":
        chat_history_payload = data.get("chat_history", [])
        history: list[ChatMessage] = []
        for item in chat_history_payload:
            history.append(_message_from_payload(item))
        return cls(
            task=_message_from_payload(data.get("task")),
            chat_history=history,
            participant_descriptions=dict(data.get("participant_descriptions", {})),
            round_count=data.get("round_count", 0),
            stall_count=data.get("stall_count", 0),
            reset_count=data.get("reset_count", 0),
        )

    def reset(self) -> None:
        """Reset the context.

        This will clear the chat history and reset the stall count.
        This will not reset the task, round count, or participant descriptions.
        """
        self.chat_history.clear()
        self.stall_count = 0
        self.reset_count += 1


# endregion Messages and Types

# region Utilities


def _team_block(participants: dict[str, str]) -> str:
    """Render participant descriptions as a readable block."""
    return "\n".join(f"- {name}: {desc}" for name, desc in participants.items())


def _first_assistant(messages: list[ChatMessage]) -> ChatMessage | None:
    for msg in reversed(messages):
        if msg.role == Role.ASSISTANT:
            return msg
    return None


def _extract_json(text: str) -> dict[str, Any]:
    """Potentially temp helper method.

    Note: this method is required right now because the ChatClientProtocol, when calling
    response.text, returns duplicate JSON payloads - need to figure out why.

    The `text` method is concatenating multiple text contents from diff msgs into a single string.
    """
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    if fence:
        candidate = fence.group(1)
    else:
        # Find first balanced JSON object
        start = text.find("{")
        if start == -1:
            raise ValueError("No JSON object found.")
        depth = 0
        end = None
        for i, ch in enumerate(text[start:], start=start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            raise ValueError("Unbalanced JSON braces.")
        candidate = text[start:end]

    for attempt in (candidate, candidate.replace("True", "true").replace("False", "false").replace("None", "null")):
        with contextlib.suppress(Exception):
            val = json.loads(attempt)
            if isinstance(val, dict):
                return cast(dict[str, Any], val)

    with contextlib.suppress(Exception):
        import ast

        obj = ast.literal_eval(candidate)
        if isinstance(obj, dict):
            return cast(dict[str, Any], obj)

    raise ValueError("Unable to parse JSON from model output.")


T = TypeVar("T")


def _coerce_model(model_cls: type[T], data: dict[str, Any]) -> T:
    # Use type: ignore to suppress mypy errors for dynamic attribute access
    # We check with hasattr() first, so this is safe
    if hasattr(model_cls, "from_dict") and callable(model_cls.from_dict):  # type: ignore[attr-defined]
        return model_cls.from_dict(data)  # type: ignore[attr-defined,return-value,no-any-return]
    return model_cls(**data)  # type: ignore[arg-type,call-arg]


# endregion Utilities

# region Magentic Manager


class MagenticManagerBase(ABC):
    """Base class for the Magentic One manager."""

    def __init__(
        self,
        *,
        max_stall_count: int = 3,
        max_reset_count: int | None = None,
        max_round_count: int | None = None,
    ) -> None:
        self.max_stall_count = max_stall_count
        self.max_reset_count = max_reset_count
        self.max_round_count = max_round_count
        # Base prompt surface for type safety; concrete managers may override with a str field.
        self.task_ledger_full_prompt: str = ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT

    @abstractmethod
    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Create a plan for the task."""
        ...

    @abstractmethod
    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Replan for the task."""
        ...

    @abstractmethod
    async def create_progress_ledger(self, magentic_context: MagenticContext) -> _MagenticProgressLedger:
        """Create a progress ledger."""
        ...

    @abstractmethod
    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        """Prepare the final answer."""
        ...

    def on_checkpoint_save(self) -> dict[str, Any]:
        """Serialize runtime state for checkpointing."""
        return {}

    def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore runtime state from checkpoint data."""
        return


class StandardMagenticManager(MagenticManagerBase):
    """Standard Magentic manager that performs real LLM calls via a ChatAgent.

    The manager constructs prompts that mirror the original Magentic One orchestration:
    - Facts gathering
    - Plan creation
    - Progress ledger in JSON
    - Facts update and plan update on reset
    - Final answer synthesis
    """

    task_ledger: _MagenticTaskLedger | None

    def __init__(
        self,
        agent: AgentProtocol,
        task_ledger: _MagenticTaskLedger | None = None,
        *,
        task_ledger_facts_prompt: str | None = None,
        task_ledger_plan_prompt: str | None = None,
        task_ledger_full_prompt: str | None = None,
        task_ledger_facts_update_prompt: str | None = None,
        task_ledger_plan_update_prompt: str | None = None,
        progress_ledger_prompt: str | None = None,
        final_answer_prompt: str | None = None,
        max_stall_count: int = 3,
        max_reset_count: int | None = None,
        max_round_count: int | None = None,
        progress_ledger_retry_count: int | None = None,
    ) -> None:
        """Initialize the Standard Magentic Manager.

        Args:
            agent: An agent instance to use for LLM calls. The agent's configured
                options (temperature, seed, instructions, etc.) will be applied.
            task_ledger: Optional task ledger for managing task state.

        Keyword Args:
            task_ledger_facts_prompt: Optional prompt for the task ledger facts.
            task_ledger_plan_prompt: Optional prompt for the task ledger plan.
            task_ledger_full_prompt: Optional prompt for the full task ledger.
            task_ledger_facts_update_prompt: Optional prompt for updating task ledger facts.
            task_ledger_plan_update_prompt: Optional prompt for updating task ledger plan.
            progress_ledger_prompt: Optional prompt for the progress ledger.
            final_answer_prompt: Optional prompt for the final answer.
            max_stall_count: Maximum number of stalls allowed.
            max_reset_count: Maximum number of resets allowed.
            max_round_count: Maximum number of rounds allowed.
            progress_ledger_retry_count: Maximum number of retries for the progress ledger.
        """
        super().__init__(
            max_stall_count=max_stall_count,
            max_reset_count=max_reset_count,
            max_round_count=max_round_count,
        )

        self._agent: AgentProtocol = agent
        self.task_ledger: _MagenticTaskLedger | None = task_ledger

        # Prompts may be overridden if needed
        self.task_ledger_facts_prompt: str = task_ledger_facts_prompt or ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT
        self.task_ledger_plan_prompt: str = task_ledger_plan_prompt or ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT
        self.task_ledger_full_prompt = task_ledger_full_prompt or ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT
        self.task_ledger_facts_update_prompt: str = (
            task_ledger_facts_update_prompt or ORCHESTRATOR_TASK_LEDGER_FACTS_UPDATE_PROMPT
        )
        self.task_ledger_plan_update_prompt: str = (
            task_ledger_plan_update_prompt or ORCHESTRATOR_TASK_LEDGER_PLAN_UPDATE_PROMPT
        )
        self.progress_ledger_prompt: str = progress_ledger_prompt or ORCHESTRATOR_PROGRESS_LEDGER_PROMPT
        self.final_answer_prompt: str = final_answer_prompt or ORCHESTRATOR_FINAL_ANSWER_PROMPT

        self.progress_ledger_retry_count: int = (
            progress_ledger_retry_count if progress_ledger_retry_count is not None else 3
        )

    async def _complete(
        self,
        messages: list[ChatMessage],
    ) -> ChatMessage:
        """Call the underlying agent and return the last assistant message.

        The agent's run method is called which applies the agent's configured options
        (temperature, seed, instructions, etc.).
        """
        response: AgentRunResponse = await self._agent.run(messages)
        out_messages = response.messages if response else None
        if out_messages:
            last = out_messages[-1]
            return ChatMessage(
                role=last.role,
                text=last.text,
                author_name=last.author_name or MAGENTIC_MANAGER_NAME,
            )
        return ChatMessage(role=Role.ASSISTANT, text="No output produced.", author_name=MAGENTIC_MANAGER_NAME)

    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Create facts and plan using the model, then render a combined task ledger as a single assistant message."""
        task_text = magentic_context.task.text
        team_text = _team_block(magentic_context.participant_descriptions)

        # Gather facts
        facts_user = ChatMessage(
            role=Role.USER,
            text=self.task_ledger_facts_prompt.format(task=task_text),
        )
        facts_msg = await self._complete([*magentic_context.chat_history, facts_user])

        # Create plan
        plan_user = ChatMessage(
            role=Role.USER,
            text=self.task_ledger_plan_prompt.format(team=team_text),
        )
        plan_msg = await self._complete([*magentic_context.chat_history, facts_user, facts_msg, plan_user])

        # Store ledger and render full combined view
        self.task_ledger = _MagenticTaskLedger(facts=facts_msg, plan=plan_msg)

        # Also store individual messages in chat_history for better grounding
        # This gives the progress ledger model access to the detailed reasoning
        magentic_context.chat_history.extend([facts_user, facts_msg, plan_user, plan_msg])

        combined = self.task_ledger_full_prompt.format(
            task=task_text,
            team=team_text,
            facts=facts_msg.text,
            plan=plan_msg.text,
        )
        return ChatMessage(role=Role.ASSISTANT, text=combined, author_name=MAGENTIC_MANAGER_NAME)

    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Update facts and plan when stalling or looping has been detected."""
        if self.task_ledger is None:
            raise RuntimeError("replan() called before plan(); call plan() once before requesting a replan.")

        task_text = magentic_context.task.text
        team_text = _team_block(magentic_context.participant_descriptions)

        # Update facts
        facts_update_user = ChatMessage(
            role=Role.USER,
            text=self.task_ledger_facts_update_prompt.format(task=task_text, old_facts=self.task_ledger.facts.text),
        )
        updated_facts = await self._complete([*magentic_context.chat_history, facts_update_user])

        # Update plan
        plan_update_user = ChatMessage(
            role=Role.USER,
            text=self.task_ledger_plan_update_prompt.format(team=team_text),
        )
        updated_plan = await self._complete([
            *magentic_context.chat_history,
            facts_update_user,
            updated_facts,
            plan_update_user,
        ])

        # Store and render
        self.task_ledger = _MagenticTaskLedger(facts=updated_facts, plan=updated_plan)

        # Also store individual messages in chat_history for better grounding
        # This gives the progress ledger model access to the detailed reasoning
        magentic_context.chat_history.extend([facts_update_user, updated_facts, plan_update_user, updated_plan])

        combined = self.task_ledger_full_prompt.format(
            task=task_text,
            team=team_text,
            facts=updated_facts.text,
            plan=updated_plan.text,
        )
        return ChatMessage(role=Role.ASSISTANT, text=combined, author_name=MAGENTIC_MANAGER_NAME)

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> _MagenticProgressLedger:
        """Use the model to produce a JSON progress ledger based on the conversation so far.

        Adds lightweight retries with backoff for transient parse issues and avoids selecting a
        non-existent "unknown" agent. If there are no participants, a clear error is raised.
        """
        agent_names = list(magentic_context.participant_descriptions.keys())
        if not agent_names:
            raise RuntimeError("No participants configured; cannot determine next speaker.")

        names_csv = ", ".join(agent_names)
        team_text = _team_block(magentic_context.participant_descriptions)

        prompt = self.progress_ledger_prompt.format(
            task=magentic_context.task.text,
            team=team_text,
            names=names_csv,
        )
        user_message = ChatMessage(role=Role.USER, text=prompt)

        # Include full context to help the model decide current stage, with small retry loop
        attempts = 0
        last_error: Exception | None = None
        while attempts < self.progress_ledger_retry_count:
            raw = await self._complete([*magentic_context.chat_history, user_message])
            try:
                ledger_dict = _extract_json(raw.text)
                return _coerce_model(_MagenticProgressLedger, ledger_dict)
            except Exception as ex:
                last_error = ex
                attempts += 1
                logger.warning(
                    f"Progress ledger JSON parse failed (attempt {attempts}/{self.progress_ledger_retry_count}): {ex}"
                )
                if attempts < self.progress_ledger_retry_count:
                    # brief backoff before next try
                    await asyncio.sleep(0.25 * attempts)

        raise RuntimeError(
            f"Progress ledger parse failed after {self.progress_ledger_retry_count} attempt(s): {last_error}"
        )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        """Ask the model to produce the final answer addressed to the user."""
        prompt = self.final_answer_prompt.format(task=magentic_context.task.text)
        user_message = ChatMessage(role=Role.USER, text=prompt)
        response = await self._complete([*magentic_context.chat_history, user_message])
        # Ensure role is assistant
        return ChatMessage(
            role=Role.ASSISTANT,
            text=response.text,
            author_name=response.author_name or MAGENTIC_MANAGER_NAME,
        )

    @override
    def on_checkpoint_save(self) -> dict[str, Any]:
        state: dict[str, Any] = {}
        if self.task_ledger is not None:
            state["task_ledger"] = self.task_ledger.to_dict()
        return state

    @override
    def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        ledger = state.get("task_ledger")
        if ledger is not None:
            try:
                self.task_ledger = _MagenticTaskLedger.from_dict(ledger)
            except Exception:  # pragma: no cover - defensive
                logger.warning("Failed to restore manager task ledger from checkpoint state")


# endregion Magentic Manager

# region Magentic Executors


class MagenticOrchestratorExecutor(BaseGroupChatOrchestrator):
    """Magentic orchestrator executor that handles all orchestration logic.

    This executor manages the entire Magentic One workflow including:
    - Initial planning and task ledger creation
    - Progress tracking and completion detection
    - Agent coordination and message routing
    - Reset and replanning logic
    """

    # Typed attributes (initialized in __init__)
    _agent_executors: dict[str, "MagenticAgentExecutor"]
    _context: "MagenticContext | None"
    _task_ledger: "ChatMessage | None"
    _inner_loop_lock: asyncio.Lock
    _require_plan_signoff: bool
    _plan_review_round: int
    _max_plan_review_rounds: int
    _terminated: bool
    _enable_stall_intervention: bool

    def __init__(
        self,
        manager: MagenticManagerBase,
        participants: dict[str, str],
        *,
        require_plan_signoff: bool = False,
        max_plan_review_rounds: int = 10,
        enable_stall_intervention: bool = False,
        executor_id: str | None = None,
    ) -> None:
        """Initializes a new instance of the MagenticOrchestratorExecutor.

        Args:
            manager: The Magentic manager instance.
            participants: A dictionary of participant IDs to their names.
            require_plan_signoff: Whether to require plan sign-off from a human.
            max_plan_review_rounds: The maximum number of plan review rounds.
            enable_stall_intervention: Whether to request human input on stalls instead of auto-replan.
            executor_id: An optional executor ID.
        """
        super().__init__(executor_id or f"magentic_orchestrator_{uuid4().hex[:8]}")
        self._manager = manager
        self._participants = participants
        self._context = None
        self._task_ledger = None
        self._require_plan_signoff = require_plan_signoff
        self._plan_review_round = 0
        self._max_plan_review_rounds = max_plan_review_rounds
        self._enable_stall_intervention = enable_stall_intervention
        # Registry of agent executors for internal coordination (e.g., resets)
        self._agent_executors = {}
        # Terminal state marker to stop further processing after completion/limits
        self._terminated = False
        # Tracks whether checkpoint state has been applied for this run

    def _get_author_name(self) -> str:
        """Get the magentic manager name for orchestrator-generated messages."""
        return MAGENTIC_MANAGER_NAME

    def register_agent_executor(self, name: str, executor: "MagenticAgentExecutor") -> None:
        """Register an agent executor for internal control (no messages)."""
        self._agent_executors[name] = executor

    async def _emit_orchestrator_message(
        self,
        ctx: WorkflowContext[Any, list[ChatMessage]],
        message: ChatMessage,
        kind: str,
    ) -> None:
        """Emit orchestrator message to the workflow event stream.

        Emits an AgentRunUpdateEvent (for agent wrapper consumers) with metadata indicating
        the orchestrator event type.

        Args:
            ctx: Workflow context for adding events to the stream
            message: Orchestrator message to emit (task, plan, instruction, notice)
            kind: Message classification (user_task, task_ledger, instruction, notice)

        Example:
            async for event in workflow.run_stream("task"):
                if isinstance(event, AgentRunUpdateEvent):
                    props = event.data.additional_properties if event.data else None
                    if props and props.get("magentic_event_type") == "orchestrator_message":
                        kind = props.get("orchestrator_message_kind", "")
                        print(f"Orchestrator {kind}: {event.data.text}")
        """
        # Emit AgentRunUpdateEvent with metadata
        update = AgentRunResponseUpdate(
            text=message.text,
            role=message.role,
            author_name=self._get_author_name(),
            additional_properties={
                "magentic_event_type": MAGENTIC_EVENT_TYPE_ORCHESTRATOR,
                "orchestrator_message_kind": kind,
                "orchestrator_id": self.id,
            },
        )
        await ctx.add_event(AgentRunUpdateEvent(executor_id=self.id, data=update))

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Capture current orchestrator state for checkpointing.

        Uses OrchestrationState for structure but maintains Magentic's complex metadata
        at the top level for backward compatibility with existing checkpoints.

        Returns:
            Dict ready for checkpoint persistence
        """
        state: dict[str, Any] = {
            "plan_review_round": self._plan_review_round,
            "max_plan_review_rounds": self._max_plan_review_rounds,
            "require_plan_signoff": self._require_plan_signoff,
            "terminated": self._terminated,
        }
        if self._context is not None:
            state["magentic_context"] = self._context.to_dict()
        if self._task_ledger is not None:
            state["task_ledger"] = _message_to_payload(self._task_ledger)

        try:
            state["manager_state"] = self._manager.on_checkpoint_save()
        except Exception as exc:
            logger.warning(f"Failed to save manager state for checkpoint: {exc}\nSkipping...")

        return state

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore orchestrator state from checkpoint.

        Maintains backward compatibility with existing Magentic checkpoints
        while supporting OrchestrationState structure.

        Args:
            state: Checkpoint data dict
        """
        # Support both old format (direct keys) and new format (wrapped in OrchestrationState)
        if "metadata" in state and isinstance(state.get("metadata"), dict):
            # New OrchestrationState format - extract metadata
            from ._orchestration_state import OrchestrationState

            orch_state = OrchestrationState.from_dict(state)
            state = orch_state.metadata

        ctx_payload = state.get("magentic_context")
        if ctx_payload is not None:
            try:
                if isinstance(ctx_payload, dict):
                    self._context = MagenticContext.from_dict(ctx_payload)  # type: ignore[arg-type]
                else:
                    self._context = None
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning(f"Failed to restore magentic context: {exc}")
                self._context = None
        ledger_payload = state.get("task_ledger")
        if ledger_payload is not None:
            try:
                self._task_ledger = _message_from_payload(ledger_payload)
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Failed to restore task ledger message: {exc}")
                self._task_ledger = None

        if "plan_review_round" in state:
            try:
                self._plan_review_round = int(state["plan_review_round"])
            except Exception:  # pragma: no cover
                logger.debug("Ignoring invalid plan_review_round in checkpoint state")
        if "max_plan_review_rounds" in state:
            self._max_plan_review_rounds = state.get("max_plan_review_rounds")  # type: ignore[assignment]
        if "require_plan_signoff" in state:
            self._require_plan_signoff = bool(state.get("require_plan_signoff"))
        if "terminated" in state:
            self._terminated = bool(state.get("terminated"))

        manager_state = state.get("manager_state")
        if manager_state is not None:
            try:
                self._manager.on_checkpoint_restore(manager_state)
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Failed to restore manager state: {exc}")

        self._reconcile_restored_participants()

    def _reconcile_restored_participants(self) -> None:
        """Ensure restored participant roster matches the current workflow graph."""
        if self._context is None:
            return

        restored = self._context.participant_descriptions or {}
        expected = self._participants

        restored_names = set(restored.keys())
        expected_names = set(expected.keys())

        if restored_names != expected_names:
            missing = ", ".join(sorted(expected_names - restored_names)) or "none"
            unexpected = ", ".join(sorted(restored_names - expected_names)) or "none"
            raise RuntimeError(
                "Magentic checkpoint restore failed: participant names do not match the checkpoint. "
                "Ensure MagenticBuilder.participants keys remain stable across runs. "
                f"Missing names: {missing}; unexpected names: {unexpected}."
            )

        # Refresh descriptions so prompt surfaces always reflect the rebuilt workflow inputs.
        for name, description in expected.items():
            restored[name] = description

    @handler
    async def handle_start_message(
        self,
        message: _MagenticStartMessage,
        context: WorkflowContext[
            _MagenticResponseMessage | _MagenticRequestMessage | _MagenticHumanInterventionRequest, list[ChatMessage]
        ],
    ) -> None:
        """Handle the initial start message to begin orchestration."""
        if getattr(self, "_terminated", False):
            return
        logger.info("Magentic Orchestrator: Received start message")

        self._context = MagenticContext(
            task=message.task,
            participant_descriptions=self._participants,
        )
        if message.messages:
            self._context.chat_history.extend(message.messages)

        # Non-streaming callback for the orchestrator receipt of the task
        await self._emit_orchestrator_message(context, message.task, ORCH_MSG_KIND_USER_TASK)

        # Initial planning using the manager with real model calls
        self._task_ledger = await self._manager.plan(self._context.clone(deep=True))

        # If a human must sign off, ask now and return. The response handler will resume.
        if self._require_plan_signoff:
            await self._send_plan_review_request(cast(WorkflowContext, context))
            return

        # Add task ledger to conversation history
        self._context.chat_history.append(self._task_ledger)

        logger.debug("Task ledger created.")

        await self._emit_orchestrator_message(context, self._task_ledger, ORCH_MSG_KIND_TASK_LEDGER)

        # Start the inner loop
        ctx2 = cast(
            WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
            context,
        )
        await self._run_inner_loop(ctx2)

    @handler
    async def handle_task_text(
        self,
        task_text: str,
        context: WorkflowContext[
            _MagenticResponseMessage | _MagenticRequestMessage | _MagenticHumanInterventionRequest, list[ChatMessage]
        ],
    ) -> None:
        await self.handle_start_message(_MagenticStartMessage.from_string(task_text), context)

    @handler
    async def handle_task_message(
        self,
        task_message: ChatMessage,
        context: WorkflowContext[
            _MagenticResponseMessage | _MagenticRequestMessage | _MagenticHumanInterventionRequest, list[ChatMessage]
        ],
    ) -> None:
        await self.handle_start_message(_MagenticStartMessage(task_message), context)

    @handler
    async def handle_task_messages(
        self,
        conversation: list[ChatMessage],
        context: WorkflowContext[
            _MagenticResponseMessage | _MagenticRequestMessage | _MagenticHumanInterventionRequest, list[ChatMessage]
        ],
    ) -> None:
        await self.handle_start_message(_MagenticStartMessage(conversation), context)

    @handler
    async def handle_response_message(
        self,
        message: _MagenticResponseMessage,
        context: WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
    ) -> None:
        """Handle responses from agents."""
        if getattr(self, "_terminated", False):
            return

        if self._context is None:
            raise RuntimeError("Magentic Orchestrator: Received response but not initialized")

        logger.debug("Magentic Orchestrator: Received response from agent")

        # Add transfer message if needed
        if message.body.role != Role.USER:
            transfer_msg = ChatMessage(
                role=Role.USER,
                text=f"Transferred to {getattr(message.body, 'author_name', 'agent')}",
            )
            self._context.chat_history.append(transfer_msg)

        # Add agent response to context
        self._context.chat_history.append(message.body)

        # Continue with inner loop
        await self._run_inner_loop(context)

    @response_handler
    async def handle_human_intervention_response(
        self,
        original_request: _MagenticHumanInterventionRequest,
        response: _MagenticHumanInterventionReply,
        context: WorkflowContext[
            _MagenticResponseMessage | _MagenticRequestMessage | _MagenticHumanInterventionRequest, list[ChatMessage]
        ],
    ) -> None:
        """Handle unified human intervention responses.

        Routes the response to the appropriate handler based on the original request kind.
        """
        if getattr(self, "_terminated", False):
            return

        if self._context is None:
            return

        if original_request.kind == MagenticHumanInterventionKind.PLAN_REVIEW:
            await self._handle_plan_review_response(original_request, response, context)
        elif original_request.kind == MagenticHumanInterventionKind.STALL:
            await self._handle_stall_intervention_response(original_request, response, context)
        # TOOL_APPROVAL is handled by MagenticAgentExecutor, not the orchestrator

    async def _handle_plan_review_response(
        self,
        original_request: _MagenticHumanInterventionRequest,
        response: _MagenticHumanInterventionReply,
        context: WorkflowContext[
            _MagenticResponseMessage | _MagenticRequestMessage | _MagenticHumanInterventionRequest, list[ChatMessage]
        ],
    ) -> None:
        """Handle plan review response."""
        if self._context is None:
            return

        is_approve = response.decision == MagenticHumanInterventionDecision.APPROVE

        if is_approve:
            # Close the review loop on approval (no further plan review requests this run)
            self._require_plan_signoff = False
            # If the user supplied an edited plan, adopt it
            if response.edited_plan_text:
                # Update the manager's internal ledger and rebuild the combined message
                mgr_ledger = getattr(self._manager, "task_ledger", None)
                if mgr_ledger is not None:
                    mgr_ledger.plan.text = response.edited_plan_text
                team_text = _team_block(self._participants)
                combined = self._manager.task_ledger_full_prompt.format(
                    task=self._context.task.text,
                    team=team_text,
                    facts=(mgr_ledger.facts.text if mgr_ledger else ""),
                    plan=response.edited_plan_text,
                )
                self._task_ledger = ChatMessage(
                    role=Role.ASSISTANT,
                    text=combined,
                    author_name=MAGENTIC_MANAGER_NAME,
                )
            # If approved with comments but no edited text, apply comments via replan and proceed
            elif response.comments:
                self._context.chat_history.append(
                    ChatMessage(role=Role.USER, text=f"Human plan feedback: {response.comments}")
                )
                self._task_ledger = await self._manager.replan(self._context.clone(deep=True))

            # Record the signed-off plan (no broadcast)
            if self._task_ledger:
                self._context.chat_history.append(self._task_ledger)
                await self._emit_orchestrator_message(context, self._task_ledger, ORCH_MSG_KIND_TASK_LEDGER)

            # Enter the normal coordination loop
            ctx2 = cast(
                WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
                context,
            )
            await self._run_inner_loop(ctx2)
            return

        # Otherwise, REVISION round
        self._plan_review_round += 1
        if self._plan_review_round > self._max_plan_review_rounds:
            logger.warning("Magentic Orchestrator: Max plan review rounds reached. Proceeding with current plan.")
            self._require_plan_signoff = False
            notice = ChatMessage(
                role=Role.ASSISTANT,
                text=(
                    "Plan review closed after max rounds. Proceeding with the current plan and will no longer "
                    "prompt for plan approval."
                ),
                author_name=MAGENTIC_MANAGER_NAME,
            )
            self._context.chat_history.append(notice)
            await self._emit_orchestrator_message(context, notice, ORCH_MSG_KIND_NOTICE)
            if self._task_ledger:
                self._context.chat_history.append(self._task_ledger)
            ctx2 = cast(
                WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
                context,
            )
            await self._run_inner_loop(ctx2)
            return

        # If the user provided an edited plan, adopt it and ask for confirmation
        if response.edited_plan_text:
            mgr_ledger2 = getattr(self._manager, "task_ledger", None)
            if mgr_ledger2 is not None:
                mgr_ledger2.plan.text = response.edited_plan_text
            team_text = _team_block(self._participants)
            combined = self._manager.task_ledger_full_prompt.format(
                task=self._context.task.text,
                team=team_text,
                facts=(mgr_ledger2.facts.text if mgr_ledger2 else ""),
                plan=response.edited_plan_text,
            )
            self._task_ledger = ChatMessage(role=Role.ASSISTANT, text=combined, author_name=MAGENTIC_MANAGER_NAME)
            await self._send_plan_review_request(cast(WorkflowContext, context))
            return

        # Else pass comments into the chat history and replan
        if response.comments:
            self._context.chat_history.append(
                ChatMessage(role=Role.USER, text=f"Human plan feedback: {response.comments}")
            )

        self._task_ledger = await self._manager.replan(self._context.clone(deep=True))
        await self._send_plan_review_request(cast(WorkflowContext, context))

    async def _handle_stall_intervention_response(
        self,
        original_request: _MagenticHumanInterventionRequest,
        response: _MagenticHumanInterventionReply,
        context: WorkflowContext[
            _MagenticResponseMessage | _MagenticRequestMessage | _MagenticHumanInterventionRequest, list[ChatMessage]
        ],
    ) -> None:
        """Handle stall intervention response."""
        if self._context is None:
            return

        ctx = self._context
        logger.info(
            f"Stall intervention response: decision={response.decision.value}, "
            f"stall_count was {original_request.stall_count}"
        )

        if response.decision == MagenticHumanInterventionDecision.CONTINUE:
            ctx.stall_count = 0
            ctx2 = cast(
                WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
                context,
            )
            await self._run_inner_loop(ctx2)
            return

        if response.decision == MagenticHumanInterventionDecision.REPLAN:
            ctx2 = cast(
                WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
                context,
            )
            await self._reset_and_replan(ctx2)
            return

        if response.decision == MagenticHumanInterventionDecision.GUIDANCE:
            ctx.stall_count = 0
            guidance = response.comments or response.response_text
            if guidance:
                guidance_msg = ChatMessage(
                    role=Role.USER,
                    text=f"Human guidance to help with stall: {guidance}",
                )
                ctx.chat_history.append(guidance_msg)
                await self._emit_orchestrator_message(context, guidance_msg, ORCH_MSG_KIND_NOTICE)
            ctx2 = cast(
                WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
                context,
            )
            await self._run_inner_loop(ctx2)
            return

    async def _run_outer_loop(
        self,
        context: WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
    ) -> None:
        """Run the outer orchestration loop - planning phase."""
        if self._context is None:
            raise RuntimeError("Context not initialized")

        logger.info("Magentic Orchestrator: Outer loop - entering inner loop")

        # Add task ledger to history if not already there
        if self._task_ledger and (
            not self._context.chat_history or self._context.chat_history[-1] != self._task_ledger
        ):
            self._context.chat_history.append(self._task_ledger)

        # Optionally surface the updated task ledger via message callback (no broadcast)
        if self._task_ledger is not None:
            await self._emit_orchestrator_message(context, self._task_ledger, ORCH_MSG_KIND_TASK_LEDGER)

        # Start inner loop
        await self._run_inner_loop(context)

    async def _run_inner_loop(
        self,
        context: WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
    ) -> None:
        """Run the inner orchestration loop. Coordination phase. Serialized with a lock."""
        if self._context is None or self._task_ledger is None:
            raise RuntimeError("Context or task ledger not initialized")

        await self._run_inner_loop_helper(context)

    async def _run_inner_loop_helper(
        self,
        context: WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
    ) -> None:
        """Run inner loop with exclusive access."""
        # Narrow optional context for the remainder of this method
        ctx = self._context
        if ctx is None:
            raise RuntimeError("Context not initialized")
        # Check limits first
        within_limits = await self._check_within_limits_or_complete(context)
        if not within_limits:
            return

        ctx.round_count += 1
        logger.info(f"Magentic Orchestrator: Inner loop - round {ctx.round_count}")

        # Create progress ledger using the manager
        try:
            current_progress_ledger = await self._manager.create_progress_ledger(ctx.clone(deep=True))
        except Exception as ex:
            logger.warning(f"Magentic Orchestrator: Progress ledger creation failed, triggering reset: {ex}")
            await self._reset_and_replan(context)
            return

        logger.debug(
            f"Progress evaluation: satisfied={current_progress_ledger.is_request_satisfied.answer}, "
            f"next={current_progress_ledger.next_speaker.answer}"
        )

        # Check for task completion
        if current_progress_ledger.is_request_satisfied.answer:
            logger.info("Magentic Orchestrator: Task completed")
            await self._prepare_final_answer(context)
            return

        # Check for stalling or looping
        if not current_progress_ledger.is_progress_being_made.answer or current_progress_ledger.is_in_loop.answer:
            ctx.stall_count += 1
        else:
            ctx.stall_count = max(0, ctx.stall_count - 1)

        if ctx.stall_count > self._manager.max_stall_count:
            logger.info(f"Magentic Orchestrator: Stalling detected after {ctx.stall_count} rounds")
            if self._enable_stall_intervention:
                # Request human intervention instead of auto-replan
                is_progress = current_progress_ledger.is_progress_being_made.answer
                is_loop = current_progress_ledger.is_in_loop.answer
                stall_reason = "No progress being made" if not is_progress else ""
                if is_loop:
                    loop_msg = "Agents appear to be in a loop"
                    stall_reason = f"{stall_reason}; {loop_msg}" if stall_reason else loop_msg
                next_speaker_val = current_progress_ledger.next_speaker.answer
                last_agent = next_speaker_val if isinstance(next_speaker_val, str) else ""
                # Get facts and plan from manager's task ledger
                mgr_ledger = getattr(self._manager, "task_ledger", None)
                facts_text = mgr_ledger.facts.text if mgr_ledger else ""
                plan_text = mgr_ledger.plan.text if mgr_ledger else ""
                request = _MagenticHumanInterventionRequest(
                    kind=MagenticHumanInterventionKind.STALL,
                    stall_count=ctx.stall_count,
                    max_stall_count=self._manager.max_stall_count,
                    task_text=ctx.task.text if ctx.task else "",
                    facts_text=facts_text,
                    plan_text=plan_text,
                    last_agent=last_agent,
                    stall_reason=stall_reason,
                )
                await context.request_info(request, _MagenticHumanInterventionReply)
                return
            # Default behavior: auto-replan
            await self._reset_and_replan(context)
            return

        # Determine the next speaker and instruction
        answer_val = current_progress_ledger.next_speaker.answer
        if not isinstance(answer_val, str):
            # Fallback to first participant if ledger returns non-string
            logger.warning("Next speaker answer was not a string; selecting first participant as fallback")
            answer_val = next(iter(self._participants.keys()))
        next_speaker_value: str = answer_val
        instruction = current_progress_ledger.instruction_or_question.answer

        if next_speaker_value not in self._participants:
            logger.warning(f"Invalid next speaker: {next_speaker_value}")
            await self._prepare_final_answer(context)
            return

        # Add instruction to conversation (assistant guidance)
        instruction_msg = ChatMessage(
            role=Role.ASSISTANT,
            text=str(instruction),
            author_name=MAGENTIC_MANAGER_NAME,
        )
        ctx.chat_history.append(instruction_msg)
        await self._emit_orchestrator_message(context, instruction_msg, ORCH_MSG_KIND_INSTRUCTION)

        # Determine the selected agent's executor id
        target_executor_id = f"agent_{next_speaker_value}"

        # Request specific agent to respond
        logger.debug(f"Magentic Orchestrator: Requesting {next_speaker_value} to respond")
        await context.send_message(
            _MagenticRequestMessage(
                agent_name=next_speaker_value,
                instruction=str(instruction),
                task_context=ctx.task.text,
            ),
            target_id=target_executor_id,
        )

    async def _reset_and_replan(
        self,
        context: WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
    ) -> None:
        """Reset context and replan."""
        if self._context is None:
            return

        logger.info("Magentic Orchestrator: Resetting and replanning")

        # Reset context
        self._context.reset()

        # Replan
        self._task_ledger = await self._manager.replan(self._context.clone(deep=True))
        self._context.chat_history.append(self._task_ledger)
        await self._emit_orchestrator_message(context, self._task_ledger, ORCH_MSG_KIND_TASK_LEDGER)

        # Internally reset all registered agent executors (no handler/messages involved)
        for agent in self._agent_executors.values():
            with contextlib.suppress(Exception):
                agent.reset()

        # Restart outer loop
        await self._run_outer_loop(context)

    async def _prepare_final_answer(
        self,
        context: WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
    ) -> None:
        """Prepare the final answer using the manager."""
        if self._context is None:
            return

        logger.info("Magentic Orchestrator: Preparing final answer")
        final_answer = await self._manager.prepare_final_answer(self._context.clone(deep=True))

        # Emit a completed event for the workflow
        await context.yield_output([final_answer])

    async def _check_within_limits_or_complete(
        self,
        context: WorkflowContext[_MagenticResponseMessage | _MagenticRequestMessage, list[ChatMessage]],
    ) -> bool:
        """Check if orchestrator is within operational limits."""
        if self._context is None:
            return False
        ctx = self._context

        hit_round_limit = self._manager.max_round_count is not None and ctx.round_count >= self._manager.max_round_count
        hit_reset_limit = self._manager.max_reset_count is not None and ctx.reset_count >= self._manager.max_reset_count

        if hit_round_limit or hit_reset_limit:
            limit_type = "round" if hit_round_limit else "reset"
            logger.error(f"Magentic Orchestrator: Max {limit_type} count reached")

            # Only emit completion once and then mark terminated
            if not self._terminated:
                self._terminated = True
                # Get partial result
                partial_result = _first_assistant(ctx.chat_history)
                if partial_result is None:
                    partial_result = ChatMessage(
                        role=Role.ASSISTANT,
                        text=f"Stopped due to {limit_type} limit. No partial result available.",
                        author_name=MAGENTIC_MANAGER_NAME,
                    )

                # Yield the partial result and signal completion
                await context.yield_output([partial_result])
            return False

        return True

    async def _send_plan_review_request(self, context: WorkflowContext) -> None:
        """Send a human intervention request for plan review."""
        # If plan sign-off is disabled (e.g., ran out of review rounds), do nothing
        if not self._require_plan_signoff:
            return
        ledger = getattr(self._manager, "task_ledger", None)
        facts_text = ledger.facts.text if ledger else ""
        plan_text = ledger.plan.text if ledger else ""
        task_text = self._context.task.text if self._context else ""

        req = _MagenticHumanInterventionRequest(
            kind=MagenticHumanInterventionKind.PLAN_REVIEW,
            task_text=task_text,
            facts_text=facts_text,
            plan_text=plan_text,
            round_index=self._plan_review_round,
        )
        await context.request_info(req, _MagenticHumanInterventionReply)


# region Magentic Executors


class MagenticAgentExecutor(Executor):
    """Magentic agent executor that wraps an agent for participation in workflows.

    Leverages enhanced AgentExecutor with conversation injection hooks for:
    - Receiving task ledger broadcasts
    - Responding to specific agent requests
    - Resetting agent state when needed
    - Surfacing tool approval requests (user_input_requests) as HITL events
    """

    def __init__(
        self,
        agent: AgentProtocol | Executor,
        agent_id: str,
    ) -> None:
        super().__init__(f"agent_{agent_id}")
        self._agent = agent
        self._agent_id = agent_id
        self._chat_history: list[ChatMessage] = []
        self._pending_human_input_request: _MagenticHumanInterventionRequest | None = None
        self._pending_tool_request: FunctionApprovalRequestContent | None = None
        self._current_request_message: _MagenticRequestMessage | None = None

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Capture current executor state for checkpointing.

        Returns:
            Dict containing serialized chat history
        """
        from ._conversation_state import encode_chat_messages

        return {
            "chat_history": encode_chat_messages(self._chat_history),
        }

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore executor state from checkpoint.

        Args:
            state: Checkpoint data dict
        """
        from ._conversation_state import decode_chat_messages

        history_payload = state.get("chat_history")
        if history_payload:
            try:
                self._chat_history = decode_chat_messages(history_payload)
            except Exception as exc:  # pragma: no cover
                logger.warning(f"Agent {self._agent_id}: Failed to restore chat history: {exc}")
                self._chat_history = []
        else:
            self._chat_history = []

    @handler
    async def handle_response_message(
        self, message: _MagenticResponseMessage, context: WorkflowContext[_MagenticResponseMessage]
    ) -> None:
        """Handle response message (task ledger broadcast)."""
        logger.debug(f"Agent {self._agent_id}: Received response message")

        # Check if this message is intended for this agent
        if message.target_agent is not None and message.target_agent != self._agent_id and not message.broadcast:
            # Message is targeted to a different agent, ignore it
            logger.debug(f"Agent {self._agent_id}: Ignoring message targeted to {message.target_agent}")
            return

        # Add transfer message if needed
        if message.body.role != Role.USER:
            transfer_msg = ChatMessage(
                role=Role.USER,
                text=f"Transferred to {getattr(message.body, 'author_name', 'agent')}",
            )
            self._chat_history.append(transfer_msg)

        # Add message to agent's history
        self._chat_history.append(message.body)

    def _get_persona_adoption_role(self) -> Role:
        """Determine the best role for persona adoption messages.

        Uses SYSTEM role if the agent supports it, otherwise falls back to USER.
        """
        # Only BaseAgent-derived agents are assumed to support SYSTEM messages reliably.
        from agent_framework import BaseAgent as _AF_AgentBase  # local import to avoid cycles

        if isinstance(self._agent, _AF_AgentBase) and hasattr(self._agent, "chat_client"):
            return Role.SYSTEM
        # For other agent types or when we can't determine support, use USER
        return Role.USER

    @handler
    async def handle_request_message(
        self, message: _MagenticRequestMessage, context: WorkflowContext[_MagenticResponseMessage, AgentRunResponse]
    ) -> None:
        """Handle request to respond."""
        if message.agent_name != self._agent_id:
            return

        logger.info(f"Agent {self._agent_id}: Received request to respond")

        # Store the original request message for potential continuation after human input
        self._current_request_message = message

        # Add persona adoption message with appropriate role
        persona_role = self._get_persona_adoption_role()
        persona_msg = ChatMessage(
            role=persona_role,
            text=f"Transferred to {self._agent_id}, adopt the persona immediately.",
        )
        self._chat_history.append(persona_msg)

        # Add the orchestrator's instruction as a USER message so the agent treats it as the prompt
        if message.instruction:
            self._chat_history.append(ChatMessage(role=Role.USER, text=message.instruction))
        try:
            # If the participant is not an invokable BaseAgent, return a no-op response.
            from agent_framework import BaseAgent as _AF_AgentBase  # local import to avoid cycles

            if not isinstance(self._agent, _AF_AgentBase):
                response: ChatMessage = ChatMessage(
                    role=Role.ASSISTANT,
                    text=f"{self._agent_id} is a workflow executor and cannot be invoked directly.",
                    author_name=self._agent_id,
                )
                self._chat_history.append(response)
                await self._emit_agent_message_event(context, response)
                await context.send_message(_MagenticResponseMessage(body=response))
            else:
                # Invoke the agent
                agent_response = await self._invoke_agent(context)
                if agent_response is None:
                    # Agent is waiting for human input - don't send response yet
                    return
                self._chat_history.append(agent_response)
                # Send response back to orchestrator
                await context.send_message(_MagenticResponseMessage(body=agent_response))

        except Exception as e:
            logger.warning(f"Agent {self._agent_id} invoke failed: {e}")
            # Fallback response
            response = ChatMessage(
                role=Role.ASSISTANT,
                text=f"Agent {self._agent_id}: Error processing request - {str(e)[:100]}",
            )
            self._chat_history.append(response)
            await self._emit_agent_message_event(context, response)
            await context.send_message(_MagenticResponseMessage(body=response))

    def reset(self) -> None:
        """Reset the internal chat history of the agent (internal operation)."""
        logger.debug(f"Agent {self._agent_id}: Resetting chat history")
        self._chat_history.clear()
        self._pending_human_input_request = None
        self._pending_tool_request = None
        self._current_request_message = None

    @response_handler
    async def handle_tool_approval_response(
        self,
        original_request: _MagenticHumanInterventionRequest,
        response: _MagenticHumanInterventionReply,
        context: WorkflowContext[_MagenticResponseMessage, AgentRunResponse],
    ) -> None:
        """Handle human response for tool approval and continue agent execution.

        When a human provides input in response to a tool approval request,
        this handler processes the response based on the decision type:

        - APPROVE: Execute the tool call with the provided response text
        - REJECT: Do not execute the tool, inform the agent of rejection
        - GUIDANCE: Execute the tool call with the guidance text as input

        Args:
            original_request: The original human intervention request
            response: The human's response containing the decision and any text
            context: The workflow context
        """
        response_text = response.response_text or response.comments or ""
        decision = response.decision
        logger.info(
            f"Agent {original_request.agent_id}: Received tool approval response "
            f"(decision={decision.value}): {response_text[:50] if response_text else ''}"
        )

        # Get the pending tool request to extract call_id
        pending_tool_request = self._pending_tool_request
        self._pending_human_input_request = None
        self._pending_tool_request = None

        # Handle REJECT decision - do not execute the tool call
        if decision == MagenticHumanInterventionDecision.REJECT:
            rejection_reason = response_text or "Tool call rejected by human"
            logger.info(f"Agent {self._agent_id}: Tool call rejected: {rejection_reason}")

            if pending_tool_request is not None:
                # Create a FunctionResultContent indicating rejection
                function_result = FunctionResultContent(
                    call_id=pending_tool_request.function_call.call_id,
                    result=f"Tool call was rejected by human reviewer. Reason: {rejection_reason}",
                )
                result_msg = ChatMessage(
                    role=Role.USER,
                    contents=[function_result],
                )
                self._chat_history.append(result_msg)
            else:
                # Fallback without pending tool request
                rejection_msg = ChatMessage(
                    role=Role.USER,
                    text=f"Tool call '{original_request.prompt}' was rejected: {rejection_reason}",
                    author_name="human",
                )
                self._chat_history.append(rejection_msg)

            # Re-invoke the agent so it can adapt to the rejection
            agent_response = await self._invoke_agent(context)
            if agent_response is None:
                return
            self._chat_history.append(agent_response)
            await context.send_message(_MagenticResponseMessage(body=agent_response))
            return

        # Handle APPROVE and GUIDANCE decisions - execute the tool call
        if pending_tool_request is not None:
            # Create a FunctionResultContent with the human's response
            function_result = FunctionResultContent(
                call_id=pending_tool_request.function_call.call_id,
                result=response_text,
            )
            # Add the function result as a message to continue the conversation
            result_msg = ChatMessage(
                role=Role.USER,
                contents=[function_result],
            )
            self._chat_history.append(result_msg)

            # Re-invoke the agent to continue execution
            agent_response = await self._invoke_agent(context)
            if agent_response is None:
                # Agent is waiting for more human input
                return
            self._chat_history.append(agent_response)
            await context.send_message(_MagenticResponseMessage(body=agent_response))
        else:
            # Fallback: no pending tool request, just add as text message
            logger.warning(
                f"Agent {original_request.agent_id}: No pending tool request found for response, "
                "using fallback text handling",
            )
            human_response_msg = ChatMessage(
                role=Role.USER,
                text=f"Human response to '{original_request.prompt}': {response_text}",
                author_name="human",
            )
            self._chat_history.append(human_response_msg)

            # Create a response message indicating human input was received
            agent_response_msg = ChatMessage(
                role=Role.ASSISTANT,
                text=f"Received human input for: {original_request.prompt}. Continuing with the task.",
                author_name=original_request.agent_id,
            )
            self._chat_history.append(agent_response_msg)
            await context.send_message(_MagenticResponseMessage(body=agent_response_msg))

    async def _emit_agent_delta_event(
        self,
        ctx: WorkflowContext[Any, Any],
        update: AgentRunResponseUpdate,
    ) -> None:
        # Add metadata to identify this as an agent streaming update
        props = update.additional_properties
        if props is None:
            props = {}
            update.additional_properties = props
        props["magentic_event_type"] = MAGENTIC_EVENT_TYPE_AGENT_DELTA
        props["agent_id"] = self._agent_id

        # Emit AgentRunUpdateEvent with the agent response update
        await ctx.add_event(AgentRunUpdateEvent(executor_id=self._agent_id, data=update))

    async def _emit_agent_message_event(
        self,
        ctx: WorkflowContext[Any, Any],
        message: ChatMessage,
    ) -> None:
        # Agent message completion is already communicated via streaming updates
        # No additional event needed
        pass

    async def _invoke_agent(
        self,
        ctx: WorkflowContext[_MagenticResponseMessage, AgentRunResponse],
    ) -> ChatMessage | None:
        """Invoke the wrapped agent and return a response.

        This method streams the agent's response updates, collects them into an
        AgentRunResponse, and handles any human input requests (tool approvals).

        Note:
            If multiple user input requests are present in the agent's response,
            only the first one is processed. A warning is logged and subsequent
            requests are ignored. This is a current limitation of the single-request
            pending state architecture.

        Returns:
            ChatMessage with the agent's response, or None if waiting for human input.
        """
        logger.debug(f"Agent {self._agent_id}: Running with {len(self._chat_history)} messages")

        updates: list[AgentRunResponseUpdate] = []
        # The wrapped participant is guaranteed to be an BaseAgent when this is called.
        agent = cast("AgentProtocol", self._agent)
        async for update in agent.run_stream(messages=self._chat_history):  # type: ignore[attr-defined]
            updates.append(update)
            await self._emit_agent_delta_event(ctx, update)

        run_result: AgentRunResponse = AgentRunResponse.from_agent_run_response_updates(updates)

        # Handle human input requests (tool approval) - process one at a time
        if run_result.user_input_requests:
            if len(run_result.user_input_requests) > 1:
                logger.warning(
                    f"Agent {self._agent_id}: Multiple user input requests received "
                    f"({len(run_result.user_input_requests)}), processing only the first one"
                )

            user_input_request = run_result.user_input_requests[0]

            # Build a prompt from the request based on its type
            prompt: str
            context_text: str | None = None

            if isinstance(user_input_request, FunctionApprovalRequestContent):
                fn_call = user_input_request.function_call
                prompt = f"Approve function call: {fn_call.name}"
                if fn_call.arguments:
                    context_text = f"Arguments: {fn_call.arguments}"
            else:
                # Fallback for unknown request types
                request_type = type(user_input_request).__name__
                prompt = f"Agent {self._agent_id} requires human input ({request_type})"
                logger.warning(f"Agent {self._agent_id}: Unrecognized user input request type: {request_type}")

            # Store the original FunctionApprovalRequestContent for later use
            self._pending_tool_request = user_input_request

            # Create and send the human intervention request for tool approval
            request = _MagenticHumanInterventionRequest(
                kind=MagenticHumanInterventionKind.TOOL_APPROVAL,
                agent_id=self._agent_id,
                prompt=prompt,
                context=context_text,
                conversation_snapshot=list(self._chat_history[-5:]),
            )
            self._pending_human_input_request = request
            await ctx.request_info(request, _MagenticHumanInterventionReply)
            return None  # Signal that we're waiting for human input

        messages: list[ChatMessage] | None = None
        with contextlib.suppress(Exception):
            messages = list(run_result.messages)  # type: ignore[assignment]
        if messages and len(messages) > 0:
            last: ChatMessage = messages[-1]
            author = last.author_name or self._agent_id
            role: Role = last.role if last.role else Role.ASSISTANT
            text = last.text or ""
            msg = ChatMessage(role=role, text=text, author_name=author)
            await self._emit_agent_message_event(ctx, msg)
            return msg

        msg = ChatMessage(
            role=Role.ASSISTANT,
            text=f"Agent {self._agent_id}: No output produced",
            author_name=self._agent_id,
        )
        await self._emit_agent_message_event(ctx, msg)
        return msg


# endregion Magentic Executors

# region Magentic Workflow Builder


class MagenticBuilder:
    """Fluent builder for creating Magentic One multi-agent orchestration workflows.

    Magentic One workflows use an LLM-powered manager to coordinate multiple agents through
    dynamic task planning, progress tracking, and adaptive replanning. The manager creates
    plans, selects agents, monitors progress, and determines when to replan or complete.

    The builder provides a fluent API for configuring participants, the manager, optional
    plan review, checkpointing, and event callbacks.

    Usage:

    .. code-block:: python

        from agent_framework import MagenticBuilder, StandardMagenticManager
        from azure.ai.projects.aio import AIProjectClient

        # Create manager with LLM client
        project_client = AIProjectClient.from_connection_string(...)
        chat_client = project_client.inference.get_chat_completions_client()

        # Build Magentic workflow with agents
        workflow = (
            MagenticBuilder()
            .participants(researcher=research_agent, writer=writing_agent, coder=coding_agent)
            .with_standard_manager(chat_client=chat_client, max_round_count=20, max_stall_count=3)
            .with_plan_review(enable=True)
            .with_checkpointing(checkpoint_storage)
            .build()
        )

        # Execute workflow
        async for message in workflow.run("Research and write article about AI agents"):
            print(message.text)

    With custom manager:

    .. code-block:: python

        # Create custom manager subclass
        class MyCustomManager(MagenticManagerBase):
            async def plan(self, context: MagenticContext) -> ChatMessage:
                # Custom planning logic
                ...


        manager = MyCustomManager()
        workflow = MagenticBuilder().participants(agent1=agent1, agent2=agent2).with_standard_manager(manager).build()

    See Also:
        - :class:`MagenticManagerBase`: Base class for custom managers
        - :class:`StandardMagenticManager`: Default LLM-powered manager
        - :class:`MagenticContext`: Context object passed to manager methods
        - :class:`MagenticEvent`: Base class for workflow events
    """

    def __init__(self) -> None:
        self._participants: dict[str, AgentProtocol | Executor] = {}
        self._manager: MagenticManagerBase | None = None
        self._enable_plan_review: bool = False
        self._checkpoint_storage: CheckpointStorage | None = None
        self._enable_stall_intervention: bool = False

    def participants(self, **participants: AgentProtocol | Executor) -> Self:
        """Add participant agents or executors to the Magentic workflow.

        Participants are the agents that will execute tasks under the manager's direction.
        Each participant should have distinct capabilities that complement the team. The
        manager will select which participant to invoke based on the current plan and
        progress state.

        Args:
            **participants: Named agents or executors to add to the workflow. Names should
                be descriptive of the agent's role (e.g., researcher=research_agent).
                Accepts BaseAgent instances or custom Executor implementations.

        Returns:
            Self for method chaining

        Usage:

        .. code-block:: python

            workflow = (
                MagenticBuilder()
                .participants(
                    researcher=research_agent, writer=writing_agent, coder=coding_agent, reviewer=review_agent
                )
                .with_standard_manager(agent=manager_agent)
                .build()
            )

        Notes:
            - Participant names become part of the manager's context for selection
            - Agent descriptions (if available) are extracted and provided to the manager
            - Can be called multiple times to add participants incrementally
        """
        self._participants.update(participants)
        return self

    def with_plan_review(self, enable: bool = True) -> "MagenticBuilder":
        """Enable or disable human-in-the-loop plan review before task execution.

        When enabled, the workflow will pause after the manager generates the initial
        plan and emit a MagenticHumanInterventionRequest event with kind=PLAN_REVIEW.
        A human reviewer can then approve, request revisions, or reject the plan.
        The workflow continues only after approval.

        This is useful for:
        - High-stakes tasks requiring human oversight
        - Validating the manager's understanding of requirements
        - Catching hallucinations or unrealistic plans early
        - Educational scenarios where learners review AI planning

        Args:
            enable: Whether to require plan review (default True)

        Returns:
            Self for method chaining

        Usage:

        .. code-block:: python

            workflow = (
                MagenticBuilder()
                .participants(agent1=agent1)
                .with_standard_manager(agent=manager_agent)
                .with_plan_review(enable=True)
                .build()
            )

            # During execution, handle plan review
            async for event in workflow.run_stream("task"):
                if isinstance(event, RequestInfoEvent):
                    request = event.data
                    if isinstance(request, MagenticHumanInterventionRequest):
                        if request.kind == MagenticHumanInterventionKind.PLAN_REVIEW:
                            # Review plan and respond
                            reply = MagenticHumanInterventionReply(decision=MagenticHumanInterventionDecision.APPROVE)
                            await workflow.send_responses({event.request_id: reply})

        See Also:
            - :class:`MagenticHumanInterventionRequest`: Event emitted for review
            - :class:`MagenticHumanInterventionReply`: Response to send back
            - :class:`MagenticHumanInterventionDecision`: APPROVE/REVISE options
        """
        self._enable_plan_review = enable
        return self

    def with_human_input_on_stall(self, enable: bool = True) -> "MagenticBuilder":
        """Enable human intervention when the workflow detects a stall.

        When enabled, instead of automatically replanning when the workflow detects
        that agents are not making progress or are stuck in a loop, the workflow will
        pause and emit a MagenticStallInterventionRequest event. A human can then
        decide to continue, trigger replanning, or provide guidance.

        This is useful for:
        - Workflows where automatic replanning may not resolve the issue
        - Scenarios requiring human judgment about workflow direction
        - Debugging stuck workflows with human insight
        - Complex tasks where human guidance can help agents get back on track

        When stall detection triggers (based on max_stall_count), instead of calling
        _reset_and_replan automatically, the workflow will:
        1. Emit a MagenticHumanInterventionRequest with kind=STALL
        2. Wait for human response via send_responses_streaming
        3. Take action based on the human's decision (continue, replan, or guidance)

        Args:
            enable: Whether to enable stall intervention (default True)

        Returns:
            Self for method chaining

        Usage:

        .. code-block:: python

            workflow = (
                MagenticBuilder()
                .participants(agent1=agent1)
                .with_standard_manager(agent=manager_agent, max_stall_count=3)
                .with_human_input_on_stall(enable=True)
                .build()
            )

            # During execution, handle human intervention requests
            async for event in workflow.run_stream("task"):
                if isinstance(event, RequestInfoEvent):
                    if event.request_type is MagenticHumanInterventionRequest:
                        request = event.data
                        if request.kind == MagenticHumanInterventionKind.STALL:
                            print(f"Workflow stalled: {request.stall_reason}")
                            reply = MagenticHumanInterventionReply(
                                decision=MagenticHumanInterventionDecision.GUIDANCE,
                                comments="Focus on completing the current step first",
                            )
                            responses = {event.request_id: reply}
                            async for ev in workflow.send_responses_streaming(responses):
                                ...

        See Also:
            - :class:`MagenticHumanInterventionRequest`: Unified request type
            - :class:`MagenticHumanInterventionDecision`: Decision options
            - :meth:`with_standard_manager`: Configure max_stall_count for stall detection
        """
        self._enable_stall_intervention = enable
        return self

    def with_checkpointing(self, checkpoint_storage: CheckpointStorage) -> "MagenticBuilder":
        """Enable workflow state persistence using the provided checkpoint storage.

        Checkpointing allows workflows to be paused, resumed across process restarts,
        or recovered after failures. The entire workflow state including conversation
        history, task ledgers, and progress is persisted at key points.

        Args:
            checkpoint_storage: Storage backend for checkpoints (e.g., InMemoryCheckpointStorage,
                FileCheckpointStorage, or custom implementations)

        Returns:
            Self for method chaining

        Usage:

        .. code-block:: python

            from agent_framework import InMemoryCheckpointStorage

            storage = InMemoryCheckpointStorage()
            workflow = (
                MagenticBuilder()
                .participants(agent1=agent1)
                .with_standard_manager(agent=manager_agent)
                .with_checkpointing(storage)
                .build()
            )

            # First run
            thread_id = "task-123"
            async for msg in workflow.run("task", thread_id=thread_id):
                print(msg.text)

            # Resume from checkpoint
            async for msg in workflow.run("continue", thread_id=thread_id):
                print(msg.text)

        Notes:
            - Checkpoints are created after each significant state transition
            - Thread ID must be consistent across runs to resume properly
            - Storage implementations may have different persistence guarantees
        """
        self._checkpoint_storage = checkpoint_storage
        return self

    def with_standard_manager(
        self,
        manager: MagenticManagerBase | None = None,
        *,
        # Constructor args for StandardMagenticManager when manager is not provided
        agent: AgentProtocol | None = None,
        task_ledger: _MagenticTaskLedger | None = None,
        # Prompt overrides
        task_ledger_facts_prompt: str | None = None,
        task_ledger_plan_prompt: str | None = None,
        task_ledger_full_prompt: str | None = None,
        task_ledger_facts_update_prompt: str | None = None,
        task_ledger_plan_update_prompt: str | None = None,
        progress_ledger_prompt: str | None = None,
        final_answer_prompt: str | None = None,
        # Limits
        max_stall_count: int = 3,
        max_reset_count: int | None = None,
        max_round_count: int | None = None,
    ) -> Self:
        """Configure the workflow manager for task planning and agent coordination.

        The manager is responsible for creating plans, selecting agents, tracking progress,
        and deciding when to replan or complete. This method supports two usage patterns:

        1. **Provide existing manager**: Pass a pre-configured manager instance (custom
           or standard) for full control over behavior
        2. **Auto-create with agent**: Pass an agent to automatically create a
           StandardMagenticManager that uses the agent's configured instructions and
           options (temperature, seed, etc.)

        Args:
            manager: Pre-configured manager instance (StandardMagenticManager or custom
                MagenticManagerBase subclass). If provided, all other arguments are ignored.
            agent: Agent instance for generating plans and decisions. The agent's
                configured instructions and options (temperature, seed, etc.) will be
                applied.
            task_ledger: Optional custom task ledger implementation for specialized
                prompting or structured output requirements
            task_ledger_facts_prompt: Custom prompt template for extracting facts from
                task description
            task_ledger_plan_prompt: Custom prompt template for generating initial plan
            task_ledger_full_prompt: Custom prompt template for complete task ledger
                (facts + plan combined)
            task_ledger_facts_update_prompt: Custom prompt template for updating facts
                based on agent progress
            task_ledger_plan_update_prompt: Custom prompt template for replanning when
                needed
            progress_ledger_prompt: Custom prompt template for assessing progress and
                determining next actions
            final_answer_prompt: Custom prompt template for synthesizing final response
                when task is complete
            max_stall_count: Maximum consecutive rounds without progress before triggering
                replan (default 3). Set to 0 to disable stall detection.
            max_reset_count: Maximum number of complete resets allowed before failing.
                None means unlimited resets.
            max_round_count: Maximum total coordination rounds before stopping with
                partial result. None means unlimited rounds.

        Returns:
            Self for method chaining

        Raises:
            ValueError: If manager is None and agent is not provided.

        Usage with agent (recommended):

        .. code-block:: python

            from agent_framework import ChatAgent, ChatOptions
            from agent_framework.openai import OpenAIChatClient

            # Configure manager agent with specific options and instructions
            manager_agent = ChatAgent(
                name="Coordinator",
                chat_client=OpenAIChatClient(model_id="gpt-4o"),
                chat_options=ChatOptions(temperature=0.3, seed=42),
                instructions="Be concise and focus on accuracy",
            )

            workflow = (
                MagenticBuilder()
                .participants(agent1=agent1, agent2=agent2)
                .with_standard_manager(
                    agent=manager_agent,
                    max_round_count=20,
                    max_stall_count=3,
                )
                .build()
            )

        Usage with custom manager:

        .. code-block:: python

            class MyManager(MagenticManagerBase):
                async def plan(self, context: MagenticContext) -> ChatMessage:
                    # Custom planning logic
                    return ChatMessage(role=Role.ASSISTANT, text="...")


            manager = MyManager()
            workflow = MagenticBuilder().participants(agent1=agent1).with_standard_manager(manager).build()

        Usage with prompt customization:

        .. code-block:: python

            workflow = (
                MagenticBuilder()
                .participants(coder=coder_agent, reviewer=reviewer_agent)
                .with_standard_manager(
                    agent=manager_agent,
                    task_ledger_plan_prompt="Create a detailed step-by-step plan...",
                    progress_ledger_prompt="Assess progress and decide next action...",
                    max_stall_count=2,
                )
                .build()
            )

        Notes:
            - StandardMagenticManager uses structured LLM calls for all decisions
            - Custom managers can implement alternative selection strategies
            - Prompt templates support Jinja2-style variable substitution
            - Stall detection helps prevent infinite loops in stuck scenarios
            - The agent's instructions are used as system instructions for all manager prompts
        """
        if manager is not None:
            self._manager = manager
            return self

        if agent is None:
            raise ValueError("agent is required when manager is not provided: with_standard_manager(agent=...)")

        self._manager = StandardMagenticManager(
            agent=agent,
            task_ledger=task_ledger,
            task_ledger_facts_prompt=task_ledger_facts_prompt,
            task_ledger_plan_prompt=task_ledger_plan_prompt,
            task_ledger_full_prompt=task_ledger_full_prompt,
            task_ledger_facts_update_prompt=task_ledger_facts_update_prompt,
            task_ledger_plan_update_prompt=task_ledger_plan_update_prompt,
            progress_ledger_prompt=progress_ledger_prompt,
            final_answer_prompt=final_answer_prompt,
            max_stall_count=max_stall_count,
            max_reset_count=max_reset_count,
            max_round_count=max_round_count,
        )
        return self

    def build(self) -> Workflow:
        """Build a Magentic workflow with the orchestrator and all agent executors."""
        if not self._participants:
            raise ValueError("No participants added to Magentic workflow")

        if self._manager is None:
            raise ValueError("No manager configured. Call with_standard_manager(...) before build().")

        logger.info(f"Building Magentic workflow with {len(self._participants)} participants")

        # Create participant descriptions
        participant_descriptions: dict[str, str] = {}
        for name, participant in self._participants.items():
            fallback = f"Executor {name}" if isinstance(participant, Executor) else f"Agent {name}"
            participant_descriptions[name] = participant_description(participant, fallback)

        # Type narrowing: we already checked self._manager is not None above
        manager: MagenticManagerBase = self._manager  # type: ignore[assignment]
        enable_stall_intervention = self._enable_stall_intervention

        def _orchestrator_factory(wiring: _GroupChatConfig) -> Executor:
            return MagenticOrchestratorExecutor(
                manager=manager,
                participants=participant_descriptions,
                require_plan_signoff=self._enable_plan_review,
                enable_stall_intervention=enable_stall_intervention,
                executor_id="magentic_orchestrator",
            )

        def _participant_factory(
            spec: GroupChatParticipantSpec,
            wiring: _GroupChatConfig,
        ) -> _GroupChatParticipantPipeline:
            agent_executor = MagenticAgentExecutor(
                spec.participant,
                spec.name,
            )
            orchestrator = wiring.orchestrator
            if isinstance(orchestrator, MagenticOrchestratorExecutor):
                orchestrator.register_agent_executor(spec.name, agent_executor)
            return (agent_executor,)

        # Magentic provides its own orchestrator via custom factory, so no manager is needed
        group_builder = GroupChatBuilder(
            _orchestrator_factory=group_chat_orchestrator(_orchestrator_factory),
            _participant_factory=_participant_factory,
        ).participants(self._participants)

        if self._checkpoint_storage is not None:
            group_builder = group_builder.with_checkpointing(self._checkpoint_storage)

        return group_builder.build()

    def start_with_string(self, task: str) -> "MagenticWorkflow":
        """Build a Magentic workflow and return a wrapper with convenience methods for string tasks.

        Args:
            task: The task description as a string.

        Returns:
            A MagenticWorkflow wrapper that provides convenience methods for starting with strings.
        """
        return MagenticWorkflow(self.build(), task)

    def start_with_message(self, task: ChatMessage) -> "MagenticWorkflow":
        """Build a Magentic workflow and return a wrapper with convenience methods for ChatMessage tasks.

        Args:
            task: The task as a ChatMessage.

        Returns:
            A MagenticWorkflow wrapper that provides convenience methods.
        """
        return MagenticWorkflow(self.build(), task.text)

    def start_with(self, task: str | ChatMessage) -> "MagenticWorkflow":
        """Build a Magentic workflow and return a wrapper with convenience methods.

        Args:
            task: The task description as a string or ChatMessage.

        Returns:
            A MagenticWorkflow wrapper that provides convenience methods.
        """
        if isinstance(task, str):
            return self.start_with_string(task)
        return self.start_with_message(task)


# endregion Magentic Workflow Builder


# region Magentic Workflow


class MagenticWorkflow:
    """A wrapper around the base Workflow that provides convenience methods for Magentic workflows."""

    def __init__(self, workflow: Workflow, task_text: str | None = None):
        self._workflow = workflow
        self._task_text = task_text

    @property
    def workflow(self) -> Workflow:
        """Access the underlying workflow."""
        return self._workflow

    async def run_streaming_with_string(self, task_text: str) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow with a task string.

        Args:
            task_text: The task description as a string.

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """
        start_message = _MagenticStartMessage.from_string(task_text)
        async for event in self._workflow.run_stream(start_message):
            yield event

    async def run_streaming_with_message(self, task_message: ChatMessage) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow with a ChatMessage.

        Args:
            task_message: The task as a ChatMessage.

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """
        start_message = _MagenticStartMessage(task_message)
        async for event in self._workflow.run_stream(start_message):
            yield event

    async def run_stream(self, message: Any | None = None) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow with either a message object or the preset task string.

        Args:
            message: The message to send. If None and task_text was provided during construction,
                    uses the preset task string.

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """
        if message is None:
            if self._task_text is None:
                raise ValueError("No message provided and no preset task text available")
            message = _MagenticStartMessage.from_string(self._task_text)
        elif isinstance(message, str):
            message = _MagenticStartMessage.from_string(message)
        elif isinstance(message, (ChatMessage, list)):
            message = _MagenticStartMessage(message)  # type: ignore[arg-type]

        async for event in self._workflow.run_stream(message):
            yield event

    async def _validate_checkpoint_participants(
        self,
        checkpoint_id: str,
        checkpoint_storage: CheckpointStorage | None = None,
    ) -> None:
        """Ensure participant roster matches the checkpoint before attempting restoration."""
        orchestrator = next(
            (
                executor
                for executor in self._workflow.executors.values()
                if isinstance(executor, MagenticOrchestratorExecutor)
            ),
            None,
        )
        if orchestrator is None:
            return

        expected = getattr(orchestrator, "_participants", None)
        if not expected:
            return

        checkpoint: WorkflowCheckpoint | None = None
        if checkpoint_storage is not None:
            try:
                checkpoint = await checkpoint_storage.load_checkpoint(checkpoint_id)
            except Exception:  # pragma: no cover - best effort
                checkpoint = None

        if checkpoint is None:
            runner_context = getattr(self._workflow, "_runner_context", None)
            has_checkpointing = getattr(runner_context, "has_checkpointing", None)
            load_checkpoint = getattr(runner_context, "load_checkpoint", None)
            try:
                if callable(has_checkpointing) and has_checkpointing() and callable(load_checkpoint):
                    loaded_checkpoint = await load_checkpoint(checkpoint_id)  # type: ignore[misc]
                    if loaded_checkpoint is not None:
                        checkpoint = cast(WorkflowCheckpoint, loaded_checkpoint)
            except Exception:  # pragma: no cover - best effort
                checkpoint = None

        if checkpoint is None:
            return

        # At this point, checkpoint is guaranteed to be WorkflowCheckpoint
        executor_states = cast(dict[str, Any], checkpoint.shared_state.get(EXECUTOR_STATE_KEY, {}))
        orchestrator_id = getattr(orchestrator, "id", "")
        orchestrator_state = cast(Any, executor_states.get(orchestrator_id))
        if orchestrator_state is None:
            orchestrator_state = cast(Any, executor_states.get("magentic_orchestrator"))

        if not isinstance(orchestrator_state, dict):
            return

        orchestrator_state_dict = cast(dict[str, Any], orchestrator_state)
        context_payload = cast(Any, orchestrator_state_dict.get("magentic_context"))
        if not isinstance(context_payload, dict):
            return

        context_dict = cast(dict[str, Any], context_payload)
        restored_participants = cast(Any, context_dict.get("participant_descriptions"))
        if not isinstance(restored_participants, dict):
            return

        participants_dict = cast(dict[str, str], restored_participants)
        restored_names: set[str] = set(participants_dict.keys())
        expected_names = set(expected.keys())

        if restored_names == expected_names:
            return

        missing = ", ".join(sorted(expected_names - restored_names)) or "none"
        unexpected = ", ".join(sorted(restored_names - expected_names)) or "none"
        raise RuntimeError(
            "Magentic checkpoint restore failed: participant names do not match the checkpoint. "
            "Ensure MagenticBuilder.participants keys remain stable across runs. "
            f"Missing names: {missing}; unexpected names: {unexpected}."
        )

    async def run_with_string(self, task_text: str) -> WorkflowRunResult:
        """Run the workflow with a task string and return all events.

        Args:
            task_text: The task description as a string.

        Returns:
            WorkflowRunResult: All events generated during the workflow execution.
        """
        events: list[WorkflowEvent] = []
        async for event in self.run_streaming_with_string(task_text):
            events.append(event)
        return WorkflowRunResult(events)

    async def run_with_message(self, task_message: ChatMessage) -> WorkflowRunResult:
        """Run the workflow with a ChatMessage and return all events.

        Args:
            task_message: The task as a ChatMessage.

        Returns:
            WorkflowRunResult: All events generated during the workflow execution.
        """
        events: list[WorkflowEvent] = []
        async for event in self.run_streaming_with_message(task_message):
            events.append(event)
        return WorkflowRunResult(events)

    async def run(self, message: Any | None = None) -> WorkflowRunResult:
        """Run the workflow and return all events.

        Args:
            message: The message to send. If None and task_text was provided during construction,
                    uses the preset task string.

        Returns:
            WorkflowRunResult: All events generated during the workflow execution.
        """
        events: list[WorkflowEvent] = []
        async for event in self.run_stream(message):
            events.append(event)
        return WorkflowRunResult(events)

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to the underlying workflow."""
        return getattr(self._workflow, name)


# endregion Magentic Workflow

# Public aliases for unified human intervention types
MagenticHumanInterventionRequest = _MagenticHumanInterventionRequest
MagenticHumanInterventionReply = _MagenticHumanInterventionReply

# Backward compatibility aliases (deprecated)
# Old aliases - point to unified types for compatibility
MagenticHumanInputRequest = _MagenticHumanInterventionRequest  # type: ignore
MagenticStallInterventionRequest = _MagenticHumanInterventionRequest  # type: ignore
MagenticStallInterventionReply = _MagenticHumanInterventionReply  # type: ignore
MagenticStallInterventionDecision = MagenticHumanInterventionDecision  # type: ignore
