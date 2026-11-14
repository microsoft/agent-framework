# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, cast

from .._sessions import AgentSession, ContextProvider, SessionContext
from .._telemetry import FeatureIndex, mark_feature_used
from .._tools import FunctionTool, tool
from .._types import Message

DEFAULT_MODE_SOURCE_ID = "agent_mode"
_MODE_GET_INSTRUCTIONS = "Use the mode_get tool to check your current operating mode.\n"
_MODE_SET_INSTRUCTIONS = (
    "Use the mode_set tool to switch between modes as your work progresses. "
    "Only use mode_set if the user explicitly instructs/allows you to change modes.\n\n"
)
_PLAN_MODE_TRANSITION = (
    "7. When approval is granted, always switch to execute mode (using the `mode_set` tool), "
    "and follow the steps for *Execute mode*."
)
DEFAULT_MODE_INSTRUCTIONS = (
    "## Agent Mode\n\n"
    "- You can operate in different modes. Depending on the mode you are in, "
    "you will be required to follow different processes.\n\n"
    + _MODE_GET_INSTRUCTIONS
    + _MODE_SET_INSTRUCTIONS
    + "You are currently operating in the {current_mode} mode.\n\n"
    "### Mandatory Mode based Workflow\n\n"
    "For every new substantive user request, including short factual questions, "
    "your behavior is determined by the mode you are in.\n\n"
    "{available_modes}\n"
)
DEFAULT_MODE_CHANGE_NOTIFICATION = (
    '[Mode changed: The operating mode has been switched from "{previous_mode}" to "{current_mode}". '
    'You must now adjust your behavior to match the "{current_mode}" mode.]'
)
DEFAULT_MODE_MAP: dict[str, str] = {
    "plan": (
        "Use this mode when analyzing requirements, breaking down tasks, and creating plans. "
        "This is the interactive mode — ask clarifying questions, discuss options, and get user approval before "
        "proceeding.\n\n"
        "Process to follow when in plan mode:\n"
        "1. Analyze the request with the purpose of building a research plan.\n"
        "2. Create a list of todo items.\n"
        "3. If needed, use the provided tools to do some exploratory checks to help build a plan and determine "
        "what clarifying questions you may need from the user.\n"
        "4. Ask for clarifications from the user where needed.\n"
        "   1. Ask each clarification one by one.\n"
        "   2. When asking for clarification and you have specific options in mind, present them to the user, "
        "so they can choose the option instead of having to retype the entire response.\n"
        "   3. Do not proceed until you have received all the needed clarifications.\n"
        "   4. Do short exploratory research if it helps with being able to ask sensible clarifications from "
        "the user.\n"
        "5. Write the plan to a memory file, so that it is retained even if compaction happens. "
        "Make sure to update the plan file if the user requests changes.\n"
        "6. Present the plan to the user and ask for approval to switch to execute mode and process the plan.\n"
        + _PLAN_MODE_TRANSITION
    ),
    "execute": (
        "Determine the type of ask:\n"
        "1. Simple question that doesn't require any further work to answer.\n"
        "2. Any other work, including complex user request that requires a multi-step process to satisfy.\n\n"
        "If 1. just answer the question directly.\n"
        "If 2. Work autonomously using your best judgment — do not ask the user questions or wait for feedback "
        "and follow the following process:\n"
        "1. If you don't have a plan or tasks yet, analyze the user request and create tasks and a plan. "
        "(**Skip this step if you came from plan mode**)\n"
        "2. Work autonomously — use your best judgment to make decisions and keep progressing without asking "
        "the user questions. The goal is to have a complete, useful result ready when the user returns.\n"
        "3. If you encounter ambiguity or an unexpected situation during execution, choose the most reasonable "
        "option, note your choice, and keep going.\n"
        "4. Mark tasks as completed as you finish them.\n"
        "5. Continue working, thinking and calling tools until you have the research result for the user."
    ),
}

_PREVIOUS_MODE_STATE_KEY = "previous_mode_for_notification"


def _get_mode_state(session: AgentSession, *, source_id: str) -> dict[str, Any]:
    """Return the mutable session state used by the mode provider."""
    provider_state = session.state.get(source_id)
    if isinstance(provider_state, dict):
        return cast(dict[str, Any], provider_state)
    if provider_state is not None:
        raise TypeError(
            f"Session state for source_id {source_id!r} must be a dict, got {type(provider_state).__name__}."
        )
    state: dict[str, Any] = {}
    session.state[source_id] = state
    return state


def _normalize_available_modes(available_modes: Sequence[str]) -> dict[str, str]:
    """Return normalized mode names mapped to display names."""
    normalized_modes: dict[str, str] = {}
    for mode in available_modes:
        display_mode = mode.strip()
        normalized_mode = display_mode.lower()
        if normalized_mode in normalized_modes:
            raise ValueError(f"Duplicate mode configured: {mode}.")
        normalized_modes[normalized_mode] = display_mode
    return normalized_modes


def _resolve_available_modes(available_modes: Sequence[str] | None) -> dict[str, str]:
    """Normalize configured modes, using built-in modes only when none are provided."""
    configured_modes = tuple(DEFAULT_MODE_MAP) if available_modes is None else tuple(available_modes)
    normalized_modes = _normalize_available_modes(configured_modes)
    if not normalized_modes:
        raise ValueError("available_modes must contain at least one mode.")
    return normalized_modes


def _normalize_mode(mode: str, *, available_modes: Mapping[str, str]) -> str:
    """Validate and normalize a mode string."""
    normalized = mode.strip().lower()
    if normalized not in available_modes:
        supported_modes = ", ".join(repr(item) for item in available_modes.values())
        raise ValueError(f"Invalid mode: {mode}. Supported modes are {supported_modes}.")
    return normalized


def _resolve_default_mode(default_mode: str | None, *, available_modes: Mapping[str, str]) -> str:
    """Resolve the default mode, falling back to the first configured mode when omitted."""
    if default_mode is None:
        return next(iter(available_modes))
    return _normalize_mode(default_mode, available_modes=available_modes)


def get_agent_mode(
    session: AgentSession,
    *,
    source_id: str = DEFAULT_MODE_SOURCE_ID,
    default_mode: str | None = None,
    available_modes: Sequence[str] | None = None,
) -> str:
    """Get the current operating mode from session state.

    Args:
        session: The agent session to read the mode from.

    Keyword Args:
        source_id: Unique source ID for the provider state.
        default_mode: Initial mode used when no mode is stored yet. When omitted, the first entry of
            ``available_modes`` is used.
        available_modes: Supported modes to validate against. Defaults to the built-in modes.

    Returns:
        The current mode string.

    Raises:
        ValueError: The available modes are empty or duplicated, or the default mode is not configured.
    """
    normalized_modes = _resolve_available_modes(available_modes)
    normalized_default_mode = _resolve_default_mode(default_mode, available_modes=normalized_modes)
    provider_state = _get_mode_state(session, source_id=source_id)
    current_mode = provider_state.get("current_mode")
    if isinstance(current_mode, str):
        try:
            return _normalize_mode(current_mode, available_modes=normalized_modes)
        except ValueError:
            # Stored mode is no longer in the configured set (e.g. available_modes was reconfigured).
            # Fall through and reset to the default mode.
            pass
    provider_state["current_mode"] = normalized_default_mode
    return normalized_default_mode


def set_agent_mode(
    session: AgentSession,
    mode: str,
    *,
    source_id: str = DEFAULT_MODE_SOURCE_ID,
    available_modes: Sequence[str] | None = None,
    notify: bool = True,
) -> str:
    """Set the current operating mode in session state.

    External callers (e.g., a slash-command handler) should use this helper rather than mutating
    session state directly. When the mode actually changes, the prior mode is recorded so that the
    next :meth:`AgentModeProvider.before_run` invocation injects a user message announcing the
    switch — system instructions alone are insufficient to redirect a model that has already seen
    its own ``set_mode`` tool call earlier in the chat history.

    Args:
        session: The agent session to update the mode in.
        mode: The new mode to set.

    Keyword Args:
        source_id: Unique source ID for the provider state.
        available_modes: Supported modes to validate against. Defaults to the built-in modes.
        notify: Whether to notify the agent about the mode change on its next run. Set to ``False`` when the
            agent changes mode through a replacement tool and has already observed the tool result. This also
            clears any pending external-change notification.

    Returns:
        The normalized mode string that was stored.

    Raises:
        ValueError: The available modes are empty or duplicated, or the requested mode is not configured.
    """
    normalized_modes = _resolve_available_modes(available_modes)
    normalized_mode = _normalize_mode(mode, available_modes=normalized_modes)
    provider_state = _get_mode_state(session, source_id=source_id)
    previous_mode = provider_state.get("current_mode")
    provider_state["current_mode"] = normalized_mode
    # When the mode is changed externally (i.e. not via the agent's own ``set_mode`` tool), record the
    # prior mode so the next ``before_run`` can inject a user message announcing the switch. Without
    # that injection, the model often anchors on the earlier ``set_mode`` tool call in the chat history
    # and keeps behaving as if it were still in that mode — system instructions alone are insufficient.
    if notify:
        if isinstance(previous_mode, str) and previous_mode != normalized_mode:
            provider_state[_PREVIOUS_MODE_STATE_KEY] = previous_mode
    else:
        provider_state.pop(_PREVIOUS_MODE_STATE_KEY, None)
    return normalized_mode


class AgentModeProvider(ContextProvider):
    """Track the agent's operating mode in session state and provide mode tools.

    The ``AgentModeProvider`` enables agents to operate in distinct modes during long-running complex tasks.
    The current mode is persisted in the ``AgentSession`` state and is included in the instructions provided to the
    agent on each invocation.

    The set of available modes is configurable with ``mode_instructions``. By default, two modes are provided:
    ``"plan"`` (interactive planning) and ``"execute"`` (autonomous execution).

    By default, this provider exposes the following tools to the agent:
    - ``mode_set``: Switch the agent's operating mode.
    - ``mode_get``: Retrieve the agent's current operating mode.

    Set ``expose_mode_set`` or ``expose_mode_get`` to ``False`` to omit that tool while retaining mode state
    and workflow instructions. Replacement tools can be supplied through the agent's ``tools`` argument.

    Public helper functions ``get_agent_mode`` and ``set_agent_mode`` allow external code to programmatically read
    and change the mode.
    """

    def __init__(
        self,
        source_id: str = DEFAULT_MODE_SOURCE_ID,
        *,
        default_mode: str | None = None,
        mode_instructions: Mapping[str, str] | None = None,
        instructions: str | None = None,
        expose_mode_set: bool = True,
        expose_mode_get: bool = True,
    ) -> None:
        """Initialize a new agent mode provider.

        Args:
            source_id: Unique source ID for the provider.

        Keyword Args:
            default_mode: Initial mode used when no mode is stored yet. When omitted, the first entry of
                ``mode_instructions`` is used.
            mode_instructions: Mapping of supported modes to instructions on when and how to use each mode.
                Custom text is not rewritten when tools are hidden.
            instructions: Custom instructions for using the mode tools. The instructions can contain an
                ``{available_modes}`` placeholder for the configured list of modes and a ``{current_mode}`` placeholder
                for the currently active mode. When omitted, the provider uses a default set of instructions.
                Default guidance reflects tool exposure; custom text is not rewritten when tools are hidden.
            expose_mode_set: Whether to contribute the built-in ``mode_set`` tool. Defaults to ``True``.
                When ``False``, the application controls mode changes, optionally through a replacement tool.
            expose_mode_get: Whether to contribute the built-in ``mode_get`` tool. Defaults to ``True``.
                The current mode remains available in the default instructions and through ``get_agent_mode``.

        Raises:
            ValueError: No modes are configured, or the default mode is not configured.
        """
        super().__init__(source_id)
        if mode_instructions is None:
            mode_instructions = dict(DEFAULT_MODE_MAP)
            if not expose_mode_set:
                mode_instructions["plan"] = mode_instructions["plan"].replace(
                    _PLAN_MODE_TRANSITION,
                    "7. When approval is granted, use the application's configured mode-change mechanism to "
                    "transition to execute mode. Follow the steps for *Execute mode* only after the mode has changed.",
                )
        else:
            mode_instructions = dict(mode_instructions)
        self._mode_display_names = _normalize_available_modes(tuple(mode_instructions))
        if not self._mode_display_names:
            raise ValueError("mode_instructions must contain at least one mode.")
        self.mode_instructions = {
            mode.strip().lower(): mode_instruction for mode, mode_instruction in mode_instructions.items()
        }
        self.available_modes = tuple(self._mode_display_names)
        self.default_mode = _resolve_default_mode(default_mode, available_modes=self._mode_display_names)
        self.instructions = instructions
        self.expose_mode_set = expose_mode_set
        self.expose_mode_get = expose_mode_get

    def _build_instructions(self, current_mode: str) -> str:
        """Build the mode guidance injected for the current session."""
        mode_lines = "".join(
            f"#### {self._mode_display_names[mode]}\n\n{mode_instruction}\n\n"
            for mode, mode_instruction in self.mode_instructions.items()
        )
        instructions = self.instructions or DEFAULT_MODE_INSTRUCTIONS
        if not self.instructions:
            if not self.expose_mode_get:
                instructions = instructions.replace(_MODE_GET_INSTRUCTIONS, "")
            if not self.expose_mode_set:
                instructions = instructions.replace(
                    _MODE_SET_INSTRUCTIONS,
                    "Mode changes are controlled by the application. Use its configured mode-change mechanism "
                    "only when the user explicitly instructs/allows a mode change.\n\n",
                )
        return instructions.replace("{available_modes}", mode_lines).replace("{current_mode}", current_mode)

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject mode tools and instructions before the model runs.

        Args:
            agent: The agent being invoked.
            session: The agent session whose state stores the current mode.
            context: The session context to receive instructions and tools.
            state: Per-provider invocation state.
        """
        mark_feature_used(FeatureIndex.CORE_AGENT_MODE_PROVIDER)
        del agent, state
        current_mode = get_agent_mode(
            session,
            source_id=self.source_id,
            default_mode=self.default_mode,
            available_modes=self.available_modes,
        )
        # Pop the external-mode-change marker (set by ``set_agent_mode``) before injecting tools so
        # the agent only sees the notification once.
        provider_state = _get_mode_state(session, source_id=self.source_id)
        previous_mode = provider_state.pop(_PREVIOUS_MODE_STATE_KEY, None)

        @tool(name="mode_set", approval_mode="never_require")
        def mode_set(mode: str) -> str:
            """Switch the agent's operating mode."""
            normalized_mode = set_agent_mode(
                session,
                mode,
                source_id=self.source_id,
                available_modes=self.available_modes,
                notify=False,
            )
            return json.dumps({"mode": normalized_mode, "message": f"Mode changed to '{normalized_mode}'."})

        @tool(name="mode_get", approval_mode="never_require")
        def mode_get() -> str:
            """Get the agent's current operating mode."""
            current_mode_value = get_agent_mode(
                session,
                source_id=self.source_id,
                default_mode=self.default_mode,
                available_modes=self.available_modes,
            )
            return json.dumps({"mode": current_mode_value})

        context.extend_instructions(
            self.source_id,
            [self._build_instructions(current_mode)],
        )
        tools: list[FunctionTool] = []
        if self.expose_mode_set:
            tools.append(mode_set)
        if self.expose_mode_get:
            tools.append(mode_get)
        context.extend_tools(self.source_id, tools)
        if isinstance(previous_mode, str) and previous_mode != current_mode:
            # Inject a user-role message announcing the external mode change. System instructions
            # always render first in the chat history, so the agent can otherwise stay anchored to
            # the most recent ``mode_set`` tool call rather than the new mode.
            previous_display = self._mode_display_names.get(previous_mode, previous_mode)
            current_display = self._mode_display_names.get(current_mode, current_mode)
            notification = DEFAULT_MODE_CHANGE_NOTIFICATION.format(
                previous_mode=previous_display,
                current_mode=current_display,
            )
            context.extend_messages(self, [Message(role="user", contents=[notification])])
