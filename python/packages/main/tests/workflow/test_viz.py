# Copyright (c) Microsoft. All rights reserved.

"""Tests for the workflow visualization module."""

import pytest

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, WorkflowExecutor, WorkflowViz, handler


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @handler
    async def mock_handler(self, message: str, ctx: WorkflowContext) -> None:
        """A mock handler that does nothing."""
        pass


class ListStrTargetExecutor(Executor):
    """A mock executor that accepts a list of strings (for fan-in targets)."""

    @handler
    async def handle(self, message: list[str], ctx: WorkflowContext) -> None:
        pass


@pytest.fixture
def basic_sub_workflow():
    """Fixture that creates a basic sub-workflow setup for testing."""
    # Create a sub-workflow
    sub_exec1 = MockExecutor(id="sub_exec1")
    sub_exec2 = MockExecutor(id="sub_exec2")

    sub_workflow = WorkflowBuilder().add_edge(sub_exec1, sub_exec2).set_start_executor(sub_exec1).build()

    # Create a workflow executor that wraps the sub-workflow
    workflow_executor = WorkflowExecutor(sub_workflow, id="workflow_executor_1")

    # Create a main workflow that includes the workflow executor
    main_exec = MockExecutor(id="main_executor")
    final_exec = MockExecutor(id="final_executor")

    main_workflow = (
        WorkflowBuilder()
        .add_edge(main_exec, workflow_executor)
        .add_edge(workflow_executor, final_exec)
        .set_start_executor(main_exec)
        .build()
    )

    return {
        "main_workflow": main_workflow,
        "workflow_executor": workflow_executor,
        "sub_workflow": sub_workflow,
        "main_exec": main_exec,
        "final_exec": final_exec,
        "sub_exec1": sub_exec1,
        "sub_exec2": sub_exec2,
    }


def test_workflow_viz_to_digraph():
    """Test that WorkflowViz can generate a DOT digraph."""
    # Create a simple workflow
    executor1 = MockExecutor(id="executor1")
    executor2 = MockExecutor(id="executor2")

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

    viz = WorkflowViz(workflow)
    dot_content = viz.to_digraph()

    # Check that the DOT content contains expected elements
    assert "digraph Workflow {" in dot_content
    assert '"executor1"' in dot_content
    assert '"executor2"' in dot_content
    assert '"executor1" -> "executor2"' in dot_content
    assert "fillcolor=lightgreen" in dot_content  # Start executor styling
    assert "(Start)" in dot_content


def test_workflow_viz_export_dot():
    """Test exporting workflow as DOT format."""
    executor1 = MockExecutor(id="executor1")
    executor2 = MockExecutor(id="executor2")

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

    viz = WorkflowViz(workflow)

    # Test export without filename (returns temporary file path)
    file_path = viz.export(format="dot")
    assert file_path.endswith(".dot")

    with open(file_path, encoding="utf-8") as f:
        content = f.read()

    assert "digraph Workflow {" in content
    assert '"executor1" -> "executor2"' in content


def test_workflow_viz_export_dot_with_filename(tmp_path):
    """Test exporting workflow as DOT format with specified filename."""
    executor1 = MockExecutor(id="executor1")
    executor2 = MockExecutor(id="executor2")

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

    viz = WorkflowViz(workflow)

    # Test export with filename
    output_file = tmp_path / "test_workflow.dot"
    result_path = viz.export(format="dot", filename=str(output_file))

    assert result_path == str(output_file)
    assert output_file.exists()

    content = output_file.read_text(encoding="utf-8")
    assert "digraph Workflow {" in content
    assert '"executor1" -> "executor2"' in content


def test_workflow_viz_complex_workflow():
    """Test visualization of a more complex workflow."""
    executor1 = MockExecutor(id="start")
    executor2 = MockExecutor(id="middle1")
    executor3 = MockExecutor(id="middle2")
    executor4 = MockExecutor(id="end")

    workflow = (
        WorkflowBuilder()
        .add_edge(executor1, executor2)
        .add_edge(executor1, executor3)
        .add_edge(executor2, executor4)
        .add_edge(executor3, executor4)
        .set_start_executor(executor1)
        .build()
    )

    viz = WorkflowViz(workflow)
    dot_content = viz.to_digraph()

    # Check all executors are present
    assert '"start"' in dot_content
    assert '"middle1"' in dot_content
    assert '"middle2"' in dot_content
    assert '"end"' in dot_content

    # Check all edges are present
    assert '"start" -> "middle1"' in dot_content
    assert '"start" -> "middle2"' in dot_content
    assert '"middle1" -> "end"' in dot_content
    assert '"middle2" -> "end"' in dot_content

    # Check start executor has special styling
    assert "fillcolor=lightgreen" in dot_content


@pytest.mark.skipif(True, reason="Requires graphviz to be installed")
def test_workflow_viz_export_svg():
    """Test exporting workflow as SVG format. Skipped unless graphviz is available."""
    executor1 = MockExecutor(id="executor1")
    executor2 = MockExecutor(id="executor2")

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

    viz = WorkflowViz(workflow)

    try:
        file_path = viz.export(format="svg")
        assert file_path.endswith(".svg")
    except ImportError:
        pytest.skip("graphviz not available")


def test_workflow_viz_unsupported_format():
    """Test that unsupported formats raise ValueError."""
    executor1 = MockExecutor(id="executor1")
    executor2 = MockExecutor(id="executor2")

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

    viz = WorkflowViz(workflow)

    with pytest.raises(ValueError, match="Unsupported format: invalid"):
        viz.export(format="invalid")  # type: ignore


def test_workflow_viz_graphviz_binary_not_found():
    """Test that missing graphviz binary raises ImportError with helpful message."""
    import unittest.mock

    # Skip test if graphviz package is not available
    pytest.importorskip("graphviz")

    executor1 = MockExecutor(id="executor1")
    executor2 = MockExecutor(id="executor2")

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()
    viz = WorkflowViz(workflow)

    # Mock graphviz.Source.render to raise ExecutableNotFound
    with unittest.mock.patch("graphviz.Source") as mock_source_class:
        mock_source = unittest.mock.MagicMock()
        mock_source_class.return_value = mock_source

        # Import the ExecutableNotFound exception for the test
        from graphviz.backend.execute import ExecutableNotFound

        mock_source.render.side_effect = ExecutableNotFound("failed to execute PosixPath('dot')")

        # Test that the proper ImportError is raised with helpful message
        with pytest.raises(ImportError, match="The graphviz executables are not found"):
            viz.export(format="svg")


def test_workflow_viz_conditional_edge():
    """Test that conditional edges are rendered dashed with a label."""
    start = MockExecutor(id="start")
    mid = MockExecutor(id="mid")
    end = MockExecutor(id="end")

    # Condition that is never used during viz, but presence should mark the edge
    def only_if_foo(msg: str) -> bool:  # pragma: no cover - simple predicate
        return msg == "foo"

    wf = (
        WorkflowBuilder()
        .add_edge(start, mid, condition=only_if_foo)
        .add_edge(mid, end)
        .set_start_executor(start)
        .build()
    )

    dot = WorkflowViz(wf).to_digraph()

    # Conditional edge should be dashed and labeled
    assert '"start" -> "mid" [style=dashed, label="conditional"];' in dot
    # Non-conditional edge should be plain
    assert '"mid" -> "end"' in dot
    assert '"mid" -> "end" [style=dashed' not in dot


def test_workflow_viz_fan_in_edge_group():
    """Test that fan-in edges render an intermediate node with label and routed edges."""
    start = MockExecutor(id="start")
    s1 = MockExecutor(id="s1")
    s2 = MockExecutor(id="s2")
    t = ListStrTargetExecutor(id="t")

    # Build a connected workflow: start fans out to s1 and s2, which then fan-in to t
    wf = (
        WorkflowBuilder()
        .add_fan_out_edges(start, [s1, s2])
        .add_fan_in_edges([s1, s2], t)
        .set_start_executor(start)
        .build()
    )

    dot = WorkflowViz(wf).to_digraph()

    # There should be a single fan-in node with special styling and label
    lines = [line.strip() for line in dot.splitlines()]
    fan_in_lines = [line for line in lines if "shape=ellipse" in line and 'label="fan-in"' in line]
    assert len(fan_in_lines) == 1

    # Extract the intermediate node id from the line: "<id>" [shape=ellipse, ... label="fan-in"];
    fan_in_line = fan_in_lines[0]
    first_quote = fan_in_line.find('"')
    second_quote = fan_in_line.find('"', first_quote + 1)
    assert first_quote != -1 and second_quote != -1
    fan_in_node_id = fan_in_line[first_quote + 1 : second_quote]
    assert fan_in_node_id  # non-empty

    # Edges should be routed through the intermediate node, not direct to target
    assert f'"s1" -> "{fan_in_node_id}";' in dot
    assert f'"s2" -> "{fan_in_node_id}";' in dot
    assert f'"{fan_in_node_id}" -> "t";' in dot

    # Ensure direct edges are not present
    assert '"s1" -> "t"' not in dot
    assert '"s2" -> "t"' not in dot


def test_workflow_viz_to_mermaid_basic():
    """Mermaid: basic workflow nodes and edge are present with start label."""
    executor1 = MockExecutor(id="executor1")
    executor2 = MockExecutor(id="executor2")

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()
    mermaid = WorkflowViz(workflow).to_mermaid()

    # Start node and normal node
    assert 'executor1["executor1 (Start)"]' in mermaid
    assert 'executor2["executor2"]' in mermaid
    # Edge uses sanitized ids (same as ids here)
    assert "executor1 --> executor2" in mermaid


def test_workflow_viz_mermaid_conditional_edge():
    """Mermaid: conditional edges are dotted with a label."""
    start = MockExecutor(id="start")
    mid = MockExecutor(id="mid")

    def only_if_foo(msg: str) -> bool:  # pragma: no cover - simple predicate
        return msg == "foo"

    wf = WorkflowBuilder().add_edge(start, mid, condition=only_if_foo).set_start_executor(start).build()
    mermaid = WorkflowViz(wf).to_mermaid()

    assert "start -. conditional .-> mid" in mermaid


def test_workflow_viz_mermaid_fan_in_edge_group():
    """Mermaid: fan-in uses an intermediate node and routes edges via it."""
    start = MockExecutor(id="start")
    s1 = MockExecutor(id="s1")
    s2 = MockExecutor(id="s2")
    t = ListStrTargetExecutor(id="t")

    wf = (
        WorkflowBuilder()
        .add_fan_out_edges(start, [s1, s2])
        .add_fan_in_edges([s1, s2], t)
        .set_start_executor(start)
        .build()
    )

    mermaid = WorkflowViz(wf).to_mermaid()
    lines = [line.strip() for line in mermaid.splitlines()]
    # Find the fan-in node (line ends with ((fan-in)))
    fan_lines = [ln for ln in lines if ln.endswith("((fan-in))")]
    assert len(fan_lines) == 1
    fan_line = fan_lines[0]
    # fan_in node is emitted as: <id>((fan-in)) -> extract <id>
    token = fan_line.strip()
    suffix = "((fan-in))"
    assert token.endswith(suffix)
    fan_node_id = token[: -len(suffix)]
    assert fan_node_id

    # Ensure routing via the intermediate node
    assert f"s1 --> {fan_node_id}" in mermaid
    assert f"s2 --> {fan_node_id}" in mermaid
    assert f"{fan_node_id} --> t" in mermaid

    # Ensure direct edges to target are not present
    assert "s1 --> t" not in mermaid
    assert "s2 --> t" not in mermaid


def test_workflow_viz_sub_workflow_digraph(basic_sub_workflow):
    """Test that WorkflowViz can visualize sub-workflows in DOT format."""
    main_workflow = basic_sub_workflow["main_workflow"]

    viz = WorkflowViz(main_workflow)
    dot_content = viz.to_digraph()

    # Check that main workflow nodes are present
    assert "main_executor" in dot_content
    assert "workflow_executor_1" in dot_content
    assert "final_executor" in dot_content

    # Check that sub-workflow is rendered as a cluster
    assert "subgraph cluster_" in dot_content
    assert "sub-workflow: workflow_executor_1" in dot_content

    # Check that sub-workflow nodes are namespaced
    assert '"workflow_executor_1/sub_exec1"' in dot_content
    assert '"workflow_executor_1/sub_exec2"' in dot_content

    # Check that sub-workflow edges are present
    assert '"workflow_executor_1/sub_exec1" -> "workflow_executor_1/sub_exec2"' in dot_content


def test_workflow_viz_sub_workflow_mermaid(basic_sub_workflow):
    """Test that WorkflowViz can visualize sub-workflows in Mermaid format."""
    main_workflow = basic_sub_workflow["main_workflow"]

    viz = WorkflowViz(main_workflow)
    mermaid_content = viz.to_mermaid()

    # Check that main workflow nodes are present
    assert "main_executor" in mermaid_content
    assert "workflow_executor_1" in mermaid_content
    assert "final_executor" in mermaid_content

    # Check that sub-workflow is rendered as a subgraph
    assert "subgraph workflow_executor_1" in mermaid_content
    assert "end" in mermaid_content

    # Check that sub-workflow nodes are namespaced properly for Mermaid
    assert "workflow_executor_1__sub_exec1" in mermaid_content
    assert "workflow_executor_1__sub_exec2" in mermaid_content


def test_workflow_viz_nested_sub_workflows():
    """Test visualization of deeply nested sub-workflows."""
    # Create innermost sub-workflow
    inner_exec = MockExecutor(id="inner_exec")
    inner_workflow = WorkflowBuilder().set_start_executor(inner_exec).build()

    # Create middle sub-workflow that contains the inner one
    inner_workflow_executor = WorkflowExecutor(inner_workflow, id="inner_wf_exec")
    middle_exec = MockExecutor(id="middle_exec")

    middle_workflow = (
        WorkflowBuilder().add_edge(middle_exec, inner_workflow_executor).set_start_executor(middle_exec).build()
    )

    # Create outer workflow
    middle_workflow_executor = WorkflowExecutor(middle_workflow, id="middle_wf_exec")
    outer_exec = MockExecutor(id="outer_exec")

    outer_workflow = (
        WorkflowBuilder().add_edge(outer_exec, middle_workflow_executor).set_start_executor(outer_exec).build()
    )

    viz = WorkflowViz(outer_workflow)
    dot_content = viz.to_digraph()

    # Check that all levels are present
    assert "outer_exec" in dot_content
    assert "middle_wf_exec" in dot_content
    assert "inner_wf_exec" in dot_content

    # Check for nested clusters
    assert "subgraph cluster_" in dot_content
    # Should have multiple subgraphs for nested structure
    subgraph_count = dot_content.count("subgraph cluster_")
    assert subgraph_count >= 2  # At least one for each level of nesting
