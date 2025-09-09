# Copyright (c) Microsoft. All rights reserved.

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import cast

from agent_framework import AgentProtocol, AgentRunResponse, ChatMessage, Role
from agent_framework._pydantic import AFBaseModel
from pydantic import Field

from ._callback import CallbackMode, CallbackSink, FinalResultEvent
from ._events import WorkflowCompletedEvent
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


class HandoffAction(str, Enum):
    HANDOFF = "handoff"
    RESPOND = "respond"
    COMPLETE = "complete"
    ASK_HUMAN = "ask_human"


class HandoffDecision(AFBaseModel):
    """Typed decision emitted by an agent when running in decision-probe mode.

    action:
      - handoff: switch to another agent. requires target.
      - respond: return assistant_message to user.
      - complete: finish orchestration with summary.
      - ask_human: escalate to human in the loop.
    """

    action: HandoffAction = Field(..., description="Routing action for the orchestrator")
    target: str | None = Field(default=None, description="Target agent name when action=='handoff'")
    reason: str | None = Field(default=None, description="Short reason for handoff")
    summary: str | None = Field(default=None, description="One-line summary when completing")
    assistant_message: str | None = Field(default=None, description="Assistant reply when action=='respond'")


def _canonical_agent_name(agent: AgentProtocol | str) -> str:
    if isinstance(agent, str):
        return agent
    return agent.name or agent.id


def _parse_handoff_directive(text: str) -> tuple[str, str] | None:
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
    if not text:
        return None
    first = text.splitlines()[0].strip()
    m = re.match(r"^(?:complete_task|complete)\s*:\s*(.+)$", first, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.match(r"^(?:handoff\.)?complete_task\s*\(\s*[\"']?(.*?)[\"']?\s*\)\s*$", first, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


AgentHandoffs = dict[str, str]


class OrchestrationHandoffs(dict[str, AgentHandoffs]):
    """Mapping of agent name to {target_agent_name: description}."""

    def add(
        self,
        source_agent: str | AgentProtocol,
        target_agent: str | AgentProtocol,
        description: str | None = None,
    ) -> "OrchestrationHandoffs":
        src = _canonical_agent_name(source_agent)
        tgt = _canonical_agent_name(target_agent)
        desc = (description or getattr(target_agent, "description", "") or "").strip()
        self.setdefault(src, AgentHandoffs())[tgt] = desc
        return self

    def add_many(
        self,
        source_agent: str | AgentProtocol,
        target_agents: list[str | AgentProtocol] | AgentHandoffs,
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
    if not transfers:
        return {}
    if isinstance(transfers, dict) and transfers and isinstance(next(iter(transfers.values())), list):
        return transfers  # type: ignore[return-value]
    out: dict[str, list[tuple[str, str]]] = {}
    for src, mapping in transfers.items():  # type: ignore[assignment]
        items = []
        for tgt, desc in mapping.items():  # type: ignore[union-attr]
            items.append((tgt, desc or ""))
        out[src] = items
    return out


@dataclass
class HandoffHumanRequest(RequestInfoMessage):
    prompt: str
    agent: str
    preview: str | None = None


class HandoffOrchestrator(Executor):
    """Handoff orchestrator with two decision mechanisms.

    1) Structured mode. Send a one-shot decision probe with response_format=HandoffDecision.
    2) Legacy mode. Parse first-line directives if the provider ignores response_format.
    """

    def __init__(
        self,
        *,
        participants_by_name: dict[str, AgentProtocol],
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
        # Structured decision mode
        structured_decision: bool = False,
        decision_model: type[AFBaseModel] = HandoffDecision,
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

        # Structured
        self._structured_decision = bool(structured_decision)
        self._decision_model = decision_model
        self._decision_phase = False  # True when awaiting a structured decision from current agent

    # Orchestrator API

    def set_unified_callback(self, callback: CallbackSink | None) -> None:
        self._unified_callback = callback

    # Private helpers

    def _allowed_targets_for(self, agent_name: str) -> list[tuple[str, str]]:
        return self._allow_transfers.get(agent_name, [])

    def _render_instruction_for(self, agent_name: str) -> str:
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

    def _render_structured_prompt_for(self, agent_name: str) -> str:
        """Short prompt that explains the JSON decision. We rely on response_format to enforce shape."""
        allowed = self._allowed_targets_for(agent_name)
        lines = "\n".join(f"- {t}: {desc}".rstrip() for t, desc in allowed) or "(none)"
        return (
            "Decide the next routing step for this conversation and output only a decision object. "
            "Use the fields action, target, reason, summary, assistant_message. "
            "Allowed actions: 'handoff', 'respond', 'complete', 'ask_human'.\n"
            "Rules:\n"
            "- If you need a specialist, set action='handoff' and target to one of the allowed targets below.\n"
            "- If you can answer directly and should respond now, set action='respond' and fill assistant_message.\n"
            "- If the task is finished, set action='complete' and provide a one-line summary.\n"
            "- If you must ask a human a question, set action='ask_human' and set assistant_message to that question.\n"
            "Allowed targets for handoff:\n"
            f"{lines}"
        )

    async def _seed_all(self, ctx: WorkflowContext[AgentExecutorRequest], user_msg: ChatMessage) -> None:
        for name, exec_id in self._agent_name_to_exec_id.items():
            instr = ChatMessage(role=Role.USER, text=self._render_instruction_for(name))
            await ctx.send_message(
                AgentExecutorRequest(messages=[instr, user_msg], should_respond=False),
                target_id=exec_id,
            )

    async def _route_to_current(
        self,
        ctx: WorkflowContext[AgentExecutorRequest],
        user_msg: ChatMessage,
        *,
        decision_probe: bool | None = None,
    ) -> None:
        """Route to the current agent either for a structured decision or for normal content."""
        self._last_user_message = user_msg
        use_probe = self._structured_decision if decision_probe is None else decision_probe

        if use_probe:
            self._decision_phase = True
            probe_instr = ChatMessage(role=Role.USER, text=self._render_structured_prompt_for(self._current_agent))
            exec_id = self._agent_name_to_exec_id[self._current_agent]
            await ctx.send_message(
                AgentExecutorRequest(
                    messages=[probe_instr, user_msg],
                    should_respond=True,
                    response_format_model=self._decision_model,
                ),
                target_id=exec_id,
            )
            return

        # normal content turn
        self._decision_phase = False
        instruction = ChatMessage(role=Role.USER, text=self._render_instruction_for(self._current_agent))
        exec_id = self._agent_name_to_exec_id[self._current_agent]
        await ctx.send_message(
            AgentExecutorRequest(messages=[instruction, user_msg], should_respond=True),
            target_id=exec_id,
        )

    def _extract_final_assistant_message(self, response: AgentRunResponse) -> ChatMessage | None:
        try:
            for m in reversed(response.messages):
                if isinstance(m, ChatMessage) and m.role == Role.ASSISTANT:
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

    def _try_parse_structured_decision(self, response: AgentRunResponse) -> HandoffDecision | None:
        """Attempt to parse a HandoffDecision from the final assistant message. Fall back to None."""
        msg = self._extract_final_assistant_message(response)
        if not msg or not msg.text:
            return None
        text = msg.text.strip()

        # If provider honored response_format, content is usually pure JSON
        # Try direct parse
        try:
            return HandoffDecision.model_validate_json(text)
        except Exception:
            logger.exception("Handoff: exception while parsing structured decision JSON block")

        # Try to extract first JSON object substring
        try:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                candidate = text[start : end + 1]
                return HandoffDecision.model_validate_json(candidate)
        except Exception:
            return None
        return None

    # Workflow handlers

    async def _start_with_user(self, ctx: WorkflowContext[AgentExecutorRequest], user_msg: ChatMessage) -> None:
        logger.info("Handoff: start. Current=%s", self._current_agent)
        if self._seed_all_on_start and not self._seeded_once:
            await self._seed_all(ctx, user_msg)
            self._seeded_once = True
        await self._route_to_current(ctx, user_msg)

    @handler
    async def handle_start_string(self, message: str, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        await self._start_with_user(ctx, ChatMessage(role=Role.USER, text=message))

    @handler
    async def handle_start_message(self, message: ChatMessage, ctx: WorkflowContext[AgentExecutorRequest]) -> None:
        await self._start_with_user(ctx, message)

    @handler
    async def handle_agent_response(
        self,
        message: AgentExecutorResponse,
        ctx: WorkflowContext[AgentExecutorRequest | HandoffHumanRequest],
    ) -> None:
        response = message.agent_run_response
        final_msg = self._extract_final_assistant_message(response)
        text = final_msg.text if final_msg and isinstance(final_msg.text, str) else ""

        # Structured decision phase
        if self._structured_decision and self._decision_phase:
            self._decision_phase = False
            decision = self._try_parse_structured_decision(response)

            if decision is not None:
                logger.info("Handoff: structured decision %s", decision.action.value)

                if decision.action == HandoffAction.COMPLETE:
                    # Include both assistant_message (if any) and summary for richer final output
                    summary_part = (decision.summary or "").strip()
                    assistant_part = (decision.assistant_message or "").strip()
                    if assistant_part and summary_part and assistant_part != summary_part:
                        final_text = f"{assistant_part}\n\nSummary: {summary_part}".strip()
                    elif summary_part:
                        final_text = f"Task completed. Summary: {summary_part}".strip()
                    else:
                        final_text = assistant_part or "Task completed."
                    result = ChatMessage(role=Role.ASSISTANT, text=final_text)
                    if self._unified_callback is not None:
                        try:
                            await self._unified_callback(FinalResultEvent(message=result))
                        except Exception:
                            logger.exception("Handoff: unified callback failed on structured completion")
                    await ctx.add_event(WorkflowCompletedEvent(result))
                    return

                if decision.action == HandoffAction.ASK_HUMAN:
                    # Use assistant_message as the question for the human
                    if self._hitl_enabled and self._hitl_executor_id:
                        prompt = self._hitl_prompt_builder(self._current_agent, decision.assistant_message or text)
                        await ctx.send_message(
                            HandoffHumanRequest(
                                prompt=prompt,
                                agent=self._current_agent,
                                preview=(decision.assistant_message or text)[:1000] or None,
                            ),
                            target_id=self._hitl_executor_id,
                        )
                        return
                    # If HITL not enabled, fall back to finalizing with the message
                    result = ChatMessage(role=Role.ASSISTANT, text=decision.assistant_message or text)
                    if self._unified_callback is not None:
                        try:
                            await self._unified_callback(FinalResultEvent(message=result))
                        except Exception:
                            logger.exception("Handoff: unified callback failed on ask_human fallback")
                    await ctx.add_event(WorkflowCompletedEvent(result))
                    return

                if decision.action == HandoffAction.RESPOND:
                    # Finish with assistant_message if present, else use model's last message
                    result_text = (decision.assistant_message or text or "").strip()
                    if not result_text:
                        result_text = "No content."
                    # If HITL enabled and the response appears to be a question (or matches configured heuristic),
                    # treat this as a human info request rather than final completion. This preserves backwards
                    # compatibility when an agent uses action="respond" for clarifying questions instead of
                    # action="ask_human".
                    if (
                        self._hitl_enabled
                        and self._hitl_executor_id
                        and self._should_request_human(self._current_agent, result_text)
                    ):
                        prompt = self._hitl_prompt_builder(self._current_agent, result_text)
                        await ctx.send_message(
                            HandoffHumanRequest(
                                prompt=prompt,
                                agent=self._current_agent,
                                preview=result_text[:1000] or None,
                            ),
                            target_id=self._hitl_executor_id,
                        )
                        return
                    result = ChatMessage(role=Role.ASSISTANT, text=result_text)
                    if self._unified_callback is not None:
                        try:
                            await self._unified_callback(FinalResultEvent(message=result))
                        except Exception:
                            logger.exception("Handoff: unified callback failed on respond")
                    await ctx.add_event(WorkflowCompletedEvent(result))
                    return

                if decision.action == HandoffAction.HANDOFF:
                    target_name = (decision.target or "").strip()
                    allowed_targets = [t for t, _ in self._allowed_targets_for(self._current_agent)]
                    if target_name == self._current_agent:
                        # Explicit self-handoff: treat as no-op and finalize with empty message
                        logger.warning(
                            "Handoff: %s attempted self-transfer in structured decision; finalizing without content",
                            self._current_agent,
                        )
                        result = ChatMessage(role=Role.ASSISTANT, text="")
                        if self._unified_callback is not None:
                            try:
                                await self._unified_callback(FinalResultEvent(message=result))
                            except Exception:
                                logger.exception("Handoff: unified callback failed on self-handoff finalize")
                        await ctx.add_event(WorkflowCompletedEvent(result))
                        return
                    if target_name and target_name in allowed_targets and target_name in self._agent_name_to_exec_id:
                        self._handoff_count += 1
                        self._current_agent = target_name
                        self._handoff_trace.append(target_name)
                        if self._handoff_count > self._max_handoffs:
                            logger.error("Handoff: exceeded max handoffs. Trace=%s", " -> ".join(self._handoff_trace))
                            fail_msg = ChatMessage(
                                role=Role.ASSISTANT,
                                text=(
                                    "Could not resolve within the allowed number of transfers. "
                                    f"Path taken: {' -> '.join(self._handoff_trace)}"
                                ),
                            )
                            if self._unified_callback is not None:
                                try:
                                    await self._unified_callback(FinalResultEvent(message=fail_msg))
                                except Exception:
                                    logger.exception("Handoff: unified callback failed on overflow")
                            await ctx.add_event(WorkflowCompletedEvent(fail_msg))
                            return
                        # After handoff, probe the new agent again for a decision on the same user message
                        if self._last_user_message is not None:
                            # Type narrowing: ctx may include HandoffHumanRequest, but here we only
                            # dispatch AgentExecutorRequest objects via _route_to_current.
                            await self._route_to_current(
                                cast(WorkflowContext[AgentExecutorRequest], ctx),
                                self._last_user_message,
                                decision_probe=True,
                            )
                            return
                    else:
                        logger.info(
                            "Handoff: structured target '%s' not allowed from '%s' or unknown. Allowed=%s",
                            target_name,
                            self._current_agent,
                            allowed_targets,
                        )
                        # Fall through to legacy handling
            # If structured parse failed, fall back to legacy path using text
            # Do not early return. Continue to legacy handling below.

        # Legacy completion directive (first-line)
        complete_summary = _parse_complete_task(text)
        if complete_summary is not None:
            logger.info("Handoff: %s signaled completion", self._current_agent)
            result = ChatMessage(
                role=Role.ASSISTANT,
                text=f"Task completed. Summary: {complete_summary}".strip(),
            )
            if self._unified_callback is not None:
                try:
                    await self._unified_callback(FinalResultEvent(message=result))
                except Exception:
                    logger.exception("Handoff: unified callback failed on completion")
            await ctx.add_event(WorkflowCompletedEvent(result))
            return

        # Legacy handoff directive (first-line)
        parsed = _parse_handoff_function(text) or _parse_handoff_directive(text)
        # Fallback: if structured mode was active and parsing failed, scan subsequent lines
        if parsed is None and complete_summary is None and self._structured_decision and "\n" in text:
            lines = text.splitlines()[1:]
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                # Check completion on later lines too
                ls = _parse_complete_task(line)
                if ls is not None:
                    complete_summary = ls
                    logger.info(
                        "Handoff: %s legacy completion directive found on later line after malformed JSON",
                        self._current_agent,
                    )
                    result = ChatMessage(
                        role=Role.ASSISTANT,
                        text=f"Task completed. Summary: {complete_summary}".strip(),
                    )
                    if self._unified_callback is not None:
                        try:
                            await self._unified_callback(FinalResultEvent(message=result))
                        except Exception:
                            logger.exception("Handoff: unified callback failed on completion (fallback scan)")
                    await ctx.add_event(WorkflowCompletedEvent(result))
                    return
                parsed_line = _parse_handoff_function(line) or _parse_handoff_directive(line)
                if parsed_line is not None:
                    parsed = parsed_line
                    logger.info(
                        "Handoff: %s legacy handoff directive found on later line after malformed JSON",
                        self._current_agent,
                    )
                    break
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
                            role=Role.ASSISTANT,
                            text=(
                                "Could not resolve within the allowed number of transfers. "
                                f"Path taken: {' -> '.join(self._handoff_trace)}"
                            ),
                        )
                        if self._unified_callback is not None:
                            try:
                                await self._unified_callback(FinalResultEvent(message=fail_msg))
                            except Exception:
                                logger.exception("Handoff: unified callback failed on overflow")
                        await ctx.add_event(WorkflowCompletedEvent(fail_msg))
                        return
                    # After legacy handoff, structured mode re-probes the new agent
                    if self._last_user_message is not None:
                        # Cast for same reason as above (union context narrowed for routing helper).
                        await self._route_to_current(
                            cast(WorkflowContext[AgentExecutorRequest], ctx),
                            self._last_user_message,
                            decision_probe=self._structured_decision,
                        )
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
            role=Role.ASSISTANT, text=f"Agent '{message.executor_id}' produced no assistant message."
        )
        if self._unified_callback is not None:
            try:
                await self._unified_callback(FinalResultEvent(message=result))
            except Exception:
                logger.exception("Handoff: unified callback failed when sending final result")
        await ctx.add_event(WorkflowCompletedEvent(result))

    @handler
    async def handle_human_feedback(
        self,
        feedback: RequestResponse[HandoffHumanRequest, str],
        ctx: WorkflowContext[AgentExecutorRequest],
    ) -> None:
        reply = (feedback.data or "").strip()
        if not reply:
            logger.info("Handoff: empty human response. Ignoring.")
            return
        user_msg = ChatMessage(role=Role.USER, text=reply)
        # After human reply, re-run a structured decision probe if enabled
        await self._route_to_current(ctx, user_msg, decision_probe=self._structured_decision)


class HandoffAgentExecutor(AgentExecutor):
    _unified_callback: CallbackSink | None
    _callback_mode: CallbackMode

    def __init__(
        self,
        agent: AgentProtocol,
        *,
        streaming: bool,
        unified_callback: CallbackSink | None,
        callback_mode: CallbackMode | None,
        id: str | None = None,
    ) -> None:
        super().__init__(agent, streaming=streaming, id=id or agent.id)
        self._unified_callback = unified_callback
        self._callback_mode = callback_mode or CallbackMode.STREAMING

    # Note: We intentionally do NOT override the base AgentExecutor.run handler to avoid
    # pyright variance issues. Unified callbacks are handled at orchestration level.


class HandoffBuilder:
    """Builder for a handoff workflow among AgentProtocol instances."""

    def __init__(self) -> None:
        self._participants: list[AgentProtocol] = []
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

        # Structured decision
        self._structured_decision: bool = False
        self._decision_model: type[AFBaseModel] = HandoffDecision

    def participants(self, participants: list[AgentProtocol]) -> "HandoffBuilder":
        for a in participants:
            if not isinstance(a, AgentProtocol):
                # Protocol check is nominal at runtime; this protects common mistakes
                raise TypeError("HandoffBuilder.participants only supports AgentProtocol instances")
        self._participants = list(participants)
        return self

    def start_with(self, agent: str | AgentProtocol) -> "HandoffBuilder":
        self._start_agent_name = _canonical_agent_name(agent)
        return self

    def handoffs(self, handoffs: OrchestrationHandoffs | dict[str, dict[str, str]]) -> "HandoffBuilder":
        self._allow_transfers = _normalize_allow_transfers(handoffs)
        return self

    def allow_transfers(self, transfers: dict[str, list[tuple[str, str]]]) -> "HandoffBuilder":
        self._allow_transfers = _normalize_allow_transfers(transfers)
        return self

    def on_event(self, callback: CallbackSink, *, mode: CallbackMode = CallbackMode.STREAMING) -> "HandoffBuilder":
        self._unified_callback = callback
        self._callback_mode = mode
        return self

    def seed_all_on_start(self, value: bool) -> "HandoffBuilder":
        self._seed_all_on_start = bool(value)
        return self

    def max_handoffs(self, value: int) -> "HandoffBuilder":
        if value < 0:
            raise ValueError("max_handoffs must be non-negative")
        self._max_handoffs = int(value)
        return self

    def enable_human_in_the_loop(
        self,
        *,
        executor_id: str = "request_info",
        ask: str | Callable[[str, str], bool] = "if_question",
        prompt_builder: Callable[[str, str], str] | None = None,
    ) -> "HandoffBuilder":
        self._hitl_enabled = True
        self._hitl_executor_id = executor_id
        self._hitl_ask_condition = ask
        self._hitl_prompt_builder = prompt_builder
        return self

    def structured_handoff(
        self,
        *,
        enabled: bool = True,
        decision_model: type[AFBaseModel] = HandoffDecision,
    ) -> "HandoffBuilder":
        """Enable typed decision probes for routing. No mutation of user agents."""
        self._structured_decision = bool(enabled)
        self._decision_model = decision_model
        return self

    def build(self) -> Workflow:
        if not self._participants:
            raise ValueError("No participants configured. Call participants([...]) with AgentProtocol instances.")

        by_name: dict[str, AgentProtocol] = {_canonical_agent_name(a): a for a in self._participants}
        name_to_exec_id: dict[str, str] = {name: agent.id for name, agent in by_name.items()}

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
            structured_decision=self._structured_decision,
            decision_model=self._decision_model,
        )
        orchestrator.set_unified_callback(self._unified_callback)

        wb = WorkflowBuilder().set_start_executor(orchestrator)

        hitl_exec: RequestInfoExecutor | None = None
        if self._hitl_enabled:
            hitl_exec = RequestInfoExecutor(id=self._hitl_executor_id)
            wb = wb.add_edge(orchestrator, hitl_exec)
            wb = wb.add_edge(hitl_exec, orchestrator)

        for _, agent in by_name.items():
            agent_exec = HandoffAgentExecutor(
                agent,
                streaming=(self._callback_mode == CallbackMode.STREAMING),
                unified_callback=self._unified_callback,
                callback_mode=self._callback_mode,
                id=agent.id,
            )
            wb = wb.add_edge(orchestrator, agent_exec)
            wb = wb.add_edge(agent_exec, orchestrator)

        return wb.build()


__all__ = [
    "AgentHandoffs",
    "HandoffAction",
    "HandoffBuilder",
    "HandoffDecision",
    "HandoffHumanRequest",
    "OrchestrationHandoffs",
]
