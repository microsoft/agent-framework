# Copyright (c) Microsoft. All rights reserved.

"""Workflow visualization module using graphviz."""

import hashlib
import re
import tempfile
from pathlib import Path
from typing import Literal

from ._edge import FanInEdgeGroup
from ._workflow import Workflow


class WorkflowViz:
    """A class for visualizing workflows using graphviz."""

    def __init__(self, workflow: Workflow):
        """Initialize the WorkflowViz with a workflow.

        Args:
            workflow: The workflow to visualize.
        """
        self._workflow = workflow

    def to_digraph(self) -> str:
        """Export the workflow as a DOT format digraph string.

        Returns:
            A string representation of the workflow in DOT format.
        """
        lines = ["digraph Workflow {"]
        lines.append("  rankdir=TD;")  # Top to bottom layout
        lines.append("  node [shape=box, style=filled, fillcolor=lightblue];")
        lines.append("  edge [color=black, arrowhead=vee];")
        lines.append("")

        # Add start executor with special styling
        start_executor_id = self._workflow.start_executor_id
        lines.append(f'  "{start_executor_id}" [fillcolor=lightgreen, label="{start_executor_id}\\n(Start)"];')

        # Add all other executors
        for executor_id in self._workflow.executors:
            if executor_id != start_executor_id:
                lines.append(f'  "{executor_id}" [label="{executor_id}"];')

        # Build shared structures
        fan_in_nodes = self._compute_fan_in_descriptors()  # (node_id, sources, target)
        normal_edges = self._compute_normal_edges()  # (src, tgt, is_conditional)

        if fan_in_nodes:
            lines.append("")
            for node_id, _, _ in fan_in_nodes:
                lines.append(f'  "{node_id}" [shape=ellipse, fillcolor=lightgoldenrod, label="fan-in"];')

        # Route fan-in via intermediate nodes
        for node_id, sources, target in fan_in_nodes:
            for src in sources:
                lines.append(f'  "{src}" -> "{node_id}";')
            lines.append(f'  "{node_id}" -> "{target}";')

        # Draw normal edges
        for src, tgt, is_cond in normal_edges:
            edge_attr = ' [style=dashed, label="conditional"]' if is_cond else ""
            lines.append(f'  "{src}" -> "{tgt}"{edge_attr};')

        lines.append("}")
        return "\n".join(lines)

    def export(self, format: Literal["svg", "png", "pdf", "dot"] = "svg", filename: str | None = None) -> str:
        """Export the workflow visualization to a file or return the file path.

        Args:
            format: The output format. Supported formats: 'svg', 'png', 'pdf', 'dot'.
            filename: Optional filename to save the output. If None, creates a temporary file.

        Returns:
            The path to the saved file.

        Raises:
            ImportError: If graphviz is not installed.
            ValueError: If an unsupported format is specified.
        """
        # Validate format first
        if format not in ["svg", "png", "pdf", "dot"]:
            raise ValueError(f"Unsupported format: {format}. Supported formats: svg, png, pdf, dot")

        if format == "dot":
            content = self.to_digraph()
            if filename:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                return filename
            # Create temporary file for dot format
            with tempfile.NamedTemporaryFile(mode="w", suffix=".dot", delete=False, encoding="utf-8") as temp_file:
                temp_file.write(content)
                return temp_file.name

        try:
            import graphviz  # type: ignore
        except ImportError as e:
            raise ImportError(
                "viz extra is required for export. Install it with: pip install agent-framework-workflow[viz]. "
                "You also need to install graphviz separately. E.g., sudo apt-get install graphviz on Debian/Ubuntu "
                "or brew install graphviz on macOS. See https://graphviz.org/download/ for details."
            ) from e

        # Create a temporary graphviz Source object
        dot_content = self.to_digraph()
        source = graphviz.Source(dot_content)

        if filename:
            # Save to specified file
            output_path = Path(filename)
            if output_path.suffix and output_path.suffix[1:] != format:
                raise ValueError(f"File extension {output_path.suffix} doesn't match format {format}")

            # Remove extension if present since graphviz.render() adds it
            base_name = str(output_path.with_suffix(""))
            source.render(base_name, format=format, cleanup=True)

            # Return the actual filename with extension
            return f"{base_name}.{format}"
        # Create temporary file
        with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as temp_file:
            temp_path = Path(temp_file.name)
            base_name = str(temp_path.with_suffix(""))

        source.render(base_name, format=format, cleanup=True)
        return f"{base_name}.{format}"

    def save_svg(self, filename: str) -> str:
        """Convenience method to save as SVG.

        Args:
            filename: The filename to save the SVG file.

        Returns:
            The path to the saved SVG file.
        """
        return self.export(format="svg", filename=filename)

    def save_png(self, filename: str) -> str:
        """Convenience method to save as PNG.

        Args:
            filename: The filename to save the PNG file.

        Returns:
            The path to the saved PNG file.
        """
        return self.export(format="png", filename=filename)

    def save_pdf(self, filename: str) -> str:
        """Convenience method to save as PDF.

        Args:
            filename: The filename to save the PDF file.

        Returns:
            The path to the saved PDF file.
        """
        return self.export(format="pdf", filename=filename)

    def to_mermaid(self) -> str:
        """Export the workflow as a Mermaid flowchart string.

        Returns:
            A string representation of the workflow in Mermaid flowchart syntax.
        """

        def _san(s: str) -> str:
            """Sanitize an ID for Mermaid (alphanumeric and underscore, start with letter)."""
            s2 = re.sub(r"[^0-9A-Za-z_]", "_", s)
            if not s2 or not s2[0].isalpha():
                s2 = f"n_{s2}"
            return s2

        lines: list[str] = ["flowchart TD"]

        # Nodes
        start_executor_id = self._workflow.start_executor_id
        start_id = _san(start_executor_id)
        # End statements with semicolons for better compatibility and quote labels for special chars
        lines.append(f'  {start_id}["{start_executor_id} (Start)"];')

        for executor_id in self._workflow.executors:
            if executor_id == start_executor_id:
                continue
            eid = _san(executor_id)
            lines.append(f'  {eid}["{executor_id}"];')

        # Build shared structures
        fan_in_nodes_dot = self._compute_fan_in_descriptors()  # uses DOT node ids
        # Convert DOT-style node ids to Mermaid-safe ones
        fan_in_nodes: list[tuple[str, list[str], str]] = []
        for dot_node_id, sources, target in fan_in_nodes_dot:
            digest = dot_node_id.split("::")[-1]
            fan_node_id = f"fan_in__{_san(target)}__{digest}"
            fan_in_nodes.append((fan_node_id, sources, target))

        for fan_node_id, _, _ in fan_in_nodes:
            # Use double parentheses to make it circular in Mermaid
            # (Keep this line without a trailing semicolon to match existing tests.)
            lines.append(f"  {fan_node_id}((fan-in))")

        # Fan-in edges
        for fan_node_id, sources, target in fan_in_nodes:
            for s in sources:
                lines.append(f"  {_san(s)} --> {fan_node_id};")
            lines.append(f"  {fan_node_id} --> {_san(target)};")

        # Normal edges
        for src, tgt, is_cond in self._compute_normal_edges():
            s = _san(src)
            t = _san(tgt)
            if is_cond:
                lines.append(f"  {s} -. conditional .-> {t};")
            else:
                lines.append(f"  {s} --> {t};")

        return "\n".join(lines)

    # region Private helpers

    def _fan_in_digest(self, target: str, sources: list[str]) -> str:
        sources_sorted = sorted(sources)
        return hashlib.sha256((target + "|" + "|".join(sources_sorted)).encode("utf-8")).hexdigest()[:8]

    def _compute_fan_in_descriptors(self) -> list[tuple[str, list[str], str]]:
        """Return list of (node_id, sources, target) for fan-in groups.

        node_id is DOT-oriented: fan_in::target::digest
        """
        result: list[tuple[str, list[str], str]] = []
        for group in self._workflow.edge_groups:
            if isinstance(group, FanInEdgeGroup):
                target = group.target_executor_ids[0]
                sources = list(group.source_executor_ids)
                digest = self._fan_in_digest(target, sources)
                node_id = f"fan_in::{target}::{digest}"
                result.append((node_id, sorted(sources), target))
        return result

    def _compute_normal_edges(self) -> list[tuple[str, str, bool]]:
        """Return list of (source_id, target_id, is_conditional) for non-fan-in groups."""
        edges: list[tuple[str, str, bool]] = []
        for group in self._workflow.edge_groups:
            if isinstance(group, FanInEdgeGroup):
                continue
            for edge in group.edges:
                is_cond = getattr(edge, "_condition", None) is not None
                edges.append((edge.source_id, edge.target_id, is_cond))
        return edges

    # endregion
