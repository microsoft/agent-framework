# Copyright (c) Microsoft. All rights reserved.

"""Workflow visualization module using graphviz."""

import tempfile
from pathlib import Path
from typing import Literal

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
        start_executor = self._workflow.start_executor
        lines.append(f'  "{start_executor.id}" [fillcolor=lightgreen, label="{start_executor.id}\\n(Start)"];')

        # Add all other executors
        for executor in self._workflow.executors:
            if executor.id != start_executor.id:
                lines.append(f'  "{executor.id}" [label="{executor.id}"];')

        lines.append("")

        # Add edges
        for edge in self._workflow.edges:
            edge_attr = ""
            if edge._condition is not None:
                edge_attr = ' [style=dashed, label="conditional"]'
            elif edge.has_edge_group():
                edge_attr = ' [color=red, style=bold, label="fan-in"]'

            lines.append(f'  "{edge.source_id}" -> "{edge.target_id}"{edge_attr};')

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
                "viz extra is required for export. Install it with: pip install agent-framework-workflow[viz]"
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
