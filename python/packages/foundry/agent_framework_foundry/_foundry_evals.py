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
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal, cast

from agent_framework._evaluation import (
    AgentEvalConverter,
    ConversationSplit,
    ConversationSplitter,
    EvalItem,
    EvalItemResult,
    EvalResults,
    EvalScoreResult,
    RubricScore,
)
from agent_framework._feature_stage import ExperimentalFeature, experimental
from openai import AsyncOpenAI

from ._chat_client import FoundryChatClient

if TYPE_CHECKING:
    from agent_framework._agents import BaseAgent
    from agent_framework._workflows._workflow import Workflow
    from azure.ai.projects.aio import AIProjectClient
    from openai.types.evals import RunRetrieveResponse

logger = logging.getLogger(__name__)


# region Generated rubric evaluator types


@experimental(feature_id=ExperimentalFeature.EVALS)
@dataclass(frozen=True)
class RubricDimension:
    """A single dimension of a generated rubric evaluator.

    Rubric evaluators score each item along one or more named dimensions,
    each with its own description and weight.  Foundry's evaluator
    generation pipeline produces these dimensions from agent/workflow
    metadata; ``RubricDimension`` surfaces them so callers can inspect a
    generated evaluator's structure without round-tripping through the
    portal.

    Attributes:
        id: Stable identifier for the dimension (e.g. ``"policy_enforcement"``).
        description: Natural-language description of what the dimension scores.
        weight: Integer weight controlling the dimension's contribution to
            the aggregate score.
        always_applicable: When ``False``, evaluators may mark this
            dimension non-applicable on a per-item basis.
    """

    id: str
    description: str
    weight: int
    always_applicable: bool = False


@experimental(feature_id=ExperimentalFeature.EVALS)
@dataclass(frozen=True)
class GeneratedEvaluatorRef:
    """A reference to a generated rubric evaluator stored in Foundry.

    Pass instances of this class to :class:`FoundryEvals` to score items
    with a previously generated rubric evaluator.  Construct directly
    when the evaluator already exists, or obtain one from
    :meth:`FoundryEvals.generate_rubric`.

    Pinning ``version`` is strongly recommended so evaluation runs are
    reproducible.  The dataclass accepts ``version=None`` for the
    convenience of :meth:`latest`, but ``FoundryEvals`` emits a warning
    whenever a versionless reference is used; CI gates should always
    pass a concrete version.

    Attributes:
        name: Evaluator name as stored in the Foundry project (e.g.
            ``"my-policy-evaluator"``).  Distinct from built-in
            evaluators such as ``"builtin.relevance"``.
        version: Pinned evaluator version.  ``None`` means "latest" —
            this is discouraged for CI/repro and ``FoundryEvals`` will
            emit a warning when used.
        category: ``"quality"`` for ungrounded rubric scoring,
            ``"safety"`` for safety-focused evaluators.  Matches the
            Foundry evaluator's declared category.
        display_name: Optional human-readable name used in result
            summaries.  Defaults to ``name`` when unset.
        description: Optional description carried over from the
            generated evaluator definition for documentation.
        dimensions: Optional snapshot of the rubric's dimensions for
            inspection.  Not required to invoke the evaluator — the
            service uses the persisted definition.
        pass_threshold: Optional aggregate score threshold (0.0-1.0) the
            evaluator considers a passing item.  ``None`` defers to the
            evaluator's stored default.
    """

    name: str
    version: str | None = None
    category: Literal["quality", "safety"] = "quality"
    display_name: str | None = None
    description: str | None = None
    dimensions: tuple[RubricDimension, ...] | None = None
    pass_threshold: float | None = None

    @classmethod
    def latest(
        cls,
        name: str,
        *,
        category: Literal["quality", "safety"] = "quality",
        display_name: str | None = None,
        description: str | None = None,
    ) -> GeneratedEvaluatorRef:
        """Construct a versionless reference (resolves to the latest version at run time).

        Discouraged for reproducible runs.  Prefer the constructor with
        an explicit ``version`` so CI and replay evaluations stay stable
        when the evaluator is regenerated.
        """
        return cls(
            name=name,
            version=None,
            category=category,
            display_name=display_name,
            description=description,
        )


@experimental(feature_id=ExperimentalFeature.EVALS)
@dataclass(frozen=True)
class EvalGenerationSource:
    """A source description passed to Foundry's evaluator generation pipeline.

    Rubric evaluator generation consumes one or more sources that describe
    the agent or workflow under evaluation.  ``FoundryEvals`` translates
    instances into the underlying ``*EvaluatorGenerationJobSource`` SDK
    types.

    Discriminated by :attr:`type`:

    * ``"prompt"`` - a free-form textual dossier (typical for local agents
      and workflows whose tools cannot be fetched server-side).
    * ``"agent"`` - a hosted Foundry agent referenced by name so the
      service fetches tool definitions and metadata directly.
    * ``"dataset"`` - a Foundry dataset of recorded interactions.
    * ``"traces"`` - tracing data scoped by metadata.

    Only the fields relevant to :attr:`type` are populated; the remaining
    fields stay ``None``.

    Attributes:
        type: Source kind.  See discriminator above.
        description: Optional short description shown in Foundry UI.
        prompt: Rendered dossier for ``type="prompt"`` sources.
        agent_name: Hosted Foundry agent name for ``type="agent"`` sources.
        agent_version: Optional pinned hosted-agent version for
            ``type="agent"`` sources.  ``None`` resolves to the latest
            version at generation time; pin for reproducible runs.
        dataset_name: Foundry dataset name for ``type="dataset"`` sources.
        dataset_version: Pinned dataset version (recommended for repro).
        metadata: Free-form metadata.  Used by ``type="traces"`` sources
            for tracing-attribute filters and as a generic escape hatch
            for additional fields not yet modeled.
    """

    type: Literal["prompt", "dataset", "agent", "traces"]
    description: str | None = None
    prompt: str | None = None
    agent_name: str | None = None
    agent_version: str | None = None
    dataset_name: str | None = None
    dataset_version: str | None = None
    metadata: dict[str, Any] | None = None


@experimental(feature_id=ExperimentalFeature.EVALS)
def agent_as_eval_source(
    agent: BaseAgent,
    *,
    include_instructions: bool = True,
    include_tools: bool = True,
    include_context_providers: bool = False,
    include_examples: bool = False,
    examples: Sequence[str] | None = None,
    hosted_agent_name: str | None = None,
    hosted_agent_version: str | None = None,
    force_prompt_source: bool = False,
) -> EvalGenerationSource:
    """Render an agent as an :class:`EvalGenerationSource` for rubric generation.

    Picks the best Foundry source variant for the supplied agent:

    * **Hosted Foundry agents** (``FoundryAgent`` connected to a Prompt
      Agent or Hosted Agent in a Foundry project) are emitted as
      ``type="agent"`` sources keyed by ``agent_name`` so the service
      fetches instructions, tools, and metadata directly from the agent
      registry — independent of whatever the local wrapper happens to
      hold.  Detected automatically from ``agent.chat_client.agent_name``
      and ``agent.chat_client.agent_version``.
    * **Local agents** (any other ``BaseAgent`` whose instructions and
      tools live client-side, e.g. ``FoundryChatClient``-backed agents or
      pure OpenAI Responses agents) are emitted as ``type="prompt"``
      sources with a rendered text dossier.

    Override the heuristic by passing ``hosted_agent_name`` explicitly
    (forces an ``"agent"`` source) or ``force_prompt_source=True``
    (forces a ``"prompt"`` source — useful when you want the service to
    score a hosted agent against the *local* wrapper's overrides).

    Args:
        agent: Agent instance (typically a ``BaseAgent`` subclass).
        include_instructions: Whether to include the agent's instructions
            text in the dossier (``"prompt"`` sources only).  Defaults to
            ``True``.
        include_tools: Whether to include tool definitions in the dossier
            (``"prompt"`` sources only).  Defaults to ``True``.
        include_context_providers: Whether to include the names of
            attached context-provider classes in the dossier
            (``"prompt"`` sources only).  Defaults to ``False`` to avoid
            leaking implementation details.
        include_examples: Whether to include the supplied ``examples`` in
            the dossier (``"prompt"`` sources only).  Defaults to
            ``False`` to avoid shipping potentially sensitive sample
            inputs by default.
        examples: Optional sample queries / interactions to include when
            ``include_examples`` is ``True``.
        hosted_agent_name: When set, emit a ``type="agent"`` source
            referencing this hosted Foundry agent name regardless of
            auto-detection.  Use to override or supplement the
            heuristic.
        hosted_agent_version: When set together with a hosted-agent
            source, pins the source to a specific hosted-agent version.
            Recommended for reproducible rubric generation against
            PromptAgents.
        force_prompt_source: When ``True``, always emit a
            ``type="prompt"`` source with the rendered dossier even when
            the agent is a hosted Foundry agent.  Useful when the local
            wrapper holds overrides the service-side agent doesn't see.

    Returns:
        An :class:`EvalGenerationSource` describing the agent.
    """
    agent_description = getattr(agent, "description", None)

    resolved_name = hosted_agent_name
    resolved_version = hosted_agent_version
    if resolved_name is None and not force_prompt_source:
        detected_name, detected_version = _detect_hosted_foundry_agent(agent)
        if detected_name is not None:
            resolved_name = detected_name
            if resolved_version is None:
                resolved_version = detected_version

    if resolved_name is not None and not force_prompt_source:
        return EvalGenerationSource(
            type="agent",
            agent_name=resolved_name,
            agent_version=resolved_version,
            description=agent_description,
        )

    prompt = agent.as_eval_source(
        include_instructions=include_instructions,
        include_tools=include_tools,
        include_context_providers=include_context_providers,
        include_examples=include_examples,
        examples=examples,
    )
    return EvalGenerationSource(
        type="prompt",
        prompt=prompt,
        description=agent_description,
    )


def _detect_hosted_foundry_agent(agent: BaseAgent) -> tuple[str | None, str | None]:
    """Return ``(agent_name, agent_version)`` for hosted Foundry agents, else ``(None, None)``.

    A hosted Foundry agent is one whose ``chat_client`` exposes a string
    ``agent_name`` — the convention used by ``RawFoundryAgentChatClient``
    when ``FoundryAgent`` connects to an existing Prompt Agent or Hosted
    Agent in a Foundry project.  Only string values are accepted so
    test doubles using ``MagicMock`` for ``chat_client`` are not
    mis-detected.
    """
    chat_client = getattr(agent, "chat_client", None)
    if chat_client is None:
        return None, None
    name = getattr(chat_client, "agent_name", None)
    version = getattr(chat_client, "agent_version", None)
    if not isinstance(name, str) or not name:
        return None, None
    if not isinstance(version, str) or not version:
        version = None
    return name, version


@experimental(feature_id=ExperimentalFeature.EVALS)
def workflow_as_eval_source(
    workflow: Workflow,
    *,
    include_instructions: bool = True,
    include_tools: bool = True,
    include_context_providers: bool = False,
    include_examples: bool = False,
    examples: Sequence[str] | None = None,
    include_topology: bool = True,
) -> EvalGenerationSource:
    """Render a workflow as an :class:`EvalGenerationSource` for rubric generation.

    Wraps :meth:`Workflow.as_eval_source` to package the workflow's
    rendered dossier (workflow name, description, topology, per-agent
    dossiers) into a typed ``type="prompt"`` Foundry generation source.

    Args:
        workflow: Workflow instance to render.
        include_instructions: Per-agent instructions inclusion.
        include_tools: Per-agent tools inclusion.
        include_context_providers: Per-agent context-provider inclusion.
            Defaults to ``False``.
        include_examples: Per-agent examples inclusion.  Defaults to
            ``False``.
        examples: Optional workflow-level sample queries.  Rendered into
            a top-level ``Examples:`` section when ``include_examples`` is
            ``True``.
        include_topology: Whether to embed the JSON-encoded workflow
            topology produced by :meth:`Workflow.to_dict`.  Defaults to
            ``True``.

    Returns:
        A ``type="prompt"`` :class:`EvalGenerationSource` describing the
        workflow.
    """
    prompt = workflow.as_eval_source(
        include_instructions=include_instructions,
        include_tools=include_tools,
        include_context_providers=include_context_providers,
        include_examples=include_examples,
        examples=examples,
        include_topology=include_topology,
    )
    return EvalGenerationSource(
        type="prompt",
        prompt=prompt,
        description=workflow.description,
    )


# endregion
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

# Evaluators that accept tool_definitions in their data mapping when the
# evaluated items include tools.
_TOOL_DEFINITION_EVALUATORS: set[str] = _TOOL_EVALUATORS | {
    "builtin.intent_resolution",
    "builtin.task_adherence",
    "builtin.task_completion",
    "builtin.task_navigation_efficiency",
}

# Evaluators that require a ground_truth / expected_output field.
_GROUND_TRUTH_EVALUATORS: set[str] = {
    "builtin.similarity",
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
    evaluators: Sequence[str | GeneratedEvaluatorRef],
    model: str,
    *,
    include_data_mapping: bool = False,
    include_tool_definitions: bool = False,
) -> list[dict[str, Any]]:
    """Build ``testing_criteria`` for ``evals.create()``.

    Args:
        evaluators: Evaluator names (built-in shorts / fully-qualified
            ``builtin.*`` names) or :class:`GeneratedEvaluatorRef`
            instances for generated rubric evaluators.
        model: Model deployment for the LLM judge.
        include_data_mapping: Whether to include field-level data mapping
            (required for the JSONL data source, not needed for response-based).
        include_tool_definitions: Whether the mapped data items include tool
            definitions.
    """
    criteria: list[dict[str, Any]] = []
    for entry_spec in evaluators:
        if isinstance(entry_spec, GeneratedEvaluatorRef):
            short = entry_spec.display_name or entry_spec.name
            ref_entry: dict[str, Any] = {
                "type": "azure_ai_evaluator",
                "name": short,
                "evaluator_name": entry_spec.name,
                "initialization_parameters": {"deployment_name": model},
            }
            if entry_spec.version is not None:
                ref_entry["evaluator_version"] = entry_spec.version
            else:
                logger.warning(
                    "GeneratedEvaluatorRef '%s' has no pinned version; the eval run "
                    "will resolve to whichever version is current at execution time. "
                    "Pin the version for reproducible runs.",
                    entry_spec.name,
                )
            if include_data_mapping:
                # Rubric evaluators accept conversation arrays like agent
                # evaluators, plus tool_definitions when items are tool-aware.
                ref_mapping: dict[str, str] = {
                    "query": "{{item.query_messages}}",
                    "response": "{{item.response_messages}}",
                }
                if include_tool_definitions:
                    ref_mapping["tool_definitions"] = "{{item.tool_definitions}}"
                ref_entry["data_mapping"] = ref_mapping
            criteria.append(ref_entry)
            continue

        name = entry_spec
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
            if qualified in _GROUND_TRUTH_EVALUATORS:
                mapping["ground_truth"] = "{{item.ground_truth}}"
            if include_tool_definitions and qualified in _TOOL_DEFINITION_EVALUATORS:
                mapping["tool_definitions"] = "{{item.tool_definitions}}"
            entry["data_mapping"] = mapping

        criteria.append(entry)
    return criteria


def _build_item_schema(
    *, has_context: bool = False, has_tools: bool = False, has_ground_truth: bool = False
) -> dict[str, Any]:
    """Build the ``item_schema`` for custom JSONL eval definitions."""
    properties: dict[str, Any] = {
        "query": {"type": "string"},
        "response": {"type": "string"},
        "query_messages": {"type": "array"},
        "response_messages": {"type": "array"},
    }
    if has_context:
        properties["context"] = {"type": "string"}
    if has_ground_truth:
        properties["ground_truth"] = {"type": "string"}
    if has_tools:
        properties["tool_definitions"] = {"type": "array"}
    return {
        "type": "object",
        "properties": properties,
        "required": ["query", "response"],
    }


def _resolve_default_evaluators(
    evaluators: Sequence[str | GeneratedEvaluatorRef] | None,
    items: Sequence[EvalItem | dict[str, Any]] | None = None,
) -> list[str | GeneratedEvaluatorRef]:
    """Resolve evaluators, applying defaults when ``None``.

    Defaults to relevance + coherence + task_adherence. Automatically adds
    tool_call_accuracy when items contain tools.
    """
    if evaluators is not None:
        return list(evaluators)

    result: list[str | GeneratedEvaluatorRef] = list(_DEFAULT_EVALUATORS)
    if items is not None:
        has_tools = any((item.tools if isinstance(item, EvalItem) else item.get("tool_definitions")) for item in items)
        if has_tools:
            result.extend(_DEFAULT_TOOL_EVALUATORS)
    return result


def _filter_tool_evaluators(
    evaluators: list[str | GeneratedEvaluatorRef],
    items: Sequence[EvalItem | dict[str, Any]],
) -> list[str | GeneratedEvaluatorRef]:
    """Remove tool evaluators if no items have tool definitions.

    Generated rubric evaluators are tool-aware but not tool-required; they
    are preserved regardless of whether items carry tool definitions.
    """
    has_tools = any((item.tools if isinstance(item, EvalItem) else item.get("tool_definitions")) for item in items)
    if has_tools:
        return evaluators

    def _is_tool_only(spec: str | GeneratedEvaluatorRef) -> bool:
        if isinstance(spec, GeneratedEvaluatorRef):
            return False
        return _resolve_evaluator(spec) in _TOOL_EVALUATORS

    filtered = [e for e in evaluators if not _is_tool_only(e)]
    if not filtered:
        raise ValueError(
            f"All requested evaluators {evaluators} require tool definitions, "
            "but no items have tools. Either add tool definitions to your items "
            "or choose evaluators that do not require tools."
        )
    if len(filtered) < len(evaluators):
        removed = [e for e in evaluators if _is_tool_only(e)]
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


_RUBRIC_DIMENSION_KEYS: tuple[str, ...] = ("dimension_scores", "rubric_scores")
"""Property keys that may carry per-dimension rubric breakdowns.

The published Foundry rubric-evaluator output format uses
``properties.dimension_scores`` (see the Microsoft Learn "Rubric
evaluators" reference).  Earlier preview builds and some SDK shapes
used ``rubric_scores``; we accept both for defensive forward/backward
compatibility.
"""


def _parse_dimension_entries(raw: Any) -> list[RubricScore]:
    """Parse a raw list-like payload into ``RubricScore`` instances.

    Returns an empty list when ``raw`` is falsy, not iterable, or
    contains no well-formed entries.
    """
    if not raw:
        return []
    try:
        raw_iter: Iterable[Any] = iter(raw)
    except TypeError:
        return []

    parsed: list[RubricScore] = []
    for raw_entry in raw_iter:
        entry: Any = raw_entry
        try:
            rid: Any
            score_val: Any
            applicable: Any
            weight: Any
            reason: Any
            if isinstance(entry, dict):
                entry_any = cast("dict[str, Any]", entry)
                rid = entry_any.get("id")
                score_val = entry_any.get("score")
                applicable = entry_any.get("applicable")
                weight = entry_any.get("weight")
                reason = entry_any.get("reason", "")
            else:
                rid = getattr(entry, "id", None)
                score_val = getattr(entry, "score", None)
                applicable = getattr(entry, "applicable", None)
                weight = getattr(entry, "weight", None)
                reason = getattr(entry, "reason", "") or ""
            if rid is None or weight is None or applicable is None:
                continue
            parsed.append(
                RubricScore(
                    id=str(rid),
                    score=int(score_val) if isinstance(score_val, (int, float)) else None,
                    applicable=bool(applicable),
                    weight=int(weight),
                    reason=str(reason) if reason is not None else "",
                )
            )
        except (TypeError, ValueError):
            logger.debug("Skipping malformed rubric dimension entry: %s", cast("Any", entry), exc_info=True)
    return parsed


def _extract_rubric_scores(sample: Any) -> list[RubricScore] | None:
    """Extract typed ``RubricScore`` instances from an evaluator's raw sample payload.

    Foundry rubric evaluators include a per-dimension breakdown under
    ``properties.dimension_scores`` on each result (preview builds used
    ``rubric_scores``; both keys are accepted, with the canonical
    ``dimension_scores`` taking priority).  The exact location may
    vary across SDK versions, so this helper accepts a few shapes:

    * The SDK ``sample`` object exposes
      ``properties.dimension_scores`` / ``properties.rubric_scores``.
    * The ``sample`` is a dict containing the same under
      ``properties.<key>``.
    * The ``sample`` is a dict with ``dimension_scores`` /
      ``rubric_scores`` at the top level.

    Returns ``None`` when no rubric scores are present (i.e. the
    evaluator was not a rubric evaluator).
    """
    if sample is None:
        return None

    containers: list[Any] = []
    properties: Any = getattr(sample, "properties", None)
    if properties is not None:
        containers.append(properties)
    if isinstance(sample, dict):
        sample_any = cast("dict[str, Any]", sample)
        props_dict: Any = sample_any.get("properties")
        if props_dict is not None and props_dict is not properties:
            containers.append(props_dict)
        containers.append(sample_any)

    for container in containers:
        for key in _RUBRIC_DIMENSION_KEYS:
            raw: Any = None
            if isinstance(container, dict):
                raw = cast("dict[str, Any]", container).get(key)
            elif hasattr(container, key):
                raw = getattr(container, key, None)
            parsed = _parse_dimension_entries(raw)
            if parsed:
                return parsed
    return None


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
                sample = r.sample
                dimensions = _extract_rubric_scores(sample)
                scores.append(
                    EvalScoreResult(
                        name=r.name,
                        score=r.score,
                        passed=r.passed,
                        sample=sample,
                        dimensions=dimensions,
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
    evaluators: list[str | GeneratedEvaluatorRef],
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
        evaluators: Evaluator specifications.  Entries may be built-in
            short names (e.g. ``"relevance"``), fully-qualified
            ``"builtin.*"`` names, or :class:`GeneratedEvaluatorRef`
            instances for previously generated rubric evaluators.  When
            ``None`` (default), uses smart defaults based on item data.
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
        evaluators: Sequence[str | GeneratedEvaluatorRef] | None = None,
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
        self._evaluators: list[str | GeneratedEvaluatorRef] | None = (
            list(evaluators) if evaluators is not None else None
        )
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
        evaluators: list[str | GeneratedEvaluatorRef],
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
            if item.expected_output is not None:
                d["ground_truth"] = item.expected_output
            dicts.append(d)

        has_context = any("context" in d for d in dicts)
        has_ground_truth = any("ground_truth" in d for d in dicts)
        has_tools = any("tool_definitions" in d for d in dicts)

        eval_obj = await self._client.evals.create(
            name=eval_name,
            data_source_config={  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
                "type": "custom",
                "item_schema": _build_item_schema(
                    has_context=has_context, has_ground_truth=has_ground_truth, has_tools=has_tools
                ),
                "include_sample_schema": True,
            },
            testing_criteria=_build_testing_criteria(  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
                evaluators,
                self._model,
                include_data_mapping=True,
                include_tool_definitions=has_tools,
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

    @classmethod
    @experimental(feature_id=ExperimentalFeature.EVALS)
    async def generate_rubric(
        cls,
        *,
        project_client: AIProjectClient,
        name: str,
        agent: BaseAgent | None = None,
        workflow: Workflow | None = None,
        sources: Sequence[EvalGenerationSource] | None = None,
        category: Literal["quality", "safety"] = "quality",
        model: str | None = None,
        display_name: str | None = None,
        description: str | None = None,
        operation_id: str | None = None,
        poll_interval: float = 5.0,
        timeout: float = 600.0,
    ) -> GeneratedEvaluatorRef:
        """Generate a Foundry rubric evaluator from an agent or workflow.

        Drives the Foundry evaluator-generation long-running operation
        (``client.beta.evaluators.create_generation_job``) end-to-end and
        returns a pinned :class:`GeneratedEvaluatorRef` for use with
        :class:`FoundryEvals` ``evaluators=`` lists.

        Exactly one of ``agent``, ``workflow``, or ``sources`` must be
        supplied.  When ``agent`` or ``workflow`` is given,
        :func:`agent_as_eval_source` / :func:`workflow_as_eval_source` is
        used to build a single conservative source (instructions and
        tools included; examples and context providers excluded).  Pass
        ``sources=`` directly to control inclusion explicitly or to
        provide multiple sources.

        Requires ``azure-ai-projects`` with the rubric-generation APIs
        (currently ``2.3.0a*`` on the Azure SDK dev feed; tracked for an
        upcoming PyPI release).  Raises :class:`NotImplementedError` with
        a clear message when the dependency is unavailable.

        Keyword Args:
            project_client: Async ``AIProjectClient`` for the target
                Foundry project.
            name: Evaluator name to register in the project.  Must be a
                stable identifier (e.g. ``"policy-enforcement-v1"``).
            agent: Optional ``BaseAgent`` to derive a source from.
            workflow: Optional ``Workflow`` to derive a source from.
            sources: Explicit list of :class:`EvalGenerationSource`
                instances.  Mutually exclusive with ``agent`` / ``workflow``.
            category: ``"quality"`` or ``"safety"``.  Defaults to
                ``"quality"``.
            model: Optional model deployment to drive generation.  When
                omitted the service picks a default.
            display_name: Optional human-readable name for the evaluator.
            description: Optional description for the evaluator.
            operation_id: Optional caller-supplied operation id to make
                the create call idempotent.
            poll_interval: Seconds between job-status polls.
            timeout: Maximum seconds to wait for the job to complete.

        Returns:
            A pinned :class:`GeneratedEvaluatorRef` referring to the
            newly created evaluator.

        Raises:
            ValueError: If the source arguments are inconsistent.
            NotImplementedError: If the installed ``azure-ai-projects``
                version does not expose the rubric APIs.
            TimeoutError: If the job does not complete within ``timeout``.
            RuntimeError: If the generation job ends in a non-succeeded
                terminal state.
        """
        resolved_sources = _coalesce_generation_sources(agent=agent, workflow=workflow, sources=sources)

        if category not in ("quality", "safety"):
            raise ValueError(f"category must be 'quality' or 'safety', got {category!r}.")

        try:
            sdk_types = _import_generation_sdk_types()
        except _RubricSdkUnavailableError as exc:
            raise NotImplementedError(str(exc)) from exc

        sdk_sources = [_to_sdk_source(s, sdk_types) for s in resolved_sources]

        inputs_kwargs: dict[str, Any] = {
            "name": name,
            "category": category,
            "sources": sdk_sources,
        }
        if model is not None:
            inputs_kwargs["model"] = model
        if display_name is not None:
            inputs_kwargs["display_name"] = display_name
        if description is not None:
            inputs_kwargs["description"] = description

        inputs = sdk_types.EvaluatorGenerationInputs(**inputs_kwargs)
        job = sdk_types.EvaluatorGenerationJob(inputs=inputs)

        create_kwargs: dict[str, Any] = {"job": job}
        if operation_id is not None:
            create_kwargs["operation_id"] = operation_id

        evaluators_ops = _get_beta_evaluators(project_client)
        created = await evaluators_ops.create_generation_job(**create_kwargs)
        completed = await _poll_generation_job(
            evaluators_ops,
            created,
            poll_interval=poll_interval,
            timeout=timeout,
        )

        return _generation_job_to_ref(completed, category=category)

    @classmethod
    @experimental(feature_id=ExperimentalFeature.EVALS)
    async def create_rubric_evaluator(
        cls,
        *,
        project_client: AIProjectClient,
        name: str,
        dimensions: Sequence[RubricDimension],
        category: Literal["quality", "safety"] = "quality",
        pass_threshold: float | None = None,
        display_name: str | None = None,
        description: str | None = None,
        tags: dict[str, str] | None = None,
        metadata: dict[str, str] | None = None,
    ) -> GeneratedEvaluatorRef:
        """Register a rubric evaluator from caller-supplied dimensions.

        This is the *manual* counterpart to :meth:`generate_rubric` and
        maps directly to ``project_client.beta.evaluators.create_version``.
        Use it to bring a rubric you authored elsewhere (e.g. authored
        from an agent's local context, ported from another framework, or
        hand-tuned) into Foundry as a versioned ``EvaluatorVersion``
        that any subsequent ``evaluators=`` list can reference via the
        returned :class:`GeneratedEvaluatorRef`.

        The service auto-attaches a non-editable residual dimension
        (``general_quality`` for ``category="quality"``,
        ``general_policy_compliance`` for ``"safety"``) — do not include
        it in ``dimensions``.

        Keyword Args:
            project_client: Async ``AIProjectClient`` for the target
                Foundry project.
            name: Stable evaluator name (e.g.
                ``"reservation-agent-policy-v1"``). A new version is
                allocated on each call.
            dimensions: One or more :class:`RubricDimension` instances
                describing the scoring blueprint. Each dimension's
                ``id`` must be unique; ``weight`` must be in ``[1, 10]``.
            category: ``"quality"`` (default) or ``"safety"``.
            pass_threshold: Optional aggregate pass threshold on the
                normalized 0.0-1.0 scale. Defaults to the service-side
                default of ``0.5`` when omitted.
            display_name: Optional human-readable name shown in the
                Foundry portal.
            description: Optional asset description.
            tags: Optional asset tags.
            metadata: Optional free-form metadata persisted with the
                evaluator definition.

        Returns:
            A pinned :class:`GeneratedEvaluatorRef` referring to the
            newly created evaluator version.

        Raises:
            ValueError: If ``dimensions`` is empty, contains duplicate
                ids, or contains a weight outside ``[1, 10]``.
            NotImplementedError: If the installed ``azure-ai-projects``
                version does not expose the manual rubric APIs.
        """
        if category not in ("quality", "safety"):
            raise ValueError(f"category must be 'quality' or 'safety', got {category!r}.")
        if pass_threshold is not None and not (0.0 <= pass_threshold <= 1.0):
            raise ValueError(f"pass_threshold must be in [0.0, 1.0] when set (got {pass_threshold!r}).")
        if not dimensions:
            raise ValueError("create_rubric_evaluator requires at least one dimension.")

        try:
            sdk_types = _import_manual_rubric_sdk_types()
        except _RubricSdkUnavailableError as exc:
            raise NotImplementedError(str(exc)) from exc

        sdk_dimensions = _to_sdk_dimensions(dimensions, sdk_types.Dimension)
        definition_kwargs: dict[str, Any] = {"dimensions": sdk_dimensions}
        if pass_threshold is not None:
            definition_kwargs["pass_threshold"] = pass_threshold
        definition = sdk_types.RubricBasedEvaluatorDefinition(**definition_kwargs)

        version_kwargs: dict[str, Any] = {
            "evaluator_type": "custom",
            "categories": [category],
            "definition": definition,
        }
        if display_name is not None:
            version_kwargs["display_name"] = display_name
        if description is not None:
            version_kwargs["description"] = description
        if tags is not None:
            version_kwargs["tags"] = tags
        if metadata is not None:
            version_kwargs["metadata"] = metadata

        evaluator_version = sdk_types.EvaluatorVersion(**version_kwargs)
        evaluators_ops = _get_beta_evaluators(project_client)
        created = await evaluators_ops.create_version(name, evaluator_version=evaluator_version)

        return _evaluator_version_to_ref(created, fallback_name=name, category=category)


_TERMINAL_GENERATION_STATUSES: frozenset[str] = frozenset({"succeeded", "failed", "cancelled", "canceled"})


class _RubricSdkUnavailableError(Exception):
    """Raised when azure-ai-projects lacks the rubric-generation APIs."""


@dataclass(frozen=True)
class _GenerationSdkTypes:
    """Resolved SDK type handles for rubric-evaluator generation."""

    EvaluatorGenerationInputs: Any
    EvaluatorGenerationJob: Any
    PromptSource: Any
    AgentSource: Any | None
    DatasetSource: Any | None
    TracesSource: Any | None


@dataclass(frozen=True)
class _ManualRubricSdkTypes:
    """Resolved SDK type handles for manual rubric-evaluator creation."""

    EvaluatorVersion: Any
    RubricBasedEvaluatorDefinition: Any
    Dimension: Any


_RUBRIC_SDK_MISSING_MSG = (
    "FoundryEvals.generate_rubric requires the rubric-evaluator generation APIs "
    "from azure-ai-projects (currently 2.3.0a* on the Azure SDK Python dev feed). "
    "Install a build that exposes "
    "`azure.ai.projects.models.EvaluatorGenerationInputs` and "
    "`AIProjectClient.beta.evaluators.create_generation_job`."
)


_MANUAL_RUBRIC_SDK_MISSING_MSG = (
    "FoundryEvals.create_rubric_evaluator requires the manual rubric-evaluator "
    "APIs from azure-ai-projects (currently 2.3.0a* on the Azure SDK Python dev "
    "feed). Install a build that exposes "
    "`azure.ai.projects.models.RubricBasedEvaluatorDefinition`, "
    "`azure.ai.projects.models.Dimension`, and "
    "`AIProjectClient.beta.evaluators.create_version`."
)


def _import_generation_sdk_types() -> _GenerationSdkTypes:
    """Lazily resolve the rubric-generation SDK types from azure-ai-projects."""
    try:
        from azure.ai.projects import models as _models  # type: ignore[import-not-found]
    except ImportError as exc:
        raise _RubricSdkUnavailableError(_RUBRIC_SDK_MISSING_MSG) from exc

    models_mod: Any = _models
    inputs_cls: Any = getattr(models_mod, "EvaluatorGenerationInputs", None)
    job_cls: Any = getattr(models_mod, "EvaluatorGenerationJob", None)
    prompt_cls: Any = getattr(models_mod, "PromptEvaluatorGenerationJobSource", None)
    if inputs_cls is None or job_cls is None or prompt_cls is None:
        raise _RubricSdkUnavailableError(_RUBRIC_SDK_MISSING_MSG)

    agent_cls: Any = getattr(models_mod, "AgentEvaluatorGenerationJobSource", None)
    dataset_cls: Any = getattr(models_mod, "DatasetEvaluatorGenerationJobSource", None)
    traces_cls: Any = getattr(models_mod, "TracesEvaluatorGenerationJobSource", None)

    return _GenerationSdkTypes(
        EvaluatorGenerationInputs=inputs_cls,
        EvaluatorGenerationJob=job_cls,
        PromptSource=prompt_cls,
        AgentSource=agent_cls,
        DatasetSource=dataset_cls,
        TracesSource=traces_cls,
    )


def _import_manual_rubric_sdk_types() -> _ManualRubricSdkTypes:
    """Lazily resolve the manual rubric-evaluator SDK types from azure-ai-projects."""
    try:
        from azure.ai.projects import models as _models  # type: ignore[import-not-found]
    except ImportError as exc:
        raise _RubricSdkUnavailableError(_MANUAL_RUBRIC_SDK_MISSING_MSG) from exc

    models_mod: Any = _models
    version_cls: Any = getattr(models_mod, "EvaluatorVersion", None)
    definition_cls: Any = getattr(models_mod, "RubricBasedEvaluatorDefinition", None)
    dimension_cls: Any = getattr(models_mod, "Dimension", None)
    if version_cls is None or definition_cls is None or dimension_cls is None:
        raise _RubricSdkUnavailableError(_MANUAL_RUBRIC_SDK_MISSING_MSG)

    return _ManualRubricSdkTypes(
        EvaluatorVersion=version_cls,
        RubricBasedEvaluatorDefinition=definition_cls,
        Dimension=dimension_cls,
    )


def _to_sdk_dimensions(
    dimensions: Sequence[RubricDimension],
    dimension_cls: Any,
) -> list[Any]:
    """Translate user-facing ``RubricDimension`` instances to SDK ``Dimension`` models.

    The agent-framework type uses ``id`` (matching the runtime output
    schema and competing frameworks); the SDK input model uses
    ``dimension_id`` for the editable identifier.
    """
    if not dimensions:
        raise ValueError("create_rubric_evaluator requires at least one dimension.")
    seen: set[str] = set()
    sdk_dims: list[Any] = []
    for dim in dimensions:
        if not dim.id:
            raise ValueError("RubricDimension.id must be a non-empty string.")
        if not dim.description:
            raise ValueError(f"RubricDimension(id={dim.id!r}).description must be non-empty.")
        if not isinstance(dim.weight, int) or not (1 <= dim.weight <= 10):
            raise ValueError(f"RubricDimension(id={dim.id!r}).weight must be an int in [1, 10] (got {dim.weight!r}).")
        if dim.id in seen:
            raise ValueError(f"Duplicate RubricDimension.id={dim.id!r}; ids must be unique within a rubric.")
        seen.add(dim.id)
        kwargs: dict[str, Any] = {
            "dimension_id": dim.id,
            "description": dim.description,
            "weight": dim.weight,
        }
        if dim.always_applicable:
            kwargs["always_applicable"] = True
        sdk_dims.append(dimension_cls(**kwargs))
    return sdk_dims


def _evaluator_version_to_ref(
    created: Any,
    *,
    fallback_name: str,
    category: Literal["quality", "safety"],
) -> GeneratedEvaluatorRef:
    """Translate a persisted ``EvaluatorVersion`` to a :class:`GeneratedEvaluatorRef`.

    Used by both the generation-job path and the manual ``create_version``
    path so callers see a uniform pinned reference regardless of how the
    evaluator was authored.
    """
    ev_name = getattr(created, "name", None) or fallback_name
    ev_version = getattr(created, "version", None)
    if ev_version is None:
        raise RuntimeError("Created evaluator version is missing a version identifier.")

    definition: Any = getattr(created, "definition", None)
    dimensions: tuple[RubricDimension, ...] | None = None
    raw_dims: Any = getattr(definition, "dimensions", None) if definition is not None else None
    if raw_dims:
        parsed: list[RubricDimension] = []
        for entry in raw_dims:
            dim_id = getattr(entry, "dimension_id", None) or getattr(entry, "id", None)
            try:
                parsed.append(
                    RubricDimension(
                        id=str(dim_id or ""),
                        description=str(getattr(entry, "description", "") or ""),
                        weight=int(getattr(entry, "weight", 0) or 0),
                        always_applicable=bool(getattr(entry, "always_applicable", False)),
                    )
                )
            except (TypeError, ValueError):
                logger.debug("Skipping malformed dimension on persisted evaluator", exc_info=True)
        if parsed:
            dimensions = tuple(parsed)

    pass_threshold: float | None = None
    raw_threshold: Any = getattr(definition, "pass_threshold", None) if definition is not None else None
    if isinstance(raw_threshold, (int, float)):
        pass_threshold = float(raw_threshold)

    return GeneratedEvaluatorRef(
        name=str(ev_name),
        version=str(ev_version),
        category=category,
        display_name=getattr(created, "display_name", None),
        description=getattr(created, "description", None),
        dimensions=dimensions,
        pass_threshold=pass_threshold,
    )


def _get_beta_evaluators(project_client: AIProjectClient) -> Any:
    """Return the ``project_client.beta.evaluators`` operations group, or raise."""
    beta = getattr(project_client, "beta", None)
    evaluators_ops = getattr(beta, "evaluators", None) if beta is not None else None
    if evaluators_ops is None:
        raise NotImplementedError(_RUBRIC_SDK_MISSING_MSG)
    return evaluators_ops


def _coalesce_generation_sources(
    *,
    agent: BaseAgent | None,
    workflow: Workflow | None,
    sources: Sequence[EvalGenerationSource] | None,
) -> list[EvalGenerationSource]:
    if sources is not None and not sources:
        raise ValueError("sources= must contain at least one EvalGenerationSource.")
    supplied = [bool(agent), bool(workflow), bool(sources)]
    if sum(supplied) == 0:
        raise ValueError("Provide one of agent=, workflow=, or sources=.")
    if sum(supplied) > 1:
        raise ValueError("Provide only one of agent=, workflow=, or sources=.")
    if sources is not None:
        return list(sources)
    if agent is not None:
        return [agent_as_eval_source(agent)]
    if workflow is None:
        raise ValueError("workflow= must be provided when agent= and sources= are not set.")
    return [workflow_as_eval_source(workflow)]


def _to_sdk_source(source: EvalGenerationSource, sdk_types: _GenerationSdkTypes) -> Any:
    """Translate an :class:`EvalGenerationSource` to its SDK counterpart."""
    if source.type == "prompt":
        if not source.prompt:
            raise ValueError("EvalGenerationSource(type='prompt') requires a non-empty prompt.")
        kwargs: dict[str, Any] = {"prompt": source.prompt}
        if source.description is not None:
            kwargs["description"] = source.description
        return sdk_types.PromptSource(**kwargs)
    if source.type == "agent":
        if sdk_types.AgentSource is None:
            raise NotImplementedError("Installed azure-ai-projects does not expose AgentEvaluatorGenerationJobSource.")
        if not source.agent_name:
            raise ValueError("EvalGenerationSource(type='agent') requires agent_name.")
        kwargs = {"agent_name": source.agent_name}
        if source.agent_version is not None:
            kwargs["agent_version"] = source.agent_version
        if source.description is not None:
            kwargs["description"] = source.description
        return sdk_types.AgentSource(**kwargs)
    if source.type == "dataset":
        if sdk_types.DatasetSource is None:
            raise NotImplementedError(
                "Installed azure-ai-projects does not expose DatasetEvaluatorGenerationJobSource."
            )
        if not source.dataset_name:
            raise ValueError("EvalGenerationSource(type='dataset') requires dataset_name.")
        # SDK uses ``name`` / ``version`` (not ``dataset_name`` / ``dataset_version``).
        kwargs = {"name": source.dataset_name}
        if source.dataset_version is not None:
            kwargs["version"] = source.dataset_version
        if source.description is not None:
            kwargs["description"] = source.description
        return sdk_types.DatasetSource(**kwargs)
    if source.type == "traces":
        if sdk_types.TracesSource is None:
            raise NotImplementedError("Installed azure-ai-projects does not expose TracesEvaluatorGenerationJobSource.")
        kwargs = {}
        if source.metadata is not None:
            kwargs["metadata"] = source.metadata
        if source.description is not None:
            kwargs["description"] = source.description
        return sdk_types.TracesSource(**kwargs)
    raise ValueError(f"Unknown EvalGenerationSource type: {source.type!r}")


async def _poll_generation_job(
    evaluators_ops: Any,
    job: Any,
    *,
    poll_interval: float,
    timeout: float,
) -> Any:
    """Poll a rubric-generation job until it reaches a terminal state."""
    job_id = getattr(job, "id", None)
    if not job_id:
        raise RuntimeError("Rubric generation job did not return an id.")

    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    current = job
    while True:
        status = (getattr(current, "status", "") or "").lower()
        if status in _TERMINAL_GENERATION_STATUSES:
            if status != "succeeded":
                err = getattr(current, "error", None)
                err_msg = getattr(err, "message", None) or str(err) if err is not None else status
                raise RuntimeError(f"Rubric generation job {job_id} ended in status {status!r}: {err_msg}")
            return current
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError(
                f"Rubric generation job {job_id} did not complete within {timeout}s (last status: {status!r})."
            )
        await asyncio.sleep(min(poll_interval, remaining))
        current = await evaluators_ops.get_generation_job(job_id)


def _generation_job_to_ref(job: Any, *, category: Literal["quality", "safety"]) -> GeneratedEvaluatorRef:
    """Build a pinned :class:`GeneratedEvaluatorRef` from a completed job."""
    artifacts: Any = getattr(job, "artifacts", None)
    evaluator: Any = getattr(artifacts, "evaluator", None) if artifacts is not None else None
    if evaluator is None:
        raise RuntimeError("Rubric generation job completed without an evaluator artifact.")

    ev_name = getattr(evaluator, "name", None)
    ev_version = getattr(evaluator, "version", None)
    if not ev_name:
        raise RuntimeError("Generated evaluator artifact is missing a name.")
    if ev_version is None:
        raise RuntimeError("Generated evaluator artifact is missing a version.")

    definition: Any = getattr(evaluator, "definition", None)
    dimensions_raw: Any = getattr(definition, "dimensions", None) if definition is not None else None
    dimensions: tuple[RubricDimension, ...] | None = None
    if dimensions_raw:
        parsed: list[RubricDimension] = []
        for entry in dimensions_raw:
            try:
                parsed.append(
                    RubricDimension(
                        id=str(getattr(entry, "id", "") or ""),
                        description=str(getattr(entry, "description", "") or ""),
                        weight=int(getattr(entry, "weight", 0) or 0),
                        always_applicable=bool(getattr(entry, "always_applicable", False)),
                    )
                )
            except (TypeError, ValueError):
                logger.debug("Skipping malformed dimension on generated evaluator", exc_info=True)
        if parsed:
            dimensions = tuple(parsed)

    pass_threshold: float | None = None
    if definition is not None:
        raw_threshold = getattr(definition, "pass_threshold", None)
        if isinstance(raw_threshold, (int, float)):
            pass_threshold = float(raw_threshold)

    return GeneratedEvaluatorRef(
        name=str(ev_name),
        version=str(ev_version),
        category=category,
        display_name=getattr(evaluator, "display_name", None),
        description=getattr(evaluator, "description", None),
        dimensions=dimensions,
        pass_threshold=pass_threshold,
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
