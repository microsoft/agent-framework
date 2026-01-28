# Copyright (c) Microsoft. All rights reserved.

import asyncio
import contextlib
import json
import logging
import re
import sys
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar, TypeVar, cast, overload

from typing_extensions import Never

from agent_framework import (
    AgentProtocol,
    AgentResponse,
    ChatMessage,
    Role,
)

from ._agent_executor import AgentExecutor, AgentExecutorRequest, AgentExecutorResponse
from ._base_group_chat_orchestrator import (
    BaseGroupChatOrchestrator,
    GroupChatParticipantMessage,
    GroupChatRequestMessage,
    GroupChatResponseMessage,
    GroupChatWorkflowContext_T_Out,
    ParticipantRegistry,
)
from ._checkpoint import CheckpointStorage
from ._events import ExecutorEvent
from ._executor import Executor, handler
from ._model_utils import DictConvertible, encode_value
from ._request_info_mixin import response_handler
from ._workflow import Workflow
from ._workflow_builder import WorkflowBuilder
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 12):
    from typing import override  # type: ignore # pragma: no cover
else:
    from typing_extensions import override  # type: ignore # pragma: no cover
if sys.version_info >= (3, 11):
    from typing import Self  # type: ignore # pragma: no cover
else:
    from typing_extensions import Self  # type: ignore # pragma: no cover


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
class MagenticProgressLedgerItem(DictConvertible):
    """Internal: A progress ledger item."""

    reason: str
    answer: str | bool

    def to_dict(self) -> dict[str, Any]:
        return {"reason": self.reason, "answer": self.answer}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MagenticProgressLedgerItem":
        answer_value = data.get("answer")
        if not isinstance(answer_value, (str, bool)):
            answer_value = ""  # Default to empty string if not str or bool
        return cls(reason=data.get("reason", ""), answer=answer_value)


@dataclass
class MagenticProgressLedger(DictConvertible):
    """Internal: A progress ledger for tracking workflow progress."""

    is_request_satisfied: MagenticProgressLedgerItem
    is_in_loop: MagenticProgressLedgerItem
    is_progress_being_made: MagenticProgressLedgerItem
    next_speaker: MagenticProgressLedgerItem
    instruction_or_question: MagenticProgressLedgerItem

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_request_satisfied": self.is_request_satisfied.to_dict(),
            "is_in_loop": self.is_in_loop.to_dict(),
            "is_progress_being_made": self.is_progress_being_made.to_dict(),
            "next_speaker": self.next_speaker.to_dict(),
            "instruction_or_question": self.instruction_or_question.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MagenticProgressLedger":
        return cls(
            is_request_satisfied=MagenticProgressLedgerItem.from_dict(data.get("is_request_satisfied", {})),
            is_in_loop=MagenticProgressLedgerItem.from_dict(data.get("is_in_loop", {})),
            is_progress_being_made=MagenticProgressLedgerItem.from_dict(data.get("is_progress_being_made", {})),
            next_speaker=MagenticProgressLedgerItem.from_dict(data.get("next_speaker", {})),
            instruction_or_question=MagenticProgressLedgerItem.from_dict(data.get("instruction_or_question", {})),
        )


@dataclass
class MagenticContext(DictConvertible):
    """Context for the Magentic manager."""

    task: str
    chat_history: list[ChatMessage] = field(default_factory=_new_chat_history)
    participant_descriptions: dict[str, str] = field(default_factory=_new_participant_descriptions)
    round_count: int = 0
    stall_count: int = 0
    reset_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task,
            "chat_history": [_message_to_payload(msg) for msg in self.chat_history],
            "participant_descriptions": dict(self.participant_descriptions),
            "round_count": self.round_count,
            "stall_count": self.stall_count,
            "reset_count": self.reset_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MagenticContext":
        # Validate required fields
        # `task` is required
        task = data.get("task")
        if task is None or not isinstance(task, str):
            raise ValueError("MagenticContext requires a 'task' string field.")
        # `chat_history` is required
        chat_history_payload = data.get("chat_history", [])
        history: list[ChatMessage] = []
        for item in chat_history_payload:
            history.append(_message_from_payload(item))
        # `participant_descriptions` is required
        participant_descriptions = data.get("participant_descriptions")
        if not isinstance(participant_descriptions, dict) or not participant_descriptions:
            raise ValueError("MagenticContext requires a 'participant_descriptions' dictionary field.")
        if not all(isinstance(k, str) and isinstance(v, str) for k, v in participant_descriptions.items()):  # type: ignore
            raise ValueError("MagenticContext 'participant_descriptions' must be a dict of str to str.")

        return cls(
            task=task,
            chat_history=history,
            participant_descriptions=participant_descriptions,  # type: ignore
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
    async def create_progress_ledger(self, magentic_context: MagenticContext) -> MagenticProgressLedger:
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

    MANAGER_NAME: ClassVar[str] = "StandardMagenticManager"

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
        response: AgentResponse = await self._agent.run(messages)
        if not response.messages:
            raise RuntimeError("Agent returned no messages in response.")
        if len(response.messages) > 1:
            logger.warning("Agent returned multiple messages; using the last one.")

        return response.messages[-1]

    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Create facts and plan using the model, then render a combined task ledger as a single assistant message."""
        team_text = _team_block(magentic_context.participant_descriptions)

        # Gather facts
        facts_user = ChatMessage(
            role=Role.USER,
            text=self.task_ledger_facts_prompt.format(task=magentic_context.task),
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
            task=magentic_context.task,
            team=team_text,
            facts=facts_msg.text,
            plan=plan_msg.text,
        )
        return ChatMessage(role=Role.ASSISTANT, text=combined, author_name=MAGENTIC_MANAGER_NAME)

    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Update facts and plan when stalling or looping has been detected."""
        if self.task_ledger is None:
            raise RuntimeError("replan() called before plan(); call plan() once before requesting a replan.")

        team_text = _team_block(magentic_context.participant_descriptions)

        # Update facts
        facts_update_user = ChatMessage(
            role=Role.USER,
            text=self.task_ledger_facts_update_prompt.format(
                task=magentic_context.task, old_facts=self.task_ledger.facts.text
            ),
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
            task=magentic_context.task,
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
            task=magentic_context.task,
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
                return _coerce_model(MagenticProgressLedger, ledger_dict)
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
        prompt = self.final_answer_prompt.format(task=magentic_context.task)
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

# region Magentic Orchestrator


class MagenticResetSignal:
    """Signal to indicate that the Magentic workflow should reset.

    This signal can be raised within the orchestrator's inner loop to trigger
    a reset of the Magentic context, clearing chat history and resetting
    stall counts.
    """

    pass


class MagenticOrchestratorEventType(str, Enum):
    """Types of Magentic orchestrator events."""

    PLAN_CREATED = "plan_created"
    REPLANNED = "replanned"
    PROGRESS_LEDGER_UPDATED = "progress_ledger_updated"


@dataclass
class MagenticOrchestratorEvent(ExecutorEvent):
    """Base class for Magentic orchestrator events."""

    def __init__(
        self,
        executor_id: str,
        event_type: MagenticOrchestratorEventType,
        data: ChatMessage | MagenticProgressLedger,
    ) -> None:
        super().__init__(executor_id, data)
        self.event_type = event_type

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(executor_id={self.executor_id}, event_type={self.event_type})"


# region Request info related types


@dataclass
class MagenticPlanReviewResponse:
    """Response to a human plan review request.

    Attributes:
        review: List of messages containing feedback and suggested revisions. If empty,
            the plan is considered approved.
    """

    review: list[ChatMessage]

    @staticmethod
    def approve() -> "MagenticPlanReviewResponse":
        """Create an approval response."""
        return MagenticPlanReviewResponse(review=[])

    @staticmethod
    def revise(feedback: str | list[str] | ChatMessage | list[ChatMessage]) -> "MagenticPlanReviewResponse":
        """Create a revision response with feedback."""
        if isinstance(feedback, str):
            feedback = [ChatMessage(role=Role.USER, text=feedback)]
        elif isinstance(feedback, ChatMessage):
            feedback = [feedback]
        elif isinstance(feedback, list):
            feedback = [ChatMessage(role=Role.USER, text=item) if isinstance(item, str) else item for item in feedback]

        return MagenticPlanReviewResponse(review=feedback)


@dataclass
class MagenticPlanReviewRequest:
    """Request for human review of a proposed plan.

    Attributes:
        plan: The proposed plan message.
        current_progress: The current progress ledger, if available.
            During the initial plan review, this will be None. In subsequent
            reviews after replanning (due to stalls), this will contain the
            latest progress ledger that determined no progress had been made
            or the workflow was in a loop.
        is_stalled: Whether the workflow is currently stalled.
    """

    plan: ChatMessage
    current_progress: MagenticProgressLedger | None
    is_stalled: bool

    def approve(self) -> MagenticPlanReviewResponse:
        """Create an approval response."""
        return MagenticPlanReviewResponse.approve()

    def revise(self, feedback: str | list[str] | ChatMessage | list[ChatMessage]) -> MagenticPlanReviewResponse:
        """Create a revision response with feedback."""
        return MagenticPlanReviewResponse.revise(feedback)


# endregion Human Intervention Types


class MagenticOrchestrator(BaseGroupChatOrchestrator):
    """Magentic orchestrator that defines the workflow structure.

    This orchestrator manages the overall Magentic workflow in the following structure:

    1. Upon receiving the task (a list of messages), it creates the plan using the manager
    then runs the inner loop.
    2. The inner loop is distributed and implementation is decentralized. In the orchestrator,
    it is responsible for:
        - Creating the progress ledger using the manager.
        - Checking for task completion.
        - Detecting stalling or looping and triggering replanning if needed.
        - Sending requests to participants based on the progress ledger's next speaker.
        - Issue requests for human intervention if enabled and needed.
    3. The inner loop waits for responses from the selected participant, then continues the loop.
    4. The orchestrator breaks out of the inner loop when the replanning or final answer conditions are met.
    5. The outer loop handles replanning and reenters the inner loop.
    """

    def __init__(
        self,
        manager: MagenticManagerBase,
        participant_registry: ParticipantRegistry,
        *,
        require_plan_signoff: bool = False,
    ) -> None:
        """Initialize the Magentic orchestrator.

        Args:
            manager: The Magentic manager instance to use for planning and progress tracking.
            participant_registry: Registry of participants involved in the workflow.

        Keyword Args:
            require_plan_signoff: If True, requires human approval of the initial plan before proceeding.
        """
        super().__init__("magentic_orchestrator", participant_registry)
        self._manager = manager
        self._require_plan_signoff = require_plan_signoff

        # Task related state
        self._magentic_context: MagenticContext | None = None
        self._task_ledger: ChatMessage | None = None
        self._progress_ledger: MagenticProgressLedger | None = None

        # Termination related state
        self._terminated: bool = False
        self._max_rounds = manager.max_round_count

    @override
    async def _handle_messages(
        self,
        messages: list[ChatMessage],
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Handle the initial task messages to start the workflow."""
        if self._terminated:
            raise RuntimeError(
                "This Magentic workflow has already been completed. No further messages can be processed. "
                "Use the builder to create a new workflow instance to handle additional tasks."
            )

        if not messages:
            raise ValueError("Magentic orchestrator requires at least one message to start the workflow.")

        if len(messages) > 1:
            raise ValueError("Magentic only support a single task message to start the workflow.")

        if messages[0].text.strip() == "":
            raise ValueError("Magentic task message must contain non-empty text.")

        self._magentic_context = MagenticContext(
            task=messages[0].text,
            participant_descriptions=self._participant_registry.participants,
            chat_history=list(messages),
        )

        # Initial planning using the manager with real model calls
        self._task_ledger = await self._manager.plan(self._magentic_context.clone(deep=True))
        await ctx.add_event(
            MagenticOrchestratorEvent(
                executor_id=self.id,
                event_type=MagenticOrchestratorEventType.PLAN_CREATED,
                data=self._task_ledger,
            )
        )

        # If a human must sign off, ask now and return. The response handler will resume.
        if self._require_plan_signoff:
            await self._send_plan_review_request(cast(WorkflowContext, ctx))
            return

        # Add task ledger to conversation history
        self._magentic_context.chat_history.append(self._task_ledger)

        logger.debug("Task ledger created.")

        # Start the inner loop
        await self._run_inner_loop(ctx)

    @override
    async def _handle_response(
        self,
        response: AgentExecutorResponse | GroupChatResponseMessage,
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Handle a response message from a participant."""
        if self._magentic_context is None or self._task_ledger is None:
            raise RuntimeError("Context or task ledger not initialized")

        messages = self._process_participant_response(response)

        self._magentic_context.chat_history.extend(messages)

        # Broadcast participant messages to all participants for context, except
        # the participant that just responded
        participant = ctx.get_source_executor_id()
        await self._broadcast_messages_to_participants(
            messages,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatParticipantMessage], ctx),
            participants=[p for p in self._participant_registry.participants if p != participant],
        )

        await self._run_inner_loop(ctx)

    @response_handler
    async def handle_plan_review_response(
        self,
        original_request: MagenticPlanReviewRequest,
        response: MagenticPlanReviewResponse,
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Handle the human response to the plan review request.

        Logic:
        There are code paths which will trigger a plan review request to the human:
        - Initial plan creation if `require_plan_signoff` is True.
        - Potentially during the inner loop if stalling is detected (resetting and replanning).

        The human can either approve the plan or request revisions with comments.
        - If approved, proceed to run the outer loop, which simply adds the task ledger
          to the conversation and enters the inner loop.
        - If revision requested, append the review comments to the chat history,
          trigger replanning via the manager, emit a REPLANNED event, then run the outer loop.
        """
        if self._magentic_context is None or self._task_ledger is None:
            raise RuntimeError("Context or task ledger not initialized")

        # Case 1: Approved
        if len(response.review) == 0:
            logger.debug("Magentic Orchestrator: Plan review approved by human.")
            await self._run_outer_loop(ctx)
            return
        # Case 2: Revision requested
        logger.debug("Magentic Orchestrator: Plan review revision requested by human.")
        self._magentic_context.chat_history.extend(response.review)
        self._task_ledger = await self._manager.replan(self._magentic_context.clone(deep=True))
        await ctx.add_event(
            MagenticOrchestratorEvent(
                executor_id=self.id,
                event_type=MagenticOrchestratorEventType.REPLANNED,
                data=self._task_ledger,
            )
        )
        # Continue the review process by sending the new plan for review again until approved
        # We don't need to check if `_require_plan_signoff` is True here, since we are already
        # in the review process.
        await self._send_plan_review_request(cast(WorkflowContext, ctx), is_stalled=original_request.is_stalled)

    async def _send_plan_review_request(self, ctx: WorkflowContext, is_stalled: bool = False) -> None:
        """Send a human intervention request for plan review.

        The response will be handled in the response handler `handle_plan_review_response`.
        """
        if self._task_ledger is None:
            raise RuntimeError("No task ledger available for plan review request.")

        await ctx.request_info(
            MagenticPlanReviewRequest(
                plan=self._task_ledger,
                current_progress=self._progress_ledger,
                is_stalled=is_stalled,
            ),
            MagenticPlanReviewResponse,
        )

    async def _run_inner_loop(
        self,
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Run the inner orchestration loop. Coordination phase. Serialized with a lock."""
        if self._magentic_context is None or self._task_ledger is None:
            raise RuntimeError("Context or task ledger not initialized")

        await self._run_inner_loop_helper(ctx)

    async def _run_inner_loop_helper(
        self,
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Run inner loop with exclusive access."""
        # Narrow optional context for the remainder of this method
        if self._magentic_context is None:
            raise RuntimeError("Context not initialized")
        # Check limits first
        within_limits = await self._check_within_limits_or_complete(
            cast(WorkflowContext[Never, list[ChatMessage]], ctx)
        )
        if not within_limits:
            return

        self._magentic_context.round_count += 1
        self._increment_round()
        logger.debug(f"Magentic Orchestrator: Inner loop - round {self._round_index}")

        # Create progress ledger using the manager
        try:
            self._progress_ledger = await self._manager.create_progress_ledger(self._magentic_context.clone(deep=True))
        except Exception as ex:
            logger.warning(f"Magentic Orchestrator: Progress ledger creation failed, triggering reset: {ex}")
            await self._reset_and_replan(ctx)
            return

        await ctx.add_event(
            MagenticOrchestratorEvent(
                executor_id=self.id,
                event_type=MagenticOrchestratorEventType.PROGRESS_LEDGER_UPDATED,
                data=self._progress_ledger,
            )
        )

        logger.debug(
            f"Progress evaluation: satisfied={self._progress_ledger.is_request_satisfied.answer}, "
            f"next={self._progress_ledger.next_speaker.answer}"
        )

        # Check for task completion
        if self._progress_ledger.is_request_satisfied.answer:
            logger.info("Magentic Orchestrator: Task completed")
            await self._prepare_final_answer(cast(WorkflowContext[Never, list[ChatMessage]], ctx))
            return

        # Check for stalling or looping
        if not self._progress_ledger.is_progress_being_made.answer or self._progress_ledger.is_in_loop.answer:
            self._magentic_context.stall_count += 1
        else:
            self._magentic_context.stall_count = max(0, self._magentic_context.stall_count - 1)

        if self._magentic_context.stall_count > self._manager.max_stall_count:
            logger.debug(f"Magentic Orchestrator: Stalling detected after {self._magentic_context.stall_count} rounds")
            await self._reset_and_replan(ctx)
            return

        # Determine the next speaker and instruction
        next_speaker = self._progress_ledger.next_speaker.answer
        if not isinstance(next_speaker, str):
            # Fallback to first participant if ledger returns non-string
            logger.warning("Next speaker answer was not a string; selecting first participant as fallback")
            next_speaker = next(iter(self._participant_registry.participants.keys()))
        instruction = self._progress_ledger.instruction_or_question.answer

        if next_speaker not in self._participant_registry.participants:
            logger.warning(f"Invalid next speaker: {next_speaker}")
            await self._prepare_final_answer(cast(WorkflowContext[Never, list[ChatMessage]], ctx))
            return

        # Add instruction to conversation (assistant guidance)
        instruction_msg = ChatMessage(
            role=Role.ASSISTANT,
            text=str(instruction),
            author_name=MAGENTIC_MANAGER_NAME,
        )
        self._magentic_context.chat_history.append(instruction_msg)

        # Request specific agent to respond
        logger.debug(f"Magentic Orchestrator: Requesting {next_speaker} to respond")
        await self._send_request_to_participant(
            next_speaker,
            cast(WorkflowContext[AgentExecutorRequest | GroupChatRequestMessage], ctx),
            additional_instruction=str(instruction),
        )

    async def _reset_and_replan(
        self,
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Reset context and replan."""
        if self._magentic_context is None:
            raise RuntimeError("Context not initialized")

        logger.debug("Magentic Orchestrator: Resetting and replanning")

        # Reset context
        self._magentic_context.reset()

        # Reset all participant states
        await self._reset_participants(cast(WorkflowContext[MagenticResetSignal], ctx))

        # Replan
        self._task_ledger = await self._manager.replan(self._magentic_context.clone(deep=True))
        await ctx.add_event(
            MagenticOrchestratorEvent(
                executor_id=self.id,
                event_type=MagenticOrchestratorEventType.REPLANNED,
                data=self._task_ledger,
            )
        )
        # If a human must sign off, ask now and return. The response handler will resume.
        if self._require_plan_signoff:
            await self._send_plan_review_request(cast(WorkflowContext, ctx), is_stalled=True)
            return

        self._magentic_context.chat_history.append(self._task_ledger)

        # Restart outer loop
        await self._run_outer_loop(ctx)

    async def _run_outer_loop(
        self,
        ctx: WorkflowContext[GroupChatWorkflowContext_T_Out, list[ChatMessage]],
    ) -> None:
        """Run the outer orchestration loop - planning phase."""
        if self._magentic_context is None:
            raise RuntimeError("Context not initialized")

        logger.debug("Magentic Orchestrator: Outer loop - entering inner loop")

        # Add task ledger to history if not already there
        if self._task_ledger and (
            not self._magentic_context.chat_history or self._magentic_context.chat_history[-1] != self._task_ledger
        ):
            self._magentic_context.chat_history.append(self._task_ledger)

        # Start inner loop
        await self._run_inner_loop(ctx)

    async def _prepare_final_answer(self, ctx: WorkflowContext[Never, list[ChatMessage]]) -> None:
        """Prepare the final answer using the manager."""
        if self._magentic_context is None:
            raise RuntimeError("Context not initialized")

        logger.info("Magentic Orchestrator: Preparing final answer")
        final_answer = await self._manager.prepare_final_answer(self._magentic_context.clone(deep=True))

        # Emit a completed event for the workflow
        await ctx.yield_output([final_answer])

        self._terminated = True

    async def _check_within_limits_or_complete(self, ctx: WorkflowContext[Never, list[ChatMessage]]) -> bool:
        """Check if orchestrator is within operational limits.

        If limits are exceeded, yield a termination message and mark the workflow as terminated.

        Args:
            ctx: The workflow context.

        Returns:
            True if within limits, False if limits exceeded and workflow is terminated.
        """
        if self._magentic_context is None:
            raise RuntimeError("Context not initialized")

        hit_round_limit = self._max_rounds is not None and self._round_index >= self._max_rounds
        hit_reset_limit = (
            self._manager.max_reset_count is not None
            and self._magentic_context.reset_count >= self._manager.max_reset_count
        )

        if hit_round_limit or hit_reset_limit:
            limit_type = "round" if hit_round_limit else "reset"
            logger.error(f"Magentic Orchestrator: Max {limit_type} count reached")

            # Yield the full conversation with an indication of termination due to limits
            await ctx.yield_output([
                *self._magentic_context.chat_history,
                ChatMessage(
                    role=Role.ASSISTANT,
                    text=f"Workflow terminated due to reaching maximum {limit_type} count.",
                    author_name=MAGENTIC_MANAGER_NAME,
                ),
            ])
            self._terminated = True

            return False

        return True

    async def _reset_participants(self, ctx: WorkflowContext[MagenticResetSignal]) -> None:
        """Reset all participant executors."""
        # Orchestrator is connected to all participants. Sending the message without specifying
        # a target will broadcast to all.
        await ctx.send_message(MagenticResetSignal())

    @override
    async def on_checkpoint_save(self) -> dict[str, Any]:
        """Capture current orchestrator state for checkpointing."""
        state = await super().on_checkpoint_save()
        state["terminated"] = self._terminated

        if self._magentic_context is not None:
            state["magentic_context"] = self._magentic_context.to_dict()
        if self._task_ledger is not None:
            state["task_ledger"] = _message_to_payload(self._task_ledger)
        if self._progress_ledger is not None:
            state["progress_ledger"] = self._progress_ledger.to_dict()

        try:
            state["manager_state"] = self._manager.on_checkpoint_save()
        except Exception as exc:
            logger.warning(f"Failed to save manager state for checkpoint: {exc}\nSkipping...")

        return state

    @override
    async def on_checkpoint_restore(self, state: dict[str, Any]) -> None:
        """Restore executor state from checkpoint."""
        await super().on_checkpoint_restore(state)
        self._terminated = state.get("terminated", False)

        magentic_context_data = state.get("magentic_context")
        if magentic_context_data is not None:
            try:
                self._magentic_context = MagenticContext.from_dict(magentic_context_data)
            except Exception:  # pragma: no cover - defensive
                logger.warning("Failed to restore Magentic context from checkpoint data")
                self._magentic_context = None

        task_ledger_data = state.get("task_ledger")
        if task_ledger_data is not None:
            try:
                self._task_ledger = _message_from_payload(task_ledger_data)
            except Exception:  # pragma: no cover - defensive
                logger.warning("Failed to restore task ledger from checkpoint data")
                self._task_ledger = None

        progress_ledger_data = state.get("progress_ledger")
        if progress_ledger_data is not None:
            try:
                self._progress_ledger = MagenticProgressLedger.from_dict(progress_ledger_data)
            except Exception:  # pragma: no cover - defensive
                logger.warning("Failed to restore progress ledger from checkpoint data")
                self._progress_ledger = None

        manager_state = state.get("manager_state")
        if manager_state is not None:
            try:
                self._manager.on_checkpoint_restore(manager_state)
            except Exception as exc:
                logger.warning(f"Failed to restore manager state from checkpoint: {exc}\nSkipping...")


# endregion Magentic Orchestrator

# region Magentic Agent Executor


class MagenticAgentExecutor(AgentExecutor):
    """Specialized AgentExecutor for Magentic agent participants."""

    def __init__(self, agent: AgentProtocol) -> None:
        """Initialize a Magentic Agent Executor.

        This executor wraps an AgentProtocol instance to be used as a participant
        in a Magentic One workflow.

        Args:
            agent: The agent instance to wrap.

        Notes: Magentic pattern requires a reset operation upon replanning. This executor
        extends the base AgentExecutor to handle resets appropriately. In order to handle
        resets, the agent threads and other states are reset when requested by the orchestrator.
        And because of this, MagenticAgentExecutor does not support custom threads.
        """
        super().__init__(agent)

    @handler
    async def handle_magentic_reset(self, signal: MagenticResetSignal, ctx: WorkflowContext) -> None:
        """Handle reset signal from the Magentic orchestrator.

        This method resets the internal state of the agent executor, including
        any threads or caches, to prepare for a fresh start after replanning.

        Args:
            signal: The MagenticResetSignal instance.
            ctx: The workflow context.
        """
        # Message related
        self._cache.clear()
        self._full_conversation.clear()
        # Request into related
        self._pending_agent_requests.clear()
        self._pending_responses_to_agent.clear()
        # Reset threads
        self._agent_thread = self._agent.get_new_thread()


#  endregion Magentic Agent Executor

# region Magentic Workflow Builder


class MagenticBuilder:
    """Fluent builder for creating Magentic One multi-agent orchestration workflows.

    Magentic One workflows use an LLM-powered manager to coordinate multiple agents through
    dynamic task planning, progress tracking, and adaptive replanning. The manager creates
    plans, selects agents, monitors progress, and determines when to replan or complete.

    The builder provides a fluent API for configuring participants, the manager, optional
    plan review, checkpointing, and event callbacks.

    Human-in-the-loop Support:
        Magentic provides specialized HITL mechanisms via:

        - `.with_plan_review()` - Review and approve/revise plans before execution
        - `.with_human_input_on_stall()` - Intervene when workflow stalls
        - Tool approval via `FunctionApprovalRequestContent` - Approve individual tool calls

        These emit `MagenticHumanInterventionRequest` events that provide structured
        decision options (APPROVE, REVISE, CONTINUE, REPLAN, GUIDANCE) appropriate
        for Magentic's planning-based orchestration.
    """

    def __init__(self) -> None:
        """Initialize the Magentic workflow builder."""
        self._participants: dict[str, AgentProtocol | Executor] = {}
        self._participant_factories: list[Callable[[], AgentProtocol | Executor]] = []

        # Manager related members
        self._manager: MagenticManagerBase | None = None
        self._manager_factory: Callable[[], MagenticManagerBase] | None = None
        self._manager_agent_factory: Callable[[], AgentProtocol] | None = None
        self._standard_manager_options: dict[str, Any] = {}
        self._enable_plan_review: bool = False

        self._checkpoint_storage: CheckpointStorage | None = None

    def register_participants(
        self,
        participant_factories: Sequence[Callable[[], AgentProtocol | Executor]],
    ) -> "MagenticBuilder":
        """Register participant factories for this Magentic workflow.

        Args:
            participant_factories: Sequence of callables that return AgentProtocol or Executor instances.

        Returns:
            Self for method chaining

        Raises:
            ValueError: If participant_factories is empty, or participants
                or participant factories are already set
        """
        if self._participants:
            raise ValueError("Cannot mix .participants() and .register_participants() in the same builder instance.")

        if self._participant_factories:
            raise ValueError("register_participants() has already been called on this builder instance.")

        if not participant_factories:
            raise ValueError("participant_factories cannot be empty")

        self._participant_factories = list(participant_factories)
        return self

    def participants(self, participants: Sequence[AgentProtocol | Executor]) -> Self:
        """Define participants for this Magentic workflow.

        Accepts AgentProtocol instances (auto-wrapped as AgentExecutor) or Executor instances.

        Args:
            participants: Sequence of participant definitions

        Returns:
            Self for method chaining

        Raises:
            ValueError: If participants are empty, names are duplicated, or participants
                or participant factories are already set
            TypeError: If any participant is not AgentProtocol or Executor instance

        Example:

        .. code-block:: python

            workflow = (
                MagenticBuilder()
                .participants([research_agent, writing_agent, coding_agent, review_agent])
                .with_manager(agent=manager_agent)
                .build()
            )

        Notes:
            - Participant names become part of the manager's context for selection
            - Agent descriptions (if available) are extracted and provided to the manager
            - Can be called multiple times to add participants incrementally
        """
        if self._participant_factories:
            raise ValueError("Cannot mix .participants() and .register_participants() in the same builder instance.")

        if self._participants:
            raise ValueError("participants have already been set. Call participants(...) at most once.")

        if not participants:
            raise ValueError("participants cannot be empty.")

        # Name of the executor mapped to participant instance
        named: dict[str, AgentProtocol | Executor] = {}
        for participant in participants:
            if isinstance(participant, Executor):
                identifier = participant.id
            elif isinstance(participant, AgentProtocol):
                if not participant.name:
                    raise ValueError("AgentProtocol participants must have a non-empty name.")
                identifier = participant.name
            else:
                raise TypeError(
                    f"Participants must be AgentProtocol or Executor instances. Got {type(participant).__name__}."
                )

            if identifier in named:
                raise ValueError(f"Duplicate participant name '{identifier}' detected")

            named[identifier] = participant

        self._participants = named

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
                .with_manager(agent=manager_agent)
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
                .participants([agent1])
                .with_manager(agent=manager_agent)
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

    @overload
    def with_manager(self, *, manager: MagenticManagerBase) -> Self:
        """Configure the workflow with a pre-defined Magentic manager instance.

        Args:
            manager: A custom manager instance (subclass of MagenticManagerBase)

        Returns:
            Self for method chaining
        """
        ...

    @overload
    def with_manager(self, *, manager_factory: Callable[[], MagenticManagerBase]) -> Self:
        """Configure the workflow with a factory for creating custom Magentic manager instances.

        Args:
            manager_factory: Callable that returns a new MagenticManagerBase instance

        Returns:
            Self for method chaining
        """
        ...

    @overload
    def with_manager(
        self,
        *,
        agent: AgentProtocol,
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
        """Configure the workflow with an agent for creating a standard manager.

        This will create a StandardMagenticManager using the provided agent.

        Args:
            agent: AgentProtocol instance for the standard magentic manager
                   (`StandardMagenticManager`)
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
        """
        ...

    @overload
    def with_manager(
        self,
        *,
        agent_factory: Callable[[], AgentProtocol],
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
        """Configure the workflow with a factory for creating the manager agent.

        This will create a StandardMagenticManager using the provided agent factory.

        Args:
            agent_factory: Callable that returns a new AgentProtocol instance for the standard
                           magentic manager (`StandardMagenticManager`)
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
        """
        ...

    def with_manager(
        self,
        *,
        manager: MagenticManagerBase | None = None,
        manager_factory: Callable[[], MagenticManagerBase] | None = None,
        agent_factory: Callable[[], AgentProtocol] | None = None,
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
        and deciding when to replan or complete. This method supports four usage patterns:

        1. **Provide existing manager**: Pass a pre-configured manager instance (custom
           or standard) for full control over behavior
        2. **Factory for custom manager**: Pass a callable that returns a new manager
           instance for more advanced scenarios so that the builder can be reused
        3. **Factory for agent**: Pass a callable that returns a new agent instance to
           automatically create a `StandardMagenticManager`
        4. **Auto-create with agent**: Pass an agent to automatically create a `StandardMagenticManager`

        Args:
            manager: Pre-configured manager instance (`StandardMagenticManager` or custom
                `MagenticManagerBase` subclass). If provided, all other arguments are ignored.
            manager_factory: Callable that returns a new manager instance.
            agent_factory: Callable that returns a new agent instance.
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
                options=ChatOptions(temperature=0.3, seed=42),
                instructions="Be concise and focus on accuracy",
            )

            workflow = (
                MagenticBuilder()
                .participants(agent1=agent1, agent2=agent2)
                .with_manager(
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
            workflow = MagenticBuilder().participants(agent1=agent1).with_manager(manager).build()

        Usage with prompt customization:

        .. code-block:: python

            workflow = (
                MagenticBuilder()
                .participants(coder=coder_agent, reviewer=reviewer_agent)
                .with_manager(
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
        if any([self._manager, self._manager_factory, self._manager_agent_factory]):
            raise ValueError("with_manager() has already been called on this builder instance.")

        if sum(x is not None for x in [manager, agent, manager_factory, agent_factory]) != 1:
            raise ValueError("Exactly one of manager, agent, manager_factory, or agent_factory must be provided.")

        def _log_warning_if_constructor_args_provided() -> None:
            if any(
                arg is not None
                for arg in [
                    task_ledger,
                    task_ledger_facts_prompt,
                    task_ledger_plan_prompt,
                    task_ledger_full_prompt,
                    task_ledger_facts_update_prompt,
                    task_ledger_plan_update_prompt,
                    progress_ledger_prompt,
                    final_answer_prompt,
                    max_stall_count,
                    max_reset_count,
                    max_round_count,
                ]
            ):
                logger.warning("Customer manager provided; all other with_manager() arguments will be ignored.")

        if manager is not None:
            self._manager = manager
            _log_warning_if_constructor_args_provided()
        elif agent is not None:
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
        elif manager_factory is not None:
            self._manager_factory = manager_factory
            _log_warning_if_constructor_args_provided()
        elif agent_factory is not None:
            self._manager_agent_factory = agent_factory
            self._standard_manager_options = {
                "task_ledger": task_ledger,
                "task_ledger_facts_prompt": task_ledger_facts_prompt,
                "task_ledger_plan_prompt": task_ledger_plan_prompt,
                "task_ledger_full_prompt": task_ledger_full_prompt,
                "task_ledger_facts_update_prompt": task_ledger_facts_update_prompt,
                "task_ledger_plan_update_prompt": task_ledger_plan_update_prompt,
                "progress_ledger_prompt": progress_ledger_prompt,
                "final_answer_prompt": final_answer_prompt,
                "max_stall_count": max_stall_count,
                "max_reset_count": max_reset_count,
                "max_round_count": max_round_count,
            }

        return self

    def _resolve_orchestrator(self, participants: Sequence[Executor]) -> Executor:
        """Determine the orchestrator to use for the workflow.

        Args:
            participants: List of resolved participant executors
        """
        if all(x is None for x in [self._manager, self._manager_factory, self._manager_agent_factory]):
            raise ValueError("No manager configured. Call with_manager(...) before building the orchestrator.")
        # We don't need to check if multiple are set since that is handled in with_orchestrator()

        if self._manager:
            manager = self._manager
        elif self._manager_factory:
            manager = self._manager_factory()
        elif self._manager_agent_factory:
            agent_instance = self._manager_agent_factory()
            manager = StandardMagenticManager(
                agent=agent_instance,
                **self._standard_manager_options,
            )
        else:
            # This should never be reached due to the checks above
            raise RuntimeError("Manager could not be resolved. Please set the manager properly with with_manager().")

        return MagenticOrchestrator(
            manager=manager,
            participant_registry=ParticipantRegistry(participants),
            require_plan_signoff=self._enable_plan_review,
        )

    def _resolve_participants(self) -> list[Executor]:
        """Resolve participant instances into Executor objects."""
        if not self._participants and not self._participant_factories:
            raise ValueError("No participants provided. Call .participants() or .register_participants() first.")
        # We don't need to check if both are set since that is handled in the respective methods

        participants: list[Executor | AgentProtocol] = []
        if self._participant_factories:
            for factory in self._participant_factories:
                participant = factory()
                participants.append(participant)
        else:
            participants = list(self._participants.values())

        executors: list[Executor] = []
        for participant in participants:
            if isinstance(participant, Executor):
                executors.append(participant)
            elif isinstance(participant, AgentProtocol):
                executors.append(MagenticAgentExecutor(participant))
            else:
                raise TypeError(
                    f"Participants must be AgentProtocol or Executor instances. Got {type(participant).__name__}."
                )

        return executors

    def build(self) -> Workflow:
        """Build a Magentic workflow with the orchestrator and all agent executors."""
        logger.info(f"Building Magentic workflow with {len(self._participants)} participants")

        participants: list[Executor] = self._resolve_participants()
        orchestrator: Executor = self._resolve_orchestrator(participants)

        # Build workflow graph
        workflow_builder = WorkflowBuilder().set_start_executor(orchestrator)
        for participant in participants:
            # Orchestrator and participant bi-directional edges
            workflow_builder = workflow_builder.add_edge(orchestrator, participant)
            workflow_builder = workflow_builder.add_edge(participant, orchestrator)
        if self._checkpoint_storage is not None:
            workflow_builder = workflow_builder.with_checkpointing(self._checkpoint_storage)

        return workflow_builder.build()


# endregion Magentic Workflow Builder
