# Copyright (c) Microsoft. All rights reserved.

import json

import pytest
from agent_framework.workflow import Executor, WorkflowBuilder, WorkflowContext, handler

from agent_framework_workflow._edge import Edge, FanOutEdgeGroup, SingleEdgeGroup


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
        """Test that Executor can be serialized and has correct fields."""
        executor = SampleExecutor(id="test-executor")

        # Test model_dump
        data = executor.model_dump()
        assert data["id"] == "test-executor"

        # Test model_dump_json
        json_str = executor.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["id"] == "test-executor"

    def test_edge_serialization(self) -> None:
        """Test that Edge can be serialized and has correct fields."""
        edge = Edge(source_id="source", target_id="target")

        # Test model_dump
        data = edge.model_dump()
        assert data["source_id"] == "source"
        assert data["target_id"] == "target"

        # Test model_dump_json
        json_str = edge.model_dump_json()
        parsed = json.loads(json_str)
        assert parsed["source_id"] == "source"
        assert parsed["target_id"] == "target"

    def test_single_edge_group_serialization(self) -> None:
        """Test that SingleEdgeGroup can be serialized and has correct fields, including edges."""
        edge_group = SingleEdgeGroup(source_id="source", target_id="target")

        # Test model_dump
        data = edge_group.model_dump()
        assert "id" in data
        assert data["id"].startswith("SingleEdgeGroup/")

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

        # Verify edges are preserved in JSON
        assert "edges" in parsed, "JSON should have 'edges' field"
        assert len(parsed["edges"]) == 1, "JSON should have exactly one edge"
        json_edge = parsed["edges"][0]
        assert json_edge["source_id"] == "source", "JSON should preserve edge source_id"
        assert json_edge["target_id"] == "target", "JSON should preserve edge target_id"

    def test_fan_out_edge_group_serialization(self) -> None:
        """Test that FanOutEdgeGroup can be serialized and has correct fields, including edges."""
        edge_group = FanOutEdgeGroup(source_id="source", target_ids=["target1", "target2"])

        # Test model_dump
        data = edge_group.model_dump()
        assert "id" in data
        assert data["id"].startswith("FanOutEdgeGroup/")

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

        # Verify edges are preserved in JSON
        assert "edges" in parsed, "JSON should have 'edges' field"
        assert len(parsed["edges"]) == 2, "JSON should have exactly two edges"
        json_edges = parsed["edges"]
        json_sources = [edge["source_id"] for edge in json_edges]
        json_targets = [edge["target_id"] for edge in json_edges]

        assert all(source == "source" for source in json_sources), "JSON should preserve edge sources"
        assert set(json_targets) == {"target1", "target2"}, "JSON should preserve edge targets"

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
        assert "workflow_id" in data

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

        # Test validation failure for empty id - pydantic automatically validates min_length=1
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
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
    from agent_framework_workflow._edge import Case, Default

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
