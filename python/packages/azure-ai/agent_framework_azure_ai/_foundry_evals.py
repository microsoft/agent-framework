# Copyright (c) Microsoft. All rights reserved.

"""Microsoft Foundry Evals integration for Microsoft Agent Framework.

Provides ``FoundryEvals``, an ``Evaluator`` implementation backed by Azure AI
Foundry's built-in evaluators. See docs/decisions/0018-foundry-evals-integration.md
for the design rationale.

Typical usage::

    from agent_framework import evaluate_agent
    from agent_framework_azure_ai import FoundryEvals

    evals = FoundryEvals(project_client=project_client, model_deployment="gpt-4o")
    results = await evaluate_agent(
        agent=my_agent,
        queries=["What's the weather in Seattle?"],
        evaluators=evals,
    )
    assert results.all_passed
    print(results.report_url)
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast

from agent_framework._evaluation import (
    AgentEvalConverter,
    ConversationSplit,
    ConversationSplitter,
    EvalItem,
    EvalItemResult,
    EvalResults,
    EvalScoreResult,
)

if TYPE_CHECKING:
    from azure.ai.projects.aio import AIProjectClient
    from openai import AsyncOpenAI

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
    model_deployment: str,
    *,
    include_data_mapping: bool = False,
) -> list[dict[str, Any]]:
    """Build ``testing_criteria`` for ``evals.create()``.

    Args:
        evaluators: Evaluator names.
        model_deployment: Model deployment for the LLM judge.
        include_data_mapping: Whether to include field-level data mapping
            (required for the JSONL data source, not needed for response-based).
    """
    criteria: list[dict[str, Any]] = []
    for name in evaluators:
        qualified = _resolve_evaluator(name)
        short = name if not name.startswith("builtin.") else name.split(".")[-1]

        entry: dict[str, Any] = {
            "type": "azure_ai_evaluator",
            "name": short,
            "evaluator_name": qualified,
            "initialization_parameters": {"deployment_name": model_deployment},
        }

        if include_data_mapping:
            if qualified in _AGENT_EVALUATORS:
                # Agent evaluators: query/response as conversation arrays
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
                error_msg = (
                    getattr(run, "error", None)
                    or getattr(run, "error_message", None)
                    or getattr(run, "failure_reason", None)
                )
                if error_msg and not isinstance(error_msg, str):
                    error_msg = str(error_msg)

            items: list[EvalItemResult] = []
            if fetch_output_items and run.status == "completed":
                items = await _fetch_output_items(client, eval_id, run_id)

            return EvalResults(
                provider=provider,
                eval_id=eval_id,
                run_id=run_id,
                status=run.status,
                result_counts=_extract_result_counts(run),
                report_url=getattr(run, "report_url", None),
                error=error_msg,
                per_evaluator=_extract_per_evaluator(run),
                items=items,
            )
        remaining = deadline - loop.time()
        if remaining <= 0:
            return EvalResults(provider=provider, eval_id=eval_id, run_id=run_id, status="timeout")
        logger.debug("Eval run %s status: %s (%.0fs remaining)", run_id, run.status, remaining)
        await asyncio.sleep(min(max(poll_interval, 1.0), remaining, 60.0))


def _extract_result_counts(run: Any) -> dict[str, int] | None:
    """Safely extract result_counts from an eval run object."""
    counts = getattr(run, "result_counts", None)
    if counts is None:
        return None
    if isinstance(counts, dict):
        return cast(dict[str, int], counts)
    try:
        attrs = cast(dict[str, Any], vars(counts))
        return {str(k): v for k, v in attrs.items() if isinstance(v, int)}
    except TypeError:
        return None


def _extract_per_evaluator(run: Any) -> dict[str, dict[str, int]]:
    """Safely extract per-evaluator result breakdowns from an eval run."""
    per_eval: dict[str, dict[str, int]] = {}
    per_testing_criteria = getattr(run, "per_testing_criteria_results", None)
    if per_testing_criteria is None:
        return per_eval
    try:
        items = cast(list[Any], per_testing_criteria) if isinstance(per_testing_criteria, list) else []  # type: ignore[redundant-cast]
        for item in items:
            name: str = str(getattr(item, "name", None) or getattr(item, "testing_criteria", "unknown"))
            counts = _extract_result_counts(item)
            if name and counts:
                per_eval[name] = counts
    except (TypeError, AttributeError):
        pass
    return per_eval


async def _fetch_output_items(
    client: AsyncOpenAI,
    eval_id: str,
    run_id: str,
) -> list[EvalItemResult]:
    """Fetch per-item results from the output_items API.

    Converts the provider-specific ``OutputItemListResponse`` objects into
    provider-agnostic ``EvalItemResult`` instances with per-evaluator scores,
    error categorization, and token usage.
    """
    items: list[EvalItemResult] = []
    try:
        output_items_page = await client.evals.runs.output_items.list(
            run_id=run_id,
            eval_id=eval_id,
        )

        for oi in output_items_page:
            item_id = getattr(oi, "id", "") or ""
            status = getattr(oi, "status", "unknown") or "unknown"

            # Extract per-evaluator scores
            scores: list[EvalScoreResult] = []
            for r in getattr(oi, "results", []) or []:
                scores.append(
                    EvalScoreResult(
                        name=getattr(r, "name", "unknown"),
                        score=getattr(r, "score", 0.0),
                        passed=getattr(r, "passed", None),
                        sample=getattr(r, "sample", None),
                    )
                )

            # Extract error info from sample
            error_code: str | None = None
            error_message: str | None = None
            token_usage: dict[str, int] | None = None
            input_text: str | None = None
            output_text: str | None = None
            response_id: str | None = None

            sample = getattr(oi, "sample", None)
            if sample is not None:
                error = getattr(sample, "error", None)
                if error is not None:
                    code = getattr(error, "code", None)
                    msg = getattr(error, "message", None)
                    if code or msg:
                        error_code = code or None
                        error_message = msg or None

                usage = getattr(sample, "usage", None)
                if usage is not None:
                    total = getattr(usage, "total_tokens", 0)
                    if total:
                        token_usage = {
                            "prompt_tokens": getattr(usage, "prompt_tokens", 0),
                            "completion_tokens": getattr(usage, "completion_tokens", 0),
                            "total_tokens": total,
                            "cached_tokens": getattr(usage, "cached_tokens", 0),
                        }

                # Extract input/output text
                sample_input = getattr(sample, "input", None)
                if sample_input:
                    parts = [getattr(si, "content", "") for si in sample_input if getattr(si, "role", "") == "user"]
                    if parts:
                        input_text = " ".join(parts)

                sample_output = getattr(sample, "output", None)
                if sample_output:
                    parts = [
                        getattr(so, "content", "") or ""
                        for so in sample_output
                        if getattr(so, "role", "") == "assistant"
                    ]
                    if parts:
                        output_text = " ".join(parts)

            # Extract response_id from datasource_item
            ds_item = getattr(oi, "datasource_item", None)
            if ds_item and isinstance(ds_item, dict):
                ds_dict = cast(dict[str, Any], ds_item)
                resp_id_val = ds_dict.get("resp_id") or ds_dict.get("response_id")
                response_id = str(resp_id_val) if resp_id_val else None

            items.append(
                EvalItemResult(
                    item_id=item_id,
                    status=status,
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
    openai_client: AsyncOpenAI | None = None,
    project_client: AIProjectClient | None = None,
) -> AsyncOpenAI:
    """Resolve an OpenAI client from explicit client or project_client."""
    if openai_client is not None:
        return openai_client
    if project_client is not None:
        client = project_client.get_openai_client()
        if client is None:  # pyright: ignore[reportUnnecessaryComparison]
            raise ValueError("project_client.get_openai_client() returned None. Check project configuration.")
        if not hasattr(client, "__aenter__"):
            raise TypeError(
                "project_client.get_openai_client() returned a sync client. "
                "FoundryEvals requires an async AIProjectClient (from azure.ai.projects.aio)."
            )
        return client
    raise ValueError("Provide either 'openai_client' or 'project_client'.")


async def _evaluate_via_responses_impl(
    *,
    client: AsyncOpenAI,
    response_ids: Sequence[str],
    evaluators: list[str],
    model_deployment: str,
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
        testing_criteria=_build_testing_criteria(evaluators, model_deployment),  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
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


class FoundryEvals:
    """Evaluation provider backed by Microsoft Foundry.

    Implements the ``Evaluator`` protocol so it can be passed to the
    provider-agnostic ``evaluate_agent()`` and
    ``evaluate_workflow()`` functions from ``agent_framework``.

    Also provides constants for built-in evaluator names for IDE
    autocomplete and typo prevention::

        from agent_framework_azure_ai import FoundryEvals

        evaluators = [FoundryEvals.RELEVANCE, FoundryEvals.TOOL_CALL_ACCURACY]

    The simplest usage::

        from agent_framework import evaluate_agent
        from agent_framework_azure_ai import FoundryEvals

        evals = FoundryEvals(project_client=client, model_deployment="gpt-4o")
        results = await evaluate_agent(agent=agent, queries=queries, evaluators=evals)

    **Evaluator selection:**

    By default, runs ``relevance``, ``coherence``, and ``task_adherence``.
    Automatically adds ``tool_call_accuracy`` when items contain tool
    definitions. Override with ``evaluators=``.

    Args:
        project_client: An ``AIProjectClient`` instance (sync or async).
            Provide this or *openai_client*.
        openai_client: An ``AsyncOpenAI`` client with evals API.
        model_deployment: Model deployment name for the evaluator LLM judge.
        evaluators: Evaluator names (e.g. ``["relevance", "tool_call_accuracy"]``).
            When ``None`` (default), uses smart defaults based on item data.
        conversation_split: How to split multi-turn conversations into
            query/response halves.  Defaults to ``LAST_TURN``.  Pass a
            ``ConversationSplit`` enum value or a custom callable — see
            ``ConversationSplitter``.
        poll_interval: Seconds between status polls (default 5.0).
        timeout: Maximum seconds to wait for completion (default 180.0).
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
        project_client: AIProjectClient | None = None,
        openai_client: AsyncOpenAI | None = None,
        model_deployment: str,
        evaluators: Sequence[str] | None = None,
        conversation_split: ConversationSplitter = ConversationSplit.LAST_TURN,
        poll_interval: float = 5.0,
        timeout: float = 180.0,
    ):
        self.name = "Microsoft Foundry"
        self._client = _resolve_openai_client(openai_client, project_client)
        self._model_deployment = model_deployment
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
                self._model_deployment,
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


async def evaluate_traces(
    *,
    evaluators: Sequence[str] | None = None,
    openai_client: AsyncOpenAI | None = None,
    project_client: AIProjectClient | None = None,
    model_deployment: str,
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
        openai_client: ``AsyncOpenAI`` client. Provide this or *project_client*.
        project_client: An ``AIProjectClient`` instance.
        model_deployment: Model deployment name for the evaluator LLM judge.
        response_ids: Evaluate specific Responses API responses.
        trace_ids: Evaluate specific OTel trace IDs from App Insights.
        agent_id: Filter traces by agent ID (used with *lookback_hours*).
        lookback_hours: Hours of trace history to evaluate (default 24).
        eval_name: Display name for the evaluation.
        poll_interval: Seconds between status polls.
        timeout: Maximum seconds to wait for completion.

    Returns:
        ``EvalResults`` with status, result counts, and portal link.

    Example::

        results = await evaluate_traces(
            response_ids=[response.response_id],
            evaluators=[FoundryEvals.RELEVANCE],
            project_client=project_client,
            model_deployment="gpt-4o",
        )
    """
    client = _resolve_openai_client(openai_client, project_client)
    resolved_evaluators = _resolve_default_evaluators(evaluators)

    if response_ids:
        return await _evaluate_via_responses_impl(
            client=client,
            response_ids=response_ids,
            evaluators=resolved_evaluators,
            model_deployment=model_deployment,
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

    eval_obj = await client.evals.create(
        name=eval_name,
        data_source_config={"type": "azure_ai_source", "scenario": "traces"},  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        testing_criteria=_build_testing_criteria(resolved_evaluators, model_deployment),  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    run = await client.evals.runs.create(
        eval_id=eval_obj.id,
        name=f"{eval_name} Run",
        data_source=trace_source,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    return await _poll_eval_run(client, eval_obj.id, run.id, poll_interval, timeout)


async def evaluate_foundry_target(
    *,
    target: dict[str, Any],
    test_queries: Sequence[str],
    evaluators: Sequence[str] | None = None,
    openai_client: AsyncOpenAI | None = None,
    project_client: AIProjectClient | None = None,
    model_deployment: str,
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
        openai_client: ``AsyncOpenAI`` client. Provide this or *project_client*.
        project_client: An ``AIProjectClient`` instance.
        model_deployment: Model deployment name for the evaluator LLM judge.
        eval_name: Display name for the evaluation.
        poll_interval: Seconds between status polls.
        timeout: Maximum seconds to wait for completion.

    Returns:
        ``EvalResults`` with status, result counts, and portal link.

    Example::

        results = await evaluate_foundry_target(
            target={"type": "azure_ai_agent", "name": "my-agent"},
            test_queries=["Book a flight to Paris"],
            project_client=project_client,
            model_deployment="gpt-4o",
        )
    """
    if "type" not in target:
        raise ValueError("target dict must include a 'type' key (e.g., 'azure_ai_agent').")
    client = _resolve_openai_client(openai_client, project_client)
    resolved_evaluators = _resolve_default_evaluators(evaluators)

    eval_obj = await client.evals.create(
        name=eval_name,
        data_source_config={  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
            "type": "azure_ai_source",
            "scenario": "target_completions",
        },
        testing_criteria=_build_testing_criteria(resolved_evaluators, model_deployment),  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    data_source: dict[str, Any] = {
        "type": "azure_ai_target_completions",
        "target": target,
        "source": {
            "type": "file_content",
            "content": [{"item": {"query": q}} for q in test_queries],
        },
    }

    run = await client.evals.runs.create(
        eval_id=eval_obj.id,
        name=f"{eval_name} Run",
        data_source=data_source,  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
    )

    return await _poll_eval_run(client, eval_obj.id, run.id, poll_interval, timeout)
