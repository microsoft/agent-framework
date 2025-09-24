# Copyright (c) Microsoft. All rights reserved.

import json
from typing import Any

import pytest

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from agent_framework._workflow._edge import (
    Case,
    Default,
    Edge,
    FanInEdgeGroup,
    FanOutEdgeGroup,
    SingleEdgeGroup,
    SwitchCaseEdgeGroup,
    SwitchCaseEdgeGroupCase,
    SwitchCaseEdgeGroupDefault,
)
from agent_framework._workflow._workflow_executor import (
    WorkflowExecutor,
)


class SampleExecutor(Executor):
    """Sample executor for serialization testing."""

    @handler
    async def handle_str(self, message: str, ctx: WorkflowContext[str]) -> None:
        """Handle string messages."""
        await ctx.send_message(f"Processed: {message}")


class SampleAggregator(Executor):
    """Sample aggregator executor that can handle lists of messages."""

    @handler
    async def handle_str_list(self, messages: list[str], ctx: WorkflowContext[str]) -> None:
        """Handle list of string messages for fan-in aggregation."""
        combined = " | ".join(messages)
        await ctx.send_message(f"Aggregated: {combined}")


class TestSerializationWorkflowClasses:
    """Test serialization of workflow classes."""

    def test_executor_serialization(self) -> None:
        """Test that Executor can be serialized and has correct fields, including type."""
        executor = SampleExecutor(id="test-executor")

        # Test model_dump
        data = executor.model_dump(by_alias=True)
        assert data["id"] == "test-executor"

        # Test type field
        assert "type" in data, "Executor should have 'type' field"
        assert data["type"] == "SampleExecutor", f"Expected type 'SampleExecutor', got {data['type']}"

        # Test model_dump_json
        json_str = executor.model_dump_json(by_alias=True)
        parsed = json.loads(json_str)
        assert parsed["id"] == "test-executor"

        # Test type field in JSON
        assert "type" in parsed, "JSON should have 'type' field"
        assert parsed["type"] == "SampleExecutor", "JSON should preserve type field"

    def test_edge_serialization(self) -> None:
        """Test that Edge can be serialized and has correct fields."""
        # Test edge without condition
        edge = Edge(source_id="source", target_id="target")

        # Test model_dump
        data = edge.model_dump()
        assert data["source_id"] == "source"
        assert data["target_id"] == "target"
        assert "condition_name" not in data or data["condition_name"] is None

        # Test model_dump_json
        json_str = edge.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["source_id"] == "source"
        assert parsed["target_id"] == "target"
        assert "condition_name" not in parsed or parsed["condition_name"] is None

    def test_edge_serialization_with_named_condition(self) -> None:
        """Test that Edge with named function condition serializes condition_name correctly."""

        def is_positive(x: int) -> bool:
            return x > 0

        edge = Edge(source_id="source", target_id="target", condition=is_positive)

        # Test model_dump
        data = edge.model_dump()
        assert data["source_id"] == "source"
        assert data["target_id"] == "target"
        assert data["condition_name"] == "is_positive"

        # Test model_dump_json
        json_str = edge.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["source_id"] == "source"
        assert parsed["target_id"] == "target"
        assert parsed["condition_name"] == "is_positive"

    def test_edge_serialization_with_lambda_condition(self) -> None:
        """Test that Edge with lambda condition serializes condition_name as '<lambda>'."""
        edge = Edge(source_id="source", target_id="target", condition=lambda x: x > 0)

        # Test model_dump
        data = edge.model_dump()
        assert data["source_id"] == "source"
        assert data["target_id"] == "target"
        assert data["condition_name"] == "<lambda>"

        # Test model_dump_json
        json_str = edge.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["source_id"] == "source"
        assert parsed["target_id"] == "target"
        assert parsed["condition_name"] == "<lambda>"

    def test_single_edge_group_serialization(self) -> None:
        """Test that SingleEdgeGroup can be serialized and has correct fields, including edges and type."""
        edge_group = SingleEdgeGroup(source_id="source", target_id="target")

        # Test model_dump
        data = edge_group.model_dump(by_alias=True)
        assert "id" in data
        assert data["id"].startswith("SingleEdgeGroup/")

        # Test type field
        assert "type" in data, "SingleEdgeGroup should have 'type' field"
        assert data["type"] == "SingleEdgeGroup", f"Expected type 'SingleEdgeGroup', got {data['type']}"

        # Verify edges field is present and contains the edge
        assert "edges" in data, "SingleEdgeGroup should have 'edges' field"
        assert len(data["edges"]) == 1, "SingleEdgeGroup should have exactly one edge"
        edge = data["edges"][0]
        assert "source_id" in edge, "Edge should have source_id"
        assert "target_id" in edge, "Edge should have target_id"
        assert edge["source_id"] == "source", f"Expected source_id 'source', got {edge['source_id']}"
        assert edge["target_id"] == "target", f"Expected target_id 'target', got {edge['target_id']}"

        # Test model_dump_json
        json_str = edge_group.model_dump_json()
        parsed = json.loads(json_str)
        assert "id" in parsed
        assert parsed["id"].startswith("SingleEdgeGroup/")

        # Test type field in JSON
        assert "type" in parsed, "JSON should have 'type' field"
        assert parsed["type"] == "SingleEdgeGroup", "JSON should preserve type field"

        # Verify edges are preserved in JSON
        assert "edges" in parsed, "JSON should have 'edges' field"
        assert len(parsed["edges"]) == 1, "JSON should have exactly one edge"
        json_edge = parsed["edges"][0]
        assert json_edge["source_id"] == "source", "JSON should preserve edge source_id"
        assert json_edge["target_id"] == "target", "JSON should preserve edge target_id"

    def test_fan_out_edge_group_serialization(self) -> None:
        """Test that FanOutEdgeGroup can be serialized and has correct fields, including edges and type."""
        edge_group = FanOutEdgeGroup(source_id="source", target_ids=["target1", "target2"])

        # Test model_dump
        data = edge_group.model_dump()
        assert "id" in data
        assert data["id"].startswith("FanOutEdgeGroup/")

        # Test type field
        assert "type" in data, "FanOutEdgeGroup should have 'type' field"
        assert data["type"] == "FanOutEdgeGroup", f"Expected type 'FanOutEdgeGroup', got {data['type']}"

        # Test selection_func_name field (should be None when no selection function is provided)
        assert "selection_func_name" in data, "FanOutEdgeGroup should have 'selection_func_name' field"
        assert data["selection_func_name"] is None, (
            "selection_func_name should be None when no selection function is provided"
        )

        # Verify edges field is present and contains the correct edges
        assert "edges" in data, "FanOutEdgeGroup should have 'edges' field"
        assert len(data["edges"]) == 2, "FanOutEdgeGroup should have exactly two edges"

        edges = data["edges"]
        sources = [edge["source_id"] for edge in edges]
        targets = [edge["target_id"] for edge in edges]

        assert all(source == "source" for source in sources), f"All edges should have source 'source', got {sources}"
        assert set(targets) == {"target1", "target2"}, f"Expected targets {{'target1', 'target2'}}, got {set(targets)}"

        # Test model_dump_json
        json_str = edge_group.model_dump_json()
        parsed = json.loads(json_str)
        assert "id" in parsed
        assert parsed["id"].startswith("FanOutEdgeGroup/")

        # Test type field in JSON
        assert "type" in parsed, "JSON should have 'type' field"
        assert parsed["type"] == "FanOutEdgeGroup", "JSON should preserve type field"

        # Test selection_func_name field in JSON
        assert "selection_func_name" in parsed, "JSON should have 'selection_func_name' field"
        assert parsed["selection_func_name"] is None, (
            "JSON selection_func_name should be None when no selection function is provided"
        )

        # Verify edges are preserved in JSON
        assert "edges" in parsed, "JSON should have 'edges' field"
        assert len(parsed["edges"]) == 2, "JSON should have exactly two edges"
        json_edges = parsed["edges"]
        json_sources = [edge["source_id"] for edge in json_edges]
        json_targets = [edge["target_id"] for edge in json_edges]

        assert all(source == "source" for source in json_sources), "JSON should preserve edge sources"
        assert set(json_targets) == {"target1", "target2"}, "JSON should preserve edge targets"

    def test_fan_out_edge_group_serialization_with_selection_func(self) -> None:
        """Test that FanOutEdgeGroup with named selection function serializes selection_func_name correctly."""

        def custom_selector(data: Any, targets: list[str]) -> list[str]:
            """Custom selection function for testing."""
            return targets[:1]  # Select only the first target

        edge_group = FanOutEdgeGroup(
            source_id="source", target_ids=["target1", "target2"], selection_func=custom_selector
        )

        # Test model_dump
        data = edge_group.model_dump()
        assert "selection_func_name" in data, "FanOutEdgeGroup should have 'selection_func_name' field"
        assert data["selection_func_name"] == "custom_selector", (
            f"Expected selection_func_name 'custom_selector', got {data['selection_func_name']}"
        )

        # Test model_dump_json
        json_str = edge_group.model_dump_json()
        parsed = json.loads(json_str)
        assert "selection_func_name" in parsed, "JSON should have 'selection_func_name' field"
        assert parsed["selection_func_name"] == "custom_selector", "JSON should preserve selection_func_name"

    def test_fan_out_edge_group_serialization_with_lambda_selection_func(self) -> None:
        """Test that FanOutEdgeGroup with lambda selection function serializes selection_func_name as '<lambda>'."""
        edge_group = FanOutEdgeGroup(
            source_id="source", target_ids=["target1", "target2"], selection_func=lambda data, targets: targets[:1]
        )

        # Test model_dump
        data = edge_group.model_dump()
        assert "selection_func_name" in data, "FanOutEdgeGroup should have 'selection_func_name' field"
        assert data["selection_func_name"] == "<lambda>", (
            f"Expected selection_func_name '<lambda>', got {data['selection_func_name']}"
        )

        # Test model_dump_json
        json_str = edge_group.model_dump_json()
        parsed = json.loads(json_str)
        assert "selection_func_name" in parsed, "JSON should have 'selection_func_name' field"
        assert parsed["selection_func_name"] == "<lambda>", "JSON should preserve selection_func_name as '<lambda>'"

    def test_fan_in_edge_group_serialization(self) -> None:
        """Test that FanInEdgeGroup can be serialized and has correct fields, including edges and type."""
        edge_group = FanInEdgeGroup(source_ids=["source1", "source2"], target_id="target")

        # Test model_dump
        data = edge_group.model_dump()
        assert "id" in data
        assert data["id"].startswith("FanInEdgeGroup/")

        # Test type field
        assert "type" in data, "FanInEdgeGroup should have 'type' field"
        assert data["type"] == "FanInEdgeGroup", f"Expected type 'FanInEdgeGroup', got {data['type']}"

        # Verify edges field is present and contains the correct edges
        assert "edges" in data, "FanInEdgeGroup should have 'edges' field"
        assert len(data["edges"]) == 2, "FanInEdgeGroup should have exactly two edges"

        edges = data["edges"]
        sources = [edge["source_id"] for edge in edges]
        targets = [edge["target_id"] for edge in edges]

        assert set(sources) == {"source1", "source2"}, f"Expected sources {{'source1', 'source2'}}, got {set(sources)}"
        assert all(target == "target" for target in targets), f"All edges should have target 'target', got {targets}"

        # Test model_dump_json
        json_str = edge_group.model_dump_json()
        parsed = json.loads(json_str)
        assert "id" in parsed
        assert parsed["id"].startswith("FanInEdgeGroup/")

        # Test type field in JSON
        assert "type" in parsed, "JSON should have 'type' field"
        assert parsed["type"] == "FanInEdgeGroup", "JSON should preserve type field"

        # Verify edges are preserved in JSON
        assert "edges" in parsed, "JSON should have 'edges' field"
        assert len(parsed["edges"]) == 2, "JSON should have exactly two edges"
        json_edges = parsed["edges"]
        json_sources = [edge["source_id"] for edge in json_edges]
        json_targets = [edge["target_id"] for edge in json_edges]

        assert set(json_sources) == {"source1", "source2"}, "JSON should preserve edge sources"
        assert all(target == "target" for target in json_targets), "JSON should preserve edge targets"

    def test_switch_case_edge_group_serialization(self) -> None:
        """Test that SwitchCaseEdgeGroup can be serialized and has correct fields, including edges and type."""
        cases = [
            SwitchCaseEdgeGroupCase(condition=lambda x: x > 0, target_id="positive"),
            SwitchCaseEdgeGroupDefault(target_id="default"),
        ]
        edge_group = SwitchCaseEdgeGroup(source_id="source", cases=cases)

        # Test model_dump
        data = edge_group.model_dump()
        assert "id" in data
        assert data["id"].startswith("SwitchCaseEdgeGroup/")

        # Test type field
        assert "type" in data, "SwitchCaseEdgeGroup should have 'type' field"
        assert data["type"] == "SwitchCaseEdgeGroup", f"Expected type 'SwitchCaseEdgeGroup', got {data['type']}"

        # Test cases field
        assert "cases" in data, "SwitchCaseEdgeGroup should have 'cases' field"
        assert len(data["cases"]) == 2, "SwitchCaseEdgeGroup should have exactly two cases"

        cases_data = data["cases"]
        # Check first case (SwitchCaseEdgeGroupCase)
        case_obj = cases_data[0]
        assert "target_id" in case_obj, "SwitchCaseEdgeGroupCase should have 'target_id' field"
        assert "condition_name" in case_obj, "SwitchCaseEdgeGroupCase should have 'condition_name' field"
        assert "type" in case_obj, "SwitchCaseEdgeGroupCase should have 'type' field"
        assert case_obj["target_id"] == "positive", f"Expected target_id 'positive', got {case_obj['target_id']}"
        assert case_obj["condition_name"] == "<lambda>", (
            f"Expected condition_name '<lambda>', got {case_obj['condition_name']}"
        )
        assert case_obj["type"] == "Case", f"Expected type 'Case', got {case_obj['type']}"

        # Check default case (SwitchCaseEdgeGroupDefault)
        default_obj = cases_data[1]
        assert "target_id" in default_obj, "SwitchCaseEdgeGroupDefault should have 'target_id' field"
        assert "type" in default_obj, "SwitchCaseEdgeGroupDefault should have 'type' field"
        assert default_obj["target_id"] == "default", f"Expected target_id 'default', got {default_obj['target_id']}"
        assert default_obj["type"] == "Default", f"Expected type 'Default', got {default_obj['type']}"

        # Verify edges field is present and contains the correct edges
        assert "edges" in data, "SwitchCaseEdgeGroup should have 'edges' field"
        assert len(data["edges"]) == 2, "SwitchCaseEdgeGroup should have exactly two edges"

        edges = data["edges"]
        sources = [edge["source_id"] for edge in edges]
        targets = [edge["target_id"] for edge in edges]

        assert all(source == "source" for source in sources), f"All edges should have source 'source', got {sources}"
        assert set(targets) == {"positive", "default"}, (
            f"Expected targets {{'positive', 'default'}}, got {set(targets)}"
        )

        # Check condition_name field in edges - SwitchCaseEdgeGroup edges don't have conditions
        # because the conditional logic is implemented in the selection_func at the group level
        condition_names = [edge.get("condition_name") for edge in edges]
        assert all(name is None for name in condition_names), (
            "SwitchCaseEdgeGroup edges should not have condition_name since conditions are handled at group level"
        )

        # Test model_dump_json
        json_str = edge_group.model_dump_json()
        parsed = json.loads(json_str)
        assert "id" in parsed
        assert parsed["id"].startswith("SwitchCaseEdgeGroup/")

        # Test type field in JSON
        assert "type" in parsed, "JSON should have 'type' field"
        assert parsed["type"] == "SwitchCaseEdgeGroup", "JSON should preserve type field"

        # Test cases field in JSON
        assert "cases" in parsed, "JSON should have 'cases' field"
        assert len(parsed["cases"]) == 2, "JSON should have exactly two cases"

        json_cases = parsed["cases"]
        json_case_obj = json_cases[0]
        assert json_case_obj["target_id"] == "positive", "JSON should preserve case target_id"
        assert json_case_obj["condition_name"] == "<lambda>", "JSON should preserve case condition_name"
        assert json_case_obj["type"] == "Case", "JSON should preserve case type"

        json_default_obj = json_cases[1]
        assert json_default_obj["target_id"] == "default", "JSON should preserve default target_id"
        assert json_default_obj["type"] == "Default", "JSON should preserve default type"

        # Verify edges are preserved in JSON
        assert "edges" in parsed, "JSON should have 'edges' field"
        assert len(parsed["edges"]) == 2, "JSON should have exactly two edges"
        json_edges = parsed["edges"]
        json_sources = [edge["source_id"] for edge in json_edges]
        json_targets = [edge["target_id"] for edge in json_edges]

        assert all(source == "source" for source in json_sources), "JSON should preserve edge sources"
        assert set(json_targets) == {"positive", "default"}, "JSON should preserve edge targets"

        # Check condition_name field in JSON edges - should be None for SwitchCaseEdgeGroup
        json_condition_names = [edge.get("condition_name") for edge in json_edges]
        assert all(name is None for name in json_condition_names), (
            "JSON SwitchCaseEdgeGroup edges should not have condition_name"
        )

    def test_nested_workflow_executor_serialization(self) -> None:
        """Test complete serialization of deeply nested WorkflowExecutors (subworkflows within subworkflows).

        This test verifies that nested WorkflowExecutor objects are fully serialized with their
        complete workflow structures, including deeply nested workflows and all their executors.
        """
        # Create innermost workflow
        inner_executor = SampleExecutor(id="inner-exec")
        inner_workflow = WorkflowBuilder().set_start_executor(inner_executor).set_max_iterations(10).build()

        # Create middle workflow with WorkflowExecutor
        inner_workflow_executor = WorkflowExecutor(workflow=inner_workflow, id="inner-workflow-exec")
        middle_executor = SampleExecutor(id="middle-exec")
        middle_workflow = (
            WorkflowBuilder()
            .set_start_executor(middle_executor)
            .add_edge(middle_executor, inner_workflow_executor)
            .set_max_iterations(20)
            .build()
        )

        # Create outer workflow with nested WorkflowExecutor
        middle_workflow_executor = WorkflowExecutor(workflow=middle_workflow, id="middle-workflow-exec")
        outer_executor = SampleExecutor(id="outer-exec")
        outer_workflow = (
            WorkflowBuilder()
            .set_start_executor(outer_executor)
            .add_edge(outer_executor, middle_workflow_executor)
            .set_max_iterations(30)
            .build()
        )

        # Test serialization of the nested structure
        data = outer_workflow.model_dump(by_alias=True)

        # Verify outer structure
        assert data["start_executor_id"] == "outer-exec"
        assert data["max_iterations"] == 30
        assert "outer-exec" in data["executors"]
        assert "middle-workflow-exec" in data["executors"]

        # Verify middle WorkflowExecutor is present with full nested workflow serialization
        middle_exec_data = data["executors"]["middle-workflow-exec"]
        assert middle_exec_data["type"] == "WorkflowExecutor"
        assert middle_exec_data["id"] == "middle-workflow-exec"

        # Verify the nested workflow is fully serialized
        assert "workflow" in middle_exec_data, "WorkflowExecutor should include nested workflow in serialization"
        middle_workflow_data = middle_exec_data["workflow"]
        assert "start_executor_id" in middle_workflow_data
        assert "executors" in middle_workflow_data
        assert "max_iterations" in middle_workflow_data
        assert middle_workflow_data["start_executor_id"] == "middle-exec"
        assert middle_workflow_data["max_iterations"] == 20

        # Verify the deeply nested executors are present
        assert "middle-exec" in middle_workflow_data["executors"]
        assert "inner-workflow-exec" in middle_workflow_data["executors"]

        # Verify the innermost WorkflowExecutor is also fully serialized
        inner_workflow_exec_data = middle_workflow_data["executors"]["inner-workflow-exec"]
        assert inner_workflow_exec_data["type"] == "WorkflowExecutor"
        assert "workflow" in inner_workflow_exec_data, "Deeply nested WorkflowExecutor should also include its workflow"
        innermost_workflow_data = inner_workflow_exec_data["workflow"]
        assert "start_executor_id" in innermost_workflow_data
        assert "executors" in innermost_workflow_data
        assert "max_iterations" in innermost_workflow_data
        assert innermost_workflow_data["start_executor_id"] == "inner-exec"
        assert innermost_workflow_data["max_iterations"] == 10
        assert "inner-exec" in innermost_workflow_data["executors"]

        # Test JSON serialization preserves the complete nested structure
        json_str = outer_workflow.model_dump_json(by_alias=True)
        parsed = json.loads(json_str)

        # Verify the complete structure is preserved in JSON
        middle_exec_json = parsed["executors"]["middle-workflow-exec"]
        assert middle_exec_json["type"] == "WorkflowExecutor"
        assert middle_exec_json["id"] == "middle-workflow-exec"

        # Verify nested workflow is present in JSON
        assert "workflow" in middle_exec_json, "JSON serialization should include nested workflow"
        middle_workflow_json = middle_exec_json["workflow"]
        assert middle_workflow_json["start_executor_id"] == "middle-exec"
        assert middle_workflow_json["max_iterations"] == 20
        assert "middle-exec" in middle_workflow_json["executors"]
        assert "inner-workflow-exec" in middle_workflow_json["executors"]

        # Verify deeply nested structure in JSON
        inner_workflow_exec_json = middle_workflow_json["executors"]["inner-workflow-exec"]
        assert inner_workflow_exec_json["type"] == "WorkflowExecutor"
        assert "workflow" in inner_workflow_exec_json, "Deeply nested WorkflowExecutor should be in JSON"
        innermost_workflow_json = inner_workflow_exec_json["workflow"]
        assert innermost_workflow_json["start_executor_id"] == "inner-exec"
        assert innermost_workflow_json["max_iterations"] == 10
        assert "inner-exec" in innermost_workflow_json["executors"]

        # Test that WorkflowExecutor also serializes correctly when accessed directly
        direct_middle_data = middle_workflow_executor.model_dump(by_alias=True)
        assert "workflow" in direct_middle_data
        assert direct_middle_data["type"] == "WorkflowExecutor"
        assert "executors" in direct_middle_data["workflow"]
        assert "inner-workflow-exec" in direct_middle_data["workflow"]["executors"]

    def test_switch_case_edge_group_serialization_with_named_condition(self) -> None:
        """Test that SwitchCaseEdgeGroup with named condition function serializes condition_name correctly."""

        def is_positive(x: int) -> bool:
            return x > 0

        cases = [
            SwitchCaseEdgeGroupCase(condition=is_positive, target_id="positive"),
            SwitchCaseEdgeGroupDefault(target_id="default"),
        ]
        edge_group = SwitchCaseEdgeGroup(source_id="source", cases=cases)

        # Test model_dump
        data = edge_group.model_dump()
        assert "cases" in data, "SwitchCaseEdgeGroup should have 'cases' field"

        cases_data = data["cases"]
        case_obj = cases_data[0]
        assert case_obj["condition_name"] == "is_positive", (
            f"Expected condition_name 'is_positive', got {case_obj['condition_name']}"
        )

        # Test model_dump_json
        json_str = edge_group.model_dump_json()
        parsed = json.loads(json_str)
        json_cases = parsed["cases"]
        json_case_obj = json_cases[0]
        assert json_case_obj["condition_name"] == "is_positive", "JSON should preserve named condition_name"

    def test_workflow_serialization(self) -> None:
        """Test that Workflow can be serialized and has correct fields, including edges."""
        executor1 = SampleExecutor(id="executor1")
        executor2 = SampleExecutor(id="executor2")

        workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

        # Test model_dump
        data = workflow.model_dump()
        assert "edge_groups" in data
        assert "executors" in data
        assert "start_executor_id" in data
        assert "max_iterations" in data
        assert "id" in data

        assert data["start_executor_id"] == "executor1"
        assert "executor1" in data["executors"]
        assert "executor2" in data["executors"]

        # Verify edge groups contain edges
        edge_groups = data["edge_groups"]
        assert len(edge_groups) == 1, "Should have exactly one edge group"
        edge_group = edge_groups[0]
        assert "edges" in edge_group, "Edge group should contain 'edges' field"
        assert len(edge_group["edges"]) == 1, "Should have exactly one edge"

        edge = edge_group["edges"][0]
        assert "source_id" in edge, "Edge should have source_id"
        assert "target_id" in edge, "Edge should have target_id"
        assert edge["source_id"] == "executor1", f"Expected source_id 'executor1', got {edge['source_id']}"
        assert edge["target_id"] == "executor2", f"Expected target_id 'executor2', got {edge['target_id']}"

        # Test model_dump_json
        json_str = workflow.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["start_executor_id"] == "executor1"
        assert "executor1" in parsed["executors"]
        assert "executor2" in parsed["executors"]

        # Verify edges are preserved in JSON serialization
        json_edge_groups = parsed["edge_groups"]
        assert len(json_edge_groups) == 1, "JSON should have exactly one edge group"
        json_edge_group = json_edge_groups[0]
        assert "edges" in json_edge_group, "JSON edge group should contain 'edges' field"
        json_edge = json_edge_group["edges"][0]
        assert json_edge["source_id"] == "executor1", "JSON should preserve edge source_id"
        assert json_edge["target_id"] == "executor2", "JSON should preserve edge target_id"

    def test_workflow_serialization_excludes_non_serializable_fields(self) -> None:
        """Test that non-serializable fields are excluded from serialization."""
        executor1 = SampleExecutor(id="executor1")
        executor2 = SampleExecutor(id="executor2")

        workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

        # Test model_dump - should not include private runtime objects
        data = workflow.model_dump()

        # These private runtime fields should not be in the serialized data
        assert "_runner_context" not in data
        assert "_shared_state" not in data
        assert "_runner" not in data

    def test_executor_field_validation(self) -> None:
        """Test that Executor field validation works correctly."""
        # Valid executor
        executor = SampleExecutor(id="valid-id")
        assert executor.id == "valid-id"

        with pytest.raises(ValueError):
            SampleExecutor(id="")

    def test_edge_field_validation(self) -> None:
        """Test that Edge field validation works correctly."""
        # Valid edge
        edge = Edge(source_id="source", target_id="target")
        assert edge.source_id == "source"
        assert edge.target_id == "target"

        # Test validation failure for empty source_id
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            Edge(source_id="", target_id="target")

        # Test validation failure for empty target_id
        with pytest.raises(ValidationError):
            Edge(source_id="source", target_id="")


def test_comprehensive_edge_groups_workflow_serialization() -> None:
    """Test serialization of a workflow that uses all edge group types: SwitchCase, FanOut, and FanIn."""
    # Create executors for a comprehensive workflow
    router = SampleExecutor(id="router")
    processor_a = SampleExecutor(id="proc_a")
    processor_b = SampleExecutor(id="proc_b")
    fanout_hub = SampleExecutor(id="fanout_hub")
    parallel_1 = SampleExecutor(id="parallel_1")
    parallel_2 = SampleExecutor(id="parallel_2")
    aggregator = SampleAggregator(id="aggregator")

    # Build workflow with all three edge group types
    workflow = (
        WorkflowBuilder()
        .set_start_executor(router)
        # 1. SwitchCaseEdgeGroup: Conditional routing
        .add_switch_case_edge_group(
            router,
            [
                Case(condition=lambda msg: len(str(msg)) < 10, target=processor_a),
                Default(target=processor_b),
            ],
        )
        # 2. Direct edges
        .add_edge(processor_a, fanout_hub)
        .add_edge(processor_b, fanout_hub)
        # 3. FanOutEdgeGroup: One-to-many distribution
        .add_fan_out_edges(fanout_hub, [parallel_1, parallel_2])
        # 4. FanInEdgeGroup: Many-to-one aggregation
        .add_fan_in_edges([parallel_1, parallel_2], aggregator)
        .build()
    )

    # Test workflow serialization
    data = workflow.model_dump()

    # Verify basic workflow structure
    assert "edge_groups" in data
    assert "executors" in data
    assert "start_executor_id" in data
    assert data["start_executor_id"] == "router"

    # Verify all executors are present
    expected_executors = {"router", "proc_a", "proc_b", "fanout_hub", "parallel_1", "parallel_2", "aggregator"}
    assert set(data["executors"].keys()) == expected_executors

    # Verify edge groups contain all three types
    edge_groups = data["edge_groups"]
    edge_group_types = [eg.get("id", "").split("/")[0] for eg in edge_groups]

    # Should have: SwitchCaseEdgeGroup, SingleEdgeGroup (x2), FanOutEdgeGroup, FanInEdgeGroup
    assert "SwitchCaseEdgeGroup" in edge_group_types, f"Expected SwitchCaseEdgeGroup in {edge_group_types}"
    assert "FanOutEdgeGroup" in edge_group_types, f"Expected FanOutEdgeGroup in {edge_group_types}"
    assert "FanInEdgeGroup" in edge_group_types, f"Expected FanInEdgeGroup in {edge_group_types}"
    assert "SingleEdgeGroup" in edge_group_types, f"Expected SingleEdgeGroup in {edge_group_types}"

    # Test JSON serialization
    json_str = workflow.model_dump_json()
    parsed = json.loads(json_str)

    # Verify JSON structure matches model_dump
    assert parsed["start_executor_id"] == "router"
    assert set(parsed["executors"].keys()) == expected_executors
    assert len(parsed["edge_groups"]) == len(edge_groups)

    # Verify that serialization excludes non-serializable fields
    assert "_runner_context" not in data
    assert "_shared_state" not in data
    assert "_runner" not in data

    # Test that we can identify each edge group type by examining their structure
    switch_case_groups = [eg for eg in edge_groups if eg.get("id", "").startswith("SwitchCaseEdgeGroup/")]
    fan_out_groups = [eg for eg in edge_groups if eg.get("id", "").startswith("FanOutEdgeGroup/")]
    fan_in_groups = [eg for eg in edge_groups if eg.get("id", "").startswith("FanInEdgeGroup/")]
    single_groups = [eg for eg in edge_groups if eg.get("id", "").startswith("SingleEdgeGroup/")]

    assert len(switch_case_groups) == 1, f"Expected 1 SwitchCaseEdgeGroup, got {len(switch_case_groups)}"
    assert len(fan_out_groups) == 1, f"Expected 1 FanOutEdgeGroup, got {len(fan_out_groups)}"
    assert len(fan_in_groups) == 1, f"Expected 1 FanInEdgeGroup, got {len(fan_in_groups)}"
    assert len(single_groups) == 2, f"Expected 2 SingleEdgeGroups, got {len(single_groups)}"

    # The key validation is that all edge group types are present and serializable
    # Individual edge group fields may vary based on implementation,
    # but each should have at least an 'id' field that identifies its type and 'edges' field
    for group_type, groups in [
        ("SwitchCaseEdgeGroup", switch_case_groups),
        ("FanOutEdgeGroup", fan_out_groups),
        ("FanInEdgeGroup", fan_in_groups),
        ("SingleEdgeGroup", single_groups),
    ]:
        for group in groups:
            assert "id" in group, f"{group_type} should have 'id' field"
            assert group["id"].startswith(f"{group_type}/"), f"{group_type} id should start with '{group_type}/'"
            assert "edges" in group, f"{group_type} should have 'edges' field"
            assert isinstance(group["edges"], list), f"{group_type} 'edges' should be a list"
            assert len(group["edges"]) > 0, f"{group_type} should have at least one edge"

            # Verify each edge has required fields
            for edge in group["edges"]:
                assert "source_id" in edge, f"{group_type} edge should have 'source_id'"
                assert "target_id" in edge, f"{group_type} edge should have 'target_id'"
                assert isinstance(edge["source_id"], str), f"{group_type} edge source_id should be string"
                assert isinstance(edge["target_id"], str), f"{group_type} edge target_id should be string"
                assert len(edge["source_id"]) > 0, f"{group_type} edge source_id should not be empty"
                assert len(edge["target_id"]) > 0, f"{group_type} edge target_id should not be empty"

    # Verify specific edge group edge counts
    assert len(switch_case_groups[0]["edges"]) == 2, "SwitchCaseEdgeGroup should have 2 edges (proc_a and proc_b)"
    assert len(fan_out_groups[0]["edges"]) == 2, "FanOutEdgeGroup should have 2 edges (parallel_1 and parallel_2)"
    assert len(fan_in_groups[0]["edges"]) == 2, "FanInEdgeGroup should have 2 edges (from parallel_1 and parallel_2)"
    for single_group in single_groups:
        assert len(single_group["edges"]) == 1, "Each SingleEdgeGroup should have exactly 1 edge"
