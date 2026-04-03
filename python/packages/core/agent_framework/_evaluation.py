# Copyright (c) Microsoft. All rights reserved.

"""Provider-agnostic evaluation framework for Microsoft Agent Framework.

Defines the core evaluation types and orchestration functions that work with
any evaluation provider (Azure AI Foundry, local evaluators, third-party
libraries, etc.).  Also includes ``LocalEvaluator`` and built-in check
functions for fast, API-free evaluation during inner-loop development and
CI smoke tests.

Cloud evaluator example:

.. code-block:: python

    from agent_framework import evaluate_agent, EvalResults
    from agent_framework.foundry import FoundryEvals

    evals = FoundryEvals(project_client=client, model="gpt-4o")
    results = await evaluate_agent(agent=agent, queries=["Hello"], evaluators=evals)
    results.raise_for_status()

Local evaluator example:

.. code-block:: python

    from agent_framework import LocalEvaluator, keyword_check, evaluate_agent

    local = LocalEvaluator(
        keyword_check("weather", "temperature"),
        tool_called_check("get_weather"),
    )
    results = await evaluate_agent(agent=agent, queries=queries, evaluators=local)
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import json
import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    TYPE_CHECKING,
    Any,
    Literal,
    Protocol,
    TypedDict,
    cast,
    overload,
    runtime_checkable,
)

from ._feature_stage import ExperimentalFeature, experimental
from ._tools import FunctionTool
from ._types import AgentResponse, Message

if TYPE_CHECKING:
    from ._agents import SupportsAgentRun
    from ._workflows._agent_executor import AgentExecutorResponse
    from ._workflows._workflow import Workflow, WorkflowRunResult

logger = logging.getLogger(__name__)


@experimental(feature_id=ExperimentalFeature.EVALS)
class EvalNotPassedError(Exception):
    """Raised when evaluation results contain failures."""


# region Core types


@experimental(feature_id=ExperimentalFeature.EVALS)
@runtime_checkable
class ConversationSplitter(Protocol):
    """Strategy for splitting a conversation into (query, response) messages.

    Any callable with this signature satisfies the protocol — including the
    built-in ``ConversationSplit`` enum members and custom functions:

    .. code-block:: python

        def my_splitter(conversation: list[Message]) -> tuple[list[Message], list[Message]]:
            '''Return (query_messages, response_messages).'''

    Custom splitters let you evaluate domain-specific boundaries — for example,
    splitting just before a memory-retrieval tool call to evaluate recall quality:

    .. code-block:: python

        def split_before_memory(conversation):
            for i, msg in enumerate(conversation):
                for c in msg.contents or []:
                    if c.type == "function_call" and c.name == "retrieve_memory":
                        return conversation[:i], conversation[i:]
            # Fallback: split at last user message
            return EvalItem._split_last_turn_static(conversation)


        item.split_messages(split=split_before_memory)
    """

    def __call__(self, conversation: list[Message]) -> tuple[list[Message], list[Message]]: ...


@experimental(feature_id=ExperimentalFeature.EVALS)
class ConversationSplit(str, Enum):
    """Built-in conversation split strategies.

    Each member is callable, satisfying the ``ConversationSplitter`` protocol::

        query_msgs, response_msgs = ConversationSplit.LAST_TURN(conversation)

    - ``LAST_TURN``: Split at the last user message.  Everything up to and
      including that message is the query; everything after is the response.
      Evaluates whether the agent answered the *latest* question well.

    - ``FULL``: The first user message (and any preceding system messages) is
      the query; the entire remainder of the conversation is the response.
      Evaluates whether the *whole conversation trajectory* served the
      original request.

    For custom splits, pass any callable with the ``ConversationSplitter``
    signature.
    """

    LAST_TURN = "last_turn"
    FULL = "full"

    def __call__(self, conversation: list[Message]) -> tuple[list[Message], list[Message]]:
        """Dispatch to the built-in splitter implementation."""
        return _BUILT_IN_SPLITTERS[self](conversation)


@experimental(feature_id=ExperimentalFeature.EVALS)
@dataclass
class ExpectedToolCall:
    """A tool call that an agent is expected to make.

    Used with :func:`evaluate_agent` to assert that the agent called the
    correct tools.  The *evaluator* decides the matching semantics (order,
    extras, argument checking); this type is pure data.

    Attributes:
        name: The tool/function name (e.g. ``"get_weather"``).
        arguments: Expected arguments.  ``None`` means "don't check arguments" or "no arguments".
    """

    name: str
    arguments: dict[str, Any] | None = None


def _split_last_turn(conversation: list[Message]) -> tuple[list[Message], list[Message]]:
    """Split at the last user message (default strategy)."""
    last_user_idx = -1
    for i, msg in enumerate(conversation):
        if msg.role == "user":
            last_user_idx = i
    if last_user_idx >= 0:
        return conversation[: last_user_idx + 1], conversation[last_user_idx + 1 :]
    return [], list(conversation)


def _split_full(conversation: list[Message]) -> tuple[list[Message], list[Message]]:
    """Split after the first user message (evaluates whole trajectory)."""
    for i, msg in enumerate(conversation):
        if msg.role == "user":
            return conversation[: i + 1], conversation[i + 1 :]
    return [], list(conversation)


_BUILT_IN_SPLITTERS: dict[ConversationSplit, Callable[[list[Message]], tuple[list[Message], list[Message]]]] = {
    ConversationSplit.LAST_TURN: _split_last_turn,
    ConversationSplit.FULL: _split_full,
}


@experimental(feature_id=ExperimentalFeature.EVALS)
class EvalItem:
    """A single item to be evaluated.

    Represents one query/response interaction in a provider-agnostic format.
    ``conversation`` is the single source of truth — ``query`` and ``response``
    are derived from it via the split strategy.

    Attributes:
        conversation: Full conversation as ``Message`` objects.
        tools: Typed tool objects (e.g. ``FunctionTool``) for evaluator logic.
        context: Optional grounding context document.
        expected_output: Optional expected output for ground-truth comparison.
        expected_tool_calls: Expected tool calls for tool-correctness
            evaluation.  See :class:`ExpectedToolCall`.
        split_strategy: Split strategy controlling how ``query`` and
            ``response`` are derived from the conversation. Defaults to
            ``ConversationSplit.LAST_TURN``.
    """

    def __init__(
        self,
        conversation: list[Message],
        tools: list[FunctionTool] | None = None,
        context: str | None = None,
        expected_output: str | None = None,
        expected_tool_calls: list[ExpectedToolCall] | None = None,
        split_strategy: ConversationSplitter | None = None,
    ) -> None:
        self.conversation = conversation
        self.tools = tools
        self.context = context
        self.expected_output = expected_output
        self.expected_tool_calls = expected_tool_calls
        self.split_strategy = split_strategy

    @property
    def query(self) -> str:
        """User query text, derived from the query side of the conversation split."""
        query_msgs, _ = self._split_conversation(self.split_strategy or ConversationSplit.LAST_TURN)
        user_texts = [m.text for m in query_msgs if m.role == "user" and m.text]
        return " ".join(user_texts).strip()

    @property
    def response(self) -> str:
        """Agent response text, derived from the response side of the conversation split."""
        _, response_msgs = self._split_conversation(self.split_strategy or ConversationSplit.LAST_TURN)
        assistant_texts = [m.text for m in response_msgs if m.role == "assistant" and m.text]
        return " ".join(assistant_texts).strip()

    def _split_conversation(self, split: ConversationSplitter) -> tuple[list[Message], list[Message]]:
        """Split ``self.conversation`` into (query_messages, response_messages)."""
        return split(self.conversation)

    def split_messages(
        self,
        split: ConversationSplitter | None = None,
    ) -> tuple[list[Message], list[Message]]:
        """Split the conversation into (query_messages, response_messages).

        Resolution order: explicit *split*, then ``self.split_strategy``,
        then ``ConversationSplit.LAST_TURN``.
        """
        effective = split or self.split_strategy or ConversationSplit.LAST_TURN
        return self._split_conversation(effective)

    @staticmethod
    def _split_last_turn_static(
        conversation: list[Message],
    ) -> tuple[list[Message], list[Message]]:
        """Split at the last user message.  Usable as a fallback in custom splitters."""
        return _split_last_turn(conversation)

    @staticmethod
    def per_turn_items(
        conversation: list[Message],
        *,
        tools: list[FunctionTool] | None = None,
        context: str | None = None,
    ) -> list[EvalItem]:
        """Split a multi-turn conversation into one ``EvalItem`` per turn.

        Each user message starts a new turn.  The resulting ``EvalItem``
        has cumulative context: ``query_messages`` contains the full
        conversation up to and including that user message, and
        ``response_messages`` contains the agent's actions up to the next
        user message.  This lets you evaluate each response independently
        with its full preceding context.

        Args:
            conversation: Full conversation as ``Message`` objects.
            tools: Tool objects shared across all items.
            context: Optional grounding context shared across all items.

        Returns:
            A list of ``EvalItem`` instances, one per user turn.
        """
        user_indices = [i for i, m in enumerate(conversation) if m.role == "user"]
        if not user_indices:
            return []

        items: list[EvalItem] = []
        for turn_idx, _ui in enumerate(user_indices):
            # Response runs from after the user message to the next user
            # message (or end of conversation).
            next_ui = user_indices[turn_idx + 1] if turn_idx + 1 < len(user_indices) else len(conversation)

            items.append(
                EvalItem(
                    conversation=conversation[:next_ui],
                    tools=tools,
                    context=context,
                )
            )

        return items


# endregion

# region Score and result types


@experimental(feature_id=ExperimentalFeature.EVALS)
@dataclass
class EvalScoreResult:
    """Result from a single evaluator on a single item.

    Attributes:
        name: Evaluator name (e.g. ``"relevance"``).
        score: Numeric score from the evaluator.
        passed: Whether the item passed this evaluator's threshold.
        sample: Optional raw evaluator output (rationale, metadata).
    """

    name: str
    score: float
    passed: bool | None = None
    sample: dict[str, Any] | None = None


@experimental(feature_id=ExperimentalFeature.EVALS)
@dataclass
class EvalItemResult:
    """Per-item result from an evaluation run.

    Attributes:
        item_id: Provider-assigned item identifier.
        status: ``"pass"``, ``"fail"``, or ``"error"``.
        scores: Per-evaluator results for this item.
        error_code: Error category when ``status == "error"``
            (e.g. ``"QueryExtractionError"``).
        error_message: Human-readable error detail.
        response_id: Responses API response ID, if applicable.
        input_text: The query/input that was evaluated.
        output_text: The response/output that was evaluated.
        token_usage: Token counts (``prompt_tokens``,
            ``completion_tokens``, ``total_tokens``).
        metadata: Additional provider-specific data.
    """

    item_id: str
    status: str
    scores: list[EvalScoreResult] = field(default_factory=lambda: list[EvalScoreResult]())
    error_code: str | None = None
    error_message: str | None = None
    response_id: str | None = None
    input_text: str | None = None
    output_text: str | None = None
    token_usage: dict[str, int] | None = None
    metadata: dict[str, Any] | None = None

    @property
    def is_error(self) -> bool:
        """Whether this item errored (infrastructure failure, not quality)."""
        return self.status in ("error", "errored")

    @property
    def is_passed(self) -> bool:
        """Whether this item passed all evaluators."""
        return self.status == "pass"

    @property
    def is_failed(self) -> bool:
        """Whether this item failed at least one evaluator."""
        return self.status == "fail"


@experimental(feature_id=ExperimentalFeature.EVALS)
class EvalResults:
    """Results from an evaluation run by a single provider.

    Attributes:
        provider: Name of the evaluation provider that produced these results.
        eval_id: The evaluation definition ID (provider-specific).
        run_id: The evaluation run ID (provider-specific).
        status: Run status - ``"completed"``, ``"failed"``, ``"canceled"``,
            or ``"timeout"`` if polling exceeded the deadline.
        result_counts: Pass/fail counts, populated when completed.
        report_url: URL to view results in the provider's portal.
        error: Error details when the run failed.
        per_evaluator: Per-evaluator result counts, keyed by evaluator name.
        items: Per-item results with individual pass/fail/error status,
            evaluator scores, error details, and token usage. Populated
            when the provider supports per-item retrieval (e.g. Foundry
            ``output_items`` API).
        sub_results: Per-agent breakdown for workflow evaluations, keyed by
            agent/executor name.

    Example:

    .. code-block:: python

        results = await evaluate_agent(agent=my_agent, queries=["Hello"], evaluators=evals)
        for r in results:
            print(f"{r.provider}: {r.passed}/{r.total}")

            # Per-item detail
            for item in r.items:
                print(f"  {item.item_id}: {item.status}")
                for score in item.scores:
                    print(f"    {score.name}: {score.score} ({'pass' if score.passed else 'fail'})")
                if item.is_error:
                    print(f"    Error: {item.error_code} - {item.error_message}")

        # Workflow eval - per-agent breakdown
        for r in results:
            for name, sub in r.sub_results.items():
                print(f"  {name}: {sub.passed}/{sub.total}")
    """

    def __init__(
        self,
        *,
        provider: str,
        eval_id: str = "",
        run_id: str = "",
        status: str = "completed",
        result_counts: dict[str, int] | None = None,
        report_url: str | None = None,
        error: str | None = None,
        per_evaluator: dict[str, dict[str, int]] | None = None,
        items: list[EvalItemResult] | None = None,
        sub_results: dict[str, EvalResults] | None = None,
    ) -> None:
        self.provider = provider
        self.eval_id = eval_id
        self.run_id = run_id
        self.status = status
        self.result_counts = result_counts
        self.report_url = report_url
        self.error = error
        self.per_evaluator = per_evaluator or {}
        self.items = items or []
        self.sub_results = sub_results or {}

    @property
    def passed(self) -> int:
        """Number of passing results."""
        return (self.result_counts or {}).get("passed", 0)

    @property
    def failed(self) -> int:
        """Number of failing results."""
        return (self.result_counts or {}).get("failed", 0)

    @property
    def total(self) -> int:
        """Total number of results (passed + failed)."""
        return self.passed + self.failed

    @property
    def all_passed(self) -> bool:
        """Whether all results passed with no failures or errors.

        For workflow evals with sub-agents, checks that all sub-results passed.
        Returns ``False`` if the run did not complete successfully.
        """
        if self.status not in ("completed",):
            return False
        errored = (self.result_counts or {}).get("errored", 0)
        own_passed = self.failed == 0 and errored == 0 and self.total > 0 if self.result_counts else True
        if self.sub_results:
            return own_passed and all(sub.all_passed for sub in self.sub_results.values())
        return self.failed == 0 and errored == 0 and self.total > 0

    def raise_for_status(self, msg: str | None = None) -> None:
        """Raise ``EvalNotPassedError`` if any results failed or errored.

        Similar to ``requests.Response.raise_for_status()`` — call after
        evaluation to verify quality in CI pipelines or test suites.

        Args:
            msg: Optional custom failure message.

        Raises:
            EvalNotPassedError: When any results failed or errored.
        """
        if not self.all_passed:
            errored = (self.result_counts or {}).get("errored", 0)
            detail = msg or (f"Eval run {self.run_id} {self.status}: {self.passed} passed, {self.failed} failed.")
            if errored:
                detail += f" {errored} errored."
            if self.report_url:
                detail += f" See {self.report_url} for details."
            if self.error:
                detail += f" Error: {self.error}"
            if self.sub_results:
                failed = [name for name, sub in self.sub_results.items() if not sub.all_passed]
                if failed:
                    detail += f" Failed: {', '.join(failed)}."
            if self.items:
                errored_items = [i for i in self.items if i.is_error]
                if errored_items:
                    summaries = [f"{i.item_id}: {i.error_code or 'unknown'}" for i in errored_items]
                    detail += f" Errored items: {', '.join(summaries)}."
            raise EvalNotPassedError(detail)


# endregion

# region Evaluator protocol


@experimental(feature_id=ExperimentalFeature.EVALS)
@runtime_checkable
class Evaluator(Protocol):
    """Protocol for evaluation providers.

    Any evaluation backend (Azure AI Foundry, local LLM-as-judge, custom
    scorers, etc.) implements this protocol. The provider encapsulates all
    connection details, evaluator selection, and execution logic.

    Example implementation:

    .. code-block:: python

        class MyEvaluator:
            def __init__(self, name: str = "my-evaluator"):
                self.name = name

            async def evaluate(self, items: Sequence[EvalItem], *, eval_name: str = "Eval") -> EvalResults:
                # Score each item and return results
                ...
    """

    name: str

    async def evaluate(
        self,
        items: Sequence[EvalItem],
        *,
        eval_name: str,
    ) -> EvalResults:
        """Evaluate a batch of items and return results.

        The evaluator determines which metrics to run. It may auto-detect
        capabilities from the items (e.g., run tool evaluators only when
        ``tools`` is present).

        Args:
            items: Eval data items to score.
            eval_name: Display name for the evaluation run.

        Returns:
            ``EvalResults`` with status, counts, and optional portal link.
        """
        ...


# endregion

# region Converter


@experimental(feature_id=ExperimentalFeature.EVALS)
class AgentEvalConverter:
    """Converts agent-framework types to evaluation format.

    Handles the type gap between agent-framework's ``Message`` / ``Content`` /
    ``FunctionTool`` types and the OpenAI-style agent message schema used by
    evaluation providers.  All methods are static — no instantiation needed.
    """

    @staticmethod
    def convert_message(message: Message) -> list[dict[str, Any]]:
        """Convert a single ``Message`` to Foundry agent evaluator format.

        Uses typed content lists as required by Foundry evaluators:

        .. code-block:: python

            {"role": "assistant", "content": [{"type": "tool_call", ...}]}
            {"role": "user", "content": [{"type": "input_image", ...}]}

        Supported content types:

        * ``text`` → ``{"type": "text", "text": ...}``
        * ``data`` / ``uri`` (images) → ``{"type": "input_image", "image_url": ...}``
        * ``function_call`` → ``{"type": "tool_call", ...}``
        * ``function_result`` → ``{"type": "tool_result", ...}``

        A single agent-framework ``Message`` with multiple ``function_result``
        contents produces multiple output messages (one per tool result).

        Args:
            message: An agent-framework ``Message``.

        Returns:
            A list of Foundry-format message dicts.
        """
        role = message.role
        contents = message.contents or []

        content_items: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []

        for c in contents:
            if c.type == "text" and c.text:
                content_items.append({"type": "text", "text": c.text})
            elif c.type in ("data", "uri") and c.uri:
                # Image / media content → OpenAI input_image format
                img: dict[str, Any] = {
                    "type": "input_image",
                    "image_url": c.uri,
                }
                if c.media_type:
                    img["detail"] = "auto"
                content_items.append(img)
            elif c.type == "function_call":
                args = c.arguments
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except (json.JSONDecodeError, TypeError):
                        # Sanitize to avoid leaking sensitive tool-call arguments
                        # to external evaluation services.
                        args = {"_raw_arguments": "[unparseable]"}
                tc: dict[str, Any] = {
                    "type": "tool_call",
                    "tool_call_id": c.call_id or "",
                    "name": c.name or "",
                }
                if args:
                    tc["arguments"] = args
                content_items.append(tc)
            elif c.type == "function_result":
                result_val = c.result
                if isinstance(result_val, str):
                    with contextlib.suppress(json.JSONDecodeError, TypeError):
                        result_val = json.loads(result_val)
                tool_results.append({
                    "call_id": c.call_id or "",
                    "result": result_val,
                })

        output: list[dict[str, Any]] = []

        if tool_results:
            for tr in tool_results:
                output.append({
                    "role": "tool",
                    "tool_call_id": tr["call_id"],
                    "content": [{"type": "tool_result", "tool_result": tr["result"]}],
                })
        elif content_items:
            output.append({"role": role, "content": content_items})
        else:
            output.append({
                "role": role,
                "content": [{"type": "text", "text": ""}],
            })

        return output

    @staticmethod
    def convert_messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
        """Convert a sequence of ``Message`` objects to Foundry evaluator format.

        Args:
            messages: Agent-framework messages.

        Returns:
            A list of Foundry-format message dicts with typed content lists.
        """
        result: list[dict[str, Any]] = []
        for msg in messages:
            result.extend(AgentEvalConverter.convert_message(msg))
        return result

    @staticmethod
    def extract_tools(agent: Any) -> list[dict[str, Any]]:
        """Extract tool definitions from an agent instance.

        Reads ``agent.default_options["tools"]`` and ``agent.mcp_tools``
        and converts each ``FunctionTool`` to ``{name, description, parameters}``.

        Args:
            agent: An agent-framework agent instance.

        Returns:
            A list of tool definition dicts.
        """
        tools: list[dict[str, Any]] = []
        seen: set[str] = set()
        raw_tools = getattr(agent, "default_options", {}).get("tools", [])
        for t in raw_tools:
            if isinstance(t, FunctionTool) and t.name not in seen:
                tools.append({
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.parameters(),
                })
                seen.add(t.name)
        # Include tools from connected MCP servers
        for mcp in getattr(agent, "mcp_tools", []):
            for t in getattr(mcp, "functions", []):
                if isinstance(t, FunctionTool) and t.name not in seen:
                    tools.append({
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters(),
                    })
                    seen.add(t.name)
        return tools

    @staticmethod
    def to_eval_item(
        *,
        query: str | Sequence[Message],
        response: AgentResponse[Any],
        agent: Any | None = None,
        tools: Sequence[FunctionTool] | None = None,
        context: str | None = None,
    ) -> EvalItem:
        """Convert a complete agent interaction to an ``EvalItem``.

        Args:
            query: The user query string, or input messages.
            response: The agent's response.
            agent: Optional agent instance to auto-extract tool definitions.
            tools: Explicit tool list (takes precedence over *agent*).
            context: Optional context document for groundedness evaluation.

        Returns:
            An ``EvalItem`` suitable for passing to any ``Evaluator``.
        """
        input_msgs = [Message("user", [query])] if isinstance(query, str) else list(query)

        all_msgs = list(input_msgs) + list(response.messages or [])

        typed_tools: list[FunctionTool] = []
        if tools:
            typed_tools = list(tools)
        elif agent:
            raw_tools = getattr(agent, "default_options", {}).get("tools", [])
            typed_tools = [t for t in raw_tools if isinstance(t, FunctionTool)]
            # Include tools from connected MCP servers
            seen = {t.name for t in typed_tools}
            for mcp in getattr(agent, "mcp_tools", []):
                for t in getattr(mcp, "functions", []):
                    if isinstance(t, FunctionTool) and t.name not in seen:
                        typed_tools.append(t)
                        seen.add(t.name)

        return EvalItem(
            conversation=all_msgs,
            tools=typed_tools or None,
            context=context,
        )


# endregion

# region Workflow extraction helpers


class _AgentEvalData(TypedDict):
    executor_id: str
    query: str | Sequence[Message]
    response: AgentResponse[Any]
    agent: Any | None


def _extract_agent_eval_data(
    workflow_result: WorkflowRunResult,
    workflow: Workflow | None = None,
) -> list[_AgentEvalData]:
    """Walk a WorkflowRunResult and extract per-agent query/response pairs.

    Pairs ``executor_invoked`` with ``executor_completed`` events for each
    ``AgentExecutor``. Skips internal framework executors.
    """
    from ._workflows._agent_executor import AgentExecutor as AE
    from ._workflows._agent_executor import AgentExecutorResponse

    invoked_data: dict[str, Any] = {}
    results: list[_AgentEvalData] = []

    for event in workflow_result:
        if event.type == "executor_invoked" and event.executor_id:
            invoked_data[event.executor_id] = event.data

        elif event.type == "executor_completed" and event.executor_id:
            executor_id = event.executor_id

            # Skip internal framework executors
            if executor_id.startswith("_") or executor_id.lower() in {"input-conversation", "end-conversation", "end"}:
                logger.debug("Skipping internal executor %r during eval data extraction", executor_id)
                continue

            completion_data: Any = event.data
            agent_exec_response: AgentExecutorResponse | None = None

            if isinstance(completion_data, list):
                for cdata_item in cast(list[Any], completion_data):  # type: ignore[redundant-cast]
                    if isinstance(cdata_item, AgentExecutorResponse):
                        agent_exec_response = cdata_item
                        break
            elif isinstance(completion_data, AgentExecutorResponse):
                agent_exec_response = completion_data

            if agent_exec_response is None:
                continue

            query: str | list[Message]
            if agent_exec_response.full_conversation:
                user_msgs = [m for m in agent_exec_response.full_conversation if m.role == "user"]
                query = user_msgs or agent_exec_response.full_conversation  # type: ignore[assignment]
            elif executor_id in invoked_data:
                input_data: Any = invoked_data[executor_id]
                query = (  # type: ignore[assignment]
                    input_data if isinstance(input_data, (str, list)) else str(input_data)
                )
            else:
                continue

            agent_ref = None
            if workflow is not None:
                executor = workflow.executors.get(executor_id)
                if executor is not None and isinstance(executor, AE):
                    agent_ref = executor.agent

            results.append(
                _AgentEvalData(
                    executor_id=executor_id,
                    query=query,
                    response=agent_exec_response.agent_response,
                    agent=agent_ref,
                )
            )

    return results


def _extract_overall_query(workflow_result: WorkflowRunResult) -> str | None:
    """Extract the original user query from a workflow result."""
    for event in workflow_result:
        if event.type == "executor_invoked" and event.data is not None:
            data: Any = event.data
            if isinstance(data, str):
                return data
            if isinstance(data, list) and data:
                items_list = cast(list[Any], data)  # type: ignore[redundant-cast]
                first = items_list[0]
                if isinstance(first, Message):
                    msgs: list[Message] = [m for m in items_list if isinstance(m, Message)]
                    return " ".join(str(m.text) for m in msgs if hasattr(m, "text") and m.role == "user")
                if isinstance(first, str):
                    return " ".join(str(s) for s in items_list)
            return str(data)  # type: ignore[reportUnknownArgumentType]
    return None


# endregion

# region Local evaluation checks


@experimental(feature_id=ExperimentalFeature.EVALS)
@dataclass
class CheckResult:
    """Result of a single check on a single evaluation item.

    Attributes:
        passed: Whether the check passed.
        reason: Human-readable explanation.
        check_name: Name of the check that produced this result.
    """

    passed: bool
    reason: str
    check_name: str


EvalCheck = Callable[[EvalItem], CheckResult | Awaitable[CheckResult]]
"""A check function that takes an ``EvalItem`` and returns a ``CheckResult``.

Both sync and async functions are supported.  Async checks should return
an awaitable ``CheckResult``; they will be awaited automatically by
``LocalEvaluator``.
"""


@experimental(feature_id=ExperimentalFeature.EVALS)
def keyword_check(*keywords: str, case_sensitive: bool = False) -> EvalCheck:
    """Check that the response contains all specified keywords.

    Args:
        *keywords: Required keywords that must appear in the response.
        case_sensitive: Whether matching is case-sensitive (default ``False``).

    Returns:
        A check function for use with ``LocalEvaluator``.

    Example:

    .. code-block:: python

        check = keyword_check("weather", "temperature")
    """

    def _check(item: EvalItem) -> CheckResult:
        text = item.response if case_sensitive else item.response.lower()
        missing = [k for k in keywords if (k if case_sensitive else k.lower()) not in text]
        if missing:
            return CheckResult(passed=False, reason=f"Missing keywords: {missing}", check_name="keyword_check")
        return CheckResult(passed=True, reason="All keywords found", check_name="keyword_check")

    return _check


@experimental(feature_id=ExperimentalFeature.EVALS)
def tool_called_check(*tool_names: str, mode: Literal["all", "any"] = "all") -> EvalCheck:
    """Check that specific tools were called during the conversation.

    Inspects the conversation history for ``tool_calls`` entries matching
    the expected tool names.

    Args:
        *tool_names: Names of tools that should have been called.
        mode: ``"all"`` requires every tool to be called; ``"any"`` requires
            at least one.  Defaults to ``"all"``.

    Returns:
        A check function for use with ``LocalEvaluator``.

    Example:

    .. code-block:: python

        check = tool_called_check("get_weather", "get_flight_price")
    """

    def _check(item: EvalItem) -> CheckResult:
        expected = set(tool_names)
        called: set[str] = set()
        for msg in item.conversation:
            for c in msg.contents or []:
                if c.type == "function_call" and c.name:
                    called.add(c.name)
                    if mode == "all" and expected.issubset(called):
                        return CheckResult(
                            passed=True,
                            reason=f"All expected tools called: {sorted(called)}",
                            check_name="tool_called",
                        )
                    if mode == "any" and expected & called:
                        return CheckResult(
                            passed=True,
                            reason=f"Expected tool found: {sorted(expected & called)}",
                            check_name="tool_called",
                        )
        if mode == "all":
            missing = [t for t in tool_names if t not in called]
            if missing:
                return CheckResult(
                    passed=False,
                    reason=f"Expected tools not called: {missing} (called: {sorted(called)})",
                    check_name="tool_called",
                )
            return CheckResult(
                passed=True,
                reason=f"All expected tools called: {sorted(called)}",
                check_name="tool_called",
            )
        return CheckResult(
            passed=False,
            reason=f"None of expected tools called: {list(tool_names)} (called: {sorted(called)})",
            check_name="tool_called",
        )

    return _check


def _extract_tool_calls(item: EvalItem) -> list[tuple[str, dict[str, Any] | None]]:
    """Extract (name, arguments) pairs from the conversation's function calls."""
    calls: list[tuple[str, dict[str, Any] | None]] = []
    for msg in item.conversation:
        for c in msg.contents or []:
            if c.type == "function_call" and c.name:
                args: dict[str, Any] | None = None
                if isinstance(c.arguments, dict):
                    args = c.arguments
                elif isinstance(c.arguments, str):
                    try:
                        parsed = json.loads(c.arguments)
                        if isinstance(parsed, dict):
                            args = cast(dict[str, Any], parsed)
                    except (json.JSONDecodeError, TypeError):
                        pass
                calls.append((c.name, args))
    return calls


@experimental(feature_id=ExperimentalFeature.EVALS)
def tool_calls_present(item: EvalItem) -> CheckResult:
    """Check that all expected tool calls were made (unordered, extras OK).

    Uses ``item.expected_tool_calls`` — checks that every expected tool name
    appears at least once in the conversation.  Does not check arguments or
    ordering.  Extra (unexpected) tool calls are not penalized.

    Example:

    .. code-block:: python

        local = LocalEvaluator(tool_calls_present)
        results = await evaluate_agent(
            agent=agent,
            queries=["What's the weather?"],
            expected_tool_calls=[[ExpectedToolCall("get_weather")]],
            evaluators=local,
        )
    """
    expected = item.expected_tool_calls or []
    if not expected:
        return CheckResult(passed=True, reason="No expected tool calls specified.", check_name="tool_calls_present")

    actual_names = {name for name, _ in _extract_tool_calls(item)}
    expected_names = [e.name for e in expected]
    found = [n for n in expected_names if n in actual_names]
    missing = [n for n in expected_names if n not in actual_names]

    if missing:
        return CheckResult(
            passed=False,
            reason=f"Missing tool calls: {missing} (called: {sorted(actual_names)})",
            check_name="tool_calls_present",
        )
    return CheckResult(
        passed=True,
        reason=f"All expected tools called: {found} (called: {sorted(actual_names)})",
        check_name="tool_calls_present",
    )


@experimental(feature_id=ExperimentalFeature.EVALS)
def tool_call_args_match(item: EvalItem) -> CheckResult:
    """Check that expected tool calls match on name and arguments.

    For each expected tool call, finds matching calls in the conversation
    by name.  If ``ExpectedToolCall.arguments`` is provided, checks that
    the actual arguments contain all expected key-value pairs (subset
    match — extra actual arguments are OK).

    Example:

    .. code-block:: python

        local = LocalEvaluator(tool_call_args_match)
        results = await evaluate_agent(
            agent=agent,
            queries=["What's the weather in NYC?"],
            expected_tool_calls=[
                [ExpectedToolCall("get_weather", {"location": "NYC"})],
            ],
            evaluators=local,
        )
    """
    expected = item.expected_tool_calls or []
    if not expected:
        return CheckResult(passed=True, reason="No expected tool calls specified.", check_name="tool_call_args_match")

    actual_calls = _extract_tool_calls(item)
    matched = 0
    details: list[str] = []

    for exp in expected:
        matching = [(n, a) for n, a in actual_calls if n == exp.name]
        if not matching:
            details.append(f"  {exp.name}: not called")
            continue

        if exp.arguments is None:
            matched += 1
            details.append(f"  {exp.name}: called (args not checked)")
            continue

        # Subset match — all expected keys present with expected values
        found = False
        for _, actual_args in matching:
            if actual_args is None:
                continue
            if all(actual_args.get(k) == v for k, v in exp.arguments.items()):
                found = True
                break

        if found:
            matched += 1
            details.append(f"  {exp.name}: args match")
        else:
            actual_args_list = [a for _, a in matching]
            details.append(f"  {exp.name}: args mismatch (actual: {actual_args_list})")

    passed = matched == len(expected)
    score_str = f"{matched}/{len(expected)}"
    detail_str = "\n".join(details)
    reason = f"Tool call args match: {score_str}\n{detail_str}"

    return CheckResult(passed=passed, reason=reason, check_name="tool_call_args_match")


# endregion

# region Function evaluator — wrap plain functions as EvalChecks

# Parameters recognized by the function evaluator wrapper
_KNOWN_PARAMS = frozenset({
    "query",
    "response",
    "expected_output",
    "expected_tool_calls",
    "conversation",
    "tools",
    "context",
})


def _resolve_function_args(
    fn: Callable[..., Any],
    item: EvalItem,
    *,
    _param_names: frozenset[str] | set[str] | None = None,
) -> dict[str, Any]:
    """Build a kwargs dict for *fn* based on its signature and the EvalItem.

    Supported parameter names:

    ====================== ====================================================
    Name                   Value from EvalItem
    ====================== ====================================================
    query                  ``item.query``
    response               ``item.response``
    expected_output        ``item.expected_output``  (empty string if not set)
    expected_tool_calls    ``item.expected_tool_calls``  (empty list if not set)
    conversation           ``item.conversation``  (list[Message])
    tools                  ``item.tools``  (typed ``FunctionTool`` objects)
    context                ``item.context``
    ====================== ====================================================

    Parameters with default values are only supplied when their name is
    recognised.  Unknown required parameters raise ``TypeError``.

    When called from the ``@evaluator`` wrapper the pre-computed
    *_param_names* set avoids repeated ``inspect.signature`` calls.
    """
    field_map: dict[str, Any] = {
        "query": item.query,
        "response": item.response,
        "expected_output": item.expected_output or "",
        "expected_tool_calls": item.expected_tool_calls or [],
        "conversation": item.conversation,
        "tools": item.tools,
        "context": item.context,
    }

    if _param_names is not None:
        return {k: field_map[k] for k in _param_names if k in field_map}

    # Fallback: introspect at call time (for direct callers)
    sig = inspect.signature(fn)
    kwargs: dict[str, Any] = {}

    for name, param in sig.parameters.items():
        if name in field_map:
            kwargs[name] = field_map[name]
        elif param.default is inspect.Parameter.empty:
            raise TypeError(
                f"Function evaluator '{fn.__name__}' has unknown required parameter "
                f"'{name}'.  Supported: {sorted(_KNOWN_PARAMS)}"
            )
        # else: has a default — leave it to Python

    return kwargs


def _coerce_result(value: Any, check_name: str) -> CheckResult:
    """Convert a function evaluator return value to a ``CheckResult``.

    Accepted return types:

    * ``bool`` — True/False maps directly to pass/fail.
    * ``int | float`` — ≥ 0.5 is pass (score is included in reason).
    * ``CheckResult`` — returned as-is.
    * ``dict`` with ``score`` or ``passed`` key — converted to CheckResult.
    """
    if isinstance(value, CheckResult):
        return value

    if isinstance(value, bool):
        return CheckResult(passed=value, reason="passed" if value else "failed", check_name=check_name)

    if isinstance(value, (int, float)):
        passed = value >= 0.5
        return CheckResult(passed=passed, reason=f"score={value:.3f}", check_name=check_name)

    if isinstance(value, dict):
        d = cast(dict[str, Any], value)
        if "score" in d:
            try:
                score = float(d["score"])
            except (TypeError, ValueError) as exc:
                raise TypeError(
                    f"Function evaluator '{check_name}' returned dict with non-numeric 'score' value: {d['score']!r}"
                ) from exc
            # Honour an explicit 'passed' override; otherwise threshold-based.
            passed = bool(d["passed"]) if "passed" in d else score >= float(d.get("threshold", 0.5))
            reason = str(d.get("reason", f"score={score:.3f}"))
            return CheckResult(passed=passed, reason=reason, check_name=check_name)
        if "passed" in d:
            passed_val = d["passed"]
            if not isinstance(passed_val, (bool, int)):
                raise TypeError(
                    f"Function evaluator '{check_name}' returned dict with non-boolean 'passed' value: {passed_val!r}"
                )
            return CheckResult(
                passed=bool(passed_val),
                reason=str(d.get("reason", "passed" if passed_val else "failed")),
                check_name=check_name,
            )

    value_type_name = type(value).__name__  # type: ignore[reportUnknownMemberType]
    msg = (
        f"Function evaluator '{check_name}' returned unsupported type "
        f"{value_type_name}. Expected bool, float, dict, or CheckResult."
    )
    raise TypeError(msg)


@overload
def evaluator(fn: Callable[..., Any], /) -> EvalCheck: ...


@overload
def evaluator(*, name: str | None = None) -> Callable[[Callable[..., Any]], EvalCheck]: ...


@experimental(feature_id=ExperimentalFeature.EVALS)
def evaluator(
    fn: Callable[..., Any] | None = None,
    *,
    name: str | None = None,
) -> EvalCheck | Callable[[Callable[..., Any]], EvalCheck]:
    """Wrap a plain function as an ``EvalCheck`` for use with ``LocalEvaluator``.

    Works with both sync and async functions.  The function's parameter names
    determine what data it receives from the ``EvalItem``.  Any combination of
    the following parameter names is valid:

    * ``query`` — the user query (str)
    * ``response`` — the agent response (str)
    * ``expected_output`` — expected output for ground-truth comparison (str)
    * ``conversation`` — full conversation history (list[Message])
    * ``tools`` — typed tool objects (list[FunctionTool])
    * ``context`` — grounding context (str | None)

    Return ``bool``, ``float`` (≥0.5 = pass), ``dict`` with ``score`` or
    ``passed`` key, or ``CheckResult``.

    Can be used as a decorator (with or without arguments) or called directly:

    .. code-block:: python

        # Decorator — no args
        @evaluator
        def mentions_weather(query: str, response: str) -> bool:
            return "weather" in response.lower()


        # Decorator — with name
        @evaluator(name="length_check")
        def is_not_too_long(response: str) -> bool:
            return len(response) < 2000


        # Direct wrapping
        check = evaluator(my_scorer, name="my_scorer")


        # Async function — handled automatically
        @evaluator
        async def llm_judge(query: str, response: str) -> float:
            result = await my_llm_client.score(query, response)
            return result.score


        # Use with LocalEvaluator
        local = LocalEvaluator(mentions_weather, is_not_too_long, check, llm_judge)

    Args:
        fn: The function to wrap.  If omitted, returns a decorator.
        name: Display name for the check (defaults to ``fn.__name__``).
    """

    def _wrap(func: Callable[..., Any]) -> EvalCheck:
        check_name: str = name or getattr(func, "__name__", None) or "evaluator"
        # Cache signature introspection once per wrapped function
        sig = inspect.signature(func)
        param_names = {
            n for n, p in sig.parameters.items() if n in _KNOWN_PARAMS or p.default is inspect.Parameter.empty
        }
        required_unknown = {
            n for n, p in sig.parameters.items() if n not in _KNOWN_PARAMS and p.default is inspect.Parameter.empty
        }
        if required_unknown:
            raise TypeError(
                f"Function evaluator '{func.__name__}' has unknown required parameter(s) "
                f"{sorted(required_unknown)}.  Supported: {sorted(_KNOWN_PARAMS)}"
            )

        async def _check(item: EvalItem) -> CheckResult:
            kwargs = _resolve_function_args(func, item, _param_names=param_names)
            result = func(**kwargs)
            if inspect.isawaitable(result):
                result = await result
            return _coerce_result(value=result, check_name=check_name)

        _check.__name__ = check_name  # type: ignore[attr-defined,assignment]
        _check.__doc__ = func.__doc__
        return _check

    # Support @evaluator (no parens) and @evaluator(name="x")
    if fn is not None:
        return _wrap(fn)
    return _wrap


# endregion

# region LocalEvaluator


async def _run_check(check_fn: EvalCheck, item: EvalItem) -> CheckResult:
    """Run a single check, awaiting the result if it is a coroutine."""
    result = check_fn(item)
    if inspect.isawaitable(result):
        result = await result
    return result


@experimental(feature_id=ExperimentalFeature.EVALS)
class LocalEvaluator:
    """Evaluation provider that runs checks locally without API calls.

    Implements the ``Evaluator`` protocol. Each check function is applied
    to every item. An item passes only if all checks pass.

    Examples:
        Basic usage:

        .. code-block:: python

            from agent_framework import LocalEvaluator, keyword_check, evaluate_agent

            local = LocalEvaluator(
                keyword_check("weather"),
                tool_called_check("get_weather"),
            )
            results = await evaluate_agent(agent=agent, queries=queries, evaluators=local)

        Mixing with cloud evaluators:

        .. code-block:: python

            from agent_framework.foundry import FoundryEvals

            results = await evaluate_agent(
                agent=agent,
                queries=queries,
                evaluators=[local, FoundryEvals(project_client=client, model="gpt-4o")],
            )
    """

    def __init__(self, *checks: EvalCheck):
        self.name = "Local"
        self._checks = checks

    async def evaluate(
        self,
        items: Sequence[EvalItem],
        *,
        eval_name: str = "Local Eval",
    ) -> EvalResults:
        """Run all checks on each item and return aggregated results.

        An item passes only if every check passes for that item. Per-check
        breakdowns are available in ``per_evaluator``.

        Supports both sync and async check functions (from
        :func:`evaluator`).
        """
        passed = 0
        failed = 0
        per_check: dict[str, dict[str, int]] = {}
        failure_reasons: list[str] = []
        result_items: list[EvalItemResult] = []

        for item_idx, item in enumerate(items):
            check_results = await asyncio.gather(*[_run_check(fn, item) for fn in self._checks])
            item_passed = True
            item_scores: list[EvalScoreResult] = []
            for result in check_results:
                counts = per_check.setdefault(result.check_name, {"passed": 0, "failed": 0, "errored": 0})
                if result.passed:
                    counts["passed"] += 1
                else:
                    counts["failed"] += 1
                    item_passed = False
                    failure_reasons.append(f"{result.check_name}: {result.reason}")
                item_scores.append(
                    EvalScoreResult(
                        name=result.check_name,
                        score=1.0 if result.passed else 0.0,
                        passed=result.passed,
                        sample={"reason": result.reason} if result.reason else None,
                    )
                )

            if item_passed:
                passed += 1
            else:
                failed += 1

            result_items.append(
                EvalItemResult(
                    item_id=str(item_idx),
                    status="pass" if item_passed else "fail",
                    scores=item_scores,
                    input_text=item.query,
                    output_text=item.response,
                )
            )

        return EvalResults(
            provider=self.name,
            eval_id="local",
            run_id=eval_name,
            status="completed",
            result_counts={"passed": passed, "failed": failed, "errored": 0},
            per_evaluator=per_check,
            items=result_items,
            error="; ".join(failure_reasons) if failure_reasons else None,
        )


# endregion

# region Public orchestration functions


@experimental(feature_id=ExperimentalFeature.EVALS)
async def evaluate_agent(
    *,
    agent: SupportsAgentRun | None = None,
    queries: str | Sequence[str] | None = None,
    expected_output: str | Sequence[str] | None = None,
    expected_tool_calls: Sequence[ExpectedToolCall] | Sequence[Sequence[ExpectedToolCall]] | None = None,
    responses: AgentResponse[Any] | Sequence[AgentResponse[Any]] | None = None,
    evaluators: Evaluator | Callable[..., Any] | Sequence[Evaluator | Callable[..., Any]],
    eval_name: str | None = None,
    context: str | None = None,
    conversation_split: ConversationSplitter | None = None,
    num_repetitions: int = 1,
) -> list[EvalResults]:
    """Run an agent against test queries and evaluate the results.

    The simplest path for evaluating an agent during development. For each
    query, runs the agent, converts the interaction to eval format, and
    submits to the evaluator(s).

    All sequence parameters (``queries``, ``expected_output``,
    ``expected_tool_calls``, ``responses``) accept either a single value
    or a list for convenience.

    If ``responses`` is provided, skips running the agent and evaluates those
    responses directly — but still extracts tool definitions from the agent.
    In this mode ``queries`` is required to construct the conversation.

    Args:
        agent: An agent-framework agent instance.
        queries: Test query or queries to run the agent against. A single
            string is wrapped into a one-element list. Required when
            ``responses`` is not provided.
        expected_output: Ground-truth expected output(s), one per query. A
            single string is wrapped into a one-element list. When provided,
            must be the same length as ``queries``. Each value is stamped on
            the corresponding ``EvalItem.expected_output`` for evaluators
            that compare against a reference answer.
        expected_tool_calls: Expected tool call(s), one list per query. A
            single flat list of ``ExpectedToolCall`` is wrapped into a
            one-element nested list. When provided, must be the same length
            as ``queries``.
        responses: Pre-existing ``AgentResponse``(s) to evaluate without
            running the agent. A single response is wrapped into a one-element
            list. When provided, ``queries`` must also be provided to
            construct the conversation for evaluation.
        evaluators: One or more ``Evaluator`` instances.
        eval_name: Display name (defaults to agent name).
        context: Optional context for groundedness evaluation.
        conversation_split: Split strategy applied to all items, overriding
            each evaluator's default.  See ``ConversationSplitter``.
        num_repetitions: Number of times to run each query (default 1).
            When > 1, each query is invoked independently N times to measure
            consistency. Results contain all N x len(queries) items.
            Ignored when ``responses`` is provided (pre-existing responses
            are evaluated as-is).

    Returns:
        A list of ``EvalResults``, one per evaluator provider.

    Raises:
        ValueError: If neither ``queries`` nor ``responses`` is provided.

    Examples:
        Run and evaluate:

        .. code-block:: python

            results = await evaluate_agent(
                agent=my_agent,
                queries="What's the weather?",
                evaluators=evals,
            )

        Evaluate existing responses:

        .. code-block:: python

            response = await agent.run([Message("user", ["What's the weather?"])])
            results = await evaluate_agent(
                agent=agent,
                responses=response,
                queries="What's the weather?",
                evaluators=evals,
            )

        With ground-truth expected answers:

        .. code-block:: python

            results = await evaluate_agent(
                agent=my_agent,
                queries=["What's 2+2?", "Capital of France?"],
                expected_output=["4", "Paris"],
                evaluators=evals,
            )

        With expected tool calls:

        .. code-block:: python

            results = await evaluate_agent(
                agent=my_agent,
                queries="What's the weather in NYC?",
                expected_tool_calls=[ExpectedToolCall("get_weather", {"location": "NYC"})],
                evaluators=evals,
            )
    """
    # Normalize singular values to lists
    if isinstance(queries, str):
        queries = [queries]
    if isinstance(expected_output, str):
        expected_output = [expected_output]
    if isinstance(responses, AgentResponse):
        responses = [responses]
    if (
        expected_tool_calls is not None
        and len(expected_tool_calls) > 0
        and isinstance(expected_tool_calls[0], ExpectedToolCall)
    ):
        expected_tool_calls = [list(cast(Sequence[ExpectedToolCall], expected_tool_calls))]

    items: list[EvalItem] = []

    # Validate num_repetitions
    if num_repetitions < 1:
        raise ValueError(f"num_repetitions must be >= 1, got {num_repetitions}.")

    # Validate expected_output length against queries
    if expected_output is not None and queries is not None and len(expected_output) != len(queries):
        raise ValueError(f"Got {len(queries)} queries but {len(expected_output)} expected_output values.")

    # Validate expected_tool_calls length against queries
    if expected_tool_calls is not None and queries is not None and len(expected_tool_calls) != len(queries):
        raise ValueError(f"Got {len(queries)} queries but {len(expected_tool_calls)} expected_tool_calls lists.")

    if responses is not None:
        # Evaluate pre-existing responses (don't run the agent)
        resp_list = list(responses)

        if queries is not None:
            query_list = list(queries)
            if len(query_list) != len(resp_list):
                raise ValueError(f"Got {len(query_list)} queries but {len(resp_list)} responses.")
            for q, r in zip(query_list, resp_list):
                items.append(
                    AgentEvalConverter.to_eval_item(
                        query=q,
                        response=r,
                        agent=agent,
                        context=context,
                    )
                )
        else:
            raise ValueError(
                "Provide 'queries' alongside 'responses' so the conversation "
                "can be constructed for evaluation. For Responses API "
                "evaluation by response ID, use evaluate_traces(response_ids=...) from "
                "the azure-ai package."
            )
    elif queries is not None and agent is not None:
        # Run the agent against test queries, with repetitions
        for _rep in range(num_repetitions):
            for query in queries:
                response = await agent.run([Message("user", [query])])
                items.append(
                    AgentEvalConverter.to_eval_item(
                        query=query,
                        response=response,
                        agent=agent,
                        context=context,
                    )
                )
    elif queries is not None and agent is None:
        raise ValueError(
            "Provide 'agent' when using 'queries' to run the agent. "
            "To evaluate pre-existing responses without an agent, use 'responses=' instead."
        )
    else:
        raise ValueError("Provide either 'queries' (with 'agent') or 'responses' (or both).")

    # Stamp expected output values on items (repeated across all repetitions)
    if expected_output is not None:
        query_count = len(expected_output)
        for i, item in enumerate(items):
            item.expected_output = expected_output[i % query_count]

    # Stamp expected tool calls on items (repeated across all repetitions)
    if expected_tool_calls is not None:
        # After normalization, expected_tool_calls is Sequence[Sequence[ExpectedToolCall]]
        tc_list = cast(Sequence[Sequence[ExpectedToolCall]], expected_tool_calls)
        query_count = len(tc_list)
        for i, item in enumerate(items):
            item.expected_tool_calls = list(tc_list[i % query_count])

    # Stamp split strategy on items so evaluators respect it
    if conversation_split is not None:
        for item in items:
            item.split_strategy = conversation_split

    name = eval_name or f"Eval: {getattr(agent, 'name', None) or getattr(agent, 'id', 'agent') if agent else 'agent'}"
    return await _run_evaluators(evaluators, items, eval_name=name)


@experimental(feature_id=ExperimentalFeature.EVALS)
async def evaluate_workflow(
    *,
    workflow: Workflow,
    workflow_result: WorkflowRunResult | None = None,
    queries: str | Sequence[str] | None = None,
    evaluators: Evaluator | Callable[..., Any] | Sequence[Evaluator | Callable[..., Any]],
    eval_name: str | None = None,
    include_overall: bool = True,
    include_per_agent: bool = True,
    conversation_split: ConversationSplitter | None = None,
    num_repetitions: int = 1,
) -> list[EvalResults]:
    """Evaluate a multi-agent workflow with per-agent breakdown.

    Evaluates each sub-agent individually and (optionally) the workflow's
    overall output. Returns one ``EvalResults`` per evaluator provider, each
    with per-agent breakdowns in ``sub_results``.

    **Two modes:**

    - **Post-hoc**: Pass ``workflow_result`` from a previous
      ``workflow.run()`` call.
    - **Run + evaluate**: Pass ``queries`` and the workflow will be run
      against each query, then evaluated.

    Args:
        workflow: The workflow instance.
        workflow_result: A completed ``WorkflowRunResult``.
        queries: Test queries to run through the workflow.
        evaluators: One or more ``Evaluator`` instances.
        eval_name: Display name for the evaluation.
        include_overall: Whether to evaluate the workflow's final output.
        include_per_agent: Whether to evaluate each sub-agent individually.
        conversation_split: Split strategy applied to all items, overriding
            each evaluator's default.  See ``ConversationSplitter``.
        num_repetitions: Number of times to run each query (default 1).
            When > 1, each query is run independently N times.
            Ignored when ``workflow_result`` is provided.

    Returns:
        A list of ``EvalResults``, one per evaluator provider.

    Example:

    .. code-block:: python

        from agent_framework.foundry import FoundryEvals

        evals = FoundryEvals(project_client=client, model="gpt-4o")
        result = await workflow.run("Plan a trip to Paris")

        eval_results = await evaluate_workflow(
            workflow=workflow,
            workflow_result=result,
            evaluators=evals,
        )
        for r in eval_results:
            print(f"{r.provider}:")
            for name, sub in r.sub_results.items():
                print(f"  {name}: {sub.passed}/{sub.total}")
    """
    from ._workflows._workflow import WorkflowRunResult as WRR

    # Normalize singular query to list
    if isinstance(queries, str):
        queries = [queries]

    if workflow_result is None and queries is None:
        raise ValueError("Provide either 'workflow_result' or 'queries'.")

    if num_repetitions < 1:
        raise ValueError(f"num_repetitions must be >= 1, got {num_repetitions}.")

    wf_name = eval_name or f"Workflow Eval: {workflow.__class__.__name__}"
    evaluator_list = _resolve_evaluators(evaluators)

    # Collect per-agent data and overall items
    all_agent_data: list[_AgentEvalData] = []
    overall_items: list[EvalItem] = []

    if queries is not None:
        results_list: list[WRR] = []
        for _rep in range(num_repetitions):
            for q in queries:
                result = await workflow.run(q)
                if not isinstance(result, WRR):
                    raise TypeError(f"Expected WorkflowRunResult from workflow.run(), got {type(result).__name__}.")
                results_list.append(result)
                all_agent_data.extend(_extract_agent_eval_data(result, workflow))
                if include_overall:
                    overall_item = _build_overall_item(q, result)
                    if overall_item:
                        overall_items.append(overall_item)
    else:
        assert workflow_result is not None  # noqa: S101  # nosec B101
        all_agent_data = _extract_agent_eval_data(workflow_result, workflow)
        if include_overall:
            original_query = _extract_overall_query(workflow_result)
            if original_query:
                overall_item = _build_overall_item(original_query, workflow_result)
                if overall_item:
                    overall_items.append(overall_item)

    # Group agent data by executor ID
    agents_by_id: dict[str, list[_AgentEvalData]] = {}
    if include_per_agent and all_agent_data:
        for ad in all_agent_data:
            agents_by_id.setdefault(ad["executor_id"], []).append(ad)

    # Build per-agent items once (shared across providers).
    agent_items_by_id: dict[str, list[EvalItem]] = {}
    for executor_id, agent_data_list in agents_by_id.items():
        agent_items_by_id[executor_id] = [
            AgentEvalConverter.to_eval_item(
                query=ad["query"],
                response=ad["response"],
                agent=ad["agent"],
            )
            for ad in agent_data_list
        ]

    if not agent_items_by_id and not overall_items:
        raise ValueError(
            "No agent executor data found in the workflow result. Ensure the workflow uses AgentExecutor-based agents."
        )

    # Stamp split strategy on all items so evaluators respect it
    if conversation_split is not None:
        for items in agent_items_by_id.values():
            for item in items:
                item.split_strategy = conversation_split
        for item in overall_items:
            item.split_strategy = conversation_split

    # Run each provider, building per-agent sub_results for each
    all_results: list[EvalResults] = []
    for ev in evaluator_list:
        suffix = f" ({ev.name})" if len(evaluator_list) > 1 else ""
        sub_results: dict[str, EvalResults] = {}

        # Per-agent evals
        for executor_id, items in agent_items_by_id.items():
            agent_result = await ev.evaluate(items, eval_name=f"{wf_name} — {executor_id}{suffix}")
            sub_results[executor_id] = agent_result

        # Overall eval
        if include_overall and overall_items:
            overall_result = await ev.evaluate(overall_items, eval_name=f"{wf_name} — overall{suffix}")
        elif sub_results:
            # Aggregate from sub-results
            total_passed = sum(s.passed for s in sub_results.values())
            total_failed = sum(s.failed for s in sub_results.values())
            all_completed = all(s.status == "completed" for s in sub_results.values())
            overall_result = EvalResults(
                provider=ev.name,
                eval_id="aggregate",
                run_id="aggregate",
                status="completed" if all_completed else "partial",
                result_counts={
                    "passed": total_passed,
                    "failed": total_failed,
                },
            )
        else:
            raise ValueError(
                "No agent executor data found in the workflow result. "
                "Ensure the workflow uses AgentExecutor-based agents."
            )

        overall_result.sub_results = sub_results
        all_results.append(overall_result)

    return all_results


# endregion

# region Internal helpers


def _build_overall_item(
    query: str,
    workflow_result: WorkflowRunResult,
) -> EvalItem | None:
    """Build an EvalItem for the overall workflow output."""
    outputs = workflow_result.get_outputs()
    if not outputs:
        return None

    final_output: Any = outputs[-1]
    overall_response: AgentResponse[None]
    if isinstance(final_output, list) and final_output and isinstance(final_output[0], Message):
        msgs: list[Message] = [m for m in cast(list[Any], final_output) if isinstance(m, Message)]  # type: ignore[redundant-cast]
        response_text = " ".join(str(m.text) for m in msgs if m.role == "assistant")
        overall_response = AgentResponse(messages=[Message("assistant", [response_text])])
    elif isinstance(final_output, AgentResponse):
        overall_response = cast(AgentResponse[None], final_output)
    else:
        overall_response = AgentResponse(
            messages=[Message("assistant", [str(final_output)])]  # type: ignore[reportUnknownArgumentType]
        )

    return AgentEvalConverter.to_eval_item(query=query, response=overall_response)


def _resolve_evaluators(
    evaluators: Evaluator | Callable[..., Any] | Sequence[Evaluator | Callable[..., Any]],
) -> list[Evaluator]:
    """Normalize evaluators into a list of concrete ``Evaluator`` instances.

    Bare callables (``EvalCheck`` functions, ``@evaluator`` decorated) are
    collected and wrapped in a single ``LocalEvaluator``.
    """
    raw_list: list[Any] = (
        [evaluators] if isinstance(evaluators, Evaluator) or callable(evaluators) else list(evaluators)
    )

    resolved: list[Evaluator] = []
    pending_checks: list[Callable[..., Any]] = []

    for item in raw_list:
        if isinstance(item, Evaluator):
            if pending_checks:
                resolved.append(LocalEvaluator(*pending_checks))
                pending_checks = []
            resolved.append(item)
        elif callable(item):
            pending_checks.append(item)
        else:
            raise TypeError(f"Expected an Evaluator or callable, got {type(item).__name__}")

    if pending_checks:
        resolved.append(LocalEvaluator(*pending_checks))

    return resolved


async def _run_evaluators(
    evaluators: Evaluator | Callable[..., Any] | Sequence[Evaluator | Callable[..., Any]],
    items: Sequence[EvalItem],
    *,
    eval_name: str,
) -> list[EvalResults]:
    """Run one or more evaluators and return a result per provider.

    Bare ``EvalCheck`` callables (including ``@evaluator`` decorated
    functions and helpers like ``keyword_check``) are auto-wrapped in a
    ``LocalEvaluator`` so they can be passed directly in the evaluators list.
    """
    evaluator_list = _resolve_evaluators(evaluators)

    async def _run_single_evaluator(
        ev: Evaluator,
        eval_items: Sequence[EvalItem],
        name: str,
        suffix: str,
    ) -> EvalResults:
        return await ev.evaluate(eval_items, eval_name=f"{name}{suffix}")

    results = await asyncio.gather(*[
        _run_single_evaluator(ev, items, eval_name, f" ({ev.name})" if len(evaluator_list) > 1 else "")
        for ev in evaluator_list
    ])
    return list(results)


# endregion
