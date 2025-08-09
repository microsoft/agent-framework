# Copyright (c) Microsoft. All rights reserved.

"""Tests for the workflow visualization module."""

import pytest

from agent_framework_workflow import Executor, WorkflowBuilder, WorkflowContext, WorkflowViz, handler


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
