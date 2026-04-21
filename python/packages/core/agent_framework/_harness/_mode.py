# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, cast

from .._feature_stage import ExperimentalFeature, experimental
from .._sessions import AgentSession, ContextProvider, SessionContext
from .._tools import tool

DEFAULT_MODE_SOURCE_ID = "session_mode"
DEFAULT_MODE_DESCRIPTIONS: dict[str, str] = {
    "plan": "Use this mode when analyzing requirements, breaking down tasks, and creating plans.",
    "execute": "Use this mode when implementing changes, writing code, and carrying out planned work.",
}


def _get_mode_state(session: AgentSession, *, source_id: str) -> dict[str, Any]:
    """Return the mutable session state used by the mode provider."""
    provider_state = session.state.get(source_id)
    if isinstance(provider_state, dict):
        return cast(dict[str, Any], provider_state)
    state: dict[str, Any] = {}
    session.state[source_id] = state
    return state


def _normalize_mode(mode: str, *, available_modes: Sequence[str]) -> str:
    """Validate and normalize a mode string."""
    normalized = mode.strip().lower()
    if normalized not in available_modes:
        supported_modes = ", ".join(repr(item) for item in available_modes)
        raise ValueError(f"Invalid mode: {mode}. Supported modes are {supported_modes}.")
    return normalized


def get_session_mode(
    session: AgentSession,
    *,
    source_id: str = DEFAULT_MODE_SOURCE_ID,
    default_mode: str = "plan",
    available_modes: Sequence[str] | None = None,
) -> str:
    """Get the current operating mode from session state."""
    normalized_modes = tuple(available_modes or DEFAULT_MODE_DESCRIPTIONS)
    normalized_default_mode = _normalize_mode(default_mode, available_modes=normalized_modes)
    provider_state = _get_mode_state(session, source_id=source_id)
    current_mode = provider_state.get("current_mode")
    if not isinstance(current_mode, str):
        provider_state["current_mode"] = normalized_default_mode
        return normalized_default_mode
    return _normalize_mode(current_mode, available_modes=normalized_modes)


def set_session_mode(
    session: AgentSession,
    mode: str,
    *,
    source_id: str = DEFAULT_MODE_SOURCE_ID,
    available_modes: Sequence[str] | None = None,
) -> str:
    """Set the current operating mode in session state."""
    normalized_modes = tuple(available_modes or DEFAULT_MODE_DESCRIPTIONS)
    normalized_mode = _normalize_mode(mode, available_modes=normalized_modes)
    provider_state = _get_mode_state(session, source_id=source_id)
    provider_state["current_mode"] = normalized_mode
    return normalized_mode


@experimental(feature_id=ExperimentalFeature.HARNESS)
class SessionModeContextProvider(ContextProvider):
    """Provide session-scoped mode tools and mode-specific instructions."""

    def __init__(
        self,
        source_id: str = DEFAULT_MODE_SOURCE_ID,
        *,
        default_mode: str = "plan",
        mode_descriptions: Mapping[str, str] | None = None,
        instructions: str | None = None,
    ) -> None:
        """Initialize the session mode provider.

        Args:
            source_id: Unique source ID for the provider.

        Keyword Args:
            default_mode: Initial mode used when no mode is stored yet.
            mode_descriptions: Mapping of supported modes to human-readable guidance.
            instructions: Optional instruction override.
        """
        super().__init__(source_id)
        self.mode_descriptions = dict(DEFAULT_MODE_DESCRIPTIONS if mode_descriptions is None else mode_descriptions)
        self.available_modes = tuple(self.mode_descriptions)
        if not self.available_modes:
            raise ValueError("mode_descriptions must contain at least one mode.")
        self.default_mode = _normalize_mode(default_mode, available_modes=self.available_modes)
        self.instructions = instructions

    def _build_default_instructions(self, current_mode: str) -> str:
        """Build the default mode guidance injected for the current session."""
        mode_lines = "\n".join(f'- "{mode}": {description}' for mode, description in self.mode_descriptions.items())
        return (
            f'You are currently operating in "{current_mode}" mode.\n'
            "Available modes:\n"
            f"{mode_lines}\n"
            "Use the set_mode tool to switch between modes as your work progresses. "
            "Only use set_mode if the user explicitly instructs you to change modes.\n"
            "Use the get_mode tool to check your current operating mode."
        )

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inject mode tools and instructions before the model runs."""
        del agent, state
        current_mode = get_session_mode(
            session,
            source_id=self.source_id,
            default_mode=self.default_mode,
            available_modes=self.available_modes,
        )

        @tool(name="set_mode", approval_mode="never_require")
        def set_mode(mode: str) -> str:
            """Switch the current operating mode."""
            normalized_mode = set_session_mode(
                session,
                mode,
                source_id=self.source_id,
                available_modes=self.available_modes,
            )
            return f'{{"mode":"{normalized_mode}","message":"Mode changed to \'{normalized_mode}\'."}}'

        @tool(name="get_mode", approval_mode="never_require")
        def get_mode() -> str:
            """Get the current operating mode."""
            current_mode_value = get_session_mode(
                session,
                source_id=self.source_id,
                default_mode=self.default_mode,
                available_modes=self.available_modes,
            )
            return f'{{"mode":"{current_mode_value}"}}'

        context.extend_instructions(
            self.source_id,
            [self.instructions or self._build_default_instructions(current_mode)],
        )
        context.extend_tools(self.source_id, [set_mode, get_mode])
