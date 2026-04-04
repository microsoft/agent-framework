# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Foundry Evals integration for Microsoft Agent Framework.

Provides ``FoundryEvals``, an ``Evaluator`` implementation backed by Azure AI
Foundry's built-in evaluators. See docs/decisions/0018-foundry-evals-integration.md
for the design rationale.

Example:

.. code-block:: python

    from agent_framework import evaluate_agent
    from agent_framework.foundry import FoundryEvals

    # Zero-config: reads FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL from env
    evals = FoundryEvals()
    results = await evaluate_agent(
        agent=my_agent,
        queries=["What's the weather in Seattle?"],
        evaluators=evals,
    )
    results[0].raise_for_status()
    print(results[0].report_url)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from agent_framework._evaluation import (
    AgentEvalConverter,
    ConversationSplit,
    ConversationSplitter,
    EvalItem,
    EvalItemResult,
    EvalResults,
    EvalScoreResult,
)
from agent_framework._feature_stage import ExperimentalFeature, experimental
from openai import AsyncOpenAI

from ._chat_client import FoundryChatClient

if TYPE_CHECKING:
    from azure.ai.projects.aio import AIProjectClient
    from openai.types.evals import RunRetrieveResponse

logger = logging.getLogger(__name__)

# Agent evaluators that accept query/response as conversation arrays.
# Maintained manually — check https://learn.microsoft.com/en-us/azure/ai-studio/how-to/develop/evaluate-sdk
# for the latest evaluator list. These are the evaluators that need conversation-format input.
_AGENT_EVALUATORS: set[str] = {
    "builtin.intent_resolution",
    "builtin.task_adherence",
    "builtin.task_completion",
    "builtin.task_navigation_efficiency",
    "builtin.tool_call_accuracy",
    "builtin.tool_selection",
    "builtin.tool_input_accuracy",
    "builtin.tool_output_utilization",
    "builtin.tool_call_success",
}

# Evaluators that additionally require tool_definitions.
_TOOL_EVALUATORS: set[str] = {
    "builtin.tool_call_accuracy",
    "builtin.tool_selection",
    "builtin.tool_input_accuracy",
    "builtin.tool_output_utilization",
    "builtin.tool_call_success",
}

_BUILTIN_EVALUATORS: dict[str, str] = {
    # Agent behavior
    "intent_resolution": "builtin.intent_resolution",
    "task_adherence": "builtin.task_adherence",
    "task_completion": "builtin.task_completion",
    "task_navigation_efficiency": "builtin.task_navigation_efficiency",
    # Tool usage
    "tool_call_accuracy": "builtin.tool_call_accuracy",
    "tool_selection": "builtin.tool_selection",
    "tool_input_accuracy": "builtin.tool_input_accuracy",
    "tool_output_utilization": "builtin.tool_output_utilization",
    "tool_call_success": "builtin.tool_call_success",
    # Quality
    "coherence": "builtin.coherence",
    "fluency": "builtin.fluency",
    "relevance": "builtin.relevance",
    "groundedness": "builtin.groundedness",
    "response_completeness": "builtin.response_completeness",
    "similarity": "builtin.similarity",
    # Safety
    "violence": "builtin.violence",
    "sexual": "builtin.sexual",
    "self_harm": "builtin.self_harm",
    "hate_unfairness": "builtin.hate_unfairness",
}

# Default evaluator sets used when evaluators=None
_DEFAULT_EVALUATORS: list[str] = [
    "relevance",
    "coherence",
    "task_adherence",
]

_DEFAULT_TOOL_EVALUATORS: list[str] = [
    "tool_call_accuracy",
]

# Consistency between evaluator sets is enforced by tests in
# test_foundry_evals.py — see TestEvaluatorSetConsistency.


def _resolve_evaluator(name: str) -> str:
    """Resolve a short evaluator name to its fully-qualified ``builtin.*`` form.

    Args:
        name: Short name (e.g. ``"relevance"``) or fully-qualified name
            (e.g. ``"builtin.relevance"``).

    Returns:
        The fully-qualified evaluator name.

    Raises:
        ValueError: If the name is not recognized.
    """
    if name.startswith("builtin."):
        # Already fully-qualified — pass through, but warn if not in our
        # known list (may indicate a typo or a newly-added evaluator).
        short = name.removeprefix("builtin.")
        if short not in _BUILTIN_EVALUATORS:
            logger.warning(
                "Evaluator '%s' is not in the known built-in list. "
                "If this is a new evaluator, consider updating _BUILTIN_EVALUATORS.",
                name,
            )
        return name
    resolved = _BUILTIN_EVALUATORS.get(name)
    if resolved is None:
        raise ValueError(f"Unknown evaluator '{name}'. Available: {sorted(_BUILTIN_EVALUATORS)}")
    return resolved


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_testing_criteria(
    evaluators: Sequence[str],
    model: str,
    *,
    include_data_mapping: bool = False,
) -> list[dict[str, Any]]:
    """Build ``testing_criteria`` for ``evals.create()``.

    Args:
        evaluators: Evaluator names.
        model: Model deployment for the LLM judge.
        include_data_mapping: Whether to include field-level data mapping
            (required for the JSONL data source, not needed for response-based).
    """
    criteria: list[dict[str, Any]] = []
    for name in evaluators:
        qualified = _resolve_evaluator(name)
        short = name if not name.startswith("builtin.") else name.split(".")[-1]

        # Structure dictated by the OpenAI evals API — see
        # https://platform.openai.com/docs/api-reference/evals/create
        entry: dict[str, Any] = {
            "type": "azure_ai_evaluator",
            "name": short,
            "evaluator_name": qualified,
            "initialization_parameters": {"deployment_name": model},
        }

        if include_data_mapping:
            if qualified in _AGENT_EVALUATORS:
                # Agent evaluators: query/response as conversation arrays.
                # {{item.*}} are Mustache-style placeholders resolved by the
                # evals API against fields in the JSONL data items.
                mapping: dict[str, str] = {
                    "query": "{{item.query_messages}}",
                    "response": "{{item.response_messages}}",
                }
            else:
                # Quality evaluators: query/response as strings
                mapping = {
                    "query": "{{item.query}}",
                    "response": "{{item.response}}",
                }
            if qualified == "builtin.groundedness":
                mapping["context"] = "{{item.context}}"
            if qualified in _TOOL_EVALUATORS:
                mapping["tool_definitions"] = "{{item.tool_definitions}}"
            entry["data_mapping"] = mapping

        criteria.append(entry)
    return criteria


def _build_item_schema(*, has_context: bool = False, has_tools: bool = False) -> dict[str, Any]:
    """Build the ``item_schema`` for custom JSONL eval definitions."""
    properties: dict[str, Any] = {
        "query": {"type": "string"},
        "response": {"type": "string"},
        "query_messages": {"type": "array"},
        "response_messages": {"type": "array"},
    }
    if has_context:
        properties["context"] = {"type": "string"}
    if has_tools:
        properties["tool_definitions"] = {"type": "array"}
    return {
        "type": "object",
        "properties": properties,
        "required": ["query", "response"],
    }


def _resolve_default_evaluators(
    evaluators: Sequence[str] | None,
    items: Sequence[EvalItem | dict[str, Any]] | None = None,
) -> list[str]:
    """Resolve evaluators, applying defaults when ``None``.

    Defaults to relevance + coherence + task_adherence. Automatically adds
    tool_call_accuracy when items contain tools.
    """
    if evaluators is not None:
        return list(evaluators)

    result = list(_DEFAULT_EVALUATORS)
    if items is not None:
        has_tools = any((item.tools if isinstance(item, EvalItem) else item.get("tool_definitions")) for item in items)
        if has_tools:
            result.extend(_DEFAULT_TOOL_EVALUATORS)
    return result


def _filter_tool_evaluators(
    evaluators: list[str],
    items: Sequence[EvalItem | dict[str, Any]],
) -> list[str]:
    """Remove tool evaluators if no items have tool definitions."""
    has_tools = any((item.tools if isinstance(item, EvalItem) else item.get("tool_definitions")) for item in items)
    if has_tools:
        return evaluators
    filtered = [e for e in evaluators if _resolve_evaluator(e) not in _TOOL_EVALUATORS]
    if not filtered:
        raise ValueError(
            f"All requested evaluators {evaluators} require tool definitions, "
            "but no items have tools. Either add tool definitions to your items "
            "or choose evaluators that do not require tools."
        )
    if len(filtered) < len(evaluators):
        removed = [e for e in evaluators if _resolve_evaluator(e) in _TOOL_EVALUATORS]
        logger.info("Removed tool evaluators %s (no items have tools)", removed)
    return filtered


async def _poll_eval_run(
    client: AsyncOpenAI,
    eval_id: str,
    run_id: str,
    poll_interval: float = 5.0,
    timeout: float = 180.0,
    provider: str = "Microsoft Foundry",
    *,
    fetch_output_items: bool = True,
) -> EvalResults:
    """Poll an eval run until completion or timeout."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        run = await client.evals.runs.retrieve(run_id=run_id, eval_id=eval_id)
        if run.status in ("completed", "failed", "canceled"):
            error_msg = None
            if run.status == "failed":
                err = run.error
                if err is not None:  # pyright: ignore[reportUnnecessaryComparison]
                    error_msg = err if isinstance(err, str) else err.message or str(err)

            items: list[EvalItemResult] = []
            if fetch_output_items and run.status == "completed":
                items = await _fetch_output_items(client, eval_id, run_id)

            return EvalResults(
                provider=provider,
                eval_id=eval_id,
                run_id=run_id,
                status=run.status,
                result_counts=_extract_result_counts(run),
                report_url=run.report_url,
                error=error_msg,
                per_evaluator=_extract_per_evaluator(run),
                items=items,
            )
        remaining = deadline - loop.time()
        if remaining <= 0:
            return EvalResults(provider=provider, eval_id=eval_id, run_id=run_id, status="timeout")
        logger.debug("Eval run %s status: %s (%.0fs remaining)", run_id, run.status, remaining)
        await asyncio.sleep(min(poll_interval, remaining))


def _extract_result_counts(run: RunRetrieveResponse) -> dict[str, int] | None:
    """Extract result_counts from an eval run as a plain dict."""
    counts = run.result_counts
    if counts is None:  # pyright: ignore[reportUnnecessaryComparison]
        return None
    return {
        "errored": counts.errored,
        "failed": counts.failed,
        "passed": counts.passed,
        "total": counts.total,
    }


def _extract_per_evaluator(run: RunRetrieveResponse) -> dict[str, dict[str, int]]:
    """Extract per-evaluator result breakdowns from an eval run."""
    per_eval: dict[str, dict[str, int]] = {}
    for item in run.per_testing_criteria_results or []:
        name = item.testing_criteria
        if name:
            per_eval[name] = {"passed": item.passed, "failed": item.failed}
    return per_eval


async def _fetch_output_items(
    client: AsyncOpenAI,
    eval_id: str,
    run_id: str,
) -> list[EvalItemResult]:
    """Fetch per-item results from the output_items API.

    Converts the provider-specific ``OutputItemListResponse`` objects into
    provider-agnostic ``EvalItemResult`` instances with per-evaluator scores,
    error categorization, and token usage.  Uses async pagination to handle
    eval runs with more items than a single page.
    """
    items: list[EvalItemResult] = []
    try:
        output_items_page = await client.evals.runs.output_items.list(
            run_id=run_id,
            eval_id=eval_id,
        )

        async for oi in output_items_page:
            # Extract per-evaluator scores
            scores: list[EvalScoreResult] = []
            for r in oi.results or []:
                scores.append(
                    EvalScoreResult(
                        name=r.name,
                        score=r.score,
                        passed=r.passed,
                        sample=r.sample,
                    )
                )

            # Extract error info from sample
            error_code: str | None = None
            error_message: str | None = None
            token_usage: dict[str, int] | None = None
            input_text: str | None = None
            output_text: str | None = None
            response_id: str | None = None

            sample = oi.sample
            if sample is not None:  # pyright: ignore[reportUnnecessaryComparison]
                err = sample.error
                if err is not None and (err.code or err.message):  # pyright: ignore[reportUnnecessaryComparison]
                    error_code = err.code or None
                    error_message = err.message or None

                usage = sample.usage
                if usage is not None and usage.total_tokens:  # pyright: ignore[reportUnnecessaryComparison]
                    token_usage = {
                        "prompt_tokens": usage.prompt_tokens,
                        "completion_tokens": usage.completion_tokens,
                        "total_tokens": usage.total_tokens,
                        "cached_tokens": usage.cached_tokens,
                    }

                # Extract input/output text
                if sample.input:
                    parts = [si.content for si in sample.input if si.role == "user"]
                    if parts:
                        input_text = " ".join(parts)

                if sample.output:
                    parts = [so.content or "" for so in sample.output if so.role == "assistant"]
                    if parts:
                        output_text = " ".join(parts)

            # Extract response_id from datasource_item
            ds_item = oi.datasource_item
            if ds_item:
                resp_id_val = ds_item.get("resp_id") or ds_item.get("response_id")
                response_id = str(resp_id_val) if resp_id_val else None

            items.append(
                EvalItemResult(
                    item_id=oi.id,
                    status=oi.status,
                    scores=scores,
                    error_code=error_code,
                    error_message=error_message,
                    response_id=response_id,
                    input_text=input_text,
                    output_text=output_text,
                    token_usage=token_usage,
                )
            )
    except (AttributeError, KeyError, TypeError):
        logger.warning("Could not fetch output_items for run %s", run_id, exc_info=True)

    return items


def _resolve_openai_client(
    client: FoundryChatClient | AsyncOpenAI | None = None,
    project_client: AIProjectClient | None = None,
) -> AsyncOpenAI:
    """Resolve an AsyncOpenAI client from a FoundryChatClient, raw client, or project_client."""
    if client is not None:
        if isinstance(client, FoundryChatClient):
            return client.client
        return client
    if project_client is not None:
        oai = project_client.get_openai_client()
        if oai is None:  # pyright: ignore[reportUnnecessaryComparison]
            raise ValueError("project_client.get_openai_client() returned None. Check project configuration.")
        if not isinstance(oai, AsyncOpenAI):
            raise TypeError(
                "project_client.get_openai_client() returned a sync client. "
                "FoundryEvals requires an async AIProjectClient (from azure.ai.projects.aio)."
            )
        return oai
    raise ValueError("Provide either 'client' or 'project_client'.")


async def _evaluate_via_responses_impl(
    *,
    client: AsyncOpenAI,
    response_ids: Sequence[str],
    evaluators: list[str],
    model: str,
    eval_name: str,
    poll_interval: float,
    timeout: float,
    provider: str = "foundry",
) -> EvalResults:
    """Evaluate using Foundry's Responses API retrieval path.

    Module-level helper used by both ``FoundryEvals`` and ``evaluate_traces``.
    """
    eval_obj = await client.evals.create(
        name=eval_name,
        data_source_config={"type": "azure_ai_source", "scenario": "responses"},  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        testing_criteria=_build_testing_criteria(evaluators, model),  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    data_source = {
        "type": "azure_ai_responses",
        "item_generation_params": {
            "type": "response_retrieval",
            "data_mapping": {"response_id": "{{item.resp_id}}"},
            "source": {
                "type": "file_content",
                "content": [{"item": {"resp_id": rid}} for rid in response_ids],
            },
        },
    }

    run = await client.evals.runs.create(
        eval_id=eval_obj.id,
        name=f"{eval_name} Run",
        data_source=data_source,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    return await _poll_eval_run(client, eval_obj.id, run.id, poll_interval, timeout, provider=provider)


# ---------------------------------------------------------------------------
# FoundryEvals — Evaluator implementation for Microsoft Foundry
# ---------------------------------------------------------------------------


@experimental(feature_id=ExperimentalFeature.EVALS)
class FoundryEvals:
    """Evaluation provider backed by Microsoft Foundry.

    Implements the ``Evaluator`` protocol so it can be passed to the
    provider-agnostic ``evaluate_agent()`` and
    ``evaluate_workflow()`` functions from ``agent_framework``.

    Also provides constants for built-in evaluator names for IDE
    autocomplete and typo prevention:

    .. code-block:: python

        from agent_framework.foundry import FoundryEvals

        evaluators = [FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY]

    Examples:
        Basic usage:

        .. code-block:: python

            from agent_framework import evaluate_agent
            from agent_framework.foundry import FoundryEvals, FoundryChatClient

            chat_client = FoundryChatClient(model="gpt-4o")
            evals = FoundryEvals(client=chat_client)
            results = await evaluate_agent(agent=agent, queries=queries, evaluators=evals)

        Zero-config with environment variables (``FOUNDRY_PROJECT_ENDPOINT``
        and ``FOUNDRY_MODEL``):

        .. code-block:: python

            evals = FoundryEvals()  # reads env vars via FoundryChatClient

    **Evaluator selection:**

    By default, runs ``relevance``, ``coherence``, and ``task_adherence``.
    Automatically adds ``tool_call_accuracy`` when items contain tool
    definitions. Override with ``evaluators=``.

    .. note::

        The ``builtin.*`` evaluators are accessed through the OpenAI Evals
        API (``client.evals.create`` / ``client.evals.runs.create``).  Any
        ``AsyncOpenAI`` client pointing at a Foundry endpoint can run them.

    Args:
        client: A ``FoundryChatClient`` instance.  The ``builtin.*``
            evaluators are a Foundry feature and require a Foundry endpoint.
            When omitted (and *project_client* is also omitted), a
            ``FoundryChatClient`` is auto-created from ``FOUNDRY_PROJECT_ENDPOINT``
            and ``FOUNDRY_MODEL`` environment variables.
        project_client: An async ``AIProjectClient`` instance
            (from ``azure.ai.projects.aio``).  Provide this or *client*.
        model: Model deployment name for the evaluator LLM judge.
            Resolved from ``client.model`` when omitted.
        evaluators: Evaluator names (e.g. ``["relevance", "tool_call_accuracy"]``).
            When ``None`` (default), uses smart defaults based on item data.
        conversation_split: How to split multi-turn conversations into
            query/response halves.  Defaults to ``LAST_TURN``.  Pass a
            ``ConversationSplit`` enum value or a custom callable — see
            ``ConversationSplitter``.
        poll_interval: Seconds between status polls (default 5.0).
        timeout: Maximum seconds to wait for completion (default 180.0).
        eval_name: Display name for the eval definition created in Foundry.
            Defaults to ``"agent-framework-eval"``.  The name is visible in
            the Foundry portal; it does not affect evaluation behavior.
    """

    # ---------------------------------------------------------------------------
    # Built-in evaluator name constants
    # ---------------------------------------------------------------------------

    # Agent behavior
    INTENT_RESOLUTION: str = "intent_resolution"
    TASK_ADHERENCE: str = "task_adherence"
    TASK_COMPLETION: str = "task_completion"
    TASK_NAVIGATION_EFFICIENCY: str = "task_navigation_efficiency"

    # Tool usage
    TOOL_CALL_ACCURACY: str = "tool_call_accuracy"
    TOOL_SELECTION: str = "tool_selection"
    TOOL_INPUT_ACCURACY: str = "tool_input_accuracy"
    TOOL_OUTPUT_UTILIZATION: str = "tool_output_utilization"
    TOOL_CALL_SUCCESS: str = "tool_call_success"

    # Quality
    COHERENCE: str = "coherence"
    FLUENCY: str = "fluency"
    RELEVANCE: str = "relevance"
    GROUNDEDNESS: str = "groundedness"
    RESPONSE_COMPLETENESS: str = "response_completeness"
    SIMILARITY: str = "similarity"

    # Safety
    VIOLENCE: str = "violence"
    SEXUAL: str = "sexual"
    SELF_HARM: str = "self_harm"
    HATE_UNFAIRNESS: str = "hate_unfairness"

    def __init__(
        self,
        *,
        client: FoundryChatClient | None = None,
        project_client: AIProjectClient | None = None,
        model: str | None = None,
        evaluators: Sequence[str] | None = None,
        conversation_split: ConversationSplitter = ConversationSplit.LAST_TURN,
        poll_interval: float = 5.0,
        timeout: float = 180.0,
    ):
        self.name = "Microsoft Foundry"

        # Auto-create a FoundryChatClient from env vars when no client is provided
        if client is None and project_client is None:
            client = FoundryChatClient(model=model or "gpt-4o")

        self._client = _resolve_openai_client(client, project_client)
        # Resolve model: explicit param > client.model > error
        resolved_model = model or (client.model if client is not None else None)
        if not resolved_model:
            raise ValueError(
                "Model is required. Pass model= explicitly or use a FoundryChatClient that has a model configured."
            )
        self._model = resolved_model
        self._evaluators = list(evaluators) if evaluators is not None else None
        self._conversation_split = conversation_split
        self._poll_interval = poll_interval
        self._timeout = timeout

    async def evaluate(
        self,
        items: Sequence[EvalItem],
        *,
        eval_name: str = "Agent Framework Eval",
    ) -> EvalResults:
        """Evaluate items using Foundry evaluators.

        Implements the ``Evaluator`` protocol. Automatically resolves default
        evaluators and filters tool evaluators for items without tool definitions.

        Args:
            items: Eval data items from ``AgentEvalConverter.to_eval_item()``.
            eval_name: Display name for the evaluation run.

        Returns:
            ``EvalResults`` with status, counts, and portal link.
        """
        # Resolve evaluators with auto-detection
        resolved = _resolve_default_evaluators(self._evaluators, items=items)
        # Filter tool evaluators if items don't have tools
        resolved = _filter_tool_evaluators(resolved, items)

        # Standard JSONL dataset path
        return await self._evaluate_via_dataset(items, resolved, eval_name)

    # -- Internal evaluation paths --

    async def _evaluate_via_dataset(
        self,
        items: Sequence[EvalItem],
        evaluators: list[str],
        eval_name: str,
    ) -> EvalResults:
        """Evaluate using JSONL dataset upload path."""
        dicts: list[dict[str, Any]] = []
        for item in items:
            # Build JSONL dict directly from split_messages + converter
            # to avoid splitting the conversation twice.
            effective_split = item.split_strategy or self._conversation_split
            query_msgs, response_msgs = item.split_messages(effective_split)

            query_text = " ".join(m.text for m in query_msgs if m.role == "user" and m.text).strip()
            response_text = " ".join(m.text for m in response_msgs if m.role == "assistant" and m.text).strip()

            d: dict[str, Any] = {
                "query": query_text,
                "response": response_text,
                "query_messages": AgentEvalConverter.convert_messages(query_msgs),
                "response_messages": AgentEvalConverter.convert_messages(response_msgs),
            }
            if item.tools:
                d["tool_definitions"] = [
                    {"name": t.name, "description": t.description, "parameters": t.parameters()} for t in item.tools
                ]
            if item.context:
                d["context"] = item.context
            dicts.append(d)

        has_context = any("context" in d for d in dicts)
        has_tools = any("tool_definitions" in d for d in dicts)

        eval_obj = await self._client.evals.create(
            name=eval_name,
            data_source_config={  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
                "type": "custom",
                "item_schema": _build_item_schema(has_context=has_context, has_tools=has_tools),
                "include_sample_schema": True,
            },
            testing_criteria=_build_testing_criteria(  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
                evaluators,
                self._model,
                include_data_mapping=True,
            ),
        )

        data_source = {
            "type": "jsonl",
            "source": {
                "type": "file_content",
                "content": [{"item": d} for d in dicts],
            },
        }

        run = await self._client.evals.runs.create(
            eval_id=eval_obj.id,
            name=f"{eval_name} Run",
            data_source=data_source,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        )

        return await _poll_eval_run(
            self._client,
            eval_obj.id,
            run.id,
            self._poll_interval,
            self._timeout,
            provider=self.name,
        )


# ---------------------------------------------------------------------------
# Foundry-specific functions (not part of the Evaluator protocol)
# ---------------------------------------------------------------------------


@experimental(feature_id=ExperimentalFeature.EVALS)
async def evaluate_traces(
    *,
    evaluators: Sequence[str] | None = None,
    client: FoundryChatClient | None = None,
    project_client: AIProjectClient | None = None,
    model: str,
    response_ids: Sequence[str] | None = None,
    trace_ids: Sequence[str] | None = None,
    agent_id: str | None = None,
    lookback_hours: int = 24,
    eval_name: str = "Agent Framework Trace Eval",
    poll_interval: float = 5.0,
    timeout: float = 180.0,
) -> EvalResults:
    """Evaluate agent behavior from OTel traces or response IDs.

    Foundry-specific function — works with any agent that emits OTel traces
    to App Insights. Provide *response_ids* for specific responses,
    *trace_ids* for specific traces, or *agent_id* with *lookback_hours*
    to evaluate recent activity.

    Args:
        evaluators: Evaluator names (e.g. ``[FoundryEvals.RELEVANCE]``).
            Defaults to relevance, coherence, and task_adherence.
        client: A ``FoundryChatClient`` instance. Provide this or *project_client*.
        project_client: An ``AIProjectClient`` instance.
        model: Model deployment name for the evaluator LLM judge.
        response_ids: Evaluate specific Responses API responses.
        trace_ids: Evaluate specific OTel trace IDs from App Insights.
        agent_id: Filter traces by agent ID (used with *lookback_hours*).
        lookback_hours: Hours of trace history to evaluate (default 24).
        eval_name: Display name for the evaluation.
        poll_interval: Seconds between status polls.
        timeout: Maximum seconds to wait for completion.

    Returns:
        ``EvalResults`` with status, result counts, and portal link.

    Example:

    .. code-block:: python

        results = await evaluate_traces(
            response_ids=[response.response_id],
            evaluators=[FoundryEvals.RELEVANCE],
            client=chat_client,
            model="gpt-4o",
        )
    """
    oai_client = _resolve_openai_client(client, project_client)
    resolved_evaluators = _resolve_default_evaluators(evaluators)

    if response_ids:
        return await _evaluate_via_responses_impl(
            client=oai_client,
            response_ids=response_ids,
            evaluators=resolved_evaluators,
            model=model,
            eval_name=eval_name,
            poll_interval=poll_interval,
            timeout=timeout,
        )

    if not trace_ids and not agent_id:
        raise ValueError("Provide at least one of: response_ids, trace_ids, or agent_id")

    trace_source: dict[str, Any] = {
        "type": "azure_ai_traces",
        "lookback_hours": lookback_hours,
    }
    if trace_ids:
        trace_source["trace_ids"] = list(trace_ids)
    if agent_id:
        trace_source["agent_id"] = agent_id

    eval_obj = await oai_client.evals.create(
        name=eval_name,
        data_source_config={"type": "azure_ai_source", "scenario": "traces"},  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        testing_criteria=_build_testing_criteria(resolved_evaluators, model),  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    run = await oai_client.evals.runs.create(
        eval_id=eval_obj.id,
        name=f"{eval_name} Run",
        data_source=trace_source,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    return await _poll_eval_run(oai_client, eval_obj.id, run.id, poll_interval, timeout)


@experimental(feature_id=ExperimentalFeature.EVALS)
async def evaluate_foundry_target(
    *,
    target: dict[str, Any],
    test_queries: Sequence[str],
    evaluators: Sequence[str] | None = None,
    client: FoundryChatClient | None = None,
    project_client: AIProjectClient | None = None,
    model: str,
    eval_name: str = "Agent Framework Target Eval",
    poll_interval: float = 5.0,
    timeout: float = 180.0,
) -> EvalResults:
    """Evaluate a Foundry-registered agent or model deployment.

    Foundry invokes the target, captures the output, and evaluates it. Use
    this for scheduled evals, red teaming, and CI/CD quality gates.

    Args:
        target: Target configuration dict.
        test_queries: Queries for Foundry to send to the target.
        evaluators: Evaluator names.
        client: A ``FoundryChatClient`` instance. Provide this or *project_client*.
        project_client: An ``AIProjectClient`` instance.
        model: Model deployment name for the evaluator LLM judge.
        eval_name: Display name for the evaluation.
        poll_interval: Seconds between status polls.
        timeout: Maximum seconds to wait for completion.

    Returns:
        ``EvalResults`` with status, result counts, and portal link.

    Example:

    .. code-block:: python

        results = await evaluate_foundry_target(
            target={"type": "azure_ai_agent", "name": "my-agent"},
            test_queries=["Book a flight to Paris"],
            client=chat_client,
            model="gpt-4o",
        )
    """
    if "type" not in target:
        raise ValueError("target dict must include a 'type' key (e.g., 'azure_ai_agent').")
    oai_client = _resolve_openai_client(client, project_client)
    resolved_evaluators = _resolve_default_evaluators(evaluators)

    eval_obj = await oai_client.evals.create(
        name=eval_name,
        data_source_config={  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
            "type": "azure_ai_source",
            "scenario": "target_completions",
        },
        testing_criteria=_build_testing_criteria(resolved_evaluators, model),  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    data_source: dict[str, Any] = {
        "type": "azure_ai_target_completions",
        "target": target,
        "source": {
            "type": "file_content",
            "content": [{"item": {"query": q}} for q in test_queries],
        },
    }

    run = await oai_client.evals.runs.create(
        eval_id=eval_obj.id,
        name=f"{eval_name} Run",
        data_source=data_source,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    return await _poll_eval_run(oai_client, eval_obj.id, run.id, poll_interval, timeout)
