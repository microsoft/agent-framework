# Copyright (c) Microsoft. All rights reserved.

"""Signal protocol utilities for AgentLoopMiddleware autonomous loops.

Provides a text-based convention for agents to signal loop termination:
  TASK_COMPLETE: <summary>  -- agent is done; loop should stop
  NEED_INPUT: <question>    -- agent needs human input; loop should stop

Use :func:`signal_should_continue` to get a :class:`SignalParser` instance
ready to pass as ``should_continue`` to :class:`~agent_framework.AgentLoopMiddleware`.
Use :func:`get_loop_exit_reason` to read the typed exit reason after the loop.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .._types import AgentResponse

__all__ = [
    "LOOP_EXIT_REASON_KEY",
    "LOOP_NEED_INPUT_KEY",
    "NEED_INPUT_TOKEN",
    "TASK_COMPLETE_TOKEN",
    "LoopExitReason",
    "SignalParser",
    "get_loop_exit_reason",
    "signal_should_continue",
]

# Text tokens the agent emits in its response to signal loop state.
# Case-sensitive: the agent is instructed to emit the exact tokens.
TASK_COMPLETE_TOKEN: str = "TASK_COMPLETE:"  # ruff: ignore[hardcoded-password-string]
NEED_INPUT_TOKEN: str = "NEED_INPUT:"  # ruff: ignore[hardcoded-password-string]

# Keys used in AgentResponse.additional_properties to surface loop metadata.
LOOP_EXIT_REASON_KEY: str = "loop_exit_reason"
LOOP_NEED_INPUT_KEY: str = "loop_need_input"


class LoopExitReason:
    """Typed exit reason strings for AgentLoopMiddleware runs.

    Values are plain strings (not an enum) to match the ``FinishReason``
    convention in this codebase and remain JSON-transparent.

    Examples::

        from agent_framework import get_loop_exit_reason, LoopExitReason

        exit_reason = get_loop_exit_reason(response)
        if exit_reason == LoopExitReason.completed:
            print("Task done!")
        elif exit_reason == LoopExitReason.need_input:
            # question is in response.text after NEED_INPUT:
    """

    completed: str = "completed"
    """``TASK_COMPLETE:`` signal detected in the agent's response."""

    iteration_cap_reached: str = "iteration_cap_reached"
    """``max_iterations`` cap fired before any terminal signal was emitted."""

    need_input: str = "need_input"
    """``NEED_INPUT:`` signal detected; loop stopped to surface a question."""

    cancelled: str = "cancelled"
    """External cancellation (reserved for future use)."""

    token_budget_exceeded: str = "token_budget_exceeded"  # ruff: ignore[hardcoded-password-string]
    """Token budget (``max_tokens``) exhausted before the loop completed."""

    time_budget_exceeded: str = "time_budget_exceeded"
    """Wall-clock time budget (``max_duration``) exhausted before the loop completed."""


class SignalParser:
    """A ``should_continue`` predicate that scans for signal tokens.

    Scans the agent's latest response text for :data:`TASK_COMPLETE_TOKEN`
    and :data:`NEED_INPUT_TOKEN` and returns the appropriate continuation
    decision for :class:`~agent_framework.AgentLoopMiddleware`.

    ``TASK_COMPLETE:`` is checked before ``NEED_INPUT:``; if an agent emits
    both, the loop treats the run as completed.

    The extracted text after the token (up to the first newline) is returned
    as the feedback string so ``next_message`` and ``record_feedback``
    callbacks can reference it.

    Examples::

        from agent_framework import AgentLoopMiddleware, signal_should_continue

        agent = Agent(
            client=client,
            middleware=[AgentLoopMiddleware(signal_should_continue())],
        )
    """

    def __call__(self, *, last_result: AgentResponse, **kwargs: Any) -> tuple[bool, str | None]:
        """Return ``(False, extracted_text)`` on a terminal signal, ``(True, None)`` otherwise."""
        text = last_result.text or ""

        idx = text.find(TASK_COMPLETE_TOKEN)
        if idx != -1:
            summary = text[idx + len(TASK_COMPLETE_TOKEN) :].split("\n", 1)[0].strip()
            return (False, summary or None)

        idx = text.find(NEED_INPUT_TOKEN)
        if idx != -1:
            question = text[idx + len(NEED_INPUT_TOKEN) :].split("\n", 1)[0].strip()
            return (False, question or None)

        return (True, None)


def signal_should_continue() -> SignalParser:
    """Return a :class:`SignalParser` instance ready for :class:`~agent_framework.AgentLoopMiddleware`.

    Pass the returned callable as ``should_continue``::

        middleware = AgentLoopMiddleware(signal_should_continue())
    """
    return SignalParser()


def get_loop_exit_reason(response: AgentResponse) -> str | None:
    """Return the typed exit reason for a completed loop run, or ``None`` if unknown.

    Scans the agent's own (assistant-role) response messages for signal tokens first,
    then falls back to ``response.additional_properties[LOOP_EXIT_REASON_KEY]``
    (set by :class:`~agent_framework.AgentLoopMiddleware` when the iteration cap fires).

    Signal tokens take priority: an agent that emitted ``TASK_COMPLETE:`` on the final
    allowed iteration is treated as completed, not cap-reached.

    Args:
        response: The :class:`~agent_framework.AgentResponse` returned by the loop.

    Returns:
        A :class:`LoopExitReason` string, or ``None`` when the reason cannot
        be determined (e.g. the loop was stopped by a custom predicate with no
        signal tokens in the response).

    Examples:

        .. code-block:: python

            from agent_framework import get_loop_exit_reason, LoopExitReason

            response = await agent.run(task)
            match get_loop_exit_reason(response):
                case LoopExitReason.completed:
                    print("Done:", response.text)
                case LoopExitReason.need_input:
                    # Question is in response.text after NEED_INPUT:
                    # LOOP_NEED_INPUT_KEY is a convention key reserved for future use.
                    print("Agent needs input; see response.text for the question.")
                case LoopExitReason.iteration_cap_reached:
                    print("Hit cap - partial result")
                case _:
                    print("Unknown exit reason")
    """
    # Scan only assistant messages - the agent's own output. User-role nudges injected
    # by the loop between iterations must not trigger a false completion signal.
    assistant_text = "".join(m.text or "" for m in response.messages if m.role == "assistant")
    if TASK_COMPLETE_TOKEN in assistant_text:
        return LoopExitReason.completed
    if NEED_INPUT_TOKEN in assistant_text:
        return LoopExitReason.need_input
    # Fall back to additional_properties for framework-set reasons (e.g. iteration cap).
    return response.additional_properties.get(LOOP_EXIT_REASON_KEY) or None
