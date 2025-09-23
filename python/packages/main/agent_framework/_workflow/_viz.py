# Copyright (c) Microsoft. All rights reserved.

import hashlib
import re
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from ._edge import FanInEdgeGroup
from ._workflow import Workflow

# Import of WorkflowExecutor is performed lazily inside methods to avoid cycles

"""Workflow visualization module using graphviz."""


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

        # Emit the top-level workflow nodes/edges
        self._emit_workflow_digraph(self._workflow, lines, indent="  ")

        # Emit sub-workflows hosted by WorkflowExecutor as nested clusters
        self._emit_sub_workflows_digraph(self._workflow, lines, indent="  ")

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
                "viz extra is required for export. Install it with: pip install agent-framework[viz]. "
                "You also need to install graphviz separately. E.g., sudo apt-get install graphviz on Debian/Ubuntu "
                "or brew install graphviz on macOS. See https://graphviz.org/download/ for details."
            ) from e

        # Create a temporary graphviz Source object
        dot_content = self.to_digraph()
        source = graphviz.Source(dot_content)

        try:
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
        except graphviz.backend.execute.ExecutableNotFound as e:
            raise ImportError(
                "The graphviz executables are not found. The graphviz Python package is installed, but the "
                "graphviz executables (dot, neato, etc.) are not available on your system's PATH. "
                "Install graphviz executables: sudo apt-get install graphviz on Debian/Ubuntu, "
                "brew install graphviz on macOS, or download from https://graphviz.org/download/ for other platforms."
            ) from e

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

        # Emit top-level workflow
        self._emit_workflow_mermaid(self._workflow, lines, indent="  ")

        # Emit sub-workflows as Mermaid subgraphs
        self._emit_sub_workflows_mermaid(self._workflow, lines, indent="  ")

        return "\n".join(lines)

    # region Private helpers

    def _fan_in_digest(self, target: str, sources: list[str]) -> str:
        sources_sorted = sorted(sources)
        return hashlib.sha256((target + "|" + "|".join(sources_sorted)).encode("utf-8")).hexdigest()[:8]

    def _compute_fan_in_descriptors(self, wf: Workflow | None = None) -> list[tuple[str, list[str], str]]:
        """Return list of (node_id, sources, target) for fan-in groups.

        node_id is DOT-oriented: fan_in::target::digest
        """
        result: list[tuple[str, list[str], str]] = []
        workflow = wf or self._workflow
        for group in workflow.edge_groups:
            if isinstance(group, FanInEdgeGroup):
                target = group.target_executor_ids[0]
                sources = list(group.source_executor_ids)
                digest = self._fan_in_digest(target, sources)
                node_id = f"fan_in::{target}::{digest}"
                result.append((node_id, sorted(sources), target))
        return result

    def _compute_normal_edges(self, wf: Workflow | None = None) -> list[tuple[str, str, bool]]:
        """Return list of (source_id, target_id, is_conditional) for non-fan-in groups."""
        edges: list[tuple[str, str, bool]] = []
        workflow = wf or self._workflow
        for group in workflow.edge_groups:
            if isinstance(group, FanInEdgeGroup):
                continue
            for edge in group.edges:
                is_cond = getattr(edge, "_condition", None) is not None
                edges.append((edge.source_id, edge.target_id, is_cond))
        return edges

    # endregion

    # region Internal emitters (DOT)

    def _emit_workflow_digraph(self, wf: Workflow, lines: list[str], indent: str, ns: str | None = None) -> None:
        """Emit DOT nodes/edges for the given workflow.

        If ns (namespace) is provided, node ids are prefixed with f"{ns}/" for uniqueness,
        but labels remain the original executor ids.
        """

        def map_id(x: str) -> str:
            return f"{ns}/{x}" if ns else x

        # Nodes
        start_executor_id = wf.start_executor_id
        lines.append(
            f'{indent}"{map_id(start_executor_id)}" [fillcolor=lightgreen, label="{start_executor_id}\\n(Start)"];'
        )
        for executor_id in wf.executors:
            if executor_id != start_executor_id:
                lines.append(f'{indent}"{map_id(executor_id)}" [label="{executor_id}"];')

        # Fan-in nodes
        fan_in_nodes = self._compute_fan_in_descriptors(wf)
        if fan_in_nodes:
            lines.append("")
            for node_id, _, _ in fan_in_nodes:
                lines.append(f'{indent}"{map_id(node_id)}" [shape=ellipse, fillcolor=lightgoldenrod, label="fan-in"];')

        # Fan-in edges
        for node_id, sources, target in fan_in_nodes:
            for src in sources:
                lines.append(f'{indent}"{map_id(src)}" -> "{map_id(node_id)}";')
            lines.append(f'{indent}"{map_id(node_id)}" -> "{map_id(target)}";')

        # Normal edges
        for src, tgt, is_cond in self._compute_normal_edges(wf):
            edge_attr = ' [style=dashed, label="conditional"]' if is_cond else ""
            lines.append(f'{indent}"{map_id(src)}" -> "{map_id(tgt)}"{edge_attr};')

    def _emit_sub_workflows_digraph(self, wf: Workflow, lines: list[str], indent: str) -> None:
        """Emit DOT subgraphs for any WorkflowExecutor instances found in the workflow."""
        # Lazy import to avoid any potential import cycles
        try:
            from ._workflow_executor import WorkflowExecutor  # type: ignore
        except ImportError:  # pragma: no cover - best-effort; if unavailable, skip subgraphs
            return

        for exec_id, exec_obj in wf.executors.items():
            if isinstance(exec_obj, WorkflowExecutor) and hasattr(exec_obj, "workflow") and exec_obj.workflow:
                subgraph_id = f"cluster_{uuid.uuid5(uuid.NAMESPACE_OID, exec_id).hex[:8]}"
                lines.append(f"{indent}subgraph {subgraph_id} {{")
                lines.append(f'{indent}  label="sub-workflow: {exec_id}";')
                lines.append(f"{indent}  style=dashed;")

                # Emit the nested workflow inside this cluster using a namespace
                ns = exec_id
                self._emit_workflow_digraph(exec_obj.workflow, lines, indent=f"{indent}  ", ns=ns)

                # Recurse into deeper nested sub-workflows
                self._emit_sub_workflows_digraph(exec_obj.workflow, lines, indent=f"{indent}  ")

                lines.append(f"{indent}}}")

    # endregion

    # region Internal emitters (Mermaid)

    def _emit_workflow_mermaid(self, wf: Workflow, lines: list[str], indent: str, ns: str | None = None) -> None:
        def _san(s: str) -> str:
            s2 = re.sub(r"[^0-9A-Za-z_]", "_", s)
            if not s2 or not s2[0].isalpha():
                s2 = f"n_{s2}"
            return s2

        def map_id(x: str) -> str:
            if ns:
                return f"{_san(ns)}__{_san(x)}"
            return _san(x)

        # Nodes
        start_executor_id = wf.start_executor_id
        lines.append(f'{indent}{map_id(start_executor_id)}["{start_executor_id} (Start)"];')
        for executor_id in wf.executors:
            if executor_id == start_executor_id:
                continue
            lines.append(f'{indent}{map_id(executor_id)}["{executor_id}"];')

        # Fan-in nodes
        fan_in_nodes_dot = self._compute_fan_in_descriptors(wf)
        fan_in_nodes: list[tuple[str, list[str], str]] = []
        for dot_node_id, sources, target in fan_in_nodes_dot:
            digest = dot_node_id.split("::")[-1]
            base = f"{target}__{digest}"
            fan_node_id = f"fan_in__{_san(ns) + '__' if ns else ''}{_san(base)}"
            fan_in_nodes.append((fan_node_id, sources, target))

        for fan_node_id, _, _ in fan_in_nodes:
            # Keep this line without trailing semicolon to match existing tests
            lines.append(f"{indent}{fan_node_id}((fan-in))")

        # Fan-in edges
        for fan_node_id, sources, target in fan_in_nodes:
            for s in sources:
                lines.append(f"{indent}{map_id(s)} --> {fan_node_id};")
            lines.append(f"{indent}{fan_node_id} --> {map_id(target)};")

        # Normal edges
        for src, tgt, is_cond in self._compute_normal_edges(wf):
            s = map_id(src)
            t = map_id(tgt)
            if is_cond:
                lines.append(f"{indent}{s} -. conditional .-> {t};")
            else:
                lines.append(f"{indent}{s} --> {t};")

    def _emit_sub_workflows_mermaid(self, wf: Workflow, lines: list[str], indent: str) -> None:
        try:
            from ._workflow_executor import WorkflowExecutor  # type: ignore
        except ImportError:  # pragma: no cover
            return

        def _san(s: str) -> str:
            s2 = re.sub(r"[^0-9A-Za-z_]", "_", s)
            if not s2 or not s2[0].isalpha():
                s2 = f"n_{s2}"
            return s2

        for exec_id, exec_obj in wf.executors.items():
            if isinstance(exec_obj, WorkflowExecutor) and hasattr(exec_obj, "workflow") and exec_obj.workflow:
                sg_id = _san(exec_id)
                lines.append(f"{indent}subgraph {sg_id}")
                # Render nested workflow within this subgraph using namespacing
                self._emit_workflow_mermaid(exec_obj.workflow, lines, indent=f"{indent}  ", ns=exec_id)
                # Recurse into deeper sub-workflows
                self._emit_sub_workflows_mermaid(exec_obj.workflow, lines, indent=f"{indent}  ")
                lines.append(f"{indent}end")

    # endregion
