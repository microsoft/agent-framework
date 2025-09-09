# Copyright (c) Microsoft. All rights reserved.

import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import Literal, cast

from agent_framework import AgentProtocol, AgentRunResponse, AgentRunResponseUpdate, ChatMessage, Role
from agent_framework._pydantic import AFBaseModel
from pydantic import Field

from ._callback import AgentDeltaEvent, AgentMessageEvent, CallbackMode, CallbackSink, FinalResultEvent
from ._events import AgentRunEvent, AgentRunUpdateEvent, WorkflowCompletedEvent
from ._executor import (
    AgentExecutor,
    AgentExecutorRequest,
    AgentExecutorResponse,
    Executor,
    RequestInfoMessage,
    RequestResponse,
    handler,
)
from ._workflow import RequestInfoExecutor, Workflow, WorkflowBuilder  # type: ignore[attr-defined]
from ._workflow_context import WorkflowContext

logger = logging.getLogger(__name__)

_RE_HANDOFF_DIRECTIVE = re.compile(r"^(?:HANDOFF|TRANSFER)\s+TO\s+([\w\-.]+)(?:\s*:\s*(.*))?$", re.IGNORECASE)
_RE_HANDOFF_FUNCTION = re.compile(
    r"^(?:handoff\.)?transfer_to_([\w\-.]+)\s*(?:\(\s*\))?\s*(?::\s*(.*))?$", re.IGNORECASE
)
_RE_COMPLETE_DIRECT = re.compile(r"^(?:complete_task|complete)\s*:\s*(.+)$", re.IGNORECASE)
_RE_COMPLETE_FUNCTION = re.compile(r"^(?:handoff\.)?complete_task\s*\(\s*[\"']?(.*?)[\"']?\s*\)\s*$", re.IGNORECASE)
# Relaxed mode: interrogative/modal sentence starters
_RE_RELAXED_INTERROGATIVE_START = re.compile(
    r"^(?:who|what|when|where|why|how|could|can|would|should|may|do|does|did|are|is|will)\b",
    re.IGNORECASE,
)


class HandoffAction(str, Enum):
    HANDOFF = "handoff"
    RESPOND = "respond"
    COMPLETE = "complete"
    ASK_HUMAN = "ask_human"


class HITLAskCondition(str, Enum):
    """Enumeration of built-in Human-In-The-Loop ask trigger modes.

    ALWAYS: Always route clarifying output to a human.
    IF_QUESTION: Only when the assistant text ends with a question mark.
        HEURISTIC: Question mark OR starts with a configured polite request cue (stricter than legacy substring scan).
        RELAXED: Clarification if any question mark appears anywhere OR the first sentence begins with
            a common interrogative/modal (who/what/when/where/why/how/could/can/would/should/may/do/does/
            did/are/is/will) even if extra explanatory sentences follow. More forgiving for prompts like
            "Could you confirm X? This helps me Y." that end with a period.
    """

    ALWAYS = "always"
    IF_QUESTION = "if_question"
    HEURISTIC = "heuristic"
    RELAXED = "relaxed"


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
    """Return a stable non-empty canonical name for an agent or raise.

    Preference order:
      1. Provided string (must be non-blank if str)
      2. agent.name
      3. agent.id
    Raises ValueError if the resolved name is blank/empty to avoid silent key collisions.
    """
    if isinstance(agent, str):
        if not agent or not agent.strip():
            raise ValueError("Blank agent name")
        return agent.strip()
    name = getattr(agent, "name", None) or getattr(agent, "id", None)
    if not name or not str(name).strip():
        raise ValueError("Agent has neither name nor id")
    return str(name).strip()


def _parse_handoff_directive(text: str) -> tuple[str, str] | None:
    if not text:
        return None
    first_line = text.splitlines()[0].strip()
    m = _RE_HANDOFF_DIRECTIVE.match(first_line)
    if not m:
        return None
    target = m.group(1).strip()
    reason = (m.group(2) or "").strip()
    return target, reason


def _parse_handoff_function(text: str) -> tuple[str, str] | None:
    if not text:
        return None
    first = text.splitlines()[0].strip()
    m = _RE_HANDOFF_FUNCTION.match(first)
    if not m:
        return None
    target = m.group(1).strip()
    reason = (m.group(2) or "").strip()
    return target, reason


def _parse_complete_task(text: str) -> str | None:
    if not text:
        return None
    first = text.splitlines()[0].strip()
    m = _RE_COMPLETE_DIRECT.match(first)
    if m:
        return m.group(1).strip()
    m = _RE_COMPLETE_FUNCTION.match(first)
    if m:
        return m.group(1).strip()
    return None


class AgentHandoffs(dict[str, str]):
    """A mapping of target_agent_name to description."""

    pass


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
            for tgt_key, desc in target_agents.items():
                self.add(src, tgt_key, desc)
        else:
            for tgt in target_agents:
                self.add(src, tgt, None)
        return self


def _normalize_allow_transfers(
    transfers: dict[str, list[tuple[str, str]]] | OrchestrationHandoffs | dict[str, dict[str, str]] | None,
) -> dict[str, list[tuple[str, str]]]:
    if not transfers:
        return {}
    # If values are lists we still validate element structure instead of blindly trusting shape.
    if isinstance(transfers, dict) and transfers and isinstance(next(iter(transfers.values())), list):
        validated: dict[str, list[tuple[str, str]]] = {}
        for src, items in transfers.items():  # type: ignore[assignment]
            if not isinstance(items, list):
                raise TypeError("Expected list for transfers mapping values in list-shape variant")
            norm_list: list[tuple[str, str]] = []
            for idx, item in enumerate(items):
                tgt: str
                desc: str
                if isinstance(item, tuple):
                    if len(item) != 2:
                        raise ValueError(f"Transfer entry at {src}[{idx}] tuple must have length 2, got {len(item)}")
                    raw_tgt, raw_desc = item
                    tgt = str(raw_tgt)
                    # Normalize description. Treat falsey (None, "") as empty string; otherwise str().
                    desc = "" if not raw_desc else str(raw_desc)
                elif isinstance(item, list):
                    if len(item) == 1:
                        tgt = str(item[0])
                        desc = ""
                    elif len(item) == 2:
                        tgt = str(item[0])
                        desc = "" if item[1] is None else str(item[1])
                    else:
                        raise ValueError(
                            f"Transfer entry at {src}[{idx}] list must have length 1 or 2, got {len(item)}"
                        )
                elif isinstance(item, str):
                    tgt = item
                    desc = ""
                else:
                    raise TypeError(
                        "Unsupported transfer entry type at "
                        f"{src}[{idx}]: {type(item).__name__}; expected tuple, list, or str"
                    )
                if not tgt or not tgt.strip():
                    raise ValueError(f"Blank target agent name at {src}[{idx}]")
                norm_list.append((tgt.strip(), desc.strip()))
            validated[src] = norm_list
        return validated

    # Remaining cases: OrchestrationHandoffs | dict[str, dict[str, str]]
    dict_of_dicts: dict[str, dict[str, str]] = cast(dict[str, dict[str, str]], transfers)
    out: dict[str, list[tuple[str, str]]] = {}
    for src, mapping in dict_of_dicts.items():
        out[src] = [(tgt, (desc or "")) for tgt, desc in mapping.items()]
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
        seed_all_on_start: bool = False,
        max_seed_agents: int | None = None,
        max_handoffs: int = 8,
        # HITL configuration
        hitl_enabled: bool = False,
        hitl_executor_id: str | None = None,
        hitl_prompt_builder: Callable[[str, str], str] | None = None,
        hitl_ask_condition: (
            HITLAskCondition
            | Literal["always", "if_question", "heuristic", "relaxed"]
            | Callable[[str, str], bool]
            | None
        ) = None,
        hitl_ask_condition_map: (
            dict[
                str,
                HITLAskCondition
                | Literal["always", "if_question", "heuristic", "relaxed"]
                | Callable[[str, str], bool],
            ]
            | None
        ) = None,
        hitl_heuristic_cues: list[str] | None = None,
        # Structured decision mode
        structured_decision: bool = False,
        decision_model: type[AFBaseModel] = HandoffDecision,
        decision_prompt_builder: (Callable[[type[AFBaseModel], list[str], list[tuple[str, str]]], str] | None) = None,
        structured_require: bool = False,
        decision_retries: int = 0,
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
        # If provided, only seed-all when participant count <= max_seed_agents
        if max_seed_agents is not None and max_seed_agents <= 0:
            raise ValueError("max_seed_agents must be positive when provided")
        self._max_seed_agents = max_seed_agents
        self._handoff_count = 0
        self._max_handoffs = max_handoffs
        self._handoff_trace: list[str] = [start_agent_name]
        # Correlation id for traceability across overflow / finalization logs
        self._correlation_id: str = uuid.uuid4().hex

        # HITL
        self._hitl_enabled = bool(hitl_enabled)
        self._hitl_executor_id = hitl_executor_id
        self._hitl_prompt_builder = hitl_prompt_builder or self._default_hitl_prompt
        self._hitl_ask_condition = hitl_ask_condition or HITLAskCondition.IF_QUESTION
        self._hitl_ask_condition_map = hitl_ask_condition_map or {}
        # Default polite request cues (must be lowercase, no trailing '?')
        self._hitl_heuristic_cues = (
            [
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
            if hitl_heuristic_cues is None
            else [c.lower() for c in hitl_heuristic_cues]
        )

        # Structured
        self._structured_decision = bool(structured_decision)
        self._decision_model = decision_model
        self._decision_prompt_builder = decision_prompt_builder
        self._decision_phase = False  # True when awaiting a structured decision from current agent
        self._structured_require = bool(structured_require)
        # Remaining structured attrs
        self._decision_retries = max(0, int(decision_retries))
        self._decision_retry_count = 0
        self._finalized = False  # Ensures single final emission

    # Orchestrator API

    def set_unified_callback(self, callback: CallbackSink | None) -> None:
        self._unified_callback = callback

    # (helper removed; inline initialization now used)

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
        """Build the structured decision probe prompt.

        Extensible: if a custom decision_model with different field names is supplied, we
        introspect its field names instead of hard-coding the defaults. Users can also
        pass a custom decision_prompt_builder for full control.
        """
        allowed = self._allowed_targets_for(agent_name)
        allowed_lines = "\n".join(f"- {t}: {desc}".rstrip() for t, desc in allowed) or "(none)"

        if self._decision_prompt_builder is not None:
            try:
                return self._decision_prompt_builder(self._decision_model, [a for a, _ in allowed], allowed)
            except Exception:  # pragma: no cover - defensive logging
                logger.exception("Handoff: custom decision_prompt_builder failed; falling back to default prompt")

        field_names: list[str] = []
        try:
            raw_fields = getattr(self._decision_model, "model_fields", {})
            if isinstance(raw_fields, dict):
                field_names = [str(k) for k in raw_fields]  # type: ignore[allow-any-exp]
        except Exception:  # pragma: no cover
            logger.debug("Handoff: unable to introspect decision model fields; using defaults")
        if not field_names:
            # Fallback to legacy default ordering
            field_names = ["action", "target", "reason", "summary", "assistant_message"]

        fields_str = ", ".join(field_names)
        return (
            "Decide the next routing step for this conversation and output only a JSON object. "
            f"Use the fields: {fields_str}. "
            "Common actions (if present): 'handoff', 'respond', 'complete', 'ask_human'.\n"
            "Guidelines:\n"
            "- If you need a specialist, use a handoff action and set the target accordingly.\n"
            "- If you can answer directly, use respond and include the reply text.\n"
            "- If the task is finished, use complete with a concise summary.\n"
            "- If you require a human's answer, use ask_human with the question.\n"
            "Allowed targets for handoff:\n"
            f"{allowed_lines}"
        )

    def _render_retry_structured_prompt_for(self, agent_name: str) -> str:
        base = self._render_structured_prompt_for(agent_name)
        return base + (
            "\nSTRICT MODE: Previous response was not valid JSON. Respond with ONLY one JSON object conforming "
            "exactly to the schema; no commentary, markdown, fences, or extra text."
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
            logger.exception(f"Handoff: failed to extract final assistant message: {e}")
        return None

    def _default_hitl_prompt(self, agent_name: str, agent_text: str) -> str:
        return (
            f"The '{agent_name}' agent requests more information:\n\n"
            f"{agent_text}\n\n"
            "Reply with your answer in plain text."
        )

    def _should_request_human(self, agent_name: str, text: str) -> bool:
        """Determine if we should route to a human based on configured ask condition(s).

        Precedence:
          1. Per-agent condition map entry if present
          2. Global condition / callable

        Heuristic differences (updated):
          - A question mark at end always triggers (when heuristic or if_question).
          - Otherwise, heuristic triggers only if the lowercase message STRIPS leading whitespace
            and starts with one of the configured polite cues (reduces false positives vs substring scan).
        """
        if not self._hitl_enabled or not self._hitl_executor_id:
            return False
        if not text or not text.strip():
            return False

        cond = self._hitl_ask_condition_map.get(agent_name, self._hitl_ask_condition)

        # Callable -> custom logic
        if callable(cond):
            try:
                return bool(cond(agent_name, text))
            except Exception:  # pragma: no cover
                logger.exception("Handoff: custom HITL condition raised")
                return False

        norm = str(cond).lower()
        if norm == HITLAskCondition.ALWAYS.value:
            return True
        if norm == HITLAskCondition.IF_QUESTION.value:
            return text.strip().endswith("?")
        if norm == HITLAskCondition.HEURISTIC.value:
            stripped = text.lstrip()
            if stripped.endswith("?"):
                return True
            low = stripped.lower()
            return any(low.startswith(c) for c in self._hitl_heuristic_cues)
        if norm == HITLAskCondition.RELAXED.value:
            # 1. Any question mark anywhere qualifies (multi-sentence clarifications ending with period)
            if "?" in text:
                return True
            stripped = text.strip()
            if not stripped:
                return False
            # 2. First sentence interrogative/modal start heuristic
            first_sentence = stripped.split(".\n")[0].split(". ")[0][:160].lstrip()
            return bool(_RE_RELAXED_INTERROGATIVE_START.match(first_sentence) and len(stripped) <= 800)
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
            # Providers may ignore response_format and return normal content; treat as expected, low-noise path.
            logger.debug("Handoff: structured decision JSON parse failed on full text; attempting substring scan")

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
        logger.info(f"Handoff: start. Current={self._current_agent}")
        if self._seed_all_on_start and not self._seeded_once:
            total = len(self._participants_by_name)
            if self._max_seed_agents is not None and total > self._max_seed_agents:
                logger.info(
                    f"Handoff: skipping seed-all ({total} participants exceeds max_seed_agents={self._max_seed_agents})"
                )
            else:
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
                # Reset retry counter after a successful parse
                self._decision_retry_count = 0
                reason_snip = (decision.reason or "").replace("\n", " ")[:120].strip()
                logger.info(
                    f"Handoff: structured decision action={decision.action.value} target={decision.target or '-'} "
                    f"agent={self._current_agent} depth={self._handoff_count} reason={(reason_snip or '-',)} "
                    f"correlation={self._correlation_id}",
                )

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
                    if not self._finalized:
                        self._finalized = True
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
                    if not self._finalized:
                        self._finalized = True
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
                        if self._structured_decision:
                            logger.debug(
                                (
                                    f"Handoff: RESPOND triggered HITL escalation (agent='{self._current_agent}'). "
                                    "Consider using action='ask_human' for clarity."
                                ),
                                self._current_agent,
                            )
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
                    if not self._finalized:
                        self._finalized = True
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
                        # ignore explicit self-handoff (no finalize, no transfer).
                        logger.warning(
                            f"Handoff: {self._current_agent} attempted self-transfer in structured decision; ignoring",
                        )
                        if not self._finalized:
                            self._finalized = True
                            fallback_text = "Produced no assistant response."  # contains 'produced no assistant'
                            result_msg = ChatMessage(role=Role.ASSISTANT, text=fallback_text)
                            if self._unified_callback is not None:
                                try:
                                    await self._unified_callback(FinalResultEvent(message=result_msg))
                                except Exception:  # pragma: no cover
                                    logger.error("Handoff: unified callback failed on self-handoff finalize")
                            await ctx.add_event(WorkflowCompletedEvent(result_msg))
                        return
                    if target_name and target_name in allowed_targets and target_name in self._agent_name_to_exec_id:
                        self._handoff_count += 1
                        self._current_agent = target_name
                        self._handoff_trace.append(target_name)
                        if self._handoff_count > self._max_handoffs:
                            path = " -> ".join(self._handoff_trace)
                            user_msg_id = None
                            if self._last_user_message is not None:
                                # Try common id attribute names for robustness
                                for attr in ("id", "message_id", "uuid"):
                                    val = getattr(self._last_user_message, attr, None)
                                    if isinstance(val, str) and val:
                                        user_msg_id = val
                                        break
                            logger.error(
                                f"Handoff: exceeded max handoffs trace={path} correlation={self._correlation_id} "
                                f"user_message_id={user_msg_id or 'n/a'}"
                            )
                            extra_bits = f" Path: {path}. Correlation: {self._correlation_id}."
                            if user_msg_id:
                                extra_bits += f" UserMessageId: {user_msg_id}."
                            fail_msg = ChatMessage(
                                role=Role.ASSISTANT,
                                text=("Could not resolve within the allowed number of transfers." + extra_bits),
                            )
                            if not self._finalized:
                                self._finalized = True
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
                            f"Handoff: invalid structured target={target_name} from={self._current_agent} "
                            f"allowed={allowed_targets} correlation={self._correlation_id}",
                        )
                        # Fall through to legacy handling
            # If structured parse failed, fall back to legacy path using text
            # Do not early return. Continue to legacy handling below.
            else:
                # decision is None
                if self._structured_require:
                    if self._decision_retry_count < self._decision_retries:
                        self._decision_retry_count += 1
                        logger.debug(
                            f"Handoff: structured decision parse failed strict "
                            f"retry={self._decision_retry_count}/{self._decision_retries} "
                            f"correlation={self._correlation_id}",
                        )
                        # Re-probe current agent with stricter prompt using same last user message
                        if self._last_user_message is not None:
                            self._decision_phase = True
                            retry_instr = ChatMessage(
                                role=Role.USER,
                                text=self._render_retry_structured_prompt_for(self._current_agent),
                            )
                            exec_id = self._agent_name_to_exec_id[self._current_agent]
                            await ctx.send_message(
                                AgentExecutorRequest(
                                    messages=[retry_instr, self._last_user_message],
                                    should_respond=True,
                                    response_format_model=self._decision_model,
                                ),
                                target_id=exec_id,
                            )
                            return
                    # Either retries exhausted or none configured
                    error_msg = (
                        "Failed to obtain a valid structured handoff decision from agent "
                        f"'{self._current_agent}' after {self._decision_retry_count} retry(s)."
                    )
                    logger.error(f"Handoff: {error_msg}")
                    raise ValueError(error_msg)

        # Legacy completion directive (first-line)
        complete_summary = _parse_complete_task(text)
        if complete_summary is not None:
            logger.info(f"Handoff: {self._current_agent} signaled completion")
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
                        f"Handoff: {self._current_agent} legacy completion directive found on later "
                        f"line after malformed JSON",
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
                        f"Handoff: {self._current_agent} legacy handoff directive found on "
                        f"later line after malformed JSON",
                    )
                    break
        if parsed is not None:
            target_name, reason = parsed
            allowed_targets = [t for t, _ in self._allowed_targets_for(self._current_agent)]
            if target_name in allowed_targets and target_name in self._agent_name_to_exec_id:
                if target_name == self._current_agent:
                    logger.warning("Handoff: self._current_agent attempted self-transfer; ignoring")
                else:
                    self._handoff_count += 1
                    logger.info(f"Handoff: {self._current_agent} -> {target_name} ({reason or 'no reason'})")
                    self._current_agent = target_name
                    self._handoff_trace.append(target_name)
                    if self._handoff_count > self._max_handoffs:
                        path = " -> ".join(self._handoff_trace)
                        user_msg_id = None
                        if self._last_user_message is not None:
                            for attr in ("id", "message_id", "uuid"):
                                val = getattr(self._last_user_message, attr, None)
                                if isinstance(val, str) and val:
                                    user_msg_id = val
                                    break
                        logger.error(
                            f"Handoff: exceeded max handoffs. Trace={path} Correlation={self._correlation_id} "
                            f"UserMessageId={user_msg_id or 'n/a'}"
                        )
                        extra_bits = f" Path: {path}. Correlation: {self._correlation_id}."
                        if user_msg_id:
                            extra_bits += f" UserMessageId: {user_msg_id}."
                        fail_msg = ChatMessage(
                            role=Role.ASSISTANT,
                            text=("Could not resolve within the allowed number of transfers." + extra_bits),
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
                    f"Handoff: target '{target_name}' not allowed from '{self._current_agent}' or unknown. "
                    f"Allowed={allowed_targets}",
                )

        # No handoff and not completed. Decide whether to ask a human or to finalize.
        if self._should_request_human(self._current_agent, text):
            prompt = self._hitl_prompt_builder(self._current_agent, text)
            if self._hitl_executor_id:
                logger.info(f"Handoff: requesting human input for agent '{self._current_agent}'")
                await ctx.send_message(
                    HandoffHumanRequest(prompt=prompt, agent=self._current_agent, preview=text[:1000] or None),
                    target_id=self._hitl_executor_id,
                )
                return

        # Otherwise, finalize with the agent's final message or a fallback
        result = final_msg or ChatMessage(
            role=Role.ASSISTANT,
            text="Conversation ended without a final assistant reply. (No additional content was provided.)",
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

    async def _emit_update(
        self,
        update: AgentRunResponseUpdate,  # type: ignore[name-defined]
        ctx: WorkflowContext[AgentExecutorResponse],
    ) -> None:
        # Internal workflow event
        await ctx.add_event(AgentRunUpdateEvent(self.id, update))
        # User callback event (delta) if streaming enabled
        if self._unified_callback is not None and self._callback_mode == CallbackMode.STREAMING:
            text_val = getattr(update, "text", None)
            delta_evt = AgentDeltaEvent(agent_id=self.id, text=text_val)
            try:
                await self._unified_callback(delta_evt)
            except Exception:  # pragma: no cover
                logger.exception("HandoffAgentExecutor: unified callback failed on delta")

    async def _emit_final(
        self,
        response: AgentRunResponse,  # type: ignore[name-defined]
        ctx: WorkflowContext[AgentExecutorResponse],
    ) -> None:
        # Internal event
        await ctx.add_event(AgentRunEvent(self.id, response))
        # Callback event (final message)
        if self._unified_callback is not None:
            final_msg = None
            msgs = list(response.messages)
            if msgs:
                final_msg = msgs[-1]
            msg_evt = AgentMessageEvent(agent_id=self.id, message=final_msg)
            try:
                await self._unified_callback(msg_evt)
            except Exception:  # pragma: no cover
                logger.exception("HandoffAgentExecutor: unified callback failed on final message")

    @handler  # type: ignore[misc]
    async def run(self, request: AgentExecutorRequest, ctx: WorkflowContext[AgentExecutorResponse]) -> None:  # type: ignore[override]
        # Clone of base run with callback hooks.
        self._cache.extend(request.messages)
        if request.should_respond:
            if self._streaming:
                updates: list[AgentRunResponseUpdate] = []  # type: ignore[name-defined]
                async for update in self._agent.run_stream(self._cache, thread=self._agent_thread):
                    if not update:
                        continue
                    contents = getattr(update, "contents", None)
                    text_val = getattr(update, "text", "")
                    has_text_content = False
                    if contents:
                        for c in contents:
                            if getattr(c, "text", None):
                                has_text_content = True
                                break
                    if not (text_val or has_text_content):
                        continue
                    updates.append(update)
                    await self._emit_update(update, ctx)
                response = AgentRunResponse.from_agent_run_response_updates(updates)  # type: ignore[name-defined]
                await self._finalize_and_send(response, ctx)
            else:
                response = await self._agent.run(self._cache, thread=self._agent_thread)
                await self._emit_final(response, ctx)
                await self._finalize_and_send(response, ctx)

    async def _finalize_and_send(
        self,
        response: AgentRunResponse,  # type: ignore[name-defined]
        ctx: WorkflowContext[AgentExecutorResponse],
    ) -> None:
        full_conversation: list[ChatMessage] | None = None
        if self._cache:
            full_conversation = list(self._cache) + list(response.messages)
        agent_response = AgentExecutorResponse(self.id, response, full_conversation=full_conversation)
        await ctx.send_message(agent_response)
        self._cache.clear()


class HandoffBuilder:
    """Builder for a handoff workflow among AgentProtocol instances."""

    def __init__(self) -> None:
        self._participants: list[AgentProtocol] = []
        self._allow_transfers: dict[str, list[tuple[str, str]]] = {}
        self._start_agent_name: str | None = None
        self._unified_callback: CallbackSink | None = None
        self._callback_mode: CallbackMode | None = None
        self._seed_all_on_start: bool = False
        self._seed_all_max_agents: int | None = None
        self._max_handoffs: int = 8

        # HITL config
        self._hitl_enabled: bool = False
        self._hitl_executor_id: str = "request_info"
        self._hitl_prompt_builder: Callable[[str, str], str] | None = None
        self._hitl_ask_condition: (
            HITLAskCondition | Literal["always", "if_question", "heuristic", "relaxed"] | Callable[[str, str], bool]
        ) = HITLAskCondition.IF_QUESTION
        self._hitl_ask_condition_map: dict[
            str,
            HITLAskCondition | Literal["always", "if_question", "heuristic", "relaxed"] | Callable[[str, str], bool],
        ] = {}
        self._hitl_heuristic_cues: list[str] = []

        # Structured decision
        self._structured_decision: bool = True
        self._decision_model: type[AFBaseModel] = HandoffDecision
        self._structured_require: bool = False
        self._decision_retries: int = 0
        self._decision_prompt_builder: Callable[[type[AFBaseModel], list[str], list[tuple[str, str]]], str] | None = (
            None
        )

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

    def allow_transfers(self, transfers: dict[str, list[tuple[str, str]]]) -> "HandoffBuilder":
        self._allow_transfers = _normalize_allow_transfers(transfers)
        return self

    def on_event(self, callback: CallbackSink, *, mode: CallbackMode = CallbackMode.STREAMING) -> "HandoffBuilder":
        self._unified_callback = callback
        self._callback_mode = mode
        return self

    def seed_all_on_start(self, value: bool, *, max_agents: int | None = None) -> "HandoffBuilder":
        """Configure whether to pre-seed every participant with the initial user message.

        Parameters:
            value: Enable/disable seed-all behavior. When enabled, each agent receives the
                initial instruction + user message with should_respond=False so their local
                context is primed without invoking runs.
            max_agents: Optional guard. If provided, seed-all only occurs when the total
                number of participants is <= max_agents. Otherwise it is skipped to avoid
                large fan-out costs.
        """
        self._seed_all_on_start = bool(value)
        if max_agents is not None:
            if max_agents <= 0:
                raise ValueError("max_agents must be positive when provided")
            self._seed_all_max_agents = int(max_agents)
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
        ask: (
            HITLAskCondition | Literal["always", "if_question", "heuristic", "relaxed"] | Callable[[str, str], bool]
        ) = HITLAskCondition.IF_QUESTION,
        prompt_builder: Callable[[str, str], str] | None = None,
        ask_per_agent: (
            dict[
                str,
                HITLAskCondition
                | Literal["always", "if_question", "heuristic", "relaxed"]
                | Callable[[str, str], bool],
            ]
            | None
        ) = None,
        heuristic_cues: list[str] | None = None,
    ) -> "HandoffBuilder":
        """Enable basic Human-In-The-Loop escalation.

        Parameters:
            executor_id: The RequestInfo executor id to route human prompts.
            ask: Global ask condition (enum / literal / callable).
            prompt_builder: Optional function to build human prompt.
            ask_per_agent: Optional per-agent overrides (string enum literal or callable).
            heuristic_cues: Optional replacement list of polite request cues for heuristic mode.
        """
        self._hitl_enabled = True
        self._hitl_executor_id = executor_id
        self._hitl_ask_condition = ask
        if ask_per_agent:
            self._hitl_ask_condition_map = dict(ask_per_agent)
        if heuristic_cues is not None:
            self._hitl_heuristic_cues = [c.lower() for c in heuristic_cues]
        else:
            # Set defaults (matches orchestrator) only if empty
            if not self._hitl_heuristic_cues:
                self._hitl_heuristic_cues = [
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
        self._hitl_prompt_builder = prompt_builder
        return self

    def structured_handoff(
        self,
        *,
        enabled: bool = True,
        decision_model: type[AFBaseModel] = HandoffDecision,
        require: bool = False,
        retries: int = 0,
        decision_prompt_builder: (Callable[[type[AFBaseModel], list[str], list[tuple[str, str]]], str] | None) = None,
    ) -> "HandoffBuilder":
        """Enable typed decision probes for routing.

        Parameters:
            enabled: Turn structured decision probes on/off (default: True).
            decision_model: Pydantic model enforcing the decision schema.
            require: If True, parsing must succeed (raises on failure after retries).
            retries: Additional probe attempts (strict prompt) before failing when require=True.
        """
        self._structured_decision = bool(enabled)
        self._decision_model = decision_model
        self._decision_prompt_builder = decision_prompt_builder
        self._structured_require = bool(require)
        self._decision_retries = max(0, int(retries))
        return self

    def build(self) -> Workflow:
        if not self._participants:
            raise ValueError("No participants configured. Call participants([...]) with AgentProtocol instances.")

        # Detect duplicate canonical names (agent.name or fallback id) to avoid silent overwrite.
        names: list[str] = [_canonical_agent_name(a) for a in self._participants]
        seen_names: set[str] = set()
        dup_name_set: set[str] = set()
        for n in names:
            if n in seen_names:
                dup_name_set.add(n)
            else:
                seen_names.add(n)
        if dup_name_set:
            raise ValueError(f"Duplicate agent names: {sorted(dup_name_set)}")

        # Detect duplicate raw ids, which would corrupt executor graph wiring.
        ids: list[str] = [a.id for a in self._participants]
        seen_ids: set[str] = set()
        dup_id_set: set[str] = set()
        for i in ids:
            if i in seen_ids:
                dup_id_set.add(i)
            else:
                seen_ids.add(i)
        if dup_id_set:
            raise ValueError(f"Duplicate agent ids: {sorted(dup_id_set)}")

        by_name: dict[str, AgentProtocol] = {n: a for n, a in zip(names, self._participants, strict=True)}
        name_to_exec_id: dict[str, str] = {name: agent.id for name, agent in by_name.items()}

        for src, targets in self._allow_transfers.items():
            if src not in by_name:
                raise ValueError(f"allow_transfers refers to unknown agent '{src}'")
            for tgt, _ in targets:
                if tgt not in by_name:
                    raise ValueError(f"allow_transfers target '{tgt}' not among participants")
                if tgt == src:
                    raise ValueError(f"Agent '{src}' cannot handoff to itself")

        if self._start_agent_name is None:
            raise ValueError(
                "No start agent specified. Call start_with(<agent>) on HandoffBuilder to choose the initial agent."
            )
        start_name = self._start_agent_name
        if start_name not in by_name:
            raise ValueError(
                f"Starting agent '{start_name}' is not among participants (participants={list(by_name.keys())})."
            )

        orchestrator = HandoffOrchestrator(
            participants_by_name=by_name,
            agent_name_to_exec_id=name_to_exec_id,
            allow_transfers=self._allow_transfers,
            start_agent_name=start_name,
            seed_all_on_start=self._seed_all_on_start,
            max_seed_agents=self._seed_all_max_agents,
            max_handoffs=self._max_handoffs,
            hitl_enabled=self._hitl_enabled,
            hitl_executor_id=self._hitl_executor_id if self._hitl_enabled else None,
            hitl_prompt_builder=self._hitl_prompt_builder,
            hitl_ask_condition=self._hitl_ask_condition,
            hitl_ask_condition_map=self._hitl_ask_condition_map,
            hitl_heuristic_cues=self._hitl_heuristic_cues,
            structured_decision=self._structured_decision,
            decision_model=self._decision_model,
            decision_prompt_builder=getattr(self, "_decision_prompt_builder", None),
            structured_require=self._structured_require,
            decision_retries=self._decision_retries,
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
    "HITLAskCondition",
    "HandoffAction",
    "HandoffBuilder",
    "HandoffDecision",
    "HandoffHumanRequest",
    "OrchestrationHandoffs",
]
