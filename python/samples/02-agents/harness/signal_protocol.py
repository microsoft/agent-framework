# Copyright (c) Microsoft. All rights reserved.

"""Signal-protocol sample: agent signals task completion via TASK_COMPLETE: / NEED_INPUT:.

This sample shows how to implement a signal protocol as a ``should_continue`` callback
for :class:`~agent_framework.AgentLoopMiddleware`. The parsing logic lives here in the
application rather than in the framework core, which lets you customize the tokens, the
matching rules, and the exit-reason values for your own use case.

How it works:
1. The agent emits ``TASK_COMPLETE: <summary>`` or ``NEED_INPUT: <question>`` at the
   start of a line when it wants to stop.
2. The ``signal_should_continue`` callback detects these tokens and sets
   ``response.additional_properties["loop_exit_reason"]`` before returning ``False``.
3. The caller reads the exit reason from ``response.additional_properties`` directly.

Iteration-cap precedence:
   ``AgentLoopMiddleware`` checks ``max_iterations`` before calling ``should_continue``.
   If the agent emits ``TASK_COMPLETE:`` on the very last allowed iteration, the signal is
   NOT detected because the cap fires first and the middleware stamps
   ``"iteration_cap_reached"``. Handle that value as a distinct outcome and inspect the
   response text if needed.

The demo at the bottom uses a scripted in-memory chat client, so it runs without an LLM.
"""

from __future__ import annotations

import asyncio
import re
import warnings
from collections.abc import Awaitable, Mapping, Sequence
from typing import Any

# The harness is experimental; silence the warning for this sample.
warnings.filterwarnings("ignore", message=r"\[HARNESS\]")

from agent_framework import (  # noqa: E402
    Agent,
    AgentLoopMiddleware,
    AgentResponse,
    BaseChatClient,
    ChatOptions,
    ChatResponse,
    Message,
)

TASK_COMPLETE_TOKEN = "TASK_COMPLETE:"  # noqa: S105
NEED_INPUT_TOKEN = "NEED_INPUT:"  # noqa: S105
LOOP_EXIT_REASON_KEY = "loop_exit_reason"

# A token only counts at the start of a line (leading spaces/tabs allowed), so a
# mid-sentence or backtick-quoted mention is not a signal.
_TASK_COMPLETE_RE = re.compile(rf"^[ \t]*{re.escape(TASK_COMPLETE_TOKEN)}(?P<text>[^\n]*)", re.MULTILINE)
_NEED_INPUT_RE = re.compile(rf"^[ \t]*{re.escape(NEED_INPUT_TOKEN)}(?P<text>[^\n]*)", re.MULTILINE)


def _find_signal(response: AgentResponse) -> tuple[str, str] | None:
    """Scan assistant-role messages for a terminal signal token.

    Only assistant messages are scanned: user-role nudges injected by the loop between
    iterations must not trigger false positives. ``TASK_COMPLETE:`` wins over ``NEED_INPUT:``.

    Returns:
        ``(exit_reason, text_after_token)`` or ``None`` when no signal is present.
    """
    text = "\n".join(m.text or "" for m in response.messages if m.role == "assistant")
    for pattern, reason in ((_TASK_COMPLETE_RE, "completed"), (_NEED_INPUT_RE, "need_input")):
        match = pattern.search(text)
        if match is not None:
            return reason, match.group("text").strip()
    return None


def signal_should_continue(*, last_result: AgentResponse, **kwargs: Any) -> tuple[bool, str | None]:
    """``should_continue`` callback for :class:`~agent_framework.AgentLoopMiddleware`.

    Returns ``(False, text)`` when the agent emits a terminal signal and ``(True, None)``
    otherwise. On a signal it also stamps ``last_result.additional_properties["loop_exit_reason"]``
    so callers can read the exit reason without re-parsing the response text.
    """
    signal = _find_signal(last_result)
    if signal is None:
        return True, None
    reason, text = signal
    last_result.additional_properties.setdefault(LOOP_EXIT_REASON_KEY, reason)
    return False, text or None


class ScriptedChatClient(BaseChatClient[ChatOptions[None]]):
    """Minimal chat client that replays scripted texts, then echoes a filler reply."""

    def __init__(self, texts: list[str]) -> None:
        super().__init__()
        self._texts = list(texts)

    def _inner_get_response(  # type: ignore[override]
        self, *, messages: Sequence[Message], stream: bool = False, options: Mapping[str, Any], **kwargs: Any
    ) -> Awaitable[ChatResponse]:
        async def _get() -> ChatResponse:
            text = self._texts.pop(0) if self._texts else "still working"
            return ChatResponse(messages=Message(role="assistant", contents=[text]))

        return _get()


async def main() -> None:
    # Scenario 1: the agent signals completion on the first pass.
    agent = Agent(
        client=ScriptedChatClient(["TASK_COMPLETE: all steps finished"]),
        middleware=[AgentLoopMiddleware(signal_should_continue, max_iterations=10)],
    )
    response = await agent.run("complete the task")
    reason = response.additional_properties.get(LOOP_EXIT_REASON_KEY)
    print(f"Exit reason: {reason}")
    assert reason == "completed"

    # Scenario 2: the agent asks the user a question.
    agent = Agent(
        client=ScriptedChatClient(["NEED_INPUT: which file should I edit?"]),
        middleware=[AgentLoopMiddleware(signal_should_continue, max_iterations=10)],
    )
    response = await agent.run("edit the file")
    reason = response.additional_properties.get(LOOP_EXIT_REASON_KEY)
    print(f"Exit reason: {reason}")
    assert reason == "need_input"

    # Scenario 3: the iteration cap fires before the agent signals anything.
    agent = Agent(
        client=ScriptedChatClient(["still working"] * 3),
        middleware=[AgentLoopMiddleware(signal_should_continue, max_iterations=2)],
    )
    response = await agent.run("task that takes too long")
    reason = response.additional_properties.get(LOOP_EXIT_REASON_KEY)
    print(f"Exit reason: {reason}")
    assert reason == "iteration_cap_reached"


if __name__ == "__main__":
    asyncio.run(main())
