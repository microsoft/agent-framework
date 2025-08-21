# Copyright (c) Microsoft. All rights reserved.

"""Tests for the workflow visualization module."""

import pytest
from agent_framework.workflow import Executor, WorkflowBuilder, WorkflowContext, WorkflowViz, handler


class MockExecutor(Executor):
    """A mock executor for testing purposes."""

    @handler
    async def mock_handler(self, message: str, ctx: WorkflowContext[None]) -> None:
        """A mock handler that does nothing."""
        pass


class ListStrTargetExecutor(Executor):
    """A mock executor that accepts a list of strings (for fan-in targets)."""

    @handler
    async def handle(self, message: list[str], ctx: WorkflowContext[None]) -> None:  # type: ignore[type-arg]
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
