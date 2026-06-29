# Copyright (c) Microsoft. All rights reserved.

import asyncio
from collections.abc import Mapping
from typing import Any, Callable, cast

from agent_framework import AgentSession, ContextProvider, Message, SessionContext

"""This sample demonstrates how to detect cross-session memory injection.

When a context provider injects messages from a different ``session_id`` than
the requesting one — the legitimate cross-session memory use case (consolidated
memories, Mem0 with default scope, shared knowledge bases) — the framework
records the originating session under
``message.additional_properties["_attribution"]["origin_session_id"]``.

Downstream context observers can subscribe to this signal for governance,
audit, and behavioral analysis purposes. This is useful for defending against
the stateful-agent-backdoor attack class documented in Dai et al.,
arXiv:2605.06158, in which an adversary chains sub-backdoors across sessions
under permission isolation via persisted memory state.

The sample is self-contained: it constructs ``SessionContext`` directly and
invokes provider lifecycle methods manually, so no LLM credentials are
required to run it.
"""


class CrossSessionObserver(ContextProvider):
    """Detect injected context messages whose origin differs from the current session.

    Subscribes via the standard ``ContextProvider`` pipeline. In ``before_run``,
    walks the accumulated context messages and invokes a user-supplied
    callback for each message whose ``_attribution["origin_session_id"]``
    is present and differs from the current ``session_id``.

    The callback receives the source_id that injected the content, the
    originating session_id, the current session_id, and the message itself.
    Use it to log, alert, increment metrics, or enforce policy — the observer
    itself only surfaces the signal, leaving the response policy to the caller.
    """

    DEFAULT_SOURCE_ID = "cross_session_observer"

    def __init__(
        self,
        on_cross_session_access: Callable[[str, str, str | None, Message], None],
        *,
        source_id: str = DEFAULT_SOURCE_ID,
    ) -> None:
        """Initialize the observer.

        Args:
            on_cross_session_access: Callback invoked for each detected
                cross-session message. Signature is
                ``(source_id, origin_session_id, current_session_id, message)``.
            source_id: Unique identifier for this observer instance.
        """
        super().__init__(source_id)
        self._on_cross_session_access = on_cross_session_access

    async def before_run(
        self,
        *,
        agent: Any,
        session: AgentSession | None,
        context: SessionContext,
        state: dict[str, Any],
    ) -> None:
        """Inspect accumulated context messages for cross-session origin."""
        current_session_id = context.session_id
        for source_id, messages in context.context_messages.items():
            if source_id == self.source_id:
                continue
            for message in messages:
                attribution_raw = message.additional_properties.get("_attribution")
                if not isinstance(attribution_raw, Mapping):
                    continue
                attribution = cast(Mapping[str, Any], attribution_raw)
                origin = attribution.get("origin_session_id")
                if isinstance(origin, str) and origin != current_session_id:
                    self._on_cross_session_access(source_id, origin, current_session_id, message)


def _on_detected(source_id: str, origin: str, current: str | None, message: Message) -> None:
    """Sample callback that logs cross-session detections to stdout."""
    preview = " ".join(message.text.split())[:80]
    print(
        f"[cross-session detected] source={source_id!r} "
        f"origin_session={origin!r} current_session={current!r} "
        f"preview={preview!r}"
    )


async def main() -> None:
    """Demonstrate the observer firing on cross-session injection."""
    observer = CrossSessionObserver(_on_detected)

    # --- Case 1: same-session injection (observer should be silent) ---
    same_session_context = SessionContext(
        session_id="session-A",
        input_messages=[Message("user", ["What did we discuss last time?"])],
    )
    # Simulate a same-session provider injecting same-session history. Omitting
    # origin_session_id is semantically "no origin info" — observers treat as
    # equivalent to same-session for backward compatibility.
    same_session_context.extend_messages(
        "history_provider",
        [Message("assistant", ["We talked about Q3 revenue projections."])],
    )
    await observer.before_run(
        agent=None,
        session=None,
        context=same_session_context,
        state={},
    )
    print("--- Same-session case complete (no detections expected above) ---\n")

    # --- Case 2: cross-session injection (observer should fire) ---
    cross_session_context = SessionContext(
        session_id="session-B",
        input_messages=[Message("user", ["Continue from where we left off."])],
    )
    # Simulate a cross-session memory provider injecting content originally
    # written in session-A while we're now running in session-B.
    cross_session_context.extend_messages(
        "memory_provider",
        [Message("assistant", ["Remember: API key for prod is sk-7f3a... (from session-A)."])],
        origin_session_id="session-A",
    )
    await observer.before_run(
        agent=None,
        session=None,
        context=cross_session_context,
        state={},
    )
    print("--- Cross-session case complete (one detection expected above) ---")


if __name__ == "__main__":
    asyncio.run(main())
