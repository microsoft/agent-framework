# Copyright (c) Microsoft. All rights reserved.
#
# Magentic One workflow pattern implementation for agent-framework.
# This version preserves the original Magentic logic while adapting to the new executor-based runtime.
# It performs real LLM calls for:
# - Task facts and plan creation
# - Replanning with facts update and plan update
# - Progress ledger creation using JSON-only output from the model
# - Final answer synthesis
#
# The manager uses a ChatClientAgent internally to make calls against the provided chat_client.
# All routing is done with executors and WorkflowContext.send_message.

from __future__ import annotations

import contextlib
import json
import logging
import re
import sys
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Annotated, Any

from agent_framework import AgentRunResponse, AgentRunResponseUpdate, ChatClient, ChatMessage, ChatRole
from agent_framework._agents import AgentBase
from pydantic import BaseModel, ConfigDict, Field

from ._events import WorkflowCompletedEvent
from ._executor import Executor, handler
from ._workflow import Workflow, WorkflowBuilder
from ._workflow_context import WorkflowContext

if sys.version_info >= (3, 11):
    from typing import Self  # pragma: no cover
else:
    from typing_extensions import Self  # pragma: no cover

logger = logging.getLogger(__name__)

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

# endregion Magentic One Prompts

__all__ = [
    "MagenticAgentExecutor",
    "MagenticContext",
    "MagenticManagerBase",
    "MagenticOrchestratorExecutor",
    "MagenticRequestMessage",
    "MagenticResetMessage",
    "MagenticResponseMessage",
    "MagenticStartMessage",
    "MagenticWorkflowBuilder",
    "ProgressLedger",
    "StandardMagenticManager",
]

# region Messages and Types


@dataclass
class MagenticStartMessage:
    """A message to start a magentic workflow."""

    task: ChatMessage


@dataclass
class MagenticRequestMessage:
    """A request message type for agents in a magentic workflow."""

    agent_name: str
    instruction: str = ""
    task_context: str = ""


@dataclass
class MagenticResponseMessage:
    """A response message type from agents in a magentic workflow."""

    body: ChatMessage


@dataclass
class MagenticResetMessage:
    """A message to reset participant chat history in a magentic workflow."""

    pass


class ProgressLedgerItem(BaseModel):
    """A progress ledger item."""

    reason: str
    answer: str | bool


class ProgressLedger(BaseModel):
    """A progress ledger for tracking workflow progress."""

    is_request_satisfied: ProgressLedgerItem
    is_in_loop: ProgressLedgerItem
    is_progress_being_made: ProgressLedgerItem
    next_speaker: ProgressLedgerItem
    instruction_or_question: ProgressLedgerItem


class TaskLedger(BaseModel):
    """Structured task ledger containing facts and plan messages."""

    facts: ChatMessage
    plan: ChatMessage


class MagenticContext(BaseModel):
    """Context for the Magentic manager."""

    task: Annotated[ChatMessage, Field(description="The task to be completed.")]
    chat_history: Annotated[list[ChatMessage], Field(description="The chat history to track conversation.")] = Field(
        default_factory=list
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
        if msg.role == ChatRole.ASSISTANT:
            return msg
    return None


def _extract_json(text: str) -> dict[str, Any]:
    """Extract and parse JSON from model text output. Handles common wrappers such as ```json fences."""
    # Prefer fenced blocks
    fence = re.search(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.IGNORECASE)
    candidate = fence.group(1) if fence else None

    # Else fall back to first {...} span
    if candidate is None:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start : end + 1]
        else:
            candidate = text

    # Try strict JSON
    try:
        return json.loads(candidate)
    except Exception:
        pass

    # Try replacing Python bools and None
    repaired = candidate.replace("True", "true").replace("False", "false").replace("None", "null")
    try:
        return json.loads(repaired)
    except Exception:
        pass

    # Last resort, attempt literal_eval
    with contextlib.suppress(Exception):
        import ast

        obj = ast.literal_eval(candidate)  # type: ignore[arg-type]
        if isinstance(obj, dict):
            return obj

    raise ValueError(f"Unable to parse JSON from model output:\n{candidate[:500]}")


def _pd_validate(model: type[BaseModel], data: dict[str, Any]) -> BaseModel:
    """Validate against a Pydantic model in a way that supports v1 and v2."""
    with contextlib.suppress(AttributeError):
        # Pydantic v2
        return model.model_validate(data)  # type: ignore[attr-defined]
    # Pydantic v1 fallback
    return model.parse_obj(data)  # type: ignore[call-arg]


# endregion Utilities

# region Magentic Manager


class MagenticManagerBase(BaseModel, ABC):
    """Base class for the Magentic One manager."""

    max_stall_count: Annotated[int, Field(description="Max number of stalls before a reset.", ge=0)] = 3
    max_reset_count: Annotated[int | None, Field(description="Max number of resets allowed.", ge=0)] = None
    max_round_count: Annotated[int | None, Field(description="Max number of agent responses allowed.", gt=0)] = None

    @abstractmethod
    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Create a plan for the task."""
        ...

    @abstractmethod
    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Replan for the task."""
        ...

    @abstractmethod
    async def create_progress_ledger(self, magentic_context: MagenticContext) -> ProgressLedger:
        """Create a progress ledger."""
        ...

    @abstractmethod
    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        """Prepare the final answer."""
        ...


class StandardMagenticManager(MagenticManagerBase):
    """Standard Magentic manager that performs real LLM calls via a ChatClientAgent.

    The manager constructs prompts that mirror the original Magentic One orchestration:
    - Facts gathering
    - Plan creation
    - Progress ledger in JSON
    - Facts update and plan update on reset
    - Final answer synthesis
    """

    # Allow non-pydantic types like ChatClient
    model_config = ConfigDict(arbitrary_types_allowed=True)

    chat_client: ChatClient
    task_ledger: TaskLedger | None = None
    # Optional instructions for the internal orchestrator agent
    instructions: str | None = None

    # Prompts may be overridden if needed
    task_ledger_facts_prompt: str = ORCHESTRATOR_TASK_LEDGER_FACTS_PROMPT
    task_ledger_plan_prompt: str = ORCHESTRATOR_TASK_LEDGER_PLAN_PROMPT
    task_ledger_full_prompt: str = ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT
    task_ledger_facts_update_prompt: str = ORCHESTRATOR_TASK_LEDGER_FACTS_UPDATE_PROMPT
    task_ledger_plan_update_prompt: str = ORCHESTRATOR_TASK_LEDGER_PLAN_UPDATE_PROMPT
    progress_ledger_prompt: str = ORCHESTRATOR_PROGRESS_LEDGER_PROMPT
    final_answer_prompt: str = ORCHESTRATOR_FINAL_ANSWER_PROMPT

    # Internal working agent; created lazily
    _orchestrator_agent: Any | None = None

    def __init__(self, chat_client: ChatClient, task_ledger: TaskLedger | None = None, **kwargs: Any) -> None:
        args: dict[str, Any] = {"chat_client": chat_client}

        if task_ledger is not None:
            args["task_ledger"] = task_ledger

        if kwargs:
            args.update(kwargs)

        super().__init__(**args)

    async def _ensure_agent(self) -> Any:
        """Create or return the internal ChatClientAgent used for LLM calls."""
        if self._orchestrator_agent is not None:
            return self._orchestrator_agent

        # Lazy import to avoid hard dependency at import time
        from agent_framework import ChatClientAgent

        self._orchestrator_agent = ChatClientAgent(
            name="orchestrator_llm",
            description="Coordinator agent for planning, progress tracking, and synthesis",
            chat_client=self.chat_client,
            instructions=self.instructions or "",
        )
        return self._orchestrator_agent

    async def _complete(self, messages: list[ChatMessage]) -> ChatMessage:
        """Invoke the internal agent with the given messages and return the last assistant message."""
        agent = await self._ensure_agent()
        from agent_framework import AgentThread
        from agent_framework._threads import thread_on_new_messages

        thread = AgentThread()
        if messages:
            await thread_on_new_messages(thread, messages)

        run_result = await agent.run(thread=thread)
        out_messages: list[ChatMessage] | None = None
        with contextlib.suppress(Exception):
            out_messages = list(run_result.messages)  # type: ignore[assignment]
        if out_messages and len(out_messages) > 0:
            last = out_messages[-1]
            return ChatMessage(
                role=last.role or ChatRole.ASSISTANT,
                text=last.text or "",
                author_name=last.author_name or "orchestrator_llm",
            )

        # Fallback if no messages
        return ChatMessage(role=ChatRole.ASSISTANT, text="No output produced.", author_name="orchestrator_llm")

    async def plan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Create facts and plan using the model, then render a combined task ledger as a single assistant message."""
        task_text = magentic_context.task.text
        team_text = _team_block(magentic_context.participant_descriptions)

        # Gather facts
        facts_user = ChatMessage(
            role=ChatRole.USER,
            text=self.task_ledger_facts_prompt.format(task=task_text),
        )
        facts_msg = await self._complete(magentic_context.chat_history + [facts_user])

        # Create plan
        plan_user = ChatMessage(
            role=ChatRole.USER,
            text=self.task_ledger_plan_prompt.format(team=team_text),
        )
        plan_msg = await self._complete(magentic_context.chat_history + [facts_user, facts_msg, plan_user])

        # Store ledger and render full combined view
        self.task_ledger = TaskLedger(facts=facts_msg, plan=plan_msg)

        combined = self.task_ledger_full_prompt.format(
            task=task_text,
            team=team_text,
            facts=facts_msg.text,
            plan=plan_msg.text,
        )
        return ChatMessage(role=ChatRole.ASSISTANT, text=combined, author_name="magentic_manager")

    async def replan(self, magentic_context: MagenticContext) -> ChatMessage:
        """Update facts and plan when stalling or looping has been detected."""
        if self.task_ledger is None:
            # If plan was never created, fall back to a first plan
            return await self.plan(magentic_context)

        task_text = magentic_context.task.text
        team_text = _team_block(magentic_context.participant_descriptions)

        # Update facts
        facts_update_user = ChatMessage(
            role=ChatRole.USER,
            text=self.task_ledger_facts_update_prompt.format(task=task_text, old_facts=self.task_ledger.facts.text),
        )
        updated_facts = await self._complete(magentic_context.chat_history + [facts_update_user])

        # Update plan
        plan_update_user = ChatMessage(
            role=ChatRole.USER,
            text=self.task_ledger_plan_update_prompt.format(team=team_text),
        )
        updated_plan = await self._complete(
            magentic_context.chat_history + [facts_update_user, updated_facts, plan_update_user]
        )

        # Store and render
        self.task_ledger = TaskLedger(facts=updated_facts, plan=updated_plan)
        combined = ORCHESTRATOR_TASK_LEDGER_FULL_PROMPT.format(
            task=task_text,
            team=team_text,
            facts=updated_facts.text,
            plan=updated_plan.text,
        )
        return ChatMessage(role=ChatRole.ASSISTANT, text=combined, author_name="magentic_manager")

    async def create_progress_ledger(self, magentic_context: MagenticContext) -> ProgressLedger:
        """Use the model to produce a JSON progress ledger based on the conversation so far."""
        agent_names = list(magentic_context.participant_descriptions.keys())
        names_csv = ", ".join(agent_names)
        team_text = _team_block(magentic_context.participant_descriptions)

        prompt = self.progress_ledger_prompt.format(
            task=magentic_context.task.text,
            team=team_text,
            names=names_csv,
        )
        user_message = ChatMessage(role=ChatRole.USER, text=prompt)

        # Include full context to help the model decide current stage
        raw = await self._complete(magentic_context.chat_history + [user_message])
        try:
            ledger_dict = _extract_json(raw.text)
            model_obj = _pd_validate(ProgressLedger, ledger_dict)
            return model_obj  # type: ignore[return-value]
        except Exception as ex:
            logger.warning("Progress ledger JSON parse failed. Falling back. Error: %s", ex)

            # Fallback to a conservative ledger to avoid hard failure
            fallback_next = agent_names[0] if agent_names else "unknown"
            return ProgressLedger(
                is_request_satisfied=ProgressLedgerItem(reason="Fallback due to parsing error", answer=False),
                is_in_loop=ProgressLedgerItem(reason="Fallback", answer=False),
                is_progress_being_made=ProgressLedgerItem(reason="Fallback", answer=True),
                next_speaker=ProgressLedgerItem(reason="Fallback", answer=fallback_next),
                instruction_or_question=ProgressLedgerItem(
                    reason="Fallback",
                    answer="Provide a concrete next step with sufficient detail to move the task forward.",
                ),
            )

    async def prepare_final_answer(self, magentic_context: MagenticContext) -> ChatMessage:
        """Ask the model to produce the final answer addressed to the user."""
        prompt = self.final_answer_prompt.format(task=magentic_context.task.text)
        user_message = ChatMessage(role=ChatRole.USER, text=prompt)
        response = await self._complete(magentic_context.chat_history + [user_message])
        # Ensure role is assistant
        return ChatMessage(
            role=ChatRole.ASSISTANT,
            text=response.text,
            author_name=response.author_name or "magentic_manager",
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

    def __init__(
        self,
        manager: MagenticManagerBase,
        participants: dict[str, str],
        result_callback: Callable[[ChatMessage], Awaitable[None]] | None = None,
        agent_response_callback: Callable[[str, ChatMessage], Awaitable[None]] | None = None,
        streaming_agent_response_callback: Callable[[str, AgentRunResponseUpdate, bool], Awaitable[None]] | None = None,
    ) -> None:
        super().__init__("magentic_orchestrator")
        self._manager = manager
        self._participants = participants
        self._result_callback = result_callback
        self._agent_response_callback = agent_response_callback
        self._streaming_agent_response_callback = streaming_agent_response_callback
        self._context: MagenticContext | None = None
        self._task_ledger: ChatMessage | None = None

    @handler(output_types=[MagenticResponseMessage, MagenticRequestMessage, MagenticResetMessage])
    async def handle_start_message(self, message: MagenticStartMessage, context: WorkflowContext) -> None:
        """Handle the initial start message to begin orchestration."""
        logger.info("Magentic Orchestrator: Received start message")

        self._context = MagenticContext(
            task=message.task,
            participant_descriptions=self._participants,
        )

        # Broadcast the original user task so all agents have the request context
        self._context.chat_history.append(message.task)
        await context.send_message(MagenticResponseMessage(body=message.task))
        # Non-streaming callback for the orchestrator broadcast of the task
        if self._agent_response_callback:
            with contextlib.suppress(Exception):
                await self._agent_response_callback(self.id, message.task)

        # Initial planning using the manager with real model calls
        self._task_ledger = await self._manager.plan(self._context.model_copy(deep=True))

        # Add task ledger to conversation history
        self._context.chat_history.append(self._task_ledger)

        logger.debug("Task ledger created.")

        # Broadcast task ledger to all agents
        await context.send_message(MagenticResponseMessage(body=self._task_ledger))
        if self._agent_response_callback and self._task_ledger is not None:
            with contextlib.suppress(Exception):
                await self._agent_response_callback(self.id, self._task_ledger)

        # Start the inner loop
        await self._run_inner_loop(context)

    @handler(output_types=[MagenticResponseMessage, MagenticRequestMessage, MagenticResetMessage])
    async def handle_response_message(self, message: MagenticResponseMessage, context: WorkflowContext) -> None:
        """Handle responses from agents."""
        if self._context is None:
            logger.warning("Magentic Orchestrator: Received response but not initialized")
            return

        logger.debug("Magentic Orchestrator: Received response from agent")

        # Add transfer message if needed
        if message.body.role != ChatRole.USER:
            transfer_msg = ChatMessage(
                role=ChatRole.USER,
                text=f"Transferred to {getattr(message.body, 'author_name', 'agent')}",
            )
            self._context.chat_history.append(transfer_msg)

        # Add agent response to context
        self._context.chat_history.append(message.body)

        # Continue with inner loop
        await self._run_inner_loop(context)

    @handler(output_types=[MagenticResponseMessage, MagenticRequestMessage, MagenticResetMessage])
    async def handle_reset_message(self, message: MagenticResetMessage, context: WorkflowContext) -> None:
        """Handle reset messages to restart orchestration."""
        if self._context is None:
            return

        logger.info("Magentic Orchestrator: Resetting context")
        self._context.reset()

        # Replan using the manager
        self._task_ledger = await self._manager.replan(self._context.model_copy(deep=True))

        # Broadcast reset to agents
        await context.send_message(MagenticResetMessage())

        # Restart outer loop
        await self._run_outer_loop(context)

    async def _run_outer_loop(self, context: WorkflowContext) -> None:
        """Run the outer orchestration loop - planning phase."""
        if self._context is None:
            raise RuntimeError("Context not initialized")

        logger.info("Magentic Orchestrator: Outer loop - broadcasting task ledger and entering inner loop")

        # Add task ledger to history if not already there
        if self._task_ledger and (
            not self._context.chat_history or self._context.chat_history[-1] != self._task_ledger
        ):
            self._context.chat_history.append(self._task_ledger)

        # Broadcast updated task ledger
        if self._task_ledger:
            await context.send_message(MagenticResponseMessage(body=self._task_ledger))
            if self._agent_response_callback:
                with contextlib.suppress(Exception):
                    await self._agent_response_callback(self.id, self._task_ledger)

        # Start inner loop
        await self._run_inner_loop(context)

    async def _run_inner_loop(self, context: WorkflowContext) -> None:
        """Run the inner orchestration loop - coordination phase."""
        if self._context is None or self._task_ledger is None:
            raise RuntimeError("Context or task ledger not initialized")

        # Check limits first
        within_limits = await self._check_within_limits(context)
        if not within_limits:
            return

        self._context.round_count += 1
        logger.info("Magentic Orchestrator: Inner loop - round %s", self._context.round_count)

        # Create progress ledger using the manager
        current_progress_ledger = await self._manager.create_progress_ledger(self._context.model_copy(deep=True))

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
            self._context.stall_count += 1
        else:
            self._context.stall_count = max(0, self._context.stall_count - 1)

        if self._context.stall_count > self._manager.max_stall_count:
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
            role=ChatRole.ASSISTANT,
            text=str(instruction),
            author_name="magentic_manager",
        )
        self._context.chat_history.append(instruction_msg)

        # Broadcast instruction
        await context.send_message(MagenticResponseMessage(body=instruction_msg))
        if self._agent_response_callback:
            with contextlib.suppress(Exception):
                await self._agent_response_callback(self.id, instruction_msg)

        # Request specific agent to respond
        logger.debug("Magentic Orchestrator: Requesting %s to respond", next_speaker_value)
        await context.send_message(
            MagenticRequestMessage(
                agent_name=next_speaker_value,
                instruction=str(instruction),
                task_context=self._context.task.text,
            )
        )

    async def _reset_and_replan(self, context: WorkflowContext) -> None:
        """Reset context and replan."""
        if self._context is None:
            return

        logger.info("Magentic Orchestrator: Resetting and replanning")

        # Reset context
        self._context.reset()

        # Replan
        self._task_ledger = await self._manager.replan(self._context.model_copy(deep=True))

        # Broadcast reset to agents
        await context.send_message(MagenticResetMessage())

        # Restart outer loop
        await self._run_outer_loop(context)

    async def _prepare_final_answer(self, context: WorkflowContext) -> None:
        """Prepare the final answer using the manager."""
        if self._context is None:
            return

        logger.info("Magentic Orchestrator: Preparing final answer")
        final_answer = await self._manager.prepare_final_answer(self._context.model_copy(deep=True))

        # Emit a completed event for the workflow
        await context.add_event(WorkflowCompletedEvent(final_answer))

        if self._result_callback:
            await self._result_callback(final_answer)

    async def _check_within_limits(self, context: WorkflowContext) -> bool:
        """Check if orchestrator is within operational limits."""
        if self._context is None:
            return False

        hit_round_limit = (
            self._manager.max_round_count is not None and self._context.round_count >= self._manager.max_round_count
        )
        hit_reset_limit = (
            self._manager.max_reset_count is not None and self._context.reset_count > self._manager.max_reset_count
        )

        if hit_round_limit or hit_reset_limit:
            limit_type = "round" if hit_round_limit else "reset"
            logger.error("Magentic Orchestrator: Max %s count reached", limit_type)

            # Get partial result
            partial_result = _first_assistant(self._context.chat_history)
            if partial_result is None:
                partial_result = ChatMessage(
                    role=ChatRole.ASSISTANT,
                    text=f"Stopped due to {limit_type} limit. No partial result available.",
                    author_name="magentic_manager",
                )

            # Emit a completed event with the partial result
            await context.add_event(WorkflowCompletedEvent(partial_result))

            if self._result_callback:
                await self._result_callback(partial_result)
            return False

        return True


class MagenticAgentExecutor(Executor):
    """Magentic agent executor that wraps an agent for participation in workflows.

    This executor handles:
    - Receiving task ledger broadcasts
    - Responding to specific agent requests
    - Resetting agent state when needed
    """

    def __init__(
        self,
        agent: AgentBase | Executor,
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

    @handler(output_types=[MagenticResponseMessage])
    async def handle_response_message(self, message: MagenticResponseMessage, context: WorkflowContext) -> None:
        """Handle response message (task ledger broadcast)."""
        logger.debug("Agent %s: Received response message", self._agent_id)

        # Add transfer message if needed
        if message.body.role != ChatRole.USER:
            transfer_msg = ChatMessage(
                role=ChatRole.USER,
                text=f"Transferred to {getattr(message.body, 'author_name', 'agent')}",
            )
            self._chat_history.append(transfer_msg)

        # Add message to agent's history
        self._chat_history.append(message.body)

    @handler(output_types=[MagenticResponseMessage])
    async def handle_request_message(self, message: MagenticRequestMessage, context: WorkflowContext) -> None:
        """Handle request to respond."""
        if message.agent_name != self._agent_id:
            return

        logger.info("Agent %s: Received request to respond", self._agent_id)

        # Add persona adoption message
        persona_msg = ChatMessage(
            role=ChatRole.USER,
            text=f"Transferred to {self._agent_id}, adopt the persona immediately.",
        )
        self._chat_history.append(persona_msg)

        # Add the orchestrator's instruction as a USER message so the agent treats it as the prompt
        if message.instruction:
            self._chat_history.append(ChatMessage(role=ChatRole.USER, text=message.instruction))

        try:
            # Invoke the agent
            response = await self._invoke_agent()
            self._chat_history.append(response)

            # Send response back to orchestrator
            await context.send_message(MagenticResponseMessage(body=response))

        except Exception as e:
            logger.warning("Agent %s invoke failed: %s", self._agent_id, e)
            # Fallback response
            response = ChatMessage(
                role=ChatRole.ASSISTANT,
                text=f"Agent {self._agent_id}: Error processing request - {str(e)[:100]}",
            )
            self._chat_history.append(response)
            await context.send_message(MagenticResponseMessage(body=response))

    @handler(output_types=[MagenticResponseMessage])
    async def handle_reset_message(self, message: MagenticResetMessage, context: WorkflowContext) -> None:
        """Handle reset message."""
        logger.debug("Agent %s: Resetting chat history", self._agent_id)
        self._chat_history.clear()

    async def _invoke_agent(self) -> ChatMessage:
        """Invoke the wrapped agent and return a response."""
        # 1) Preferred: Agents implementing a run(thread=...) API (e.g., ChatClientAgent)
        if hasattr(self._agent, "run"):
            logger.debug("Agent %s: Running with %d messages", self._agent_id, len(self._chat_history))

            from agent_framework import AgentThread
            from agent_framework._threads import thread_on_new_messages

            thread = AgentThread()
            if self._chat_history:
                await thread_on_new_messages(thread, self._chat_history)

            # If streaming callback provided and agent supports streaming, stream first
            if self._streaming_agent_response_callback and hasattr(self._agent, "run_streaming"):
                updates: list[AgentRunResponseUpdate] = []
                async for update in self._agent.run_streaming(thread=thread):  # type: ignore[attr-defined]
                    updates.append(update)
                    with contextlib.suppress(Exception):
                        await self._streaming_agent_response_callback(self._agent_id, update, False)
                # assemble final from updates
                try:
                    run_result: AgentRunResponse = AgentRunResponse.from_agent_run_response_updates(updates)
                except Exception:
                    run_result = await self._agent.run(thread=thread)  # type: ignore[attr-defined]
                # mark final using last update if available
                if updates:
                    with contextlib.suppress(Exception):
                        await self._streaming_agent_response_callback(self._agent_id, updates[-1], True)
            else:
                run_result = await self._agent.run(thread=thread)  # type: ignore[attr-defined]
            messages: list[ChatMessage] | None = None
            with contextlib.suppress(Exception):
                messages = list(run_result.messages)  # type: ignore[assignment]
            if messages and len(messages) > 0:
                last: ChatMessage = messages[-1]
                author = last.author_name or self._agent_id
                role: ChatRole = last.role if last.role else ChatRole.ASSISTANT
                text = last.text or str(last)
                msg = ChatMessage(role=role, text=text, author_name=author)
                if self._agent_response_callback:
                    with contextlib.suppress(Exception):
                        await self._agent_response_callback(self._agent_id, msg)
                return msg

            msg = ChatMessage(
                role=ChatRole.ASSISTANT,
                text=f"Agent {self._agent_id}: No output produced",
                author_name=self._agent_id,
            )
            if self._agent_response_callback:
                with contextlib.suppress(Exception):
                    await self._agent_response_callback(self._agent_id, msg)
            return msg

        # 2) Duck-typed invoke(thread) on the wrapped agent
        if hasattr(self._agent, "invoke"):
            logger.debug("Agent %s: Invoking with %d messages", self._agent_id, len(self._chat_history))

            from agent_framework import AgentThread
            from agent_framework._threads import thread_on_new_messages

            thread = AgentThread()
            if self._chat_history:
                await thread_on_new_messages(thread, self._chat_history)

            last_response: Any | None = None
            async for message in self._agent.invoke(thread):  # type: ignore[attr-defined]
                last_response = message  # keep only the last
                logger.debug("Agent %s: Received response: %s", self._agent_id, message)

            if last_response is not None:
                text_val: str | None = None
                author_val: str | None = None
                role_val: ChatRole | None = None

                with contextlib.suppress(Exception):
                    text_val = last_response.text  # type: ignore[assignment, attr-defined]
                if text_val is None:
                    text_val = str(last_response)

                with contextlib.suppress(Exception):
                    author_val = last_response.author_name  # type: ignore[assignment, attr-defined]

                with contextlib.suppress(Exception):
                    role_val = last_response.role  # type: ignore[assignment, attr-defined]
                if role_val is None:
                    role_val = ChatRole.ASSISTANT

                msg2 = ChatMessage(
                    role=role_val or ChatRole.ASSISTANT,
                    text=str(text_val),
                    author_name=author_val or self._agent_id,
                )
                if self._agent_response_callback:
                    with contextlib.suppress(Exception):
                        await self._agent_response_callback(self._agent_id, msg2)
                return msg2

            # Fallback if no response
            msg3 = ChatMessage(
                role=ChatRole.ASSISTANT,
                text=f"Agent {self._agent_id}: Unable to process request",
                author_name=self._agent_id,
            )
            if self._agent_response_callback:
                with contextlib.suppress(Exception):
                    await self._agent_response_callback(self._agent_id, msg3)
            return msg3

        # 3) Fallback for agents without run or invoke
        last_user = next((m for m in reversed(self._chat_history) if m.role == ChatRole.USER), None)
        last_content = last_user.text if last_user else "task"
        msg4 = ChatMessage(
            role=ChatRole.ASSISTANT,
            text=f"Agent {self._agent_id} processed: {last_content[:100]}...",
            author_name=self._agent_id,
        )
        if self._agent_response_callback:
            with contextlib.suppress(Exception):
                await self._agent_response_callback(self._agent_id, msg4)
        return msg4


# endregion Magentic Executors

# region Magentic Workflow Builder


class MagenticWorkflowBuilder:
    """High-level builder for creating Magentic One workflows."""

    def __init__(self) -> None:
        self._participants: dict[str, AgentBase | Executor] = {}
        self._manager: MagenticManagerBase | None = None
        self._exception_callback: Callable[[Exception], None] | None = None
        self._result_callback: Callable[[ChatMessage], Awaitable[None]] | None = None
        self._agent_response_callback: Callable[[str, ChatMessage], Awaitable[None]] | None = None
        self._agent_streaming_callback: Callable[[str, AgentRunResponseUpdate, bool], Awaitable[None]] | None = None

    def participants(self, **participants: AgentBase | Executor) -> Self:
        """Add participants (agents or executors) to the workflow."""
        self._participants.update(participants)
        return self

    def with_manager(self, manager: MagenticManagerBase) -> Self:
        """Set the manager for the workflow."""
        self._manager = manager
        return self

    def with_standard_manager(self, **kwargs: Any) -> Self:
        """Use the standard Magentic manager implementation.

        Pass a real chat_client here along with limits. Example:
            builder.with_standard_manager(chat_client=my_client, max_round_count=10, max_stall_count=3)
        """
        self._manager = StandardMagenticManager(**kwargs)
        return self

    def on_exception(self, callback: Callable[[Exception], None]) -> Self:
        """Set the exception callback."""
        self._exception_callback = callback
        return self

    def on_result(self, callback: Callable[[ChatMessage], Awaitable[None]]) -> Self:
        """Set the result callback."""
        self._result_callback = callback
        return self

    def on_agent_response(self, callback: Callable[[str, ChatMessage], Awaitable[None]]) -> Self:
        """Set a callback to receive final messages from orchestrator and agents."""
        self._agent_response_callback = callback
        return self

    def on_agent_stream(self, callback: Callable[[str, AgentRunResponseUpdate, bool], Awaitable[None]]) -> Self:
        """Set a callback to receive streaming updates from agents when available.

        The callback signature is (agent_id, update, is_final).
        """
        self._agent_streaming_callback = callback
        return self

    def build(self) -> Workflow:
        """Build a Magentic workflow with the orchestrator and all agent executors."""
        if not self._participants:
            raise ValueError("No participants added to Magentic workflow")

        if self._manager is None:
            raise ValueError("No manager configured. Use with_standard_manager(chat_client=...) or with_manager(...)")

        logger.info("Building Magentic workflow with %d participants", len(self._participants))

        # Create participant descriptions
        participant_descriptions: dict[str, str] = {}
        for name, participant in self._participants.items():
            if isinstance(participant, AgentBase):
                description = getattr(participant, "description", None) or f"Agent {name}"
            else:
                description = f"Executor {name}"
            participant_descriptions[name] = description

        # Create orchestrator executor
        orchestrator_executor = MagenticOrchestratorExecutor(
            manager=self._manager,
            participants=participant_descriptions,
            result_callback=self._result_callback,
            agent_response_callback=self._agent_response_callback,
            streaming_agent_response_callback=self._agent_streaming_callback,
        )

        # Create workflow builder and set orchestrator as start
        workflow_builder = WorkflowBuilder().set_start_executor(orchestrator_executor)

        # Add agent executors and connect them
        for name, participant in self._participants.items():
            agent_executor = MagenticAgentExecutor(
                participant,
                name,
                agent_response_callback=self._agent_response_callback,
                streaming_agent_response_callback=self._agent_streaming_callback,
            )

            # Add bidirectional edges between orchestrator and agent
            workflow_builder = workflow_builder.add_edge(orchestrator_executor, agent_executor).add_edge(
                agent_executor, orchestrator_executor
            )

        return workflow_builder.build()


# endregion Magentic Workflow Builder
