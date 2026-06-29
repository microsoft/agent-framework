# Copyright (c) Microsoft. All rights reserved.

"""AgentLoopMiddleware: re-run an agent in a loop until a criterion is met.

This module provides :class:`AgentLoopMiddleware`, an :class:`~agent_framework.AgentMiddleware`
that repeatedly re-invokes the wrapped agent while a ``should_continue`` predicate says to keep
going. It serves two common patterns through a single configurable class:

1. A user-supplied ``should_continue`` predicate - for example, keep looping while a response does
   not yet contain a completion marker, while a :class:`~agent_framework.TodoProvider` still has
   open items, or while a :class:`~agent_framework.BackgroundAgentsProvider` still has running
   tasks (see the :func:`todos_remaining` and :func:`background_tasks_running` helpers, which resolve
   their provider from the running agent). The loop
   can track a **feedback log** across iterations (``record_feedback``): each pass contributes an
   entry that is exposed to every callback via the ``progress`` keyword and (by default) injected
   into the next iteration's input. Set ``fresh_context=True`` to restart each pass from the
   original task plus the progress log (with a session attached, the session is also snapshotted
   before the loop and restored between iterations so no accumulated history leaks back in).
   ``max_iterations`` bounds the loop as a safety cap.
2. A chat-client judge (via :meth:`AgentLoopMiddleware.with_judge`) - a second chat client decides
   whether the user's original request has been answered (via a :class:`JudgeVerdict` structured
   output); the loop continues while the answer is "no". This is a convenience wrapper that builds an
   async ``should_continue`` predicate, so it is a special case of (1).

In every case, the input for the next iteration is controlled by the ``next_message`` callable.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Sequence
from typing import TYPE_CHECKING, Any, TypeAlias

from pydantic import BaseModel, Field
from typing_extensions import Self

from .._feature_stage import ExperimentalFeature, experimental
from .._middleware import AgentContext, AgentMiddleware, MiddlewareTermination
from .._types import (
    AgentResponse,
    AgentResponseUpdate,
    AgentRunInputs,
    Message,
    ResponseStream,
    UsageDetails,
    add_usage_details,
    normalize_messages,
)

if TYPE_CHECKING:
    from .._clients import SupportsChatGetResponse

__all__ = [
    "AgentLoopMiddleware",
    "JudgeVerdict",
    "background_tasks_running",
    "background_tasks_running_message",
    "todos_remaining",
    "todos_remaining_message",
]

DEFAULT_NEXT_MESSAGE = "Continue working on the task. If it is complete, say so."

# Placeholder substituted with the rendered ``criteria`` block in judge instructions (see
# :meth:`AgentLoopMiddleware.with_judge`). User-supplied instructions may include it to control
# where the criteria are inserted; if absent, the criteria are not added to the judge instructions.
CRITERIA_PLACEHOLDER = "{{criteria}}"

# Verdict markers the judge is asked to emit for clients that do not honor structured output. They
# are deliberately non-overlapping: neither marker is a substring of the other, nor of the JSON
# field name ``answered``, so the text fallback in :func:`_build_judge_condition` cannot misclassify
# a negative verdict (e.g. ``{"answered": false}``) as a positive one.
JUDGE_VERDICT_DONE = "VERDICT: DONE"
JUDGE_VERDICT_MORE = "VERDICT: MORE"

DEFAULT_JUDGE_INSTRUCTIONS = (
    "You are an evaluator. You are given a user's original request and an agent's latest response. "
    "Decide whether the agent has fully addressed the original request. "
    "Set 'answered' to true if the request has been fully addressed, or false if more work is still "
    "required, and use 'reasoning' to briefly justify your decision. "
    f"If you cannot return structured output, end your reply with a line reading exactly "
    f"'{JUDGE_VERDICT_DONE}' when the request has been fully addressed or '{JUDGE_VERDICT_MORE}' "
    f"when more work is still required."
    "{{criteria}}"
)


def _render_criteria_block(criteria: Sequence[str] | None) -> str:
    """Render a list of criteria into a bullet block for the judge instructions (``""`` if none)."""
    if not criteria:
        return ""
    bullets = "\n".join(f"- {item}" for item in criteria)
    return f"\n\nThe response must satisfy all of the following criteria:\n{bullets}"


def _criteria_agent_instruction(criteria: Sequence[str]) -> str:
    """Render the criteria into an extra instruction injected for the agent before each run."""
    bullets = "\n".join(f"- {item}" for item in criteria)
    return f"Your response must satisfy all of the following criteria:\n{bullets}"


class JudgeVerdict(BaseModel):
    """Structured verdict returned by the judge chat client."""

    answered: bool = Field(
        description=(
            "True if the agent has fully addressed the original request and it adheres to the other "
            "judging standards, otherwise False."
        ),
    )
    reasoning: str = Field(
        default="",
        description="Brief justification for the verdict.",
    )


# Default iteration cap applied when ``max_iterations`` is not provided. Loops are bounded by
# default to guard against runaway re-invocation; pass ``max_iterations=None`` explicitly to opt
# into an unbounded loop.
DEFAULT_MAX_ITERATIONS = 10

# Default iteration cap for judge-driven loops. LLM-judged loops are costly and probabilistic, so
# they are bounded by a smaller default. Pass ``max_iterations=None`` explicitly to opt into an
# unbounded judge loop.
DEFAULT_JUDGE_MAX_ITERATIONS = 5


# A callable invoked between iterations. It always receives the loop keyword arguments
# (``iteration``, ``last_result``, ``messages``, ``original_messages``, ``session``, ``agent``,
# ``progress``, ``feedback``). Callers declare only the keywords they need plus ``**kwargs`` to
# ignore the rest. ``should_continue`` may return a plain ``bool`` (continue/stop) or a
# ``(bool, str | None)`` tuple whose second item is feedback surfaced to the ``next_message`` and
# ``record_feedback`` callables via the ``feedback`` keyword argument.
ShouldContinueResult: TypeAlias = "bool | tuple[bool, str | None]"
ShouldContinueCallable = Callable[..., "ShouldContinueResult | Awaitable[ShouldContinueResult]"]
NextMessageCallable = Callable[..., "AgentRunInputs | Awaitable[AgentRunInputs | None] | None"]

# A callable invoked once per work iteration to capture a progress-log entry from that iteration. It
# receives the loop keyword arguments and returns a string entry (appended to the log) or ``None``
# (record nothing for that iteration).
FeedbackCallable = Callable[..., "str | Awaitable[str | None] | None"]


async def _maybe_await(value: Any) -> Any:
    """Await ``value`` if it is awaitable, otherwise return it as-is."""
    if inspect.isawaitable(value):
        return await value
    return value


def _build_judge_condition(
    judge_client: SupportsChatGetResponse,
    instructions: str,
) -> tuple[ShouldContinueCallable, NextMessageCallable]:
    """Build the ``should_continue`` predicate and ``next_message`` callable for a judge loop.

    The judge is called directly (no agent tools, session, or middleware) with fresh messages, so
    the loop's evaluation cannot recurse back through the agent pipeline. The original input messages
    are forwarded verbatim (rather than collapsed to text) so multi-modal requests are preserved. The
    judge is asked for a :class:`JudgeVerdict` structured output; if the client does not honor
    structured output the verdict falls back to the explicit, non-overlapping ``VERDICT: DONE`` /
    ``VERDICT: MORE`` markers (``MORE`` wins, keeping the loop running, when the marker is ambiguous
    or absent).

    The predicate returns a ``(continue, reasoning)`` tuple; the loop surfaces that ``reasoning`` to
    the next-message callable as the ``feedback`` keyword argument, which feeds it back to the agent
    so it knows *why* its previous answer was judged incomplete.
    """

    async def _judge(
        *, last_result: AgentResponse, original_messages: list[Message], **kwargs: Any
    ) -> tuple[bool, str | None]:
        judge_messages = [
            Message(role="system", contents=[instructions]),
            Message(
                role="user",
                contents=["Evaluate the agent's work. The user's original request follows:"],
            ),
            *original_messages,
            Message(role="user", contents=["The agent's latest response was:"]),
            *last_result.messages,
            Message(role="user", contents=["Has the original request been fully addressed?"]),
        ]
        response = await judge_client.get_response(judge_messages, options={"response_format": JudgeVerdict})
        verdict = response.value
        if isinstance(verdict, JudgeVerdict):
            answered = verdict.answered
            reasoning = verdict.reasoning
        else:
            # Fallback for clients that do not honor structured output: look for the explicit,
            # non-overlapping verdict markers. ``FAIL`` (more work needed) takes precedence so an
            # ambiguous or marker-less reply keeps looping rather than stopping on an incomplete
            # answer.
            text = response.text.upper()
            # ``MORE`` (more work needed) takes precedence so an ambiguous reply keeps looping.
            answered = False if JUDGE_VERDICT_MORE in text else JUDGE_VERDICT_DONE in text
            reasoning = response.text.strip()
        # Continue looping while the request is not yet answered, surfacing the reasoning as feedback.
        return (not answered), (reasoning or None)

    def _next_message(*, feedback: str | None = None, **kwargs: Any) -> AgentRunInputs:
        # Feed the judge's reasoning back to the agent so the next iteration addresses the gap.
        if feedback:
            return (
                "An evaluator reviewed your previous response and judged that it does not yet fully "
                f"address the original request.\n\nEvaluator feedback: {feedback}\n\n"
                "Revise and continue so the original request is fully addressed."
            )
        return DEFAULT_NEXT_MESSAGE

    return _judge, _next_message


@experimental(feature_id=ExperimentalFeature.HARNESS)
class AgentLoopMiddleware(AgentMiddleware):
    """Re-run an agent in a loop until a criterion is met (or never).

    This middleware repeatedly invokes the wrapped agent. After each run it decides whether to run
    again based on ``should_continue`` and ``max_iterations``, and uses ``next_message`` to build
    the input for the next iteration. Use :meth:`with_judge` to drive the loop with a chat-client
    judge instead of a hand-written predicate.

    By default a non-streaming run returns an aggregated :class:`~agent_framework.AgentResponse`
    containing every iteration's messages plus the injected ``next_message`` "nudge" messages (set
    ``return_final_only=True`` to return only the last iteration's response). Streaming runs always
    yield each iteration's updates and emit the injected nudge messages as ``user`` updates between
    iterations.

    The ``should_continue`` and ``next_message`` callables are invoked with keyword arguments, so a
    caller only needs to declare the ones it uses plus ``**kwargs``. The keywords are:

    - ``iteration`` (int): the number of completed runs so far (1-based after the first run).
    - ``last_result`` (AgentResponse): the result of the iteration that just completed.
    - ``messages`` (list[Message]): the messages used for the iteration that just completed.
    - ``original_messages`` (list[Message]): the input used for the first iteration.
    - ``session`` (AgentSession | None): the active session, used by the provider helpers.
    - ``agent``: the agent being looped.
    - ``progress`` (list[str]): the feedback log accumulated so far (see ``record_feedback``).
    - ``feedback`` (str | None): the feedback string returned by ``should_continue`` for this
      iteration (``None`` when it returned a plain bool). ``should_continue`` may return either a
      ``bool`` or a ``(bool, str | None)`` tuple; the string is surfaced here so ``next_message``
      and ``record_feedback`` can reference it.

    Examples:
        .. code-block:: python

            from agent_framework import Agent, AgentResponse
            from agent_framework._harness._loop import AgentLoopMiddleware


            async def should_continue(*, iteration: int, last_result: AgentResponse, **kwargs) -> bool:
                return iteration < 3 and "DONE" not in last_result.text


            agent = Agent(client=client, middleware=[AgentLoopMiddleware(should_continue)])

    Note:
        ``max_iterations`` acts as a safety cap and defaults to ``DEFAULT_MAX_ITERATIONS`` (10). Pass
        an explicit ``None`` to make the loop unbounded, in which case it relies entirely on
        ``should_continue`` to stop, so make sure the predicate can eventually return ``False``.
    """

    def __init__(
        self,
        should_continue: ShouldContinueCallable,
        *,
        max_iterations: int | None = DEFAULT_MAX_ITERATIONS,
        next_message: NextMessageCallable | None = None,
        record_feedback: FeedbackCallable | None = None,
        inject_progress: bool = True,
        fresh_context: bool = False,
        return_final_only: bool = False,
        additional_instructions: str | None = None,
    ) -> None:
        """Initialize the agent loop middleware.

        Args:
            should_continue: Predicate that decides whether to run the agent again. May be sync or
                async and is called with the loop keyword arguments (``iteration``, ``last_result``,
                ``messages``, ``original_messages``, ``session``, ``agent``, ``progress``, and
                ``feedback`` -- see the class docstring for what each one carries; declare only the
                ones you need plus ``**kwargs``). Return ``True``/``False`` to
                continue/stop, or a ``(bool, str | None)`` tuple to also provide feedback; the
                feedback string is surfaced to the ``next_message`` and ``record_feedback`` callables
                via the ``feedback`` keyword argument. To loop on a chat-client judge instead, build
                the middleware via :meth:`with_judge`.

        Keyword Args:
            max_iterations: Maximum number of agent runs, used as a safety cap. Defaults to
                ``DEFAULT_MAX_ITERATIONS`` (10); pass an explicit ``None`` for an unbounded loop, or
                a positive integer to set a custom cap. (The :meth:`with_judge` factory uses
                ``DEFAULT_JUDGE_MAX_ITERATIONS`` (5) as its default instead.)
            next_message: Callable that produces the input for the next iteration, called with the
                loop keyword arguments. Defaults to a short "continue" nudge. Returning ``None``
                reuses the previous iteration's messages verbatim (in which case the progress log is
                *not* injected; see ``inject_progress``).
            record_feedback: Optional callable invoked once per work iteration to capture a feedback
                entry. Called as ``record_feedback(**loop_kwargs)`` and returns a
                string entry appended to the progress log, or ``None`` to record nothing for that
                iteration. When not provided, the iteration's response text (``last_result.text``) is
                recorded instead.                 The accumulated log is exposed to every callback via the
                ``progress`` loop keyword argument. For production loops prefer a ``record_feedback``
                that returns a terse summary rather than relying on the full response text.
            inject_progress: When ``True`` (default), the accumulated progress log is injected into
                the next iteration's input as a single ``user`` message ("Progress so far: ..."). To
                avoid duplication, only the most recent entry is injected when a session is attached
                (the session already retains earlier turns); the full log is injected when there is
                no session or ``fresh_context`` is set. When ``False`` the log is only exposed via the
                ``progress`` loop keyword argument and never injected automatically.
            fresh_context: When ``True``, each iteration starts from a clean context: ``context``
                messages are reset to the original input messages (plus the injected progress log)
                instead of accumulating the prior conversation. When a session is attached, the
                session is snapshotted once before the loop and restored to that pre-loop baseline
                before each subsequent iteration, so the local transcript and any service-side
                conversation id are reset too and the agent does not re-read the accumulated history.
                In-loop working-state mutations are discarded; pre-loop state is preserved; continuity
                is carried only by the progress log.
            return_final_only: Controls what a non-streaming run returns. When ``False`` (default),
                the returned :class:`~agent_framework.AgentResponse` aggregates every iteration: each
                iteration's response messages plus the injected ``next_message`` "nudge" messages
                (as ``user`` messages), so the caller sees the full back-and-forth. When ``True``,
                only the final iteration's :class:`~agent_framework.AgentResponse` is returned. This
                flag has no effect on streaming runs (the stream cannot know in advance which
                iteration is last); streaming always yields each iteration's updates and injects the
                ``next_message`` messages as ``user`` updates between iterations.
            additional_instructions: Optional extra instruction injected as a ``system`` message
                ahead of the input messages before the agent runs. It becomes part of the original
                messages, so it is preserved across ``fresh_context`` resets and (with a session)
                persists server-side across iterations. Used by :meth:`with_judge` to tell the agent
                about the criteria its response must satisfy, but available to any loop.

        Raises:
            ValueError: If ``max_iterations`` is not ``None`` and is less than 1.
        """
        if max_iterations is not None and max_iterations < 1:
            raise ValueError("max_iterations must be None or a positive integer (>= 1).")

        self.max_iterations: int | None = max_iterations
        self.should_continue: ShouldContinueCallable = should_continue
        self.next_message = next_message
        self.record_feedback = record_feedback
        self.inject_progress = inject_progress
        self.fresh_context = fresh_context
        self.return_final_only = return_final_only
        self.additional_instructions = additional_instructions

    @classmethod
    def with_judge(
        cls,
        judge_client: SupportsChatGetResponse,
        *,
        criteria: Sequence[str] | None = None,
        instructions: str | None = None,
        max_iterations: int | None = DEFAULT_JUDGE_MAX_ITERATIONS,
        next_message: NextMessageCallable | None = None,
        fresh_context: bool = False,
    ) -> Self:
        """Create a loop that continues until a judge chat client decides the request was answered.

        Convenience factory for the judge pattern: ``judge_client`` is queried with a
        :class:`JudgeVerdict` structured-output response after each iteration and the loop continues
        while the request is *not* answered. The judge's ``reasoning`` is fed back to the agent as
        the next iteration's input (unless a custom ``next_message`` is provided), so the agent knows
        why its previous answer was judged incomplete. See :meth:`__init__` for the full meaning of
        each argument.

        Args:
            judge_client: Chat client used to judge whether the original request was answered.

        Keyword Args:
            criteria: Optional list of criteria the response must satisfy. When provided, they are
                (1) injected as an extra ``system`` instruction for the agent before it runs (via
                ``additional_instructions``) and (2) rendered into the judge instructions wherever
                the ``{{criteria}}`` placeholder appears (``CRITERIA_PLACEHOLDER``).
            instructions: Optional system instructions for the judge. Defaults to
                ``DEFAULT_JUDGE_INSTRUCTIONS``. May contain the ``{{criteria}}`` placeholder, which
                is replaced with the rendered ``criteria`` (or removed when no criteria are given).
            max_iterations: Maximum number of agent runs. Defaults to
                ``DEFAULT_JUDGE_MAX_ITERATIONS`` (5); pass ``None`` for unbounded, or a positive
                integer to set a custom cap.
            next_message: Callable that produces the next iteration's input. Defaults to one that
                relays the judge's ``reasoning`` back to the agent.
            fresh_context: When ``True``, each iteration restarts from the original input messages
                (plus the injected progress log and judge feedback) instead of accumulating the prior
                conversation; an attached session is snapshotted before the loop and restored to that
                baseline between iterations. See :meth:`__init__` for the full semantics. Defaults to
                ``False``.
        """
        judge_instructions = (instructions or DEFAULT_JUDGE_INSTRUCTIONS).replace(
            CRITERIA_PLACEHOLDER, _render_criteria_block(criteria)
        )
        should_continue, judge_next_message = _build_judge_condition(judge_client, judge_instructions)
        return cls(
            should_continue=should_continue,
            max_iterations=max_iterations,
            next_message=next_message or judge_next_message,
            fresh_context=fresh_context,
            additional_instructions=_criteria_agent_instruction(criteria) if criteria else None,
        )

    async def process(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
    ) -> None:
        """Run the wrapped agent in a loop."""
        if self.additional_instructions is not None:
            # Inject the extra instruction as a system message ahead of the input so it is present
            # on every iteration and preserved across fresh_context resets (which restart from
            # ``original_messages``).
            context.messages = [
                Message(role="system", contents=[self.additional_instructions]),
                *context.messages,
            ]
        original_messages = list(context.messages)
        # For a truly fresh context per iteration the session must also be reset, otherwise the
        # next run reloads the local transcript or re-threads the service-side conversation and the
        # model still sees the accumulated history. Snapshot the session once here (the pre-loop
        # baseline) and restore it before each subsequent iteration so every pass starts clean.
        snapshot = context.session.to_dict() if self.fresh_context and context.session is not None else None
        if context.stream:
            self._process_streaming(context, call_next, original_messages, snapshot)
        else:
            await self._process_non_streaming(context, call_next, original_messages, snapshot)

    @staticmethod
    def _has_pending_approval_request(result: AgentResponse | None) -> bool:
        """Return ``True`` if ``result`` carries a pending tool-approval request.

        When the loop sits outermost (e.g. around a tool-approval middleware), an iteration may
        return a response that asks the caller to approve a tool call rather than a completed turn.
        In that case the loop must stop and hand the response back so a human can approve, instead
        of continuing or injecting the next message. This mirrors the C# ``LoopAgent`` escape hatch
        (``HasPendingApprovalRequests``). A pending request is any content whose ``type`` is
        ``"function_approval_request"``.
        """
        if result is None:
            return False
        return any(
            getattr(content, "type", None) == "function_approval_request"
            for message in result.messages
            for content in message.contents
        )

    @staticmethod
    def _restore_session(session: Any, snapshot: dict[str, Any]) -> None:
        """Restore a session in place to a previously captured ``to_dict()`` snapshot.

        Re-hydrates the snapshot via :meth:`AgentSession.from_dict` and copies the mutable fields
        (``service_session_id`` and ``state``) back onto the live ``session`` instance, so any
        reference held by the agent/context observes the reset. ``session_id`` is preserved (the
        snapshot carries the same id). A fresh ``from_dict`` is built on every call so repeated
        restores from one snapshot do not alias the same state dict.
        """
        from .._sessions import AgentSession

        restored = AgentSession.from_dict(snapshot)
        session.service_session_id = restored.service_session_id
        session.state = restored.state

    async def _process_non_streaming(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
        original_messages: list[Message],
        snapshot: dict[str, Any] | None,
    ) -> None:
        iteration = 0
        work_iterations = 0
        progress: list[str] = []
        # Aggregated transcript across iterations: each iteration's response messages plus the
        # injected "nudge" messages, used to build the combined response when return_final_only=False.
        aggregated: list[Message] = []
        aggregated_usage: UsageDetails | None = None
        final_result: AgentResponse | None = None
        while True:
            await call_next()
            iteration += 1

            result = context.result
            if not isinstance(result, AgentResponse):
                raise TypeError(
                    "AgentLoopMiddleware expected an AgentResponse from a non-streaming run, "
                    f"got {type(result).__name__}."
                )

            final_result = result
            aggregated.extend(result.messages)
            if result.usage_details is not None:
                aggregated_usage = add_usage_details(aggregated_usage, result.usage_details)

            # Escape hatch: if this iteration is asking for tool approval, stop and return the
            # response so the caller can approve, instead of continuing or injecting next_message.
            if self._has_pending_approval_request(result):
                break

            messages_used = context.messages
            loop_kwargs = self._build_loop_kwargs(
                context=context,
                iteration=iteration,
                last_result=result,
                messages_used=messages_used,
                original_messages=original_messages,
                progress=progress,
            )

            work_iterations += 1
            # Decide whether to stop and capture any feedback from should_continue first, so the
            # feedback is available to both the progress and next-message callables this iteration.
            stop, feedback = await self._evaluate_stop(loop_kwargs, work_iterations)
            loop_kwargs = self._build_loop_kwargs(
                context=context,
                iteration=iteration,
                last_result=result,
                messages_used=messages_used,
                original_messages=original_messages,
                progress=progress,
                feedback=feedback,
            )
            # Capture this iteration's progress entry, then refresh loop_kwargs so the next-message
            # resolution sees the latest entry.
            if await self._record_progress(result, loop_kwargs, progress):
                loop_kwargs = self._build_loop_kwargs(
                    context=context,
                    iteration=iteration,
                    last_result=result,
                    messages_used=messages_used,
                    original_messages=original_messages,
                    progress=progress,
                    feedback=feedback,
                )
            if stop:
                break
            if snapshot is not None and context.session is not None:
                # Reset the session to the pre-loop baseline so the next run starts fresh; only the
                # progress log (injected by _resolve_next_message) carries continuity forward.
                self._restore_session(context.session, snapshot)
            next_messages = await self._resolve_next_message(loop_kwargs, messages_used, original_messages)
            context.messages = next_messages
            aggregated.extend(next_messages)

        if not self.return_final_only:
            context.result = self._aggregate_response(final_result, aggregated, aggregated_usage)

    def _process_streaming(
        self,
        context: AgentContext,
        call_next: Callable[[], Awaitable[None]],
        original_messages: list[Message],
        snapshot: dict[str, Any] | None,
    ) -> None:
        # Holds the last iteration's final response so the outer stream's finalizer can return it
        # rather than an aggregate of every iteration.
        holder: dict[str, AgentResponse | None] = {"final": None}

        async def _generator() -> Any:
            iteration = 0
            work_iterations = 0
            progress: list[str] = []
            while True:
                try:
                    await call_next()
                    inner = context.result
                    if not isinstance(inner, ResponseStream):
                        raise TypeError(
                            "AgentLoopMiddleware expected a ResponseStream from a streaming run, "
                            f"got {type(inner).__name__}."
                        )

                    async for update in inner:
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
                # Escape hatch: if this iteration is asking for tool approval, stop the loop and
                # let the caller approve, instead of continuing or injecting next_message.
                if self._has_pending_approval_request(final):
                    return
                loop_kwargs = self._build_loop_kwargs(
                    context=context,
                    iteration=iteration,
                    last_result=final,
                    messages_used=messages_used,
                    original_messages=original_messages,
                    progress=progress,
                )

                work_iterations += 1
                # Decide whether to stop and capture any feedback from should_continue first, so the
                # feedback is available to both the progress and next-message callables this iteration.
                stop, feedback = await self._evaluate_stop(loop_kwargs, work_iterations)
                loop_kwargs = self._build_loop_kwargs(
                    context=context,
                    iteration=iteration,
                    last_result=final,
                    messages_used=messages_used,
                    original_messages=original_messages,
                    progress=progress,
                    feedback=feedback,
                )
                if await self._record_progress(final, loop_kwargs, progress):
                    loop_kwargs = self._build_loop_kwargs(
                        context=context,
                        iteration=iteration,
                        last_result=final,
                        messages_used=messages_used,
                        original_messages=original_messages,
                        progress=progress,
                        feedback=feedback,
                    )
                if stop:
                    return
                if snapshot is not None and context.session is not None:
                    # Reset the session to the pre-loop baseline before the next run. The final
                    # response was already awaited above, so the service-side conversation id has
                    # been propagated and is safe to discard here.
                    self._restore_session(context.session, snapshot)
                next_messages = await self._resolve_next_message(loop_kwargs, messages_used, original_messages)
                context.messages = next_messages
                # Surface the injected "nudge" messages in the stream so consumers see the user
                # turns that drive each subsequent iteration (the equivalent of the aggregated
                # transcript that non-streaming runs return).
                for message in next_messages:
                    yield self._message_to_update(message)

        def _finalize(updates: Sequence[AgentResponseUpdate]) -> AgentResponse:
            if holder["final"] is not None:
                return holder["final"]
            return AgentResponse.from_updates(updates)

        context.result = ResponseStream(_generator(), finalizer=_finalize)

    def _build_loop_kwargs(
        self,
        *,
        context: AgentContext,
        iteration: int,
        last_result: AgentResponse | None,
        messages_used: list[Message],
        original_messages: list[Message],
        progress: list[str],
        feedback: str | None = None,
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
            # Feedback returned by ``should_continue`` for this iteration (``None`` if it returned a
            # plain bool, or the stop was decided by ``max_iterations``).
            "feedback": feedback,
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

    async def _evaluate_stop(self, loop_kwargs: dict[str, Any], work_iterations: int) -> tuple[bool, str | None]:
        """Decide whether the loop should stop, returning ``(stop, feedback)``.

        ``max_iterations`` is a safety cap that short-circuits before ``should_continue`` is
        evaluated (so an expensive predicate/judge is not called once the cap has fired). Any
        feedback returned by ``should_continue`` is propagated so the progress and next-message
        callables can reference it.
        """
        if self.max_iterations is not None and work_iterations >= self.max_iterations:
            return True, None
        keep_going, feedback = await self._should_continue(loop_kwargs)
        return (not keep_going), feedback

    async def _should_continue(self, loop_kwargs: dict[str, Any]) -> tuple[bool, str | None]:
        """Evaluate the predicate, normalizing its result to ``(continue, feedback)``."""
        result = await _maybe_await(self.should_continue(**loop_kwargs))
        return (bool(result[0]), result[1]) if isinstance(result, tuple) else (bool(result), None)  # type: ignore

    @staticmethod
    def _message_to_update(message: Message) -> AgentResponseUpdate:
        """Wrap an injected loop message as a streaming update so consumers see it inline."""
        return AgentResponseUpdate(
            contents=message.contents,
            role=message.role,
            author_name=message.author_name,
            message_id=message.message_id,
        )

    @staticmethod
    def _aggregate_response(
        final: AgentResponse,
        messages: list[Message],
        usage: UsageDetails | None,
    ) -> AgentResponse:
        """Build a combined response carrying every iteration's messages and summed usage.

        Metadata (``response_id``, structured ``value``, etc.) is taken from the final iteration; the
        structured value is passed through pre-parsed so it is not re-derived from the aggregated text.
        """
        return AgentResponse(
            messages=messages,
            response_id=final.response_id,
            agent_id=final.agent_id,
            created_at=final.created_at,
            finish_reason=final.finish_reason,  # pyright: ignore[reportArgumentType]
            usage_details=usage,
            value=final.value,
            additional_properties=dict(final.additional_properties) if final.additional_properties else None,
            raw_representation=final.raw_representation,
        )

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


def _running_background_tasks(session: Any, agent: Any) -> list[Any]:
    """Return the still-running ``BackgroundTaskInfo`` entries for the agent's provider.

    Resolves the :class:`~agent_framework.BackgroundAgentsProvider` from the running agent
    (``agent.context_providers``) and reads its persisted task state. Returns an empty list when the
    session/agent/provider is unavailable or no task is currently running.
    """
    from ._background_agents import BackgroundAgentsProvider, BackgroundTaskInfo, BackgroundTaskStatus

    if session is None or agent is None:
        return []
    provider = _resolve_context_provider(agent, BackgroundAgentsProvider)
    if provider is None:
        return []
    state = session.state.get(provider.source_id)
    if not state:
        return []
    tasks = [BackgroundTaskInfo.from_dict(task) for task in state.get("tasks", [])]
    return [task for task in tasks if task.status == BackgroundTaskStatus.RUNNING]


def background_tasks_running() -> ShouldContinueCallable:
    """Build a ``should_continue`` predicate that loops while the agent's background tasks are busy.

    This resolves the :class:`~agent_framework.BackgroundAgentsProvider` from the running agent
    (``agent.context_providers``).

    The predicate inspects the provider's persisted task state and continues while any task is still
    marked as running. Pair it with ``max_iterations`` so the loop is guaranteed to stop even if a
    task's persisted status is never refreshed.

    Returns:
        A predicate suitable for :class:`AgentLoopMiddleware`'s ``should_continue`` argument (and for
        ``create_harness_agent``'s ``loop_should_continue``).
    """

    def _should_continue(*, session: Any = None, agent: Any = None, **kwargs: Any) -> bool:
        return bool(_running_background_tasks(session, agent))

    return _should_continue


def background_tasks_running_message(*, session: Any = None, agent: Any = None, **kwargs: Any) -> str | None:
    """``next_message`` callable that reminds the agent which background tasks are still running.

    Designed to pair with :func:`background_tasks_running` as a loop's ``next_message`` (e.g.
    ``create_harness_agent``'s ``loop_next_message``): between iterations it resolves the
    :class:`~agent_framework.BackgroundAgentsProvider` from the agent, lists the still-running tasks,
    and instructs the agent to wait for them to finish (and retrieve their results) before finishing.

    Returns ``None`` when the session/agent/provider is unavailable or no task is running. In that
    case the loop's default ``next_message`` handling applies. In normal looping a ``None`` here is
    rare, since "no running tasks" also makes :func:`background_tasks_running` stop the loop before
    the next message is consulted.
    """
    running = _running_background_tasks(session, agent)
    if not running:
        return None
    task_lines = "\n".join(f"- #{task.id} ({task.agent_name}): {task.description}" for task in running)
    return (
        f"You still have {len(running)} background task(s) running that must finish before you can "
        f"complete the work:\n{task_lines}\n\n"
        "Wait for these tasks to complete, retrieve their results, and incorporate them. Only stop "
        "once every background task has finished."
    )


def _resolve_context_provider(agent: Any, provider_type: type) -> Any:
    """Return the first ``provider_type`` instance on ``agent.context_providers`` (or ``None``).

    The harness exposes its built-in context providers (``TodoProvider``, ``AgentModeProvider``,
    ...) on ``agent.context_providers``, so loop callbacks can reuse the same instances that
    :func:`~agent_framework.create_harness_agent` wired up instead of constructing their own.
    """
    return next(
        (provider for provider in getattr(agent, "context_providers", []) if isinstance(provider, provider_type)),
        None,
    )


def todos_remaining(*, looping_modes: Sequence[str] | None = None) -> ShouldContinueCallable:
    """Build a ``should_continue`` predicate that loops while the Agent's ``TodoProvider`` has open items.

    This resolves the :class:`~agent_framework.TodoProvider` from the running agent
    (``agent.context_providers``) rather than taking it as an argument, so it can be used directly
    with :func:`~agent_framework.create_harness_agent` (whose providers are built internally) as well
    as with any agent that registers a ``TodoProvider`` via ``context_providers``. It is the Python
    counterpart of the .NET ``TodoCompletionLoopEvaluator``.

    Args:
        looping_modes: When provided, the loop only continues while the agent's current operating
            mode (read from its :class:`~agent_framework.AgentModeProvider`) is one of these modes;
            in any other mode the predicate returns ``False`` so the agent stays interactive. Mode
            matching is case-insensitive. When ``None`` (default), the loop applies in every mode. An
            empty sequence is rejected (there would be no mode in which the loop could ever run).
            Restricting looping to certain modes is useful when, for example, the agent has a planning
            and execution mode, and you only want to loop on the execution mode until all todos are
            complete.  Looping until completion in planning is usually undesirable since the agent is
            still building the list of todos to complete.

    Returns:
        A predicate suitable for :class:`AgentLoopMiddleware`'s ``should_continue`` argument (and for
        ``create_harness_agent``'s ``loop_should_continue``).

    Raises:
        ValueError: ``looping_modes`` is an empty sequence.
    """
    if looping_modes is not None:
        allowed_modes: set[str] | None = {mode.strip().lower() for mode in looping_modes}
        if not allowed_modes:
            raise ValueError("looping_modes must be None or a non-empty sequence of mode names.")
    else:
        allowed_modes = None

    async def _should_continue(*, session: Any = None, agent: Any = None, **kwargs: Any) -> bool:
        from ._mode import AgentModeProvider, get_agent_mode
        from ._todo import TodoProvider

        if session is None or agent is None:
            return False

        if allowed_modes is not None:
            mode_provider = _resolve_context_provider(agent, AgentModeProvider)
            if mode_provider is not None:
                current_mode = get_agent_mode(
                    session,
                    source_id=mode_provider.source_id,
                    default_mode=mode_provider.default_mode,
                    available_modes=mode_provider.available_modes,
                )
            else:
                current_mode = get_agent_mode(session)
            if current_mode.strip().lower() not in allowed_modes:
                return False

        todo_provider = _resolve_context_provider(agent, TodoProvider)
        if todo_provider is None:
            return False
        items = await todo_provider.store.load_items(session, source_id=todo_provider.source_id)
        return any(not item.is_complete for item in items)

    return _should_continue


async def todos_remaining_message(*, session: Any = None, agent: Any = None, **kwargs: Any) -> str | None:
    """``next_message`` callable that reminds the agent which todos are still open.

    Designed to pair with :func:`todos_remaining` as a loop's ``next_message`` (e.g.
    ``create_harness_agent``'s ``loop_next_message``): between iterations it resolves the harness
    :class:`~agent_framework.TodoProvider` from the agent, lists the still-open todo items, and
    instructs the agent to complete them all before finishing.

    Returns ``None`` when the session/agent/provider is unavailable or no todos are open. In that
    case the loop's default ``next_message`` handling applies: with ``fresh_context=False`` (the
    default, used by ``create_harness_agent``) it reuses the previous iteration's messages verbatim
    (skipping progress injection); only with ``fresh_context=True`` does it fall back to
    ``DEFAULT_NEXT_MESSAGE``. In normal looping a ``None`` here is rare, since "no open todos" also
    makes :func:`todos_remaining` stop the loop before the next message is consulted.
    """
    from ._todo import TodoProvider

    if session is None or agent is None:
        return None
    todo_provider = _resolve_context_provider(agent, TodoProvider)
    if todo_provider is None:
        return None
    items = await todo_provider.store.load_items(session, source_id=todo_provider.source_id)
    open_items = [item for item in items if not item.is_complete]
    if not open_items:
        return None
    todo_lines = "\n".join(f"- {item.title}" for item in open_items)
    return (
        f"You still have {len(open_items)} open todo item(s) that must be addressed before you can "
        f"finish:\n{todo_lines}\n\n"
        "Continue working through them now. Mark each todo complete as you finish it, and only stop "
        "once every todo item is complete."
    )
