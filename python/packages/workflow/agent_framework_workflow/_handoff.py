# # Copyright (c) Microsoft. All rights reserved.

# import logging
# import re

# from agent_framework import (
#     AgentRunResponse,
#     AgentRunResponseUpdate,
#     AIAgent,
#     ChatMessage,
#     ChatRole,
# )

# from ._callback import (
#     AgentDeltaEvent,
#     AgentMessageEvent,
#     CallbackMode,
#     CallbackSink,
#     FinalResultEvent,
# )
# from ._events import AgentRunEvent, AgentRunStreamingEvent, WorkflowCompletedEvent
# from ._executor import (
#     AgentExecutor,
#     AgentExecutorRequest,
#     AgentExecutorResponse,
#     Executor,
#     handler,
# )
# from ._workflow import Workflow, WorkflowBuilder
# from ._workflow_context import WorkflowContext

# logger = logging.getLogger(__name__)


# def _canonical_agent_name(agent: AIAgent) -> str:
#     """Returns a stable name for an agent: prefer `name`, fall back to `id`."""
#     return agent.name or agent.id


# def _parse_handoff_directive(text: str) -> tuple[str, str] | None:
#     """Parse a handoff directive from agent text.

#     Expected formats (case-insensitive, first line is parsed):
#       - HANDOFF TO <agent_name>: <reason>
#       - TRANSFER TO <agent_name>: <reason>

#     Returns (target_name, reason) if found.
#     """
#     if not text:
#         return None
#     first_line = text.splitlines()[0].strip()
#     m = re.match(r"^(?:HANDOFF|TRANSFER)\s+TO\s+([\w\-\.]+)\s*:\s*(.*)$", first_line, flags=re.IGNORECASE)
#     if not m:
#         return None
#     target = m.group(1).strip()
#     reason = m.group(2).strip()
#     return target, reason


# class HandoffOrchestrator(Executor):
#     """Simple handoff orchestrator that routes user input to a starting agent.

#     Agents may request a handoff by beginning their first response line with
#     'HANDOFF TO <agent_name>: <reason>' (or 'TRANSFER TO ...'). Allowed handoffs
#     are constrained by `allow_transfers` configuration.
#     """

#     def __init__(
#         self,
#         *,
#         participants_by_name: dict[str, AIAgent],
#         agent_name_to_exec_id: dict[str, str],
#         allow_transfers: dict[str, list[tuple[str, str]]],  # source -> [(target, description)]
#         start_agent_name: str,
#         id: str = "handoff_orchestrator",
#     ) -> None:
#         super().__init__(id)
#         self._participants_by_name = participants_by_name
#         self._agent_name_to_exec_id = agent_name_to_exec_id
#         self._allow_transfers = allow_transfers
#         self._current_agent = start_agent_name
#         self._last_user_message: ChatMessage | None = None
#         self._unified_callback: CallbackSink | None = None

#     def set_unified_callback(self, callback: CallbackSink | None) -> None:
#         """Set the unified callback for orchestrator-level result emission."""
#         self._unified_callback = callback

#     # region Helpers
#     def _allowed_targets_for(self, agent_name: str) -> list[tuple[str, str]]:
#         return self._allow_transfers.get(agent_name, [])

#     def _render_instruction_for(self, agent_name: str) -> str:
#         allowed = self._allowed_targets_for(agent_name)
#         if not allowed:
#             return (
#                 "You are the responsible agent. Answer the user's request directly. "
#                 "If you cannot address it, conclude with your best effort."
#             )
#         items = "\n".join(f"- {t} — {desc}" for t, desc in allowed)
#         return (
#             "You may transfer the conversation if needed. To transfer, start your first line exactly as:\n"
#             "HANDOFF TO <agent_name>: <brief reason>\n"
#             "Allowed targets and when to use them:\n"
#             f"{items}"
#         )

#     async def _route_to_current(self, ctx: WorkflowContext[AgentExecutorRequest], user_msg: ChatMessage) -> None:
#         self._last_user_message = user_msg
#         instruction = ChatMessage(role=ChatRole.USER, text=self._render_instruction_for(self._current_agent))
#         exec_id = self._agent_name_to_exec_id[self._current_agent]
#         await ctx.send_message(
#             AgentExecutorRequest(messages=[instruction, user_msg], should_respond=True),
#             target_id=exec_id,
#         )

#     # endregion

#     @handler
#     async def handle_start_string(self, message: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
#         logger.info("Handoff: received start string; routing to %s", self._current_agent)
#         await self._route_to_current(ctx, ChatMessage(role=ChatRole.USER, text=message))

#     @handler
#     async def handle_start_message(self, message: ChatMessage, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
#         logger.info("Handoff: received start message; routing to %s", self._current_agent)
#         await self._route_to_current(ctx, message)

#     @handler
#     async def handle_agent_response(
#         self, message: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest]
#     ) -> None:
#         """Handle an agent's response; either transfer or complete."""
#         # Find final assistant message if possible
#         final_msg: ChatMessage | None = None
#         try:
#             for m in reversed(message.agent_run_response.messages):
#                 if isinstance(m, ChatMessage) and m.role == ChatRole.ASSISTANT:
#                     final_msg = m
#                     break
#         except Exception as e:  # pragma: no cover - defensive
#             logger.exception("Handoff: failed to extract final assistant message: %s", e)
#             final_msg = None

#         # If agent requested a handoff, and allowed, transfer
#         if final_msg and isinstance(final_msg.text, str):
#             parsed = _parse_handoff_directive(final_msg.text)
#             if parsed is not None:
#                 target_name, reason = parsed
#                 allowed_targets = [t for t, _ in self._allowed_targets_for(self._current_agent)]
#                 if target_name in allowed_targets and target_name in self._agent_name_to_exec_id:
#                     logger.info("Handoff: %s -> %s (%s)", self._current_agent, target_name, reason)
#                     self._current_agent = target_name
#                     if self._last_user_message is not None:
#                         await self._route_to_current(ctx, self._last_user_message)
#                         return

#         # Otherwise, complete with the agent's final message or a fallback
#         result = final_msg or ChatMessage(
#             role=ChatRole.ASSISTANT,
#             text=f"Agent '{message.executor_id}' produced no assistant message.",
#         )
#         # Surface final result via unified callback if provided
#         if self._unified_callback is not None:
#             try:
#                 await self._unified_callback(FinalResultEvent(message=result))
#             except Exception as e:  # pragma: no cover
#                 logger.exception("Handoff: unified callback failed when sending final result: %s", e)
#         await ctx.add_event(WorkflowCompletedEvent(result))


# class HandoffAgentExecutor(AgentExecutor):
#     """Agent executor for handoff pattern with optional unified streaming callbacks."""

#     # Explicit attributes for type checkers
#     _unified_callback: CallbackSink | None
#     _callback_mode: CallbackMode

#     def __init__(
#         self,
#         agent: AIAgent,
#         *,
#         streaming: bool,
#         unified_callback: CallbackSink | None,
#         callback_mode: CallbackMode | None,
#         id: str | None = None,
#     ) -> None:
#         # Initialize as a standard AgentExecutor
#         super().__init__(agent, streaming=streaming, id=id or agent.id)
#         self._unified_callback = unified_callback
#         self._callback_mode = callback_mode or CallbackMode.STREAMING
#         # cache is initialized by AgentExecutor

#     @handler
#     async def run(
#         self: AgentExecutor,
#         request: AgentExecutorRequest,
#         ctx: WorkflowContext[AgentExecutorResponse],
#     ) -> None:
#         self._cache.extend(request.messages)

#         if not request.should_respond:
#             return

#         agent_id = self._agent.name or self._agent.id

#         # Narrow to subclass for callback attributes
#         if isinstance(self, HandoffAgentExecutor):
#             cb = self._unified_callback
#             mode = self._callback_mode
#         else:  # pragma: no cover - for type checkers only
#             cb = None
#             mode = CallbackMode.STREAMING

#         if self._streaming:
#             updates: list[AgentRunResponseUpdate] = []
#             async for update in self._agent.run_streaming(self._cache, thread=self._agent_thread):
#                 updates.append(update)
#                 await ctx.add_event(AgentRunStreamingEvent(self.id, update))
#                 if cb and mode == CallbackMode.STREAMING:
#                     text_chunk = update.text
#                     if text_chunk:
#                         try:
#                             await cb(AgentDeltaEvent(agent_id=agent_id, text=text_chunk, role=update.role))
#                         except Exception as e:  # pragma: no cover
#                             logger.exception(
#                                 "Handoff: unified callback failed during streaming delta dispatch: %s",
#                                 e,
#                             )
#             response: AgentRunResponse = AgentRunResponse.from_agent_run_response_updates(updates)
#         else:
#             response = await self._agent.run(self._cache, thread=self._agent_thread)
#             await ctx.add_event(AgentRunEvent(self.id, response))

#         # Emit final agent message via unified callback (if any)
#         if cb is not None:
#             try:
#                 # Pick the last assistant message if present
#                 msg = next((m for m in reversed(response.messages) if isinstance(m, ChatMessage)), None)
#                 await cb(AgentMessageEvent(agent_id=agent_id, message=msg))
#             except Exception as e:  # pragma: no cover
#                 logger.exception("Handoff: unified callback failed for final agent message: %s", e)

#         await ctx.send_message(AgentExecutorResponse(self.id, response))
#         self._cache.clear()


# class HandoffBuilder:
#     """Builder for a simple handoff workflow among AIAgents.

#     Usage:
#         HandoffBuilder()
#           .participants([triage, refund, order, support])
#           .allow_transfers({
#               "refund": [("support", "non-refund issues")],
#               "order": [("support", "non-order issues")],
#           })
#           .build()
#     """

#     def __init__(self) -> None:
#         self._participants: list[AIAgent] = []
#         self._allow_transfers: dict[str, list[tuple[str, str]]] = {}
#         self._start_agent_name: str | None = None
#         self._unified_callback: CallbackSink | None = None
#         self._callback_mode: CallbackMode | None = None

#     def participants(self, participants: list[AIAgent]) -> "HandoffBuilder":
#         # enforce AIAgent types at runtime (Protocol is runtime_checkable)
#         for a in participants:
#             if not isinstance(a, AIAgent):
#                 raise TypeError("HandoffBuilder.participants only supports AIAgent instances")
#         self._participants = list(participants)
#         return self

#     def start_with(self, agent: str | AIAgent) -> "HandoffBuilder":
#         self._start_agent_name = _canonical_agent_name(agent) if isinstance(agent, AIAgent) else agent
#         return self

#     def allow_transfers(self, transfers: dict[str, list[tuple[str, str]]]) -> "HandoffBuilder":
#         self._allow_transfers = dict(transfers)
#         return self

#     def on_event(self, callback: CallbackSink, *, mode: CallbackMode = CallbackMode.STREAMING) -> "HandoffBuilder":
#         """Register a unified callback for streaming deltas and final agent messages."""
#         self._unified_callback = callback
#         self._callback_mode = mode
#         return self

#     def build(self) -> Workflow:
#         if not self._participants:
#             raise ValueError("No participants configured. Call participants([...]) with AIAgent instances.")

#         # Resolve names and maps
#         by_name: dict[str, AIAgent] = {_canonical_agent_name(a): a for a in self._participants}
#         name_to_exec_id: dict[str, str] = {name: agent.id for name, agent in by_name.items()}

#         # Validate transfers refer to known names
#         for src, targets in self._allow_transfers.items():
#             if src not in by_name:
#                 raise ValueError(f"allow_transfers refers to unknown agent '{src}'")
#             for tgt, _ in targets:
#                 if tgt not in by_name:
#                     raise ValueError(f"allow_transfers target '{tgt}' not among participants")

#         start_name = self._start_agent_name or next(iter(by_name.keys()))
#         if start_name not in by_name:
#             raise ValueError(f"Starting agent '{start_name}' is not among participants")

#         # Create orchestrator
#         orchestrator = HandoffOrchestrator(
#             participants_by_name=by_name,
#             agent_name_to_exec_id=name_to_exec_id,
#             allow_transfers=self._allow_transfers,
#             start_agent_name=start_name,
#         )
#         # attach unified callback for final result via public API
#         orchestrator.set_unified_callback(self._unified_callback)

#         # Build workflow graph
#         wb = WorkflowBuilder().set_start_executor(orchestrator)

#         # Add agent executors and connect edges
#         for _, agent in by_name.items():
#             agent_exec = HandoffAgentExecutor(
#                 agent,
#                 streaming=(self._callback_mode == CallbackMode.STREAMING),
#                 unified_callback=self._unified_callback,
#                 callback_mode=self._callback_mode,
#                 id=agent.id,
#             )
#             # Orchestrator -> agent (requests)
#             wb = wb.add_edge(orchestrator, agent_exec)
#             # Agent -> orchestrator (responses)
#             wb = wb.add_edge(agent_exec, orchestrator)

#         return wb.build()


# __all__ = ["HandoffBuilder"]

# Copyright (c) Microsoft. All rights reserved.

# Copyright (c) Microsoft. All rights reserved.

import logging
import re
from dataclasses import dataclass
from typing import Callable

from agent_framework import (
    AgentRunResponse,
    AgentRunResponseUpdate,
    AIAgent,
    ChatMessage,
    ChatRole,
)

from ._callback import (
    AgentDeltaEvent,
    AgentMessageEvent,
    CallbackMode,
    CallbackSink,
    FinalResultEvent,
)
from ._events import AgentRunEvent, AgentRunStreamingEvent, WorkflowCompletedEvent
from ._executor import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    RequestInfoMessage,
    RequestResponse,
    handler,
)
from ._workflow import RequestInfoExecutor, Workflow, WorkflowBuilder
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)

HANDOFF_PLUGIN_NAME = "Handoff"


# region Helpers and parsing


def _canonical_agent_name(agent: AIAgent | str) -> str:
    """Return a stable name for an agent. Prefer `name`, fall back to `id`, or pass-through if str."""
    if isinstance(agent, str):
        return agent
    return agent.name or agent.id


def _parse_handoff_directive(text: str) -> tuple[str, str] | None:
    """Parse classic text directive from the first line:
       HANDOFF TO <agent_name>: <reason>
       TRANSFER TO <agent_name>: <reason>
    Returns (target_name, reason) if found.
    """
    if not text:
        return None
    first_line = text.splitlines()[0].strip()
    m = re.match(
        r"^(?:HANDOFF|TRANSFER)\s+TO\s+([\w\-.]+)\s*:\s*(.*)$",
        first_line,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    target = m.group(1).strip()
    reason = m.group(2).strip()
    return target, reason


def _parse_handoff_function(text: str) -> tuple[str, str] | None:
    """Parse function-like handoff on the first line, inspired by SK's virtual functions.

    Accepted forms (case-insensitive):
      - transfer_to_<agent>()
      - transfer_to_<agent>: <reason>
      - Handoff.transfer_to_<agent>()
      - Handoff.transfer_to_<agent>: <reason>
    Returns (target_name, reason) if found.
    """
    if not text:
        return None
    first = text.splitlines()[0].strip()

    m = re.match(
        r"^(?:handoff\.)?transfer_to_([\w\-.]+)\s*(?:\(\s*\))?\s*(?::\s*(.*))?$",
        first,
        flags=re.IGNORECASE,
    )
    if not m:
        return None
    target = m.group(1).strip()
    reason = (m.group(2) or "").strip()
    return target, reason


def _parse_complete_task(text: str) -> str | None:
    """Parse a completion directive from the first line.

    Accepted forms (case-insensitive):
      - complete_task: <summary>
      - complete: <summary>
      - Handoff.complete_task(<summary>)    Parentheses and quotes optional
    Returns the summary string if found.
    """
    if not text:
        return None
    first = text.splitlines()[0].strip()

    m = re.match(r"^(?:complete_task|complete)\s*:\s*(.+)$", first, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()

    m = re.match(
        r"^(?:handoff\.)?complete_task\s*\(\s*[\"']?(.*?)[\"']?\s*\)\s*$",
        first,
        flags=re.IGNORECASE,
    )
    if m:
        return m.group(1).strip()

    return None


# endregion


# region OrchestrationHandoffs

AgentHandoffs = dict[str, str]


class OrchestrationHandoffs(dict[str, AgentHandoffs]):
    """Mapping of agent name to {target_agent_name: description}."""

    def add(
        self,
        source_agent: str | AIAgent,
        target_agent: str | AIAgent,
        description: str | None = None,
    ) -> "OrchestrationHandoffs":
        src = _canonical_agent_name(source_agent)
        tgt = _canonical_agent_name(target_agent)
        desc = (description or getattr(target_agent, "description", "") or "").strip()
        self.setdefault(src, AgentHandoffs())[tgt] = desc
        return self

    def add_many(
        self,
        source_agent: str | AIAgent,
        target_agents: list[str | AIAgent] | AgentHandoffs,
    ) -> "OrchestrationHandoffs":
        src = _canonical_agent_name(source_agent)
        if isinstance(target_agents, dict):
            for tgt, desc in target_agents.items():
                self.add(src, tgt, desc)
        else:
            for tgt in target_agents:
                self.add(src, tgt, None)
        return self


def _normalize_allow_transfers(
    transfers: dict[str, list[tuple[str, str]]] | OrchestrationHandoffs | dict[str, dict[str, str]] | None,
) -> dict[str, list[tuple[str, str]]]:
    """Normalize all supported allow_transfers shapes into {src: [(tgt, desc), ...]}."""
    if not transfers:
        return {}

    # Already normalized
    if isinstance(transfers, dict) and transfers and isinstance(next(iter(transfers.values())), list):
        return transfers  # type: ignore[return-value]

    # OrchestrationHandoffs or dict[str, dict[str, str]]
    out: dict[str, list[tuple[str, str]]] = {}
    for src, mapping in transfers.items():  # type: ignore[assignment]
        items = []
        for tgt, desc in mapping.items():  # type: ignore[union-attr]
            items.append((tgt, desc or ""))
        out[src] = items
    return out


# endregion


# region Human-in-the-loop (HITL)


@dataclass
class HandoffHumanRequest(RequestInfoMessage):
    """RequestInfo payload used by the handoff orchestrator when asking a human for input."""

    prompt: str
    agent: str
    preview: str | None = None


# endregion


class HandoffOrchestrator(Executor):
    """Handoff orchestrator that routes user input to a starting agent.

    Aligns with the Semantic Kernel handoff pattern. Agents can:
      1) Request a handoff on the first line via a function-like directive:
         transfer_to_<agent> or Handoff.transfer_to_<agent> (optionally with a reason after a colon).
      2) Use the classic directive:
         HANDOFF TO <agent>: <reason>
      3) Signal completion with:
         complete_task: <summary> or Handoff.complete_task(<summary>)

    If human-in-the-loop is enabled, the orchestrator can emit a RequestInfo request to collect
    human input and then route that reply back to the current agent.
    """

    def __init__(
        self,
        *,
        participants_by_name: dict[str, AIAgent],
        agent_name_to_exec_id: dict[str, str],
        allow_transfers: dict[str, list[tuple[str, str]]],
        start_agent_name: str,
        id: str = "handoff_orchestrator",
        seed_all_on_start: bool = True,
        max_handoffs: int = 8,
        # HITL configuration
        hitl_enabled: bool = False,
        hitl_executor_id: str | None = None,
        hitl_prompt_builder: Callable[[str, str], str] | None = None,
        hitl_ask_condition: str | Callable[[str, str], bool] | None = None,
    ) -> None:
        super().__init__(id)
        self._participants_by_name = participants_by_name
        self._agent_name_to_exec_id = agent_name_to_exec_id
        self._allow_transfers = allow_transfers
        self._current_agent = start_agent_name
        self._last_user_message: ChatMessage | None = None
        self._unified_callback: CallbackSink | None = None
        self._seed_all_on_start = seed_all_on_start
        self._seeded_once = False
        self._handoff_count = 0
        self._max_handoffs = max_handoffs
        self._handoff_trace: list[str] = [start_agent_name]

        # HITL
        self._hitl_enabled = bool(hitl_enabled)
        self._hitl_executor_id = hitl_executor_id
        self._hitl_prompt_builder = hitl_prompt_builder or self._default_hitl_prompt
        self._hitl_ask_condition = hitl_ask_condition or "if_question"

    # region Orchestrator API

    def set_unified_callback(self, callback: CallbackSink | None) -> None:
        """Set the unified callback for orchestrator-level result emission."""
        self._unified_callback = callback

    # endregion

    # region Private helpers

    def _allowed_targets_for(self, agent_name: str) -> list[tuple[str, str]]:
        return self._allow_transfers.get(agent_name, [])

    def _render_instruction_for(self, agent_name: str) -> str:
        """Render a concise instruction payload for a specific agent."""
        allowed = self._allowed_targets_for(agent_name)
        if not allowed:
            return (
                "You are the responsible agent. Answer the user's request directly. "
                "If you cannot address it, reply with your best effort."
            )

        bullet_lines = "\n".join(f"- {t}: {desc}".rstrip() for t, desc in allowed)

        return (
            "Handoff rules for this conversation:\n"
            "1) To handoff, put one of the following on the first line and then stop:\n"
            "   - transfer_to_<agent_name>  (optionally append ': <brief reason>')\n"
            "   - Handoff.transfer_to_<agent_name>\n"
            "   - You may also use the classic form 'HANDOFF TO <agent_name>: <brief reason>'\n"
            "2) To finish, put 'complete_task: <one-line summary>' on the first line.\n"
            "Allowed targets for you and when to use them:\n"
            f"{bullet_lines}"
        )

    async def _seed_all(self, ctx: WorkflowContext[AgentExecutorRequest], user_msg: ChatMessage) -> None:
        """Seed each participant with the user's input and its routing instructions without requesting a response."""
        for name, exec_id in self._agent_name_to_exec_id.items():
            instr = ChatMessage(role=ChatRole.USER, text=self._render_instruction_for(name))
            await ctx.send_message(
                AgentExecutorRequest(messages=[instr, user_msg], should_respond=False),
                target_id=exec_id,
            )

    async def _route_to_current(self, ctx: WorkflowContext[AgentExecutorRequest], user_msg: ChatMessage) -> None:
        """Route the request to the current agent with a tailored instruction preamble."""
        self._last_user_message = user_msg
        instruction = ChatMessage(role=ChatRole.USER, text=self._render_instruction_for(self._current_agent))
        exec_id = self._agent_name_to_exec_id[self._current_agent]
        await ctx.send_message(
            AgentExecutorRequest(messages=[instruction, user_msg], should_respond=True),
            target_id=exec_id,
        )

    def _extract_final_assistant_message(self, response: AgentRunResponse) -> ChatMessage | None:
        """Pick the final assistant ChatMessage from an AgentRunResponse."""
        try:
            for m in reversed(response.messages):
                if isinstance(m, ChatMessage) and m.role == ChatRole.ASSISTANT:
                    return m
        except Exception as e:  # pragma: no cover
            logger.exception("Handoff: failed to extract final assistant message: %s", e)
        return None

    def _default_hitl_prompt(self, agent_name: str, agent_text: str) -> str:
        return (
            f"The '{agent_name}' agent requests more information:\n\n"
            f"{agent_text}\n\n"
            "Reply with your answer in plain text."
        )

    def _should_request_human(self, agent_name: str, text: str) -> bool:
        if not self._hitl_enabled or not self._hitl_executor_id:
            return False
        if not text or not text.strip():
            return False

        cond = self._hitl_ask_condition
        if callable(cond):
            try:
                return bool(cond(agent_name, text))
            except Exception:  # pragma: no cover
                logger.exception("Handoff: custom HITL condition raised")
                return False

        # Built-in modes
        norm = (cond or "").lower()
        if norm == "always":
            return True
        if norm == "if_question":
            return text.strip().endswith("?")
        if norm == "heuristic":
            low = text.lower()
            cues = [
                "could you",
                "can you",
                "please provide",
                "what is",
                "would you",
                "may i have",
                "i need your",
                "which order",
                "what's your",
            ]
            return text.strip().endswith("?") or any(c in low for c in cues)

        return False

    # endregion

    # region Workflow handlers

    async def _start_with_user(self, ctx: WorkflowContext[AgentExecutorRequest], user_msg: ChatMessage) -> None:
        logger.info("Handoff: start. Current=%s", self._current_agent)
        if self._seed_all_on_start and not self._seeded_once:
            await self._seed_all(ctx, user_msg)
            self._seeded_once = True
        await self._route_to_current(ctx, user_msg)

    @handler
    async def handle_start_string(self, message: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        await self._start_with_user(ctx, ChatMessage(role=ChatRole.USER, text=message))

    @handler
    async def handle_start_message(self, message: ChatMessage, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        await self._start_with_user(ctx, message)

    @handler
    async def handle_agent_response(
        self, message: AgentExecutorResponse, ctx: WorkflowContext[AgentExecutorRequest | HandoffHumanRequest]
    ) -> None:
        """Handle an agent's response, detect handoff or completion, otherwise trigger HITL or finalize."""
        response = message.agent_run_response
        final_msg = self._extract_final_assistant_message(response)

        # First line for parsing
        text = final_msg.text if final_msg and isinstance(final_msg.text, str) else ""

        # Try function-form handoff first, then classic directive
        parsed = _parse_handoff_function(text) or _parse_handoff_directive(text)
        complete_summary = _parse_complete_task(text)

        # Completion directive
        if complete_summary is not None:
            logger.info("Handoff: %s signaled completion", self._current_agent)
            result = ChatMessage(
                role=ChatRole.ASSISTANT,
                text=f"Task completed. Summary: {complete_summary}",
            )
            if self._unified_callback is not None:
                try:
                    await self._unified_callback(FinalResultEvent(message=result))
                except Exception as e:  # pragma: no cover
                    logger.exception("Handoff: unified callback failed on completion: %s", e)
            await ctx.add_event(WorkflowCompletedEvent(result))
            return

        # Handoff directive
        if parsed is not None:
            target_name, reason = parsed
            allowed_targets = [t for t, _ in self._allowed_targets_for(self._current_agent)]
            if target_name in allowed_targets and target_name in self._agent_name_to_exec_id:
                if target_name == self._current_agent:
                    logger.warning("Handoff: %s attempted self-transfer; ignoring", self._current_agent)
                else:
                    self._handoff_count += 1
                    logger.info("Handoff: %s -> %s (%s)", self._current_agent, target_name, reason or "no reason")
                    self._current_agent = target_name
                    self._handoff_trace.append(target_name)

                    if self._handoff_count > self._max_handoffs:
                        logger.error("Handoff: exceeded max handoffs. Trace=%s", " -> ".join(self._handoff_trace))
                        fail_msg = ChatMessage(
                            role=ChatRole.ASSISTANT,
                            text=(
                                "Could not resolve within the allowed number of transfers. "
                                f"Path taken: {' -> '.join(self._handoff_trace)}"
                            ),
                        )
                        if self._unified_callback is not None:
                            try:
                                await self._unified_callback(FinalResultEvent(message=fail_msg))
                            except Exception as e:  # pragma: no cover
                                logger.exception("Handoff: unified callback failed on overflow: %s", e)
                        await ctx.add_event(WorkflowCompletedEvent(fail_msg))
                        return

                    # Re-route the original user message to the new current agent
                    if self._last_user_message is not None:
                        await self._route_to_current(ctx, self._last_user_message)
                        return
            else:
                logger.info(
                    "Handoff: target '%s' not allowed from '%s' or unknown. Allowed=%s",
                    target_name,
                    self._current_agent,
                    allowed_targets,
                )

        # No handoff and not completed. Decide whether to ask a human or to finalize.
        if self._should_request_human(self._current_agent, text):
            prompt = self._hitl_prompt_builder(self._current_agent, text)
            if self._hitl_executor_id:
                logger.info("Handoff: requesting human input for agent '%s'", self._current_agent)
                await ctx.send_message(
                    HandoffHumanRequest(prompt=prompt, agent=self._current_agent, preview=text[:1000] or None),
                    target_id=self._hitl_executor_id,
                )
                return

        # Otherwise, finalize with the agent's final message or a fallback
        result = final_msg or ChatMessage(
            role=ChatRole.ASSISTANT,
            text=f"Agent '{message.executor_id}' produced no assistant message.",
        )

        if self._unified_callback is not None:
            try:
                await self._unified_callback(FinalResultEvent(message=result))
            except Exception as e:  # pragma: no cover
                logger.exception("Handoff: unified callback failed when sending final result: %s", e)

        await ctx.add_event(WorkflowCompletedEvent(result))

    @handler
    async def handle_human_feedback(
        self,
        feedback: RequestResponse[HandoffHumanRequest, str],
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        """Receive human input and route it back to the current agent."""
        reply = (feedback.data or "").strip()
        if not reply:
            logger.info("Handoff: empty human response. Ignoring.")
            return

        user_msg = ChatMessage(role=ChatRole.USER, text=reply)
        await self._route_to_current(ctx, user_msg)

    # endregion


class HandoffAgentExecutor(AgentExecutor):
    """Agent executor for the handoff pattern with unified streaming callbacks."""

    _unified_callback: CallbackSink | None
    _callback_mode: CallbackMode

    def __init__(
        self,
        agent: AIAgent,
        *,
        streaming: bool,
        unified_callback: CallbackSink | None,
        callback_mode: CallbackMode | None,
        id: str | None = None,
    ) -> None:
        super().__init__(agent, streaming=streaming, id=id or agent.id)
        self._unified_callback = unified_callback
        self._callback_mode = callback_mode or CallbackMode.STREAMING

    @handler
    async def run(
        self: "HandoffAgentExecutor",
        request: AgentExecutorRequest,
        ctx: WorkflowContext[AgentExecutorResponse],
    ) -> None:
        # Seed cache
        self._cache.extend(request.messages)

        if not request.should_respond:
            return

        agent_id = self._agent.name or self._agent.id

        cb = self._unified_callback
        mode = self._callback_mode

        if self._streaming:
            updates: list[AgentRunResponseUpdate] = []
            async for update in self._agent.run_streaming(self._cache, thread=self._agent_thread):
                updates.append(update)
                await ctx.add_event(AgentRunStreamingEvent(self.id, update))
                if cb and mode == CallbackMode.STREAMING:
                    text_chunk = update.text
                    if text_chunk:
                        try:
                            await cb(AgentDeltaEvent(agent_id=agent_id, text=text_chunk, role=update.role))
                        except Exception as e:  # pragma: no cover
                            logger.exception(
                                "Handoff: unified callback failed during streaming delta dispatch: %s",
                                e,
                            )
            response: AgentRunResponse = AgentRunResponse.from_agent_run_response_updates(updates)
        else:
            response = await self._agent.run(self._cache, thread=self._agent_thread)
            await ctx.add_event(AgentRunEvent(self.id, response))

        if cb is not None:
            try:
                msg = next((m for m in reversed(response.messages) if isinstance(m, ChatMessage)), None)
                await cb(AgentMessageEvent(agent_id=agent_id, message=msg))
            except Exception as e:  # pragma: no cover
                logger.exception("Handoff: unified callback failed for final agent message: %s", e)

        await ctx.send_message(AgentExecutorResponse(self.id, response))
        self._cache.clear()


class HandoffBuilder:
    """Builder for a handoff workflow among AIAgents, aligned with SK semantics."""

    def __init__(self) -> None:
        self._participants: list[AIAgent] = []
        self._allow_transfers: dict[str, list[tuple[str, str]]] = {}
        self._start_agent_name: str | None = None
        self._unified_callback: CallbackSink | None = None
        self._callback_mode: CallbackMode | None = None
        self._seed_all_on_start: bool = True
        self._max_handoffs: int = 8

        # HITL config
        self._hitl_enabled: bool = False
        self._hitl_executor_id: str = "request_info"
        self._hitl_prompt_builder: Callable[[str, str], str] | None = None
        self._hitl_ask_condition: str | Callable[[str, str], bool] = "if_question"

    # Participants

    def participants(self, participants: list[AIAgent]) -> "HandoffBuilder":
        for a in participants:
            if not isinstance(a, AIAgent):
                raise TypeError("HandoffBuilder.participants only supports AIAgent instances")
        self._participants = list(participants)
        return self

    def start_with(self, agent: str | AIAgent) -> "HandoffBuilder":
        self._start_agent_name = _canonical_agent_name(agent)
        return self

    # Transfers configuration

    def handoffs(self, handoffs: OrchestrationHandoffs | dict[str, dict[str, str]]) -> "HandoffBuilder":
        self._allow_transfers = _normalize_allow_transfers(handoffs)
        return self

    def allow_transfers(self, transfers: dict[str, list[tuple[str, str]]]) -> "HandoffBuilder":
        self._allow_transfers = _normalize_allow_transfers(transfers)
        return self

    # Callbacks

    def on_event(self, callback: CallbackSink, *, mode: CallbackMode = CallbackMode.STREAMING) -> "HandoffBuilder":
        self._unified_callback = callback
        self._callback_mode = mode
        return self

    # Orchestration knobs

    def seed_all_on_start(self, value: bool) -> "HandoffBuilder":
        self._seed_all_on_start = bool(value)
        return self

    def max_handoffs(self, value: int) -> "HandoffBuilder":
        if value < 0:
            raise ValueError("max_handoffs must be non-negative")
        self._max_handoffs = int(value)
        return self

    # HITL

    def enable_human_in_the_loop(
        self,
        *,
        executor_id: str = "request_info",
        ask: str | Callable[[str, str], bool] = "if_question",
        prompt_builder: Callable[[str, str], str] | None = None,
    ) -> "HandoffBuilder":
        """Enable human-in-the-loop.

        Args:
            executor_id: Workflow id for the RequestInfoExecutor node to be created.
            ask: When to ask a human. Supported strings are "if_question", "always", "heuristic".
                 A callable(agent_name, agent_text) -> bool can be provided for custom logic.
            prompt_builder: Callable(agent_name, agent_text) -> prompt string.
        """
        self._hitl_enabled = True
        self._hitl_executor_id = executor_id
        self._hitl_ask_condition = ask
        self._hitl_prompt_builder = prompt_builder
        return self

    # Build

    def build(self) -> Workflow:
        if not self._participants:
            raise ValueError("No participants configured. Call participants([...]) with AIAgent instances.")

        by_name: dict[str, AIAgent] = {_canonical_agent_name(a): a for a in self._participants}
        name_to_exec_id: dict[str, str] = {name: agent.id for name, agent in by_name.items()}

        # Validate transfers refer to known names
        for src, targets in self._allow_transfers.items():
            if src not in by_name:
                raise ValueError(f"allow_transfers refers to unknown agent '{src}'")
            for tgt, _ in targets:
                if tgt not in by_name:
                    raise ValueError(f"allow_transfers target '{tgt}' not among participants")
                if tgt == src:
                    raise ValueError(f"Agent '{src}' cannot handoff to itself")

        start_name = self._start_agent_name or next(iter(by_name.keys()))
        if start_name not in by_name:
            raise ValueError(f"Starting agent '{start_name}' is not among participants")

        # Orchestrator
        orchestrator = HandoffOrchestrator(
            participants_by_name=by_name,
            agent_name_to_exec_id=name_to_exec_id,
            allow_transfers=self._allow_transfers,
            start_agent_name=start_name,
            seed_all_on_start=self._seed_all_on_start,
            max_handoffs=self._max_handoffs,
            hitl_enabled=self._hitl_enabled,
            hitl_executor_id=self._hitl_executor_id if self._hitl_enabled else None,
            hitl_prompt_builder=self._hitl_prompt_builder,
            hitl_ask_condition=self._hitl_ask_condition,
        )
        orchestrator.set_unified_callback(self._unified_callback)

        # Build workflow graph
        wb = WorkflowBuilder().set_start_executor(orchestrator)

        # Optionally add the RequestInfoExecutor for HITL and connect edges
        hitl_exec: RequestInfoExecutor | None = None
        if self._hitl_enabled:
            hitl_exec = RequestInfoExecutor(id=self._hitl_executor_id)
            wb = wb.add_edge(orchestrator, hitl_exec)  # Orchestrator -> HITL
            wb = wb.add_edge(hitl_exec, orchestrator)  # HITL -> Orchestrator

        # Add agent executors and connect edges
        for _, agent in by_name.items():
            agent_exec = HandoffAgentExecutor(
                agent,
                streaming=(self._callback_mode == CallbackMode.STREAMING),
                unified_callback=self._unified_callback,
                callback_mode=self._callback_mode,
                id=agent.id,
            )
            wb = wb.add_edge(orchestrator, agent_exec)  # Orchestrator -> Agent
            wb = wb.add_edge(agent_exec, orchestrator)  # Agent -> Orchestrator

        return wb.build()


__all__ = [
    "AgentHandoffs",
    "HandoffBuilder",
    "HandoffHumanRequest",
    "OrchestrationHandoffs",
]
