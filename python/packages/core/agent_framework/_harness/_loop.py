# Copyright (c) Microsoft. All rights reserved.

"""AgentLoopMiddleware: re-run an agent in a loop until a criterion is met (or never).

This module provides :class:`AgentLoopMiddleware`, an :class:`~agent_framework.AgentMiddleware`
that repeatedly re-invokes the wrapped agent. It serves three common patterns through a single
configurable class:

1. The "Ralph" loop (no exit criteria) - keep asking the agent for more work, bounded only by an
   optional ``max_iterations`` cap. The loop can track a **feedback log** across iterations
   (``record_feedback``): each pass contributes an entry that is exposed to every callback via the
   ``progress`` keyword and (by default) injected into the next iteration's input. Set
   ``fresh_context=True`` to restart each pass from the original task plus the progress log (the
   Ralph "fresh context per iteration" principle), and ``is_complete`` to stop early when the agent
   signals completion.
2. A user-supplied ``should_continue`` predicate - for example, keep looping while a
   :class:`~agent_framework.TodoProvider` still has open items, or while a
   :class:`~agent_framework.BackgroundAgentsProvider` still has running tasks (see the
   :func:`todos_remaining` and :func:`background_tasks_running` helpers).
3. A ``judge_client`` - a second chat client decides whether the user's original request has been
   answered (via a :class:`JudgeVerdict` structured output); the loop continues while the answer is
   "no". This is a simpler-to-configure special case of (2).

In every case, the input for the next iteration is controlled by the ``next_message`` callable.

The loop can also resolve **approval / user-input requests** automatically via the
``on_approval_request`` callable: when a run ends with pending ``user_input_request`` content (for
example a tool with ``approval_mode="always_require"``), the callable decides each request and the
loop feeds the responses back and re-runs the agent.
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field
from typing_extensions import Self, Sentinel

from .._feature_stage import ExperimentalFeature, experimental
from .._middleware import AgentContext, AgentMiddleware, MiddlewareTermination
from .._types import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    Content,
    Message,
    ResponseStream,
    normalize_messages,
)

if TYPE_CHECKING:
    from .._clients import SupportsChatGetResponse

__all__ = [
    "AgentLoopMiddleware",
    "JudgeVerdict",
    "background_tasks_running",
    "todos_remaining",
]

logger = logging.getLogger("agent_framework")

DEFAULT_NEXT_MESSAGE = "Continue working on the task. If it is complete, say so."

DEFAULT_JUDGE_INSTRUCTIONS = (
    "You are an evaluator. You are given a user's original request and an agent's latest response. "
    "Decide whether the agent has fully addressed the original request. "
    "Set 'answered' to true if the request has been fully addressed, or false if more work is still "
    "required, and use 'reasoning' to briefly justify your decision."
)


class JudgeVerdict(BaseModel):
    """Structured verdict returned by the judge chat client."""

    answered: bool = Field(
        description="True if the agent has fully addressed the original request, otherwise False.",
    )
    reasoning: str = Field(
        default="",
        description="Brief justification for the verdict.",
    )


# Default iteration cap for judge-driven loops. LLM-judged loops are costly and probabilistic, so
# unlike the Ralph loop they are bounded by default. Pass ``max_iterations=None`` explicitly to opt
# into an unbounded judge loop.
DEFAULT_JUDGE_MAX_ITERATIONS = 5


UNSET = Sentinel("UNSET")
"""Sentinel distinguishing "argument not provided" from an explicit ``None``."""


# A callable invoked between iterations. It always receives the loop keyword arguments
# (``iteration``, ``last_result``, ``messages``, ``original_messages``, ``session``, ``agent``,
# ``progress``). Callers declare only the keywords they need plus ``**kwargs`` to ignore the rest.
ShouldContinueCallable = Callable[..., "bool | Awaitable[bool]"]
NextMessageCallable = Callable[..., "AgentRunInputs | Awaitable[AgentRunInputs | None] | None"]

# A callable invoked once per work iteration to capture a progress-log entry from that iteration. It
# receives the loop keyword arguments and returns a string entry (appended to the log) or ``None``
# (record nothing for that iteration).
FeedbackCallable = Callable[..., "str | Awaitable[str | None] | None"]

# A callable that decides whether the loop is complete (and should stop). It receives the loop
# keyword arguments and returns ``True`` to stop.
CompletionCallable = Callable[..., "bool | Awaitable[bool]"]

# A callable invoked once per pending approval / user-input request. It receives the loop keyword
# arguments plus ``request`` (the request ``Content``) and returns the decision for that request:
# ``bool`` (approve/reject, function approvals only), a response ``Content``, or ``None`` (no
# decision).
ApprovalCallback = Callable[..., "bool | Content | Awaitable[bool | Content | None] | None"]


async def _maybe_await(value: Any) -> Any:
    """Await ``value`` if it is awaitable, otherwise return it as-is."""
    if inspect.isawaitable(value):
        return await value
    return value


def _original_request_text(messages: list[Message]) -> str:
    """Join the text of the original input messages for presentation to the judge."""
    parts = [message.text for message in messages if message.text]
    return "\n".join(parts)


@experimental(feature_id=ExperimentalFeature.HARNESS)
class AgentLoopMiddleware(AgentMiddleware):
    """Re-run an agent in a loop until a criterion is met (or never).

    This middleware repeatedly invokes the wrapped agent. After each run it decides whether to run
    again based on ``should_continue`` (or a ``judge_client``) and ``max_iterations``, and uses
    ``next_message`` to build the input for the next iteration.

    The ``should_continue`` and ``next_message`` callables are invoked with keyword arguments, so a
    caller only needs to declare the ones it uses plus ``**kwargs``. The keywords are:

    - ``iteration`` (int): the number of completed runs so far (1-based after the first run),
      including any approval-resolution runs.
    - ``last_result`` (AgentResponse): the result of the iteration that just completed.
    - ``messages`` (list[Message]): the messages used for the iteration that just completed.
    - ``original_messages`` (list[Message]): the input used for the first iteration.
    - ``session`` (AgentSession | None): the active session, used by the provider helpers.
    - ``agent``: the agent being looped.

    The ``on_approval_request`` callable additionally receives ``request`` (the pending request
    ``Content``) and is invoked once per pending request before the normal continuation logic runs.

    Examples:
        .. code-block:: python

            from agent_framework import Agent, AgentResponse
            from agent_framework._harness._loop import AgentLoopMiddleware


            async def should_continue(*, iteration: int, last_result: AgentResponse, **kwargs) -> bool:
                return iteration < 3 and "DONE" not in last_result.text


            agent = Agent(client=client, middleware=[AgentLoopMiddleware(should_continue=should_continue)])

    Warning:
        When neither ``should_continue``/``judge_client`` nor ``max_iterations`` is set, the loop is
        unbounded (the "Ralph" loop). Provide ``max_iterations`` if you need a guaranteed stop.
    """

    def __init__(
        self,
        *,
        should_continue: ShouldContinueCallable | None = None,
        judge_client: SupportsChatGetResponse | None = None,
        judge_instructions: str | None = None,
        max_iterations: int | Sentinel | None = UNSET,
        next_message: NextMessageCallable | None = None,
        record_feedback: FeedbackCallable | None = None,
        inject_progress: bool = True,
        fresh_context: bool = False,
        is_complete: str | CompletionCallable | None = None,
        on_approval_request: ApprovalCallback | None = None,
        max_approval_rounds: int | None = None,
    ) -> None:
        """Initialize the agent loop middleware.

        Keyword Args:
            should_continue: Predicate that returns ``True`` to run the agent again or ``False`` to
                stop. Called with the loop keyword arguments. If ``None`` (and no ``judge_client``),
                the loop continues until ``max_iterations`` is reached (the "Ralph" loop).
            judge_client: A chat client used to decide whether the original request has been
                answered. When provided, the loop continues while the request is *not* answered.
                The judge is queried with a :class:`JudgeVerdict` structured-output response format.
                Mutually exclusive with ``should_continue``.
            judge_instructions: Optional system instructions for the judge. Defaults to
                ``DEFAULT_JUDGE_INSTRUCTIONS``. Ignored when ``judge_client`` is not set.
            max_iterations: Maximum number of agent runs. ``None`` means unbounded. When omitted in
                judge mode, defaults to ``DEFAULT_JUDGE_MAX_ITERATIONS``; otherwise defaults to
                unbounded. Approval-resolution runs (see ``on_approval_request``) do not count
                against this budget.
            next_message: Callable that produces the input for the next iteration, called with the
                loop keyword arguments. Defaults to a short "continue" nudge. Returning ``None``
                reuses the previous iteration's messages verbatim (in which case the progress log is
                *not* injected; see ``inject_progress``).
            record_feedback: Optional callable invoked once per work iteration (the "feedback loop"
                of the Ralph pattern). Called as ``record_feedback(**loop_kwargs)`` and returns a
                string entry appended to the progress log, or ``None`` to record nothing for that
                iteration. When not provided, the iteration's response text (``last_result.text``) is
                recorded instead. The accumulated log is exposed to every callback via the
                ``progress`` loop keyword argument. For production loops prefer a ``record_feedback``
                that returns a terse summary rather than relying on the full response text. Feedback
                is captured only for normal work iterations, not approval-resolution rounds.
            inject_progress: When ``True`` (default), the accumulated progress log is injected into
                the next iteration's input as a single ``user`` message ("Progress so far: ..."). To
                avoid duplication, only the most recent entry is injected when a session is attached
                (the session already retains earlier turns); the full log is injected when there is
                no session or ``fresh_context`` is set. When ``False`` the log is only exposed via the
                ``progress`` loop keyword argument and never injected automatically.
            fresh_context: When ``True``, each iteration starts from a clean context: ``context``
                messages are reset to the original input messages (plus the injected progress log)
                instead of accumulating the prior conversation. This mirrors the Ralph pattern's
                "fresh context per iteration" principle, where memory lives only in the progress log.
                Note: this resets the input *messages* only; if a session/thread is attached the
                provider may still retain history server-side, so for a truly fresh context run
                without a session (a warning is logged when ``fresh_context`` is set with a session).
            is_complete: Optional early-stop completion signal. When a ``str``, the loop stops once
                that marker appears in the latest response text (e.g. ``"<promise>COMPLETE</promise>"``).
                When a callable, it is called as ``is_complete(**loop_kwargs)`` and the loop stops
                when it returns ``True``. Composes with ``should_continue``/``judge_client`` as an
                independent early-stop check evaluated before them.
            on_approval_request: Callable that resolves pending approval / user-input requests. When
                a run ends with one or more ``user_input_request`` contents, this callable is invoked
                once per request as ``on_approval_request(request=<Content>, **loop_kwargs)`` and must
                return one of:

                - ``bool`` - approve (``True``) or reject (``False``). Only valid for
                  ``function_approval_request`` content; the middleware builds the response via
                  :meth:`Content.to_function_approval_response`. A ``bool`` returned for any other
                  request type raises ``ValueError``.
                - ``Content`` - a response content used directly. For a ``function_approval_request``
                  it must be a ``function_approval_response`` with a matching ``id``.
                - ``None`` - no decision for this request.

                Approval handling takes precedence over ``should_continue``/``next_message``: when
                requests are pending and *all* of them receive a non-``None`` decision, the responses
                are fed back and the agent re-runs (exempt from ``max_iterations``). If *any* request
                returns ``None`` the round is abandoned (no responses submitted) and normal
                continuation logic applies.
            max_approval_rounds: Optional cap on the number of consecutive approval-resolution rounds,
                guarding against an agent that endlessly emits approval requests. ``None`` (default)
                means unbounded. When the cap is exceeded the loop stops and the latest result (with
                its still-pending requests) is returned.

        Raises:
            ValueError: If both ``should_continue`` and ``judge_client`` are provided, if
                ``max_iterations`` is not ``None`` and is less than 1, or if ``max_approval_rounds``
                is not ``None`` and is less than 1.
        """
        if should_continue is not None and judge_client is not None:
            raise ValueError("Provide either 'should_continue' or 'judge_client', not both.")

        if isinstance(max_iterations, Sentinel):
            resolved_max = DEFAULT_JUDGE_MAX_ITERATIONS if judge_client is not None else None
        else:
            resolved_max = max_iterations

        if resolved_max is not None and resolved_max < 1:
            raise ValueError("max_iterations must be None or a positive integer (>= 1).")

        if max_approval_rounds is not None and max_approval_rounds < 1:
            raise ValueError("max_approval_rounds must be None or a positive integer (>= 1).")

        self.max_iterations: int | None = resolved_max
        self.next_message = next_message
        self.record_feedback = record_feedback
        self.inject_progress = inject_progress
        self.fresh_context = fresh_context
        self.is_complete = is_complete
        self.on_approval_request = on_approval_request
        self.max_approval_rounds = max_approval_rounds
        self._judge_client = judge_client
        self._judge_instructions = judge_instructions or DEFAULT_JUDGE_INSTRUCTIONS

        if judge_client is not None:
            self.should_continue: ShouldContinueCallable | None = self._build_judge_condition(judge_client)
        else:
            self.should_continue = should_continue

    @classmethod
    def ralph(
        cls,
        *,
        max_iterations: int | Sentinel | None = UNSET,
        record_feedback: FeedbackCallable | None = None,
        inject_progress: bool = True,
        fresh_context: bool = False,
        is_complete: str | CompletionCallable | None = None,
        next_message: NextMessageCallable | None = None,
        on_approval_request: ApprovalCallback | None = None,
        max_approval_rounds: int | None = None,
    ) -> Self:
        """Create a "Ralph" loop with feedback tracking and an optional completion signal.

        Convenience factory for the Ralph pattern: the agent is re-run with no ``should_continue``
        predicate and no judge, while a progress log (``record_feedback``) is accumulated and fed
        forward between iterations. See :meth:`__init__` for the full meaning of each argument.

        Keyword Args:
            max_iterations: Maximum number of agent runs. ``None`` (and the default when omitted) is
                unbounded; provide a value to guarantee the loop stops.
            record_feedback: Callable producing a per-iteration progress entry. Falls back to the
                response text when not provided.
            inject_progress: Whether to inject the accumulated progress log into the next iteration's
                input. Defaults to ``True``.
            fresh_context: Whether to restart each iteration from the original task plus the progress
                log. Defaults to ``False``.
            is_complete: Optional early-stop completion signal (marker string or callable).
            next_message: Callable that produces the next iteration's input. Defaults to a short nudge.
            on_approval_request: Optional callable that resolves pending approval requests.
            max_approval_rounds: Optional cap on consecutive approval-resolution rounds.
        """
        return cls(
            max_iterations=max_iterations,
            record_feedback=record_feedback,
            inject_progress=inject_progress,
            fresh_context=fresh_context,
            is_complete=is_complete,
            next_message=next_message,
            on_approval_request=on_approval_request,
            max_approval_rounds=max_approval_rounds,
        )

    @classmethod
    def with_predicate(
        cls,
        should_continue: ShouldContinueCallable,
        *,
        max_iterations: int | Sentinel | None = UNSET,
        is_complete: str | CompletionCallable | None = None,
        next_message: NextMessageCallable | None = None,
        record_feedback: FeedbackCallable | None = None,
        inject_progress: bool = True,
        fresh_context: bool = False,
        on_approval_request: ApprovalCallback | None = None,
        max_approval_rounds: int | None = None,
    ) -> Self:
        """Create a loop that continues while a ``should_continue`` predicate returns ``True``.

        Convenience factory for the predicate pattern - for example pairing with
        :func:`todos_remaining` or :func:`background_tasks_running`. See :meth:`__init__` for the
        full meaning of each argument.

        Args:
            should_continue: Predicate that returns ``True`` to run the agent again, called with the
                loop keyword arguments.

        Keyword Args:
            max_iterations: Maximum number of agent runs. ``None`` (and the default when omitted) is
                unbounded; provide a value to guarantee the loop stops even if the predicate never
                returns ``False``.
            is_complete: Optional early-stop completion signal (marker string or callable).
            next_message: Callable that produces the next iteration's input. Defaults to a short nudge.
            record_feedback: Optional callable producing a per-iteration progress entry.
            inject_progress: Whether to inject the accumulated progress log into the next iteration's
                input. Defaults to ``True``.
            fresh_context: Whether to restart each iteration from the original task plus the progress
                log. Defaults to ``False``.
            on_approval_request: Optional callable that resolves pending approval requests.
            max_approval_rounds: Optional cap on consecutive approval-resolution rounds.
        """
        return cls(
            should_continue=should_continue,
            max_iterations=max_iterations,
            is_complete=is_complete,
            next_message=next_message,
            record_feedback=record_feedback,
            inject_progress=inject_progress,
            fresh_context=fresh_context,
            on_approval_request=on_approval_request,
            max_approval_rounds=max_approval_rounds,
        )

    @classmethod
    def with_judge(
        cls,
        judge_client: SupportsChatGetResponse,
        *,
        judge_instructions: str | None = None,
        max_iterations: int | Sentinel | None = UNSET,
        is_complete: str | CompletionCallable | None = None,
        next_message: NextMessageCallable | None = None,
        on_approval_request: ApprovalCallback | None = None,
        max_approval_rounds: int | None = None,
    ) -> Self:
        """Create a loop that continues until a judge chat client decides the request was answered.

        Convenience factory for the judge pattern: ``judge_client`` is queried with a
        :class:`JudgeVerdict` structured-output response after each iteration and the loop continues
        while the request is *not* answered. See :meth:`__init__` for the full meaning of each
        argument.

        Args:
            judge_client: Chat client used to judge whether the original request was answered.

        Keyword Args:
            judge_instructions: Optional system instructions for the judge. Defaults to
                ``DEFAULT_JUDGE_INSTRUCTIONS``.
            max_iterations: Maximum number of agent runs. Defaults to ``DEFAULT_JUDGE_MAX_ITERATIONS``
                when omitted; pass ``None`` for unbounded.
            is_complete: Optional early-stop completion signal (marker string or callable).
            next_message: Callable that produces the next iteration's input. Defaults to a short nudge.
            on_approval_request: Optional callable that resolves pending approval requests.
            max_approval_rounds: Optional cap on consecutive approval-resolution rounds.
        """
        return cls(
            judge_client=judge_client,
            judge_instructions=judge_instructions,
            max_iterations=max_iterations,
            is_complete=is_complete,
            next_message=next_message,
            on_approval_request=on_approval_request,
            max_approval_rounds=max_approval_rounds,
        )

    def _build_judge_condition(self, judge_client: SupportsChatGetResponse) -> ShouldContinueCallable:
        """Build a ``should_continue`` predicate backed by a judge chat client.

        The judge is called directly (no agent tools, session, or middleware) with fresh messages,
        so the loop's evaluation cannot recurse back through the agent pipeline. The judge is asked
        for a :class:`JudgeVerdict` structured output; if the client does not honor structured
        output the verdict falls back to parsing ``ANSWERED``/``NOT_ANSWERED`` from the raw text.
        """
        instructions = self._judge_instructions

        async def _judge(*, last_result: AgentResponse, original_messages: list[Message], **kwargs: Any) -> bool:
            request_text = _original_request_text(original_messages)
            judge_messages = [
                Message(role="system", contents=[instructions]),
                Message(
                    role="user",
                    contents=[
                        (
                            f"Original request:\n{request_text}\n\n"
                            f"Agent's latest response:\n{last_result.text}\n\n"
                            "Has the original request been fully addressed?"
                        )
                    ],
                ),
            ]
            response = await judge_client.get_response(judge_messages, options={"response_format": JudgeVerdict})
            verdict = response.value
            if isinstance(verdict, JudgeVerdict):
                answered = verdict.answered
            else:
                # Fallback for clients that do not honor structured output: parse the raw text.
                text = response.text.strip().upper()
                answered = "NOT_ANSWERED" not in text and "ANSWERED" in text
            # Continue looping while the request is not yet answered.
            return not answered

        return _judge

    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Run the wrapped agent in a loop."""
        original_messages = list(context.messages)
        if self.fresh_context and context.session is not None:
            logger.warning(
                "AgentLoopMiddleware: fresh_context=True only resets the input messages; the "
                "attached session may still retain conversation history server-side. For a truly "
                "fresh context per iteration, run the loop without a session."
            )
        if context.stream:
            self._process_streaming(context, call_next, original_messages)
        else:
            await self._process_non_streaming(context, call_next, original_messages)

    async def _process_non_streaming(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
        original_messages: list[Message],
    ) -> None:
        iteration = 0
        work_iterations = 0
        approval_rounds = 0
        progress: list[str] = []
        while True:
            await call_next()
            iteration += 1

            result = context.result
            if not isinstance(result, AgentResponse):
                raise TypeError(
                    "AgentLoopMiddleware expected an AgentResponse from a non-streaming run, "
                    f"got {type(result).__name__}."
                )

            messages_used = context.messages
            loop_kwargs = self._build_loop_kwargs(
                context=context,
                iteration=iteration,
                last_result=result,
                messages_used=messages_used,
                original_messages=original_messages,
                progress=progress,
            )

            # Approval handling takes precedence and is exempt from ``max_iterations``.
            approval = await self._maybe_handle_approvals(
                context,
                result.user_input_requests,
                loop_kwargs,
                original_messages,
                approval_rounds,
            )
            if approval is not None:
                stop, approval_rounds = approval
                if stop:
                    break
                continue

            # Normal continuation.
            work_iterations += 1
            # Capture this iteration's feedback into the progress log, then refresh loop_kwargs so
            # the stop checks and next-message resolution see the latest entry.
            if await self._record_progress(result, loop_kwargs, progress):
                loop_kwargs = self._build_loop_kwargs(
                    context=context,
                    iteration=iteration,
                    last_result=result,
                    messages_used=messages_used,
                    original_messages=original_messages,
                    progress=progress,
                )
            if await self._is_complete(loop_kwargs):
                break
            if self.max_iterations is not None and work_iterations >= self.max_iterations:
                break
            if not await self._should_continue(loop_kwargs):
                break
            context.messages = await self._resolve_next_message(loop_kwargs, messages_used, original_messages)

    def _process_streaming(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
        original_messages: list[Message],
    ) -> None:
        # Holds the last iteration's final response so the outer stream's finalizer can return it
        # rather than an aggregate of every iteration.
        holder: dict[str, AgentResponse | None] = {"final": None}

        async def _generator() -> Any:
            iteration = 0
            work_iterations = 0
            approval_rounds = 0
            progress: list[str] = []
            while True:
                # Approval requests can arrive on streamed updates; collect them as we yield so the
                # decision does not depend on the aggregated final response alone.
                streamed_requests: list[Content] = []
                try:
                    await call_next()
                    inner = context.result
                    if not isinstance(inner, ResponseStream):
                        raise TypeError(
                            "AgentLoopMiddleware expected a ResponseStream from a streaming run, "
                            f"got {type(inner).__name__}."
                        )

                    async for update in inner:
                        if self.on_approval_request is not None and update.user_input_requests:
                            streamed_requests.extend(update.user_input_requests)
                        yield update

                    holder["final"] = await inner.get_final_response()
                except MiddlewareTermination:
                    # The pipeline's MiddlewareTermination suppression is no longer active once
                    # process() has returned (the stream is consumed lazily), so a termination
                    # raised by a downstream middleware or during stream consumption surfaces here.
                    # Stop cleanly and keep whatever final response we have from a prior iteration.
                    return

                iteration += 1

                messages_used = context.messages
                final = holder["final"]
                loop_kwargs = self._build_loop_kwargs(
                    context=context,
                    iteration=iteration,
                    last_result=final,
                    messages_used=messages_used,
                    original_messages=original_messages,
                    progress=progress,
                )

                # Approval handling takes precedence and is exempt from ``max_iterations``.
                pending = self._merge_requests(streamed_requests, final)
                approval = await self._maybe_handle_approvals(
                    context,
                    pending,
                    loop_kwargs,
                    original_messages,
                    approval_rounds,
                )
                if approval is not None:
                    stop, approval_rounds = approval
                    if stop:
                        return
                    continue

                # Normal continuation.
                work_iterations += 1
                if await self._record_progress(final, loop_kwargs, progress):
                    loop_kwargs = self._build_loop_kwargs(
                        context=context,
                        iteration=iteration,
                        last_result=final,
                        messages_used=messages_used,
                        original_messages=original_messages,
                        progress=progress,
                    )
                if await self._is_complete(loop_kwargs):
                    return
                if self.max_iterations is not None and work_iterations >= self.max_iterations:
                    return
                if not await self._should_continue(loop_kwargs):
                    return
                context.messages = await self._resolve_next_message(loop_kwargs, messages_used, original_messages)

        def _finalize(updates: Sequence[AgentResponseUpdate]) -> AgentResponse:
            if holder["final"] is not None:
                return holder["final"]
            return AgentResponse.from_updates(updates)

        context.result = ResponseStream(_generator(), finalizer=_finalize)

    async def _maybe_handle_approvals(
        self,
        context: AgentContext,
        requests: list[Content],
        loop_kwargs: dict[str, Any],
        original_messages: list[Message],
        approval_rounds: int,
    ) -> tuple[bool, int] | None:
        """Resolve pending approval requests for one iteration.

        Returns ``None`` when there is nothing to handle (the caller proceeds with the normal
        continuation logic). Otherwise returns ``(stop, approval_rounds)`` where ``stop`` indicates
        the loop should end (e.g. ``max_approval_rounds`` exceeded) and ``approval_rounds`` is the
        updated round counter. When ``stop`` is ``False`` the next iteration's messages have already
        been written to ``context.messages``.
        """
        if self.on_approval_request is None:
            return None
        pending = self._dedupe_requests(requests)
        if not pending:
            return None

        responses, all_handled = await self._build_approval_responses(pending, loop_kwargs)
        if not all_handled:
            # All-or-nothing: at least one request had no decision, so submit nothing and fall back
            # to the normal continuation logic.
            return None

        approval_rounds += 1
        if self.max_approval_rounds is not None and approval_rounds > self.max_approval_rounds:
            return True, approval_rounds

        context.messages = self._build_approval_messages(context, pending, responses, original_messages)
        return False, approval_rounds

    @staticmethod
    def _dedupe_requests(requests: list[Content]) -> list[Content]:
        """Return the requests in order, dropping later duplicates that share an ``id``."""
        seen_ids: set[str] = set()
        ordered: list[Content] = []
        for request in requests:
            request_id = getattr(request, "id", None)
            if request_id is not None:
                if request_id in seen_ids:
                    continue
                seen_ids.add(request_id)
            ordered.append(request)
        return ordered

    def _merge_requests(self, streamed: list[Content], final: AgentResponse | None) -> list[Content]:
        combined = list(streamed)
        if final is not None:
            combined.extend(final.user_input_requests)
        return self._dedupe_requests(combined)

    async def _build_approval_responses(
        self,
        pending: list[Content],
        loop_kwargs: dict[str, Any],
    ) -> tuple[list[Content], bool]:
        """Invoke the approval callable for each request, returning ``(responses, all_handled)``."""
        on_approval_request = self.on_approval_request
        if on_approval_request is None:  # pragma: no cover - guarded by caller
            return [], False
        responses: list[Content] = []
        for request in pending:
            decision = await _maybe_await(on_approval_request(request=request, **loop_kwargs))
            if decision is None:
                return [], False
            responses.append(self._coerce_decision(request, decision))
        return responses, True

    @staticmethod
    def _coerce_decision(request: Content, decision: bool | Content) -> Content:
        """Convert an approval decision into a response ``Content``, validating the result."""
        if isinstance(decision, bool):
            if request.type != "function_approval_request":
                raise ValueError(
                    f"on_approval_request returned a bool for a '{request.type}' request; bool "
                    "decisions are only valid for 'function_approval_request'. Return a response "
                    "Content instead."
                )
            return request.to_function_approval_response(decision)
        if isinstance(decision, Content):
            if request.type == "function_approval_request":
                if decision.type != "function_approval_response":
                    raise ValueError(
                        "on_approval_request returned a Content of type "
                        f"'{decision.type}' for a 'function_approval_request'; expected "
                        "'function_approval_response'."
                    )
                request_id = getattr(request, "id", None)
                decision_id = getattr(decision, "id", None)
                if decision_id != request_id:
                    raise ValueError(
                        "on_approval_request returned a function_approval_response whose id "
                        f"'{decision_id}' does not match the request id '{request_id}'."
                    )
            return decision
        raise TypeError(f"on_approval_request must return a bool, a Content, or None; got {type(decision).__name__}.")

    def _build_approval_messages(
        self,
        context: AgentContext,
        pending: list[Content],
        responses: list[Content],
        original_messages: list[Message],
    ) -> list[Message]:
        """Build the next-iteration messages carrying the approval responses.

        With a session the conversation history already holds the assistant's approval-request
        message, so only the user responses are sent. Without a session the original input, the
        assistant request message, and the user responses are all re-sent.
        """
        if context.session is not None:
            return [Message(role="user", contents=list(responses))]
        return [
            *original_messages,
            Message(role="assistant", contents=list(pending)),
            Message(role="user", contents=list(responses)),
        ]

    def _build_loop_kwargs(
        self,
        *,
        context: AgentContext,
        iteration: int,
        last_result: AgentResponse | None,
        messages_used: list[Message],
        original_messages: list[Message],
        progress: list[str],
    ) -> dict[str, Any]:
        return {
            "iteration": iteration,
            "last_result": last_result,
            "messages": messages_used,
            "original_messages": original_messages,
            "session": context.session,
            "agent": context.agent,
            # A copy so user callbacks cannot mutate the loop's internal progress log.
            "progress": list(progress),
        }

    async def _record_progress(
        self,
        last_result: AgentResponse | None,
        loop_kwargs: dict[str, Any],
        progress: list[str],
    ) -> bool:
        """Capture this iteration's feedback into ``progress``. Returns ``True`` if an entry was added."""
        if self.record_feedback is not None:
            entry = await _maybe_await(self.record_feedback(**loop_kwargs))
        else:
            entry = last_result.text.strip() if last_result is not None else None
        if entry:
            progress.append(entry)
            return True
        return False

    async def _is_complete(self, loop_kwargs: dict[str, Any]) -> bool:
        marker = self.is_complete
        if marker is None:
            return False
        if isinstance(marker, str):
            last_result = loop_kwargs.get("last_result")
            text = last_result.text if isinstance(last_result, AgentResponse) else ""
            return marker in text
        return bool(await _maybe_await(marker(**loop_kwargs)))

    async def _should_continue(self, loop_kwargs: dict[str, Any]) -> bool:
        if self.should_continue is None:
            return True
        return bool(await _maybe_await(self.should_continue(**loop_kwargs)))

    @staticmethod
    def _render_progress(entries: list[str]) -> Message:
        """Format progress-log entries into a single ``user`` message."""
        body = "\n".join(f"- {entry}" for entry in entries)
        return Message(role="user", contents=[f"Progress so far:\n{body}"])

    async def _resolve_next_message(
        self,
        loop_kwargs: dict[str, Any],
        messages_used: list[Message],
        original_messages: list[Message],
    ) -> list[Message]:
        # Compute the base next input. A ``next_message`` callable returning None requests a verbatim
        # reuse of the previous messages (no progress injection); in fresh-context mode that escape
        # hatch does not apply, so fall back to the default nudge instead.
        if self.next_message is None:
            next_msgs = normalize_messages(DEFAULT_NEXT_MESSAGE)
        else:
            next_input = await _maybe_await(self.next_message(**loop_kwargs))
            if next_input is None:
                if not self.fresh_context:
                    return list(messages_used)
                next_msgs = normalize_messages(DEFAULT_NEXT_MESSAGE)
            else:
                next_msgs = normalize_messages(next_input)

        progress: list[str] = loop_kwargs.get("progress") or []
        session = loop_kwargs.get("session")
        progress_msg: Message | None = None
        if self.inject_progress and progress:
            # With a session the earlier entries are already retained in the conversation, so only
            # the latest entry is injected to avoid duplication. Otherwise inject the full log.
            entries = progress if (session is None or self.fresh_context) else progress[-1:]
            progress_msg = self._render_progress(entries)

        if self.fresh_context:
            result = list(original_messages)
            if progress_msg is not None:
                result.append(progress_msg)
            result.extend(next_msgs)
            return result

        if progress_msg is not None:
            return [progress_msg, *next_msgs]
        return list(next_msgs)


def todos_remaining(provider: Any) -> ShouldContinueCallable:
    """Build a ``should_continue`` predicate that loops while a ``TodoProvider`` has open items.

    Args:
        provider: A :class:`~agent_framework.TodoProvider` attached to the same session as the loop.

    Returns:
        A predicate suitable for :class:`AgentLoopMiddleware`'s ``should_continue`` argument.
    """

    async def _should_continue(*, session: Any = None, **kwargs: Any) -> bool:
        if session is None:
            return False
        items = await provider.store.load_items(session, source_id=provider.source_id)
        return any(not item.is_complete for item in items)

    return _should_continue


def background_tasks_running(provider: Any) -> ShouldContinueCallable:
    """Build a ``should_continue`` predicate that loops while a ``BackgroundAgentsProvider`` is busy.

    The predicate inspects the provider's persisted task state and continues while any task is still
    marked as running. Pair it with ``max_iterations`` so the loop is guaranteed to stop even if a
    task's persisted status is never refreshed.

    Args:
        provider: A :class:`~agent_framework.BackgroundAgentsProvider` attached to the same session
            as the loop.

    Returns:
        A predicate suitable for :class:`AgentLoopMiddleware`'s ``should_continue`` argument.
    """
    from ._background_agents import BackgroundTaskInfo, BackgroundTaskStatus

    def _should_continue(*, session: Any = None, **kwargs: Any) -> bool:
        if session is None:
            return False
        state = session.state.get(provider.source_id)
        if not state:
            return False
        return any(
            BackgroundTaskInfo.from_dict(task).status == BackgroundTaskStatus.RUNNING for task in state.get("tasks", [])
        )

    return _should_continue
