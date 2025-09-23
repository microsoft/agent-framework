# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import json
import logging
import re
import sys
from abc import ABC, abstractmethod
from collections.abc import AsyncIterable, Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Annotated, Any, Literal, Protocol, TypeVar, Union, cast
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from agent_framework import (
    AgentProtocol,
    AgentRunResponse,
    AgentRunResponseUpdate,
    ChatClientProtocol,
    ChatMessage,
    FunctionCallContent,
    FunctionResultContent,
    Role,
)
from agent_framework._agents import BaseAgent
from agent_framework._pydantic import AFBaseModel

from ._events import WorkflowEvent
from ._executor import Executor, RequestInfoMessage, RequestResponse, handler
from ._workflow import Workflow, WorkflowBuilder, WorkflowRunResult
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

logger = logging.getLogger(__name__)

# Consistent author name for messages produced by the Magentic manager/orchestrator
MAGENTIC_MANAGER_NAME = "magentic_manager"

# Optional kinds for generic orchestrator message callback
ORCH_MSG_KIND_USER_TASK = "user_task"
ORCH_MSG_KIND_TASK_LEDGER = "task_ledger"
# Newly surfaced kinds for unified callback consumers
ORCH_MSG_KIND_INSTRUCTION = "instruction"
ORCH_MSG_KIND_NOTICE = "notice"

# region Unified callback API (developer-facing)


class MagenticCallbackMode(str, Enum):
    """Controls whether agent deltas are surfaced via on_event.

    STREAMING: emit AgentDeltaEvent chunks and a final AgentMessageEvent.
    NON_STREAMING: suppress deltas and only emit AgentMessageEvent.
    """

    STREAMING = "streaming"
    NON_STREAMING = "non_streaming"


@dataclass
class MagenticOrchestratorMessageEvent:
    source: Literal["orchestrator"] = "orchestrator"
    orchestrator_id: str = ""
    message: ChatMessage | None = None
    # Kind values include: user_task, task_ledger, instruction, notice
    kind: str = ""


@dataclass
class MagenticAgentDeltaEvent:
    source: Literal["agent"] = "agent"
    agent_id: str | None = None
    text: str | None = None
    # Optional: function/tool streaming payloads
    function_call_id: str | None = None
    function_call_name: str | None = None
    function_call_arguments: Any | None = None
    function_result_id: str | None = None
    function_result: Any | None = None
    role: Role | None = None


@dataclass
class MagenticAgentMessageEvent:
    source: Literal["agent"] = "agent"
    agent_id: str = ""
    message: ChatMessage | None = None


@dataclass
class MagenticFinalResultEvent:
    source: Literal["workflow"] = "workflow"
    message: ChatMessage | None = None


MagenticCallbackEvent = Union[
    MagenticOrchestratorMessageEvent,
    MagenticAgentDeltaEvent,
    MagenticAgentMessageEvent,
    MagenticFinalResultEvent,
]


class CallbackSink(Protocol):
    async def __call__(self, event: MagenticCallbackEvent) -> None: ...


# endregion Unified callback API

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


@dataclass
class MagenticStartMessage:
    """A message to start a magentic workflow."""

    task: ChatMessage

    @classmethod
    def from_string(cls, task_text: str) -> "MagenticStartMessage":
        """Create a MagenticStartMessage from a simple string.

        Args:
            task_text: The task description as a string.

        Returns:
            A MagenticStartMessage with the string converted to a ChatMessage.
        """
        return cls(task=ChatMessage(role=Role.USER, text=task_text))


@dataclass
class MagenticRequestMessage:
    """A request message type for agents in a magentic workflow."""

    agent_name: str
    instruction: str = ""
    task_context: str = ""


@dataclass
class MagenticResponseMessage:
    """A response message type.

    When emitted by the orchestrator you can mark it as a broadcast to all agents,
    or target a specific agent by name.
    """

    body: ChatMessage
    target_agent: str | None = None  # deliver only to this agent if set
    broadcast: bool = False  # deliver to all agents if True


@dataclass
class MagenticPlanReviewRequest(RequestInfoMessage):
    """Human-in-the-loop request to review and optionally edit the plan before execution."""

    # Because RequestInfoMessage defines a default field (request_id),
    # subclass fields must also have defaults to satisfy dataclass rules.
    task_text: str = ""
    facts_text: str = ""
    plan_text: str = ""
    round_index: int = 0  # number of review rounds so far


class MagenticPlanReviewDecision(str, Enum):
    APPROVE = "approve"
    REVISE = "revise"


@dataclass
class MagenticPlanReviewReply:
    """Human reply to a plan review request."""

    decision: MagenticPlanReviewDecision
    edited_plan_text: str | None = None  # if supplied, becomes the new plan text verbatim
    comments: str | None = None  # guidance for replan if no edited text provided


class MagenticTaskLedger(AFBaseModel):
    """Task ledger for the Standard Magentic manager."""

    facts: Annotated[ChatMessage, Field(description="The facts about the task.")]
    plan: Annotated[ChatMessage, Field(description="The plan for the task.")]


class MagenticProgressLedgerItem(AFBaseModel):
    """A progress ledger item."""

    reason: str
    answer: str | bool


class MagenticProgressLedger(AFBaseModel):
    """A progress ledger for tracking workflow progress."""

    is_request_satisfied: MagenticProgressLedgerItem
    is_in_loop: MagenticProgressLedgerItem
    is_progress_being_made: MagenticProgressLedgerItem
    next_speaker: MagenticProgressLedgerItem
    instruction_or_question: MagenticProgressLedgerItem


class MagenticContext(AFBaseModel):
    """Context for the Magentic manager."""

    task: Annotated[ChatMessage, Field(description="The task to be completed.")]
    chat_history: Annotated[list[ChatMessage], Field(description="The chat history to track conversation.")] = Field(
        default_factory=_new_chat_history
    )
    participant_descriptions: Annotated[
        dict[str, str], Field(description="The descriptions of the participants in the workflow.")
    ]
    round_count: Annotated[int, Field(description="The number of rounds completed.")] = 0
    stall_count: Annotated[int, Field(description="The number of stalls detected.")] = 0
    reset_count: Annotated[int, Field(description="The number of resets detected.")] = 0

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


TModel = TypeVar("TModel", bound=AFBaseModel)


def _pd_validate(model: type[TModel], data: dict[str, Any]) -> TModel:
    """Validate against a Pydantic model and return a typed instance."""
    return model.model_validate(data)  # type: ignore[attr-defined]


# endregion Utilities

# region Magentic Manager


class MagenticManagerBase(AFBaseModel, ABC):
    """Base class for the Magentic One manager."""

    max_stall_count: Annotated[int, Field(description="Max number of stalls before a reset.", ge=0)] = 3
    max_reset_count: Annotated[int | None, Field(description="Max number of resets allowed.", ge=0)] = None
    max_round_count: Annotated[int | None, Field(description="Max number of agent responses allowed.", gt=0)] = None

    # Base prompt surface for type safety; concrete managers may override with a str field
    task_ledger_full_prompt: str = ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT

    @abstractmethod
    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Create a plan for the task."""
        ...

    @abstractmethod
    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Replan for the task."""
        ...

    @abstractmethod
    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
        """Create a progress ledger."""
        ...

    @abstractmethod
    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        """Prepare the final answer."""
        ...


class StandardMagenticManager(MagenticManagerBase):
    """Standard Magentic manager that performs real LLM calls via a ChatAgent.

    The manager constructs prompts that mirror the original Magentic One orchestration:
    - Facts gathering
    - Plan creation
    - Progress ledger in JSON
    - Facts update and plan update on reset
    - Final answer synthesis
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    chat_client: ChatClientProtocol
    task_ledger: MagenticTaskLedger | None = None
    instructions: str | None = None

    # Prompts may be overridden if needed
    task_ledger_facts_prompt: str = ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT
    task_ledger_plan_prompt: str = ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT
    task_ledger_full_prompt: str = ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT
    task_ledger_facts_update_prompt: str = ORCHESTRATOR_TASK_LEDGER_FACTS_UPDATE_PROMPT
    task_ledger_plan_update_prompt: str = ORCHESTRATOR_TASK_LEDGER_PLAN_UPDATE_PROMPT
    progress_ledger_prompt: str = ORCHESTRATOR_PROGRESS_LEDGER_PROMPT
    final_answer_prompt: str = ORCHESTRATOR_FINAL_ANSWER_PROMPT

    progress_ledger_retry_count: int = Field(default=3)

    def __init__(
        self,
        chat_client: ChatClientProtocol,
        task_ledger: MagenticTaskLedger | None = None,
        *,
        instructions: str | None = None,
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
            chat_client: The chat client to use for LLM calls.
            instructions: Instructions for the orchestrator agent.
            task_ledger: Optional task ledger for managing task state.
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
        args: dict[str, Any] = {
            "chat_client": chat_client,
            "instructions": instructions,
            "max_stall_count": max_stall_count,
            "max_reset_count": max_reset_count,
            "max_round_count": max_round_count,
        }

        # Optional prompt overrides
        if task_ledger_facts_prompt is not None:
            args["task_ledger_facts_prompt"] = task_ledger_facts_prompt
        if task_ledger_plan_prompt is not None:
            args["task_ledger_plan_prompt"] = task_ledger_plan_prompt
        if task_ledger_full_prompt is not None:
            args["task_ledger_full_prompt"] = task_ledger_full_prompt
        if task_ledger_facts_update_prompt is not None:
            args["task_ledger_facts_update_prompt"] = task_ledger_facts_update_prompt
        if task_ledger_plan_update_prompt is not None:
            args["task_ledger_plan_update_prompt"] = task_ledger_plan_update_prompt
        if progress_ledger_prompt is not None:
            args["progress_ledger_prompt"] = progress_ledger_prompt
        if final_answer_prompt is not None:
            args["final_answer_prompt"] = final_answer_prompt
        if progress_ledger_retry_count is not None:
            args["progress_ledger_retry_count"] = progress_ledger_retry_count

        super().__init__(**args)

        if task_ledger is not None:
            self.task_ledger = task_ledger

    async def _complete(
        self,
        messages: list[ChatMessage],
        *,
        response_format: type[BaseModel] | None = None,
    ) -> ChatMessage:
        """Call the underlying ChatClientProtocol directly and return the last assistant message.

        If manager instructions are provided, they are injected as a SYSTEM message
        at the start of the request to guide the model consistently without needing
        an intermediate Agent wrapper.
        """
        # Prepend system instructions if present
        request_messages: list[ChatMessage] = []
        if self.instructions:
            request_messages.append(ChatMessage(role=Role.SYSTEM, text=self.instructions))
        request_messages.extend(messages)

        # Invoke the chat client non-streaming API
        response = await self.chat_client.get_response(request_messages, response_format=response_format)
        try:
            out_messages: list[ChatMessage] | None = list(response.messages)  # type: ignore[assignment]
        except Exception:
            out_messages = None

        if out_messages:
            last = out_messages[-1]
            return ChatMessage(
                role=last.role or Role.ASSISTANT,
                text=last.text or "",
                author_name=last.author_name or MAGENTIC_MANAGER_NAME,
            )

        # Fallback if no messages
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
        self.task_ledger = MagenticTaskLedger(facts=facts_msg, plan=plan_msg)

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
        self.task_ledger = MagenticTaskLedger(facts=updated_facts, plan=updated_plan)

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

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
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
            raw = await self._complete(
                [*magentic_context.chat_history, user_message],
                response_format=MagenticProgressLedger,
            )
            try:
                ledger_dict = _extract_json(raw.text)
                return _pd_validate(MagenticProgressLedger, ledger_dict)
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


# endregion Magentic Manager

# region Magentic Executors


class MagenticOrchestratorExecutor(Executor):
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

    def __init__(
        self,
        manager: MagenticManagerBase,
        participants: dict[str, str],
        result_callback: Callable[[ChatMessage], Awaitable[None]] | None = None,
        agent_response_callback: Callable[[str, ChatMessage], Awaitable[None]] | None = None,
        streaming_agent_response_callback: Callable[[str, AgentRunResponseUpdate, bool], Awaitable[None]] | None = None,
        *,
        message_callback: Callable[[str, ChatMessage, str], Awaitable[None]] | None = None,
        require_plan_signoff: bool = False,
        max_plan_review_rounds: int = 10,
        executor_id: str | None = None,
    ) -> None:
        """Initializes a new instance of the MagenticOrchestratorExecutor.

        Args:
            manager: The Magentic manager instance.
            participants: A dictionary of participant IDs to their names.
            result_callback: An optional callback for handling final results.
            message_callback: An optional generic callback for orchestrator-emitted messages. The third
                argument is a kind string, e.g., ORCH_MSG_KIND_USER_TASK or ORCH_MSG_KIND_TASK_LEDGER.
            agent_response_callback: An optional callback for handling agent responses.
            streaming_agent_response_callback: An optional callback for handling streaming agent responses.
            require_plan_signoff: Whether to require plan sign-off from a human.
            max_plan_review_rounds: The maximum number of plan review rounds.
            executor_id: An optional executor ID.
        """
        super().__init__(executor_id or f"magentic_orchestrator_{uuid4().hex[:8]}")
        self._manager = manager
        self._participants = participants
        self._result_callback = result_callback
        self._message_callback = message_callback
        self._agent_response_callback = agent_response_callback
        self._streaming_agent_response_callback = streaming_agent_response_callback
        self._context = None
        self._task_ledger = None
        self._require_plan_signoff = require_plan_signoff
        self._plan_review_round = 0
        self._max_plan_review_rounds = max_plan_review_rounds
        self._inner_loop_lock = asyncio.Lock()
        # Registry of agent executors for internal coordination (e.g., resets)
        self._agent_executors = {}
        # Terminal state marker to stop further processing after completion/limits
        self._terminated = False

    def register_agent_executor(self, name: str, executor: "MagenticAgentExecutor") -> None:
        """Register an agent executor for internal control (no messages)."""
        self._agent_executors[name] = executor

    @handler
    async def handle_start_message(
        self,
        message: MagenticStartMessage,
        context: WorkflowContext[
            MagenticResponseMessage | MagenticRequestMessage | MagenticPlanReviewRequest, ChatMessage
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
        # Record the original user task in orchestrator context (no broadcast)
        self._context.chat_history.append(message.task)
        # Non-streaming callback for the orchestrator receipt of the task
        if self._message_callback:
            with contextlib.suppress(Exception):
                await self._message_callback(self.id, message.task, ORCH_MSG_KIND_USER_TASK)

        # Initial planning using the manager with real model calls
        self._task_ledger = await self._manager.plan(self._context.model_copy(deep=True))

        # If a human must sign off, ask now and return. The response handler will resume.
        if self._require_plan_signoff:
            await self._send_plan_review_request(context)
            return

        # Add task ledger to conversation history
        self._context.chat_history.append(self._task_ledger)

        logger.debug("Task ledger created.")

        if self._message_callback:
            with contextlib.suppress(Exception):
                await self._message_callback(self.id, self._task_ledger, ORCH_MSG_KIND_TASK_LEDGER)

        # Start the inner loop
        ctx2 = cast(
            WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
            context,
        )
        await self._run_inner_loop(ctx2)

    @handler
    async def handle_response_message(
        self,
        message: MagenticResponseMessage,
        context: WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
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

    @handler
    async def handle_plan_review_response(
        self,
        response: RequestResponse[MagenticPlanReviewRequest, MagenticPlanReviewReply],
        context: WorkflowContext[
            # may broadcast ledger next, or ask for another round of review
            MagenticResponseMessage | MagenticRequestMessage | MagenticPlanReviewRequest, ChatMessage
        ],
    ) -> None:
        if getattr(self, "_terminated", False):
            return
        if self._context is None:
            return

        human = response.data
        if human is None:
            # Defensive fallback: treat as revise with empty comments
            human = MagenticPlanReviewReply(decision=MagenticPlanReviewDecision.REVISE, comments="")

        if human.decision == MagenticPlanReviewDecision.APPROVE:
            # Close the review loop on approval (no further plan review requests this run)
            self._require_plan_signoff = False
            # If the user supplied an edited plan, adopt it
            if human.edited_plan_text:
                # Update the manager's internal ledger and rebuild the combined message
                mgr_ledger = getattr(self._manager, "task_ledger", None)
                if mgr_ledger is not None:
                    mgr_ledger.plan.text = human.edited_plan_text
                team_text = _team_block(self._participants)
                combined = self._manager.task_ledger_full_prompt.format(
                    task=self._context.task.text,
                    team=team_text,
                    facts=(mgr_ledger.facts.text if mgr_ledger else ""),
                    plan=human.edited_plan_text,
                )
                self._task_ledger = ChatMessage(
                    role=Role.ASSISTANT,
                    text=combined,
                    author_name=MAGENTIC_MANAGER_NAME,
                )
            # If approved with comments but no edited text, apply comments via replan and proceed (no extra review)
            elif human.comments:
                # Record the human feedback for grounding
                self._context.chat_history.append(
                    ChatMessage(role=Role.USER, text=f"Human plan feedback: {human.comments}")
                )
                # Ask the manager to replan based on comments; proceed immediately
                self._task_ledger = await self._manager.replan(self._context.model_copy(deep=True))

            # Record the signed-off plan (no broadcast)
            if self._task_ledger:
                self._context.chat_history.append(self._task_ledger)
                if self._message_callback:
                    with contextlib.suppress(Exception):
                        await self._message_callback(self.id, self._task_ledger, ORCH_MSG_KIND_TASK_LEDGER)

            # Enter the normal coordination loop
            ctx2 = cast(
                WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
                context,
            )
            await self._run_inner_loop(ctx2)
            return

        # Otherwise, REVISION round
        self._plan_review_round += 1
        if self._plan_review_round > self._max_plan_review_rounds:
            logger.warning("Magentic Orchestrator: Max plan review rounds reached. Proceeding with current plan.")
            # Stop any further plan review requests for the rest of this run
            self._require_plan_signoff = False
            # Add a clear note to the conversation so users know review is closed
            notice = ChatMessage(
                role=Role.ASSISTANT,
                text=(
                    "Plan review closed after max rounds. Proceeding with the current plan and will no longer "
                    "prompt for plan approval."
                ),
                author_name=MAGENTIC_MANAGER_NAME,
            )
            self._context.chat_history.append(notice)
            if self._message_callback:
                with contextlib.suppress(Exception):
                    await self._message_callback(self.id, notice, ORCH_MSG_KIND_NOTICE)
            if self._task_ledger:
                self._context.chat_history.append(self._task_ledger)
                # No further review requests; proceed directly into coordination
            ctx2 = cast(
                WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
                context,
            )
            await self._run_inner_loop(ctx2)
            return

        # If the user provided an edited plan, adopt it directly and ask them to confirm once more
        if human.edited_plan_text:
            mgr_ledger2 = getattr(self._manager, "task_ledger", None)
            if mgr_ledger2 is not None:
                mgr_ledger2.plan.text = human.edited_plan_text
            # Rebuild combined message for preview in the next review request
            team_text = _team_block(self._participants)
            combined = self._manager.task_ledger_full_prompt.format(
                task=self._context.task.text,
                team=team_text,
                facts=(mgr_ledger2.facts.text if mgr_ledger2 else ""),
                plan=human.edited_plan_text,
            )
            self._task_ledger = ChatMessage(role=Role.ASSISTANT, text=combined, author_name=MAGENTIC_MANAGER_NAME)
            await self._send_plan_review_request(context)
            return

        # Else pass comments into the chat history and replan with the manager
        if human.comments:
            self._context.chat_history.append(
                ChatMessage(role=Role.USER, text=f"Human plan feedback: {human.comments}")
            )

        # Ask the manager to replan; this only adjusts the plan stage, not a full reset
        self._task_ledger = await self._manager.replan(self._context.model_copy(deep=True))
        await self._send_plan_review_request(context)

    async def _run_outer_loop(
        self,
        context: WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
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
        if self._task_ledger and self._message_callback:
            with contextlib.suppress(Exception):
                await self._message_callback(self.id, self._task_ledger, ORCH_MSG_KIND_TASK_LEDGER)

        # Start inner loop
        await self._run_inner_loop(context)

    async def _run_inner_loop(
        self,
        context: WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
    ) -> None:
        """Run the inner orchestration loop. Coordination phase. Serialized with a lock."""
        if self._context is None or self._task_ledger is None:
            raise RuntimeError("Context or task ledger not initialized")
        async with self._inner_loop_lock:
            await self._run_inner_loop_locked(context)

    async def _run_inner_loop_locked(
        self,
        context: WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
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
        logger.info("Magentic Orchestrator: Inner loop - round %s", ctx.round_count)

        # Create progress ledger using the manager
        try:
            current_progress_ledger = await self._manager.create_progress_ledger(ctx.model_copy(deep=True))
        except Exception as ex:
            logger.warning("Magentic Orchestrator: Progress ledger creation failed, triggering reset: %s", ex)
            await self._reset_and_replan(context)
            return

        logger.debug(
            "Progress evaluation: satisfied=%s, next=%s",
            current_progress_ledger.is_request_satisfied.answer,
            current_progress_ledger.next_speaker.answer,
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
            logger.info("Magentic Orchestrator: Stalling detected. Resetting and replanning")
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
            logger.warning("Invalid next speaker: %s", next_speaker_value)
            await self._prepare_final_answer(context)
            return

        # Add instruction to conversation (assistant guidance)
        instruction_msg = ChatMessage(
            role=Role.ASSISTANT,
            text=str(instruction),
            author_name=MAGENTIC_MANAGER_NAME,
        )
        ctx.chat_history.append(instruction_msg)
        # Surface instruction message to observers
        if self._message_callback:
            with contextlib.suppress(Exception):
                await self._message_callback(self.id, instruction_msg, ORCH_MSG_KIND_INSTRUCTION)

        # Determine the selected agent's executor id
        target_executor_id = f"agent_{next_speaker_value}"

        # Request specific agent to respond
        logger.debug("Magentic Orchestrator: Requesting %s to respond", next_speaker_value)
        await context.send_message(
            MagenticRequestMessage(
                agent_name=next_speaker_value,
                instruction=str(instruction),
                task_context=ctx.task.text,
            ),
            target_id=target_executor_id,
        )

    async def _reset_and_replan(
        self,
        context: WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
    ) -> None:
        """Reset context and replan."""
        if self._context is None:
            return

        logger.info("Magentic Orchestrator: Resetting and replanning")

        # Reset context
        self._context.reset()

        # Replan
        self._task_ledger = await self._manager.replan(self._context.model_copy(deep=True))

        # Internally reset all registered agent executors (no handler/messages involved)
        for agent in self._agent_executors.values():
            with contextlib.suppress(Exception):
                agent.reset()

        # Restart outer loop
        await self._run_outer_loop(context)

    async def _prepare_final_answer(
        self,
        context: WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
    ) -> None:
        """Prepare the final answer using the manager."""
        if self._context is None:
            return

        logger.info("Magentic Orchestrator: Preparing final answer")
        final_answer = await self._manager.prepare_final_answer(self._context.model_copy(deep=True))

        # Emit a completed event for the workflow
        await context.yield_output(final_answer)

        if self._result_callback:
            await self._result_callback(final_answer)

    async def _check_within_limits_or_complete(
        self,
        context: WorkflowContext[MagenticResponseMessage | MagenticRequestMessage, ChatMessage],
    ) -> bool:
        """Check if orchestrator is within operational limits."""
        if self._context is None:
            return False
        ctx = self._context

        hit_round_limit = self._manager.max_round_count is not None and ctx.round_count >= self._manager.max_round_count
        hit_reset_limit = self._manager.max_reset_count is not None and ctx.reset_count >= self._manager.max_reset_count

        if hit_round_limit or hit_reset_limit:
            limit_type = "round" if hit_round_limit else "reset"
            logger.error("Magentic Orchestrator: Max %s count reached", limit_type)

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
                await context.yield_output(partial_result)

                if self._result_callback:
                    await self._result_callback(partial_result)
            return False

        return True

    async def _send_plan_review_request(
        self,
        context: WorkflowContext[
            MagenticResponseMessage | MagenticRequestMessage | MagenticPlanReviewRequest, ChatMessage
        ],
    ) -> None:
        """Emit a PlanReviewRequest via RequestInfoExecutor."""
        # If plan sign-off is disabled (e.g., ran out of review rounds), do nothing
        if not self._require_plan_signoff:
            return
        ledger = getattr(self._manager, "task_ledger", None)
        facts_text = ledger.facts.text if ledger else ""
        plan_text = ledger.plan.text if ledger else ""
        task_text = self._context.task.text if self._context else ""

        req = MagenticPlanReviewRequest(
            task_text=task_text,
            facts_text=facts_text,
            plan_text=plan_text,
            round_index=self._plan_review_round,
        )
        await context.send_message(req)


class MagenticAgentExecutor(Executor):
    """Magentic agent executor that wraps an agent for participation in workflows.

    This executor handles:
    - Receiving task ledger broadcasts
    - Responding to specific agent requests
    - Resetting agent state when needed
    """

    def __init__(
        self,
        agent: AgentProtocol | Executor,
        agent_id: str,
        agent_response_callback: Callable[[str, ChatMessage], Awaitable[None]] | None = None,
        streaming_agent_response_callback: Callable[[str, AgentRunResponseUpdate, bool], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__(f"agent_{agent_id}")
        self._agent = agent
        self._agent_id = agent_id
        self._chat_history: list[ChatMessage] = []
        self._agent_response_callback = agent_response_callback
        self._streaming_agent_response_callback = streaming_agent_response_callback

    @handler
    async def handle_response_message(
        self, message: MagenticResponseMessage, context: WorkflowContext[MagenticResponseMessage]
    ) -> None:
        """Handle response message (task ledger broadcast)."""
        logger.debug("Agent %s: Received response message", self._agent_id)

        # Check if this message is intended for this agent
        if message.target_agent is not None and message.target_agent != self._agent_id and not message.broadcast:
            # Message is targeted to a different agent, ignore it
            logger.debug("Agent %s: Ignoring message targeted to %s", self._agent_id, message.target_agent)
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
        self, message: MagenticRequestMessage, context: WorkflowContext[MagenticResponseMessage]
    ) -> None:
        """Handle request to respond."""
        if message.agent_name != self._agent_id:
            return

        logger.info("Agent %s: Received request to respond", self._agent_id)

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
                response = ChatMessage(
                    role=Role.ASSISTANT,
                    text=f"{self._agent_id} is a workflow executor and cannot be invoked directly.",
                    author_name=self._agent_id,
                )
            else:
                # Invoke the agent
                response = await self._invoke_agent()
            self._chat_history.append(response)

            # Send response back to orchestrator
            await context.send_message(MagenticResponseMessage(body=response))

        except Exception as e:
            logger.warning("Agent %s invoke failed: %s", self._agent_id, e)
            # Fallback response
            response = ChatMessage(
                role=Role.ASSISTANT,
                text=f"Agent {self._agent_id}: Error processing request - {str(e)[:100]}",
            )
            self._chat_history.append(response)
            await context.send_message(MagenticResponseMessage(body=response))

    def reset(self) -> None:
        """Reset the internal chat history of the agent (internal operation)."""
        logger.debug("Agent %s: Resetting chat history", self._agent_id)
        self._chat_history.clear()

    async def _invoke_agent(self) -> ChatMessage:
        """Invoke the wrapped agent and return a response."""
        logger.debug(f"Agent {self._agent_id}: Running with {len(self._chat_history)} messages")

        updates: list[AgentRunResponseUpdate] = []
        # The wrapped participant is guaranteed to be an BaseAgent when this is called.
        agent = cast("AgentProtocol", self._agent)
        async for update in agent.run_stream(messages=self._chat_history):  # type: ignore[attr-defined]
            updates.append(update)
            if self._streaming_agent_response_callback is not None:
                with contextlib.suppress(Exception):
                    await self._streaming_agent_response_callback(
                        self._agent_id,
                        update,
                        False,
                    )

        run_result: AgentRunResponse = AgentRunResponse.from_agent_run_response_updates(updates)

        # mark final using last update if available
        if updates and self._streaming_agent_response_callback is not None:
            with contextlib.suppress(Exception):
                await self._streaming_agent_response_callback(self._agent_id, updates[-1], True)
        messages: list[ChatMessage] | None = None
        with contextlib.suppress(Exception):
            messages = list(run_result.messages)  # type: ignore[assignment]
        if messages and len(messages) > 0:
            last: ChatMessage = messages[-1]
            author = last.author_name or self._agent_id
            role: Role = last.role if last.role else Role.ASSISTANT
            text = last.text or str(last)
            msg = ChatMessage(role=role, text=text, author_name=author)
            if self._agent_response_callback is not None:
                with contextlib.suppress(Exception):
                    await self._agent_response_callback(self._agent_id, msg)
            return msg

        msg = ChatMessage(
            role=Role.ASSISTANT,
            text=f"Agent {self._agent_id}: No output produced",
            author_name=self._agent_id,
        )
        if self._agent_response_callback is not None:
            with contextlib.suppress(Exception):
                await self._agent_response_callback(self._agent_id, msg)
        return msg


# endregion Magentic Executors

# region Magentic Workflow Builder


class MagenticBuilder:
    """High-level builder for creating Magentic One workflows."""

    def __init__(self) -> None:
        self._participants: dict[str, AgentProtocol | Executor] = {}
        self._manager: MagenticManagerBase | None = None
        self._exception_callback: Callable[[Exception], None] | None = None
        self._result_callback: Callable[[ChatMessage], Awaitable[None]] | None = None
        # Orchestrator-emitted message callback: (orchestrator_id, message, kind)
        self._message_callback: Callable[[str, ChatMessage, str], Awaitable[None]] | None = None
        self._agent_response_callback: Callable[[str, ChatMessage], Awaitable[None]] | None = None
        self._agent_streaming_callback: Callable[[str, AgentRunResponseUpdate, bool], Awaitable[None]] | None = None
        self._enable_plan_review: bool = False
        # Unified callback wiring
        self._unified_callback: CallbackSink | None = None
        self._callback_mode: MagenticCallbackMode | None = None

    def participants(self, **participants: AgentProtocol | Executor) -> Self:
        """Add participants (agents) to the workflow."""
        self._participants.update(participants)
        return self

    def with_plan_review(self, enable: bool = True) -> "MagenticBuilder":
        """Require human sign-off on the plan before coordination begins."""
        self._enable_plan_review = enable
        return self

    def with_standard_manager(
        self,
        manager: MagenticManagerBase | None = None,
        *,
        # Constructor args for StandardMagenticManager when manager is not provided
        chat_client: ChatClientProtocol | None = None,
        task_ledger: MagenticTaskLedger | None = None,
        instructions: str | None = None,
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
        """Configure the Magentic manager.

        Usage patterns:
        - Provide an existing manager instance (recommended for custom or preconfigured managers):
            builder.with_standard_manager(my_manager)
        - Or pass explicit kwargs to construct a StandardMagenticManager for you:
            builder.with_standard_manager(chat_client=my_client, max_round_count=10, max_stall_count=3)

        Notes:
        - If ``manager`` is provided, it is used as-is (can be a StandardMagenticManager or any MagenticManagerBase).
        - If not provided, ``chat_client`` is required and a new StandardMagenticManager will be created
          with the provided options.
        """
        if manager is not None:
            self._manager = manager
            return self

        if chat_client is None:
            raise ValueError(
                "chat_client is required when manager is not provided: with_standard_manager(chat_client=...)"
            )

        self._manager = StandardMagenticManager(
            chat_client=chat_client,
            task_ledger=task_ledger,
            instructions=instructions,
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

    def on_exception(self, callback: Callable[[Exception], None]) -> Self:
        """Set the exception callback."""
        self._exception_callback = callback
        return self

    def on_result(self, callback: Callable[[ChatMessage], Awaitable[None]]) -> Self:
        """Set the result callback."""
        self._result_callback = callback
        return self

    def on_event(
        self, callback: CallbackSink, *, mode: MagenticCallbackMode = MagenticCallbackMode.NON_STREAMING
    ) -> Self:
        """Register a single sink for all workflow, orchestrator, and agent events.

        mode=STREAMING yields AgentDeltaEvent plus AgentMessageEvent at the end.
        mode=NON_STREAMING only yields AgentMessageEvent at the end (no deltas).
        """
        self._unified_callback = callback
        self._callback_mode = mode
        return self

    def build(self) -> "MagenticWorkflow":
        """Build a Magentic workflow with the orchestrator and all agent executors."""
        if not self._participants:
            raise ValueError("No participants added to Magentic workflow")

        if self._manager is None:
            raise ValueError("No manager configured. Call with_standard_manager(...) before build().")

        logger.info("Building Magentic workflow with %d participants", len(self._participants))

        # Create participant descriptions
        participant_descriptions: dict[str, str] = {}
        for name, participant in self._participants.items():
            if isinstance(participant, BaseAgent):
                description = getattr(participant, "description", None) or f"Agent {name}"
            else:
                description = f"Executor {name}"
            participant_descriptions[name] = description

        # If unified sink is provided, map it to legacy callback surfaces
        unified = self._unified_callback
        mode = self._callback_mode

        if unified is not None:
            prior_result = self._result_callback

            async def _on_result(msg: ChatMessage) -> None:
                with contextlib.suppress(Exception):
                    await unified(MagenticFinalResultEvent(message=msg))
                if prior_result is not None:
                    with contextlib.suppress(Exception):
                        await prior_result(msg)

            async def _on_orch(orch_id: str, msg: ChatMessage, kind: str) -> None:
                with contextlib.suppress(Exception):
                    await unified(MagenticOrchestratorMessageEvent(orchestrator_id=orch_id, message=msg, kind=kind))

            async def _on_agent_final(agent_id: str, message: ChatMessage) -> None:
                with contextlib.suppress(Exception):
                    await unified(MagenticAgentMessageEvent(agent_id=agent_id, message=message))

            async def _on_agent_delta(agent_id: str, update: AgentRunResponseUpdate, is_final: bool) -> None:
                if mode == MagenticCallbackMode.STREAMING:
                    # TODO(evmattso): Make sure we surface other non-text streaming items
                    # (or per-type events) and plumb through consumers.
                    chunk: str | None = getattr(update, "text", None)
                    if not chunk:
                        with contextlib.suppress(Exception):
                            contents = getattr(update, "contents", []) or []
                            chunk = "".join(getattr(c, "text", "") for c in contents) or None
                    if chunk:
                        with contextlib.suppress(Exception):
                            await unified(
                                MagenticAgentDeltaEvent(
                                    agent_id=agent_id,
                                    text=chunk,
                                    role=getattr(update, "role", None),
                                )
                            )
                    # Emit function call/result items if present on the update
                    with contextlib.suppress(Exception):
                        content_items = getattr(update, "contents", []) or []
                        for item in content_items:
                            if isinstance(item, FunctionCallContent):
                                await unified(
                                    MagenticAgentDeltaEvent(
                                        agent_id=agent_id,
                                        function_call_id=getattr(item, "call_id", None),
                                        function_call_name=getattr(item, "name", None),
                                        function_call_arguments=getattr(item, "arguments", None),
                                        role=getattr(update, "role", None),
                                    )
                                )
                            elif isinstance(item, FunctionResultContent):
                                await unified(
                                    MagenticAgentDeltaEvent(
                                        agent_id=agent_id,
                                        function_result_id=getattr(item, "call_id", None),
                                        function_result=getattr(item, "result", None),
                                        role=getattr(update, "role", None),
                                    )
                                )
                # final aggregation handled by _on_agent_final via agent_response_callback

            # Override delegates for orchestrator and agent callbacks
            self._result_callback = _on_result
            self._message_callback = _on_orch
            self._agent_response_callback = _on_agent_final
            self._agent_streaming_callback = _on_agent_delta if mode == MagenticCallbackMode.STREAMING else None

        # Create orchestrator executor
        orchestrator_executor = MagenticOrchestratorExecutor(
            manager=self._manager,
            participants=participant_descriptions,
            result_callback=self._result_callback,
            message_callback=self._message_callback,
            agent_response_callback=self._agent_response_callback,
            streaming_agent_response_callback=self._agent_streaming_callback,
            require_plan_signoff=self._enable_plan_review,
        )

        # Create workflow builder and set orchestrator as start
        workflow_builder = WorkflowBuilder().set_start_executor(orchestrator_executor)

        if self._enable_plan_review:
            from ._executor import RequestInfoExecutor

            request_info = RequestInfoExecutor(id="request_info")
            workflow_builder = (
                workflow_builder
                # Only route plan review asks to request_info
                .add_edge(
                    orchestrator_executor,
                    request_info,
                    condition=lambda msg: isinstance(msg, MagenticPlanReviewRequest),
                ).add_edge(request_info, orchestrator_executor)
            )

        def _route_to_agent(msg: object, *, agent_name: str) -> bool:
            """Route only messages meant for this agent.

            - MagenticRequestMessage -> only to the named agent
            - MagenticResponseMessage -> broadcast=True to all, or target_agent==agent_name
            Everything else (e.g., RequestInfoMessage) -> do not route to agents.
            """
            if isinstance(msg, MagenticRequestMessage):
                return msg.agent_name == agent_name
            if isinstance(msg, MagenticResponseMessage):
                return bool(getattr(msg, "broadcast", False)) or getattr(msg, "target_agent", None) == agent_name
            return False

        # Add agent executors and connect them
        for name, participant in self._participants.items():
            agent_executor = MagenticAgentExecutor(
                participant,
                name,
                agent_response_callback=self._agent_response_callback,
                streaming_agent_response_callback=self._agent_streaming_callback,
            )
            # Register for internal control (e.g., reset)
            orchestrator_executor.register_agent_executor(name, agent_executor)

            # Add bidirectional edges between orchestrator and agent
            def _cond(msg: object, _an: str = name) -> bool:
                return _route_to_agent(msg, agent_name=_an)

            workflow_builder = workflow_builder.add_edge(
                orchestrator_executor,
                agent_executor,
                condition=_cond,
            ).add_edge(agent_executor, orchestrator_executor)

        return MagenticWorkflow(workflow_builder.build())

    def start_with_string(self, task: str) -> "MagenticWorkflow":
        """Build a Magentic workflow and return a wrapper with convenience methods for string tasks.

        Args:
            task: The task description as a string.

        Returns:
            A MagenticWorkflow wrapper that provides convenience methods for starting with strings.
        """
        return MagenticWorkflow(self.build().workflow, task)

    def start_with_message(self, task: ChatMessage) -> "MagenticWorkflow":
        """Build a Magentic workflow and return a wrapper with convenience methods for ChatMessage tasks.

        Args:
            task: The task as a ChatMessage.

        Returns:
            A MagenticWorkflow wrapper that provides convenience methods.
        """
        return MagenticWorkflow(self.build().workflow, task.text)

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
        start_message = MagenticStartMessage.from_string(task_text)
        async for event in self._workflow.run_stream(start_message):
            yield event

    async def run_streaming_with_message(self, task_message: ChatMessage) -> AsyncIterable[WorkflowEvent]:
        """Run the workflow with a ChatMessage.

        Args:
            task_message: The task as a ChatMessage.

        Yields:
            WorkflowEvent: The events generated during the workflow execution.
        """
        start_message = MagenticStartMessage(task=task_message)
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
            message = MagenticStartMessage.from_string(self._task_text)
        elif isinstance(message, str):
            message = MagenticStartMessage.from_string(message)
        elif isinstance(message, ChatMessage):
            message = MagenticStartMessage(task=message)

        async for event in self._workflow.run_stream(message):
            yield event

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

    async def send_responses_streaming(self, responses: dict[str, Any]) -> AsyncIterable[WorkflowEvent]:
        """Forward responses to pending requests and stream resulting events.

        This delegates to the underlying Workflow implementation.
        """
        async for event in self._workflow.send_responses_streaming(responses):
            yield event

    async def send_responses(self, responses: dict[str, Any]) -> WorkflowRunResult:
        """Forward responses to pending requests and return all resulting events.

        This delegates to the underlying Workflow implementation.
        """
        return await self._workflow.send_responses(responses)

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to the underlying workflow."""
        return getattr(self._workflow, name)


# endregion Magentic Workflow
