# Copyright (c) Microsoft. All rights reserved.

"""Tests for the YAML-driven evaluator configuration loader."""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from agent_framework_foundry._evals_config import (
    RubricGenerationSpec,
    RubricSourceSpec,
    build_sources,
    load_evals_config,
    parse_evals_config,
)
from agent_framework_foundry._foundry_evals import EvalGenerationSource


def _make_agent(name: str = "agent-a", instructions: str = "Be brief.") -> Any:
    from agent_framework._evaluation import _render_agent_dossier

    agent = MagicMock()
    agent.name = name
    agent.description = f"{name} description"
    agent.default_options = {"instructions": instructions, "tools": []}
    agent.context_providers = []
    agent.mcp_tools = []
    agent.as_eval_source.side_effect = lambda **kw: _render_agent_dossier(
        agent,
        include_instructions=kw.get("include_instructions", True),
        include_tools=kw.get("include_tools", True),
        include_context_providers=kw.get("include_context_providers", False),
        include_examples=kw.get("include_examples", False),
        examples=kw.get("examples"),
    )
    return agent


def _make_workflow() -> Any:
    from agent_framework._evaluation import _render_workflow_dossier

    workflow = MagicMock()
    workflow.name = "wf-1"
    workflow.description = "demo"
    workflow.to_dict.return_value = {"name": "wf-1", "id": "wf_1", "executors": {}, "edge_groups": []}
    workflow.executors = {}
    workflow.as_eval_source.side_effect = lambda **kw: _render_workflow_dossier(
        workflow,
        include_instructions=kw.get("include_instructions", True),
        include_tools=kw.get("include_tools", True),
        include_context_providers=kw.get("include_context_providers", False),
        include_examples=kw.get("include_examples", False),
        examples=kw.get("examples"),
        include_topology=kw.get("include_topology", True),
    )
    return workflow


class TestParseEvalsConfig:
    """Parsing already-loaded dicts into RubricGenerationSpec instances."""

    def test_minimal_spec(self) -> None:
        config = parse_evals_config({
            "evaluators": {
                "my-rubric": {
                    "type": "foundry.generated_rubric",
                }
            }
        })
        assert "my-rubric" in config
        spec = config["my-rubric"]
        assert spec.name == "my-rubric"
        assert spec.type == "foundry.generated_rubric"
        assert spec.category == "quality"
        assert spec.sources == ()

    def test_full_spec_with_sources(self) -> None:
        config = parse_evals_config({
            "evaluators": {
                "reservation-quality": {
                    "type": "foundry.generated_rubric",
                    "category": "quality",
                    "model": "gpt-4o",
                    "agent": "reservation-agent",
                    "display_name": "Reservation Quality",
                    "description": "Custom rubric for reservation agent.",
                    "sources": [
                        {
                            "type": "agent",
                            "include_instructions": True,
                            "include_tools": True,
                            "include_context_providers": True,
                        },
                        {
                            "type": "dataset",
                            "name": "reservation-business-rules",
                            "version": 1,
                        },
                    ],
                }
            }
        })
        spec = config["reservation-quality"]
        assert spec.model == "gpt-4o"
        assert spec.agent == "reservation-agent"
        assert spec.display_name == "Reservation Quality"
        assert len(spec.sources) == 2

        agent_src = spec.sources[0]
        assert agent_src.type == "agent"
        assert agent_src.include_context_providers is True

        dataset_src = spec.sources[1]
        assert dataset_src.type == "dataset"
        assert dataset_src.name == "reservation-business-rules"
        assert dataset_src.version == "1"  # coerced to string

    def test_rejects_non_mapping(self) -> None:
        with pytest.raises(ValueError, match="must be a mapping"):
            parse_evals_config([])

    def test_rejects_missing_evaluators_key(self) -> None:
        with pytest.raises(ValueError, match="evaluators"):
            parse_evals_config({"other": {}})

    def test_rejects_unknown_type(self) -> None:
        with pytest.raises(ValueError, match="unsupported type"):
            parse_evals_config({"evaluators": {"x": {"type": "foundry.other"}}})

    def test_rejects_invalid_category(self) -> None:
        with pytest.raises(ValueError, match="invalid category"):
            parse_evals_config({"evaluators": {"x": {"type": "foundry.generated_rubric", "category": "bogus"}}})

    def test_rejects_invalid_source_type(self) -> None:
        with pytest.raises(ValueError, match="invalid type"):
            parse_evals_config({
                "evaluators": {
                    "x": {
                        "type": "foundry.generated_rubric",
                        "sources": [{"type": "bogus"}],
                    }
                }
            })


class TestLoadEvalsConfig:
    """End-to-end YAML loading."""

    def test_load_from_yaml_file(self, tmp_path: Path) -> None:
        pytest.importorskip("yaml")
        config_path = tmp_path / "evals.yaml"
        config_path.write_text(
            textwrap.dedent(
                """\
                evaluators:
                  my-eval:
                    type: foundry.generated_rubric
                    category: safety
                    model: gpt-4o-mini
                    sources:
                      - type: prompt
                        prompt: "Score the response."
                """
            ),
            encoding="utf-8",
        )
        config = load_evals_config(config_path)
        assert "my-eval" in config
        spec = config["my-eval"]
        assert spec.category == "safety"
        assert spec.model == "gpt-4o-mini"
        assert len(spec.sources) == 1
        assert spec.sources[0].type == "prompt"
        assert spec.sources[0].prompt == "Score the response."


class TestBuildSources:
    """Translate RubricGenerationSpec sources into EvalGenerationSource instances."""

    def test_no_sources_with_agent_default(self) -> None:
        spec = RubricGenerationSpec(name="x")
        agent = _make_agent()
        sources = build_sources(spec, agent=agent)
        assert len(sources) == 1
        assert sources[0].type == "prompt"
        assert sources[0].prompt is not None
        assert "Agent name: agent-a" in sources[0].prompt

    def test_no_sources_with_workflow_default(self) -> None:
        spec = RubricGenerationSpec(name="x")
        workflow = _make_workflow()
        sources = build_sources(spec, workflow=workflow)
        assert len(sources) == 1
        assert sources[0].type == "prompt"
        assert sources[0].prompt is not None
        assert "Workflow name: wf-1" in sources[0].prompt

    def test_no_sources_no_agent_or_workflow_raises(self) -> None:
        spec = RubricGenerationSpec(name="x")
        with pytest.raises(ValueError, match="no sources"):
            build_sources(spec)

    def test_agent_source_uses_supplied_agent(self) -> None:
        spec = RubricGenerationSpec(
            name="x",
            sources=(RubricSourceSpec(type="agent", include_context_providers=True),),
        )
        agent = _make_agent()
        sources = build_sources(spec, agent=agent)
        assert sources[0].type == "prompt"
        assert sources[0].prompt is not None
        assert "Agent name: agent-a" in sources[0].prompt

    def test_agent_source_with_agent_name_uses_hosted_path(self) -> None:
        spec = RubricGenerationSpec(
            name="x",
            sources=(RubricSourceSpec(type="agent", agent_name="hosted-foundry-agent"),),
        )
        sources = build_sources(spec)
        assert sources[0].type == "agent"
        assert sources[0].agent_name == "hosted-foundry-agent"

    def test_agent_source_without_agent_raises(self) -> None:
        spec = RubricGenerationSpec(
            name="x",
            sources=(RubricSourceSpec(type="agent"),),
        )
        with pytest.raises(ValueError, match="no agent="):
            build_sources(spec)

    def test_workflow_source_uses_supplied_workflow(self) -> None:
        spec = RubricGenerationSpec(
            name="x",
            sources=(RubricSourceSpec(type="workflow", include_topology=False),),
        )
        workflow = _make_workflow()
        sources = build_sources(spec, workflow=workflow)
        assert sources[0].type == "prompt"
        assert sources[0].prompt is not None
        assert "Workflow name: wf-1" in sources[0].prompt
        assert "Topology (JSON):" not in sources[0].prompt

    def test_prompt_source_translates_directly(self) -> None:
        spec = RubricGenerationSpec(
            name="x",
            sources=(RubricSourceSpec(type="prompt", prompt="Score it."),),
        )
        sources = build_sources(spec)
        assert sources[0] == EvalGenerationSource(type="prompt", prompt="Score it.")

    def test_dataset_source_translates(self) -> None:
        spec = RubricGenerationSpec(
            name="x",
            sources=(RubricSourceSpec(type="dataset", name="ds", version="2"),),
        )
        sources = build_sources(spec)
        assert sources[0].type == "dataset"
        assert sources[0].dataset_name == "ds"
        assert sources[0].dataset_version == "2"

    def test_traces_source_passes_metadata(self) -> None:
        spec = RubricGenerationSpec(
            name="x",
            sources=(RubricSourceSpec(type="traces", metadata={"environment": "prod"}),),
        )
        sources = build_sources(spec)
        assert sources[0].type == "traces"
        assert sources[0].metadata == {"environment": "prod"}
