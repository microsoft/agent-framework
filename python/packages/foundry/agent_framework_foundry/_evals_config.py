# Copyright (c) Microsoft. All rights reserved.

"""YAML-driven evaluator configuration for rubric generation and evaluation.

Defines the source-controlled config schema described in
``adaptive-evals-draft.md``: a list of named rubric-generation specs that
CI jobs and harnesses parse to drive
:meth:`FoundryEvals.generate_rubric`.

Example config:

.. code-block:: yaml

    evaluators:
      reservation-agent-quality:
        type: foundry.generated_rubric
        category: quality
        model: gpt-4o
        agent: reservation-agent
        sources:
          - type: agent
            include_instructions: true
            include_tools: true
          - type: dataset
            name: reservation-business-rules
            version: "1"

Example loader usage:

.. code-block:: python

    from agent_framework_foundry import load_evals_config, FoundryEvals

    config = load_evals_config("evaluators.yaml")
    spec = config["reservation-agent-quality"]
    sources = build_sources(spec, agent=agent)
    ref = await FoundryEvals.generate_rubric(
        project_client=client,
        name=spec.name,
        sources=sources,
        category=spec.category,
        model=spec.model,
        display_name=spec.display_name,
        description=spec.description,
    )
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, cast

from agent_framework._feature_stage import ExperimentalFeature, experimental

from ._foundry_evals import (
    EvalGenerationSource,
    agent_as_eval_source,
    workflow_as_eval_source,
)

_RUBRIC_TYPE = "foundry.generated_rubric"


@experimental(feature_id=ExperimentalFeature.EVALS)
@dataclass(frozen=True)
class RubricSourceSpec:
    """A single source entry in a :class:`RubricGenerationSpec` ``sources`` list.

    Mirrors the per-source YAML schema.  The :attr:`type` field is the
    discriminator; only the fields relevant to each type are read.

    Attributes:
        type: One of ``"agent"``, ``"workflow"``, ``"prompt"``,
            ``"dataset"``, ``"traces"``.
        description: Optional description shown in Foundry UI.
        include_instructions: Whether to include the bound agent /
            workflow's instructions.  Applies to ``"agent"`` and
            ``"workflow"`` types.
        include_tools: Whether to include the bound agent / workflow's
            tools.  Applies to ``"agent"`` and ``"workflow"`` types.
        include_context_providers: Whether to include attached
            context-provider class names.  Applies to ``"agent"`` and
            ``"workflow"`` types.
        include_examples: Whether to include ``examples``.  Applies to
            ``"agent"`` and ``"workflow"`` types.
        include_topology: Whether to include the JSON-encoded topology.
            Applies to ``"workflow"`` type.
        examples: Optional list of example queries for ``"agent"`` /
            ``"workflow"`` sources.
        prompt: Rendered dossier for ``"prompt"`` type.
        agent_name: Hosted Foundry agent name for ``"agent"`` type with
            a server-side reference.
        name: Dataset name for ``"dataset"`` type.
        version: Pinned dataset version.
        metadata: Free-form metadata for ``"traces"`` sources.
    """

    type: Literal["agent", "workflow", "prompt", "dataset", "traces"]
    description: str | None = None
    include_instructions: bool = True
    include_tools: bool = True
    include_context_providers: bool = False
    include_examples: bool = False
    include_topology: bool = True
    examples: tuple[str, ...] = field(default_factory=tuple)
    prompt: str | None = None
    agent_name: str | None = None
    name: str | None = None
    version: str | None = None
    metadata: dict[str, Any] | None = None


@experimental(feature_id=ExperimentalFeature.EVALS)
@dataclass(frozen=True)
class RubricGenerationSpec:
    """A single named entry from an evaluators YAML config.

    Attributes:
        name: Evaluator name (the YAML key under ``evaluators``).
        type: Discriminator literal.  Must be
            ``"foundry.generated_rubric"`` for rubric evaluators.
        category: ``"quality"`` or ``"safety"``.
        model: Optional model deployment to drive generation.
        agent: Optional symbolic reference to the agent in the
            caller's harness.  Resolved by user code into a
            :class:`BaseAgent` and passed to
            :func:`build_sources`.
        workflow: Optional symbolic reference to a workflow.
        display_name: Optional human-readable name.
        description: Optional description.
        sources: List of source specs to feed into generation.  When
            empty, callers typically default to a single
            ``RubricSourceSpec(type='agent')`` or
            ``RubricSourceSpec(type='workflow')`` source.
    """

    name: str
    type: str = _RUBRIC_TYPE
    category: Literal["quality", "safety"] = "quality"
    model: str | None = None
    agent: str | None = None
    workflow: str | None = None
    display_name: str | None = None
    description: str | None = None
    sources: tuple[RubricSourceSpec, ...] = field(default_factory=tuple)


@experimental(feature_id=ExperimentalFeature.EVALS)
def load_evals_config(path: str | os.PathLike[str]) -> dict[str, RubricGenerationSpec]:
    """Load a YAML evaluators config and return a name -> spec mapping.

    Reads ``path`` (UTF-8) and parses the top-level ``evaluators``
    mapping into :class:`RubricGenerationSpec` instances keyed by name.

    Requires ``PyYAML``.  Raises :class:`ImportError` with a helpful
    message when PyYAML is not installed.

    Args:
        path: Filesystem path to the YAML config.

    Returns:
        A dict mapping evaluator name to :class:`RubricGenerationSpec`.

    Raises:
        ImportError: If PyYAML is not installed.
        ValueError: If the YAML file is malformed.
    """
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise ImportError("load_evals_config requires PyYAML.  Install with `pip install pyyaml`.") from exc

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return parse_evals_config(raw)


@experimental(feature_id=ExperimentalFeature.EVALS)
def parse_evals_config(data: Any) -> dict[str, RubricGenerationSpec]:
    """Parse an already-loaded YAML mapping into rubric-generation specs.

    Useful when callers manage YAML loading themselves (e.g. CI that
    interpolates env vars before parsing).

    Args:
        data: A mapping with an ``"evaluators"`` key containing a mapping
            of evaluator names to spec dicts.

    Returns:
        A dict mapping evaluator name to :class:`RubricGenerationSpec`.

    Raises:
        ValueError: If the structure is malformed.
    """
    if not isinstance(data, Mapping):
        raise ValueError("Evaluators config must be a mapping.")
    data_map = cast("Mapping[str, Any]", data)
    raw_evaluators = data_map.get("evaluators")
    if raw_evaluators is None:
        raise ValueError("Evaluators config is missing a top-level 'evaluators' key.")
    if not isinstance(raw_evaluators, Mapping):
        raise ValueError("Evaluators config 'evaluators' entry must be a mapping.")
    evaluators = cast("Mapping[str, Any]", raw_evaluators)

    parsed: dict[str, RubricGenerationSpec] = {}
    for name, raw in evaluators.items():
        if not isinstance(raw, Mapping):
            raise ValueError(f"Evaluator entry {name!r} must be a mapping, got {type(raw).__name__}.")
        raw_map = cast("Mapping[str, Any]", raw)
        parsed[name] = _parse_spec(name, raw_map)
    return parsed


def _parse_spec(name: str, raw: Mapping[str, Any]) -> RubricGenerationSpec:
    type_value = raw.get("type", _RUBRIC_TYPE)
    if type_value != _RUBRIC_TYPE:
        raise ValueError(f"Evaluator {name!r} has unsupported type {type_value!r}; expected {_RUBRIC_TYPE!r}.")
    category = raw.get("category", "quality")
    if category not in ("quality", "safety"):
        raise ValueError(f"Evaluator {name!r} has invalid category {category!r}; expected 'quality' or 'safety'.")

    raw_sources_obj: Any = raw.get("sources") or ()
    if not isinstance(raw_sources_obj, (list, tuple)):
        raise ValueError(f"Evaluator {name!r} 'sources' must be a list.")
    sources_iter: list[Any] = list(cast("Any", raw_sources_obj))
    sources: list[RubricSourceSpec] = []
    for index, raw_source in enumerate(sources_iter):
        if not isinstance(raw_source, Mapping):
            raise ValueError(
                f"Evaluator {name!r} source entry {index} must be a mapping, got {type(raw_source).__name__}."
            )
        sources.append(_parse_source(name, index, cast("Mapping[str, Any]", raw_source)))

    return RubricGenerationSpec(
        name=name,
        type=type_value,
        category=category,
        model=raw.get("model"),
        agent=raw.get("agent"),
        workflow=raw.get("workflow"),
        display_name=raw.get("display_name"),
        description=raw.get("description"),
        sources=tuple(sources),
    )


def _parse_source(spec_name: str, index: int, raw: Mapping[str, Any]) -> RubricSourceSpec:
    type_value = raw.get("type")
    if type_value not in ("agent", "workflow", "prompt", "dataset", "traces"):
        raise ValueError(
            f"Evaluator {spec_name!r} source {index} has invalid type {type_value!r}; "
            "expected one of 'agent', 'workflow', 'prompt', 'dataset', 'traces'."
        )

    examples_raw: Any = raw.get("examples") or ()
    if not isinstance(examples_raw, (list, tuple)):
        raise ValueError(f"Evaluator {spec_name!r} source {index} 'examples' must be a list.")
    examples_iter: list[Any] = list(cast("Any", examples_raw))
    examples = tuple(str(e) for e in examples_iter)

    metadata_raw = raw.get("metadata")
    if metadata_raw is not None and not isinstance(metadata_raw, Mapping):
        raise ValueError(f"Evaluator {spec_name!r} source {index} 'metadata' must be a mapping.")

    return RubricSourceSpec(
        type=cast("Any", type_value),
        description=raw.get("description"),
        include_instructions=bool(raw.get("include_instructions", True)),
        include_tools=bool(raw.get("include_tools", True)),
        include_context_providers=bool(raw.get("include_context_providers", False)),
        include_examples=bool(raw.get("include_examples", False)),
        include_topology=bool(raw.get("include_topology", True)),
        examples=examples,
        prompt=raw.get("prompt"),
        agent_name=raw.get("agent_name"),
        name=raw.get("name"),
        version=str(raw.get("version")) if raw.get("version") is not None else None,
        metadata=dict(cast("Mapping[str, Any]", metadata_raw)) if metadata_raw is not None else None,
    )


@experimental(feature_id=ExperimentalFeature.EVALS)
def build_sources(
    spec: RubricGenerationSpec,
    *,
    agent: Any | None = None,
    workflow: Any | None = None,
) -> list[EvalGenerationSource]:
    """Translate a spec's source list into :class:`EvalGenerationSource` instances.

    Resolves each :class:`RubricSourceSpec` against the supplied
    ``agent`` and ``workflow`` instances:

    * ``type='agent'`` sources call :func:`agent_as_eval_source` with
      the spec's include-flags.  If the source carries an
      ``agent_name`` the agent is referenced server-side instead.
    * ``type='workflow'`` sources call
      :func:`workflow_as_eval_source` with the spec's include-flags.
    * ``type='prompt'``, ``type='dataset'``, and ``type='traces'``
      sources are translated directly into
      :class:`EvalGenerationSource` instances without consulting the
      runtime agent or workflow.

    When the spec has no ``sources`` entries, defaults to a single
    ``type='agent'`` source when an ``agent`` is provided, or a single
    ``type='workflow'`` source when a ``workflow`` is provided.

    Args:
        spec: Parsed :class:`RubricGenerationSpec`.
        agent: Optional agent instance for ``type='agent'`` sources.
        workflow: Optional workflow instance for ``type='workflow'``
            sources.

    Returns:
        A list of :class:`EvalGenerationSource` instances ready to pass
        to :meth:`FoundryEvals.generate_rubric` as ``sources=``.

    Raises:
        ValueError: If a source references an agent or workflow that
            was not supplied.
    """
    if not spec.sources:
        if agent is not None:
            return [agent_as_eval_source(agent)]
        if workflow is not None:
            return [workflow_as_eval_source(workflow)]
        raise ValueError(f"Spec {spec.name!r} has no sources and no agent/workflow was provided to build_sources().")

    out: list[EvalGenerationSource] = []
    for src in spec.sources:
        if src.type == "agent":
            if src.agent_name:
                out.append(
                    EvalGenerationSource(
                        type="agent",
                        agent_name=src.agent_name,
                        description=src.description,
                    )
                )
                continue
            if agent is None:
                raise ValueError(f"Spec {spec.name!r} has a source of type 'agent' but no agent= was provided.")
            out.append(
                agent_as_eval_source(
                    agent,
                    include_instructions=src.include_instructions,
                    include_tools=src.include_tools,
                    include_context_providers=src.include_context_providers,
                    include_examples=src.include_examples,
                    examples=list(src.examples) if src.examples else None,
                )
            )
        elif src.type == "workflow":
            if workflow is None:
                raise ValueError(f"Spec {spec.name!r} has a source of type 'workflow' but no workflow= was provided.")
            out.append(
                workflow_as_eval_source(
                    workflow,
                    include_instructions=src.include_instructions,
                    include_tools=src.include_tools,
                    include_context_providers=src.include_context_providers,
                    include_examples=src.include_examples,
                    examples=list(src.examples) if src.examples else None,
                    include_topology=src.include_topology,
                )
            )
        elif src.type == "prompt":
            if not src.prompt:
                raise ValueError(f"Spec {spec.name!r} has a 'prompt' source missing the 'prompt' field.")
            out.append(EvalGenerationSource(type="prompt", prompt=src.prompt, description=src.description))
        elif src.type == "dataset":
            if not src.name:
                raise ValueError(f"Spec {spec.name!r} has a 'dataset' source missing the 'name' field.")
            out.append(
                EvalGenerationSource(
                    type="dataset",
                    dataset_name=src.name,
                    dataset_version=src.version,
                    description=src.description,
                )
            )
        elif src.type == "traces":
            out.append(
                EvalGenerationSource(
                    type="traces",
                    description=src.description,
                    metadata=src.metadata,
                )
            )
        else:  # pragma: no cover - guarded by _parse_source
            raise ValueError(f"Spec {spec.name!r} has unknown source type {src.type!r}.")
    return out


__all__ = [
    "RubricGenerationSpec",
    "RubricSourceSpec",
    "build_sources",
    "load_evals_config",
    "parse_evals_config",
]
