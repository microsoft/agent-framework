# Copyright (c) Microsoft. All rights reserved.

"""Tests for the workflow visualization module."""

import pytest
from agent_framework.workflow import Executor, WorkflowBuilder, WorkflowContext, WorkflowViz, handler


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @handler
    async def mock_handler(self, message: str, ctx: WorkflowContext) -> None:
        """A mock handler that does nothing."""
        pass


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
    t = MockExecutor(id="t")

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
