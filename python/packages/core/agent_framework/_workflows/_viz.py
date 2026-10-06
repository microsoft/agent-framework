# Copyright (c) Microsoft. All rights reserved.

import hashlib
import re
import tempfile
import uuid
from pathlib import Path
from typing import Literal

from ._edge import FanInEdgeGroup, InternalEdgeGroup
from ._workflow import Workflow

# Import of WorkflowExecutor is performed lazily inside methods to avoid cycles

"""Workflow visualization module using graphviz and Mermaid."""


class WorkflowViz:
    """A class for visualizing workflows using graphviz and Mermaid."""

    def __init__(self, workflow: Workflow):
        """Initialize the WorkflowViz with a workflow.

        Args:
            workflow: The workflow to visualize.
        """
        self._workflow = workflow

    def to_digraph(self, include_internal_executors: bool = False) -> str:
        """Export the workflow as a DOT format digraph string.

        Args:
            include_internal_executors (bool): Whether to include internal executors in the visualization.
                                               Default is False.

        Returns:
            A string representation of the workflow in DOT format.
        """
        lines = ["digraph Workflow {"]
        lines.append("  rankdir=TD;")  # Top to bottom layout
        lines.append("  node [shape=box, style=filled, fillcolor=lightblue];")
        lines.append("  edge [color=black, arrowhead=vee];")
        lines.append("")

        # Emit the top-level workflow nodes/edges
        self._emit_workflow_digraph(
            self._workflow,
            lines,
            indent="  ",
            include_internal_executors=include_internal_executors,
        )

        # Emit sub-workflows hosted by WorkflowExecutor as nested clusters
        self._emit_sub_workflows_digraph(
            self._workflow,
            lines,
            indent="  ",
            include_internal_executors=include_internal_executors,
        )

        lines.append("}")
        return "\n".join(lines)

    def export(
        self,
        format: Literal["svg", "png", "pdf", "dot"] = "svg",
        filename: str | None = None,
        include_internal_executors: bool = False,
    ) -> str:
        """Export the workflow visualization to a file or return the file path.

        Args:
            format: The output format. Supported formats: 'svg', 'png', 'pdf', 'dot'.
            filename: Optional filename to save the output. If None, creates a temporary file.
            include_internal_executors (bool): Whether to include internal executors in the visualization.
                                               Default is False.

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
            content = self.to_digraph(include_internal_executors=include_internal_executors)
            if filename:
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                return filename
            # Create temporary file for dot format
            with tempfile.NamedTemporaryFile(mode="w", suffix=".dot", delete=False, encoding="utf-8") as temp_file:
                temp_file.write(content)
                return temp_file.name

        try:
            import graphviz
        except ImportError as e:
            raise ImportError(
                "viz extra is required for export. Install it with: pip install graphviz>=0.20.0 "
                "The version needs to be at least 0.20.0. "
                "You also need to install graphviz separately. E.g., sudo apt-get install graphviz on Debian/Ubuntu "
                "or brew install graphviz on macOS. See https://graphviz.org/download/ for details."
            ) from e

        # Create a temporary graphviz Source object
        dot_content = self.to_digraph(include_internal_executors=include_internal_executors)
        source = graphviz.Source(dot_content)

        try:
            if filename:
                # Save to specified file
                output_path = Path(filename)
                if output_path.suffix and output_path.suffix[1:] != format:
                    raise ValueError(f"File extension {output_path.suffix} doesn't match format {format}")

                # Remove extension if present since graphviz.render() adds it
                base_name = str(output_path.with_suffix(""))
                source.render(base_name, format=format, cleanup=True)  # type: ignore

                # Return the actual filename with extension
                return f"{base_name}.{format}"
            # Create temporary file
            with tempfile.NamedTemporaryFile(suffix=f".{format}", delete=False) as temp_file:
                temp_path = Path(temp_file.name)
                base_name = str(temp_path.with_suffix(""))

            source.render(base_name, format=format, cleanup=True)  # type: ignore
            return f"{base_name}.{format}"
        except graphviz.backend.execute.ExecutableNotFound as e:
            raise ImportError(
                "The graphviz executables are not found. The graphviz Python package is installed, but the "
                "graphviz executables (dot, neato, etc.) are not available on your system's PATH. "
                "Install graphviz executables: sudo apt-get install graphviz on Debian/Ubuntu, "
                "brew install graphviz on macOS, or download from https://graphviz.org/download/ for other platforms."
            ) from e

    def save_svg(self, filename: str, include_internal_executors: bool = False) -> str:
        """Convenience method to save as SVG.

        Args:
            filename: The filename to save the SVG file.
            include_internal_executors (bool): Whether to include internal executors in the visualization.
                                               Default is False.

        Returns:
            The path to the saved SVG file.
        """
        return self.export(format="svg", filename=filename, include_internal_executors=include_internal_executors)

    def save_png(self, filename: str, include_internal_executors: bool = False) -> str:
        """Convenience method to save as PNG.

        Args:
            filename: The filename to save the PNG file.
            include_internal_executors (bool): Whether to include internal executors in the visualization.
                                               Default is False.

        Returns:
            The path to the saved PNG file.
        """
        return self.export(format="png", filename=filename, include_internal_executors=include_internal_executors)

    def save_pdf(self, filename: str, include_internal_executors: bool = False) -> str:
        """Convenience method to save as PDF.

        Args:
            filename: The filename to save the PDF file.
            include_internal_executors (bool): Whether to include internal executors in the visualization.
                                               Default is False.

        Returns:
            The path to the saved PDF file.
        """
        return self.export(format="pdf", filename=filename, include_internal_executors=include_internal_executors)

    def to_mermaid(self, include_internal_executors: bool = False) -> str:
        """Export the workflow as a Mermaid flowchart string.

        Args:
            include_internal_executors (bool): Whether to include internal executors in the visualization.
                                               Default is False.

        Returns:
            A string representation of the workflow in Mermaid flowchart syntax.
        """
        lines: list[str] = ["flowchart TD"]
        node_ids = self._mermaid_node_ids(include_internal_executors=include_internal_executors)

        # Emit top-level workflow
        self._emit_workflow_mermaid(
            self._workflow,
            lines,
            indent="  ",
            node_ids=node_ids,
            include_internal_executors=include_internal_executors,
        )

        # Emit sub-workflows as Mermaid subgraphs
        self._emit_sub_workflows_mermaid(
            self._workflow,
            lines,
            indent="  ",
            node_ids=node_ids,
            include_internal_executors=include_internal_executors,
        )

        return "\n".join(lines)

    # region Private helpers

    def _fan_in_digest(self, target: str, sources: list[str]) -> str:
        sources_sorted = sorted(sources)
        return hashlib.sha256((target + "|" + "|".join(sources_sorted)).encode("utf-8")).hexdigest()[:8]

    def _compute_fan_in_descriptors(self, workflow: Workflow | None = None) -> list[tuple[str, list[str], str]]:
        """Return list of (node_id, sources, target) for fan-in groups.

        node_id is DOT-oriented: fan_in::target::digest
        """
        result: list[tuple[str, list[str], str]] = []
        workflow = workflow or self._workflow
        for group in workflow.edge_groups:
            if isinstance(group, FanInEdgeGroup):
                target = group.target_executor_ids[0]
                sources = list(group.source_executor_ids)
                digest = self._fan_in_digest(target, sources)
                node_id = f"fan_in::{target}::{digest}"
                result.append((node_id, sorted(sources), target))
        return result

    def _compute_normal_edges(
        self,
        workflow: Workflow | None = None,
        include_internal_executors: bool = False,
    ) -> list[tuple[str, str, bool]]:
        """Return list of (source_id, target_id, is_conditional) for non-fan-in groups."""
        edges: list[tuple[str, str, bool]] = []
        workflow = workflow or self._workflow
        for group in workflow.edge_groups:
            if isinstance(group, FanInEdgeGroup):
                continue
            if isinstance(group, InternalEdgeGroup) and not include_internal_executors:
                continue
            for edge in group.edges:
                is_cond = getattr(edge, "_condition", None) is not None
                edges.append((edge.source_id, edge.target_id, is_cond))
        return edges

    # endregion

    # region Internal emitters (DOT)

    def _emit_workflow_digraph(
        self,
        workflow: Workflow,
        lines: list[str],
        indent: str,
        ns: str | None = None,
        include_internal_executors: bool = False,
    ) -> None:
        """Emit DOT nodes/edges for the given workflow.

        If ns (namespace) is provided, node ids are prefixed with f"{ns}/" for uniqueness,
        but labels remain the original executor ids.
        """

        def map_id(x: str) -> str:
            return f"{ns}/{x}" if ns else x

        # Nodes
        start_executor_id = workflow.start_executor_id
        lines.append(
            f'{indent}"{map_id(start_executor_id)}" [fillcolor=lightgreen, label="{start_executor_id}\\n(Start)"];'
        )
        for executor_id in workflow.executors:
            if executor_id != start_executor_id:
                lines.append(f'{indent}"{map_id(executor_id)}" [label="{executor_id}"];')

        # Fan-in nodes
        fan_in_nodes = self._compute_fan_in_descriptors(workflow)
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
        for src, tgt, is_cond in self._compute_normal_edges(
            workflow, include_internal_executors=include_internal_executors
        ):
            edge_attr = ' [style=dashed, label="conditional"]' if is_cond else ""
            lines.append(f'{indent}"{map_id(src)}" -> "{map_id(tgt)}"{edge_attr};')

    def _emit_sub_workflows_digraph(
        self,
        workflow: Workflow,
        lines: list[str],
        indent: str,
        include_internal_executors: bool = False,
    ) -> None:
        """Emit DOT subgraphs for any WorkflowExecutor instances found in the workflow."""
        # Lazy import to avoid any potential import cycles
        try:
            from ._workflow_executor import WorkflowExecutor
        except ImportError:  # pragma: no cover - best-effort; if unavailable, skip subgraphs
            return

        for exec_id, exec_obj in workflow.executors.items():
            if isinstance(exec_obj, WorkflowExecutor) and hasattr(exec_obj, "workflow") and exec_obj.workflow:
                subgraph_id = f"cluster_{uuid.uuid5(uuid.NAMESPACE_OID, exec_id).hex[:8]}"
                lines.append(f"{indent}subgraph {subgraph_id} {{")
                lines.append(f'{indent}  label="sub-workflow: {exec_id}";')
                lines.append(f"{indent}  style=dashed;")

                # Emit the nested workflow inside this cluster using a namespace
                ns = exec_id
                self._emit_workflow_digraph(
                    exec_obj.workflow,
                    lines,
                    indent=f"{indent}  ",
                    ns=ns,
                    include_internal_executors=include_internal_executors,
                )

                # Recurse into deeper nested sub-workflows
                self._emit_sub_workflows_digraph(
                    exec_obj.workflow,
                    lines,
                    indent=f"{indent}  ",
                    include_internal_executors=include_internal_executors,
                )

                lines.append(f"{indent}}}")

    # endregion

    # region Internal emitters (Mermaid)

    @staticmethod
    def _sanitize_mermaid_id(value: str) -> str:
        sanitized = re.sub(r"[^0-9A-Za-z_]", "_", value)
        return sanitized if sanitized and sanitized[0].isalpha() else f"n_{sanitized}"

    def _mermaid_node_ids(self, *, include_internal_executors: bool = False) -> dict[tuple[str, ...], str]:
        """Allocate graph-wide aliases without consuming another node's ordinary ID."""
        from ._workflow_executor import WorkflowExecutor

        candidates: dict[tuple[str, ...], str] = {}

        def collect(workflow: Workflow, ns: tuple[str, ...] = ()) -> None:
            prefix = f"{self._sanitize_mermaid_id(ns[-1])}__" if ns else ""
            for executor_id, executor in workflow.executors.items():
                candidates[("executor", *ns, executor_id)] = prefix + self._sanitize_mermaid_id(executor_id)
                if isinstance(executor, WorkflowExecutor) and executor.workflow:
                    if ns:
                        candidates[("subgraph", *ns, executor_id)] = self._sanitize_mermaid_id(executor_id)
                    collect(executor.workflow, (*ns, executor_id))
            # Internal edge sources are not present in workflow.executors.
            for source, target, _ in self._compute_normal_edges(
                workflow, include_internal_executors=include_internal_executors
            ):
                for executor_id in (source, target):
                    candidates[("executor", *ns, executor_id)] = prefix + self._sanitize_mermaid_id(executor_id)
            for dot_node_id, _, target in self._compute_fan_in_descriptors(workflow):
                digest = dot_node_id.split("::")[-1]
                candidates[("fan-in", *ns, dot_node_id)] = (
                    f"fan_in__{prefix}{self._sanitize_mermaid_id(f'{target}__{digest}')}"
                )

        collect(self._workflow)
        reserved = set(candidates.values())
        used: set[str] = set()
        node_ids: dict[tuple[str, ...], str] = {}
        # Prefer unchanged executor IDs, then allocate deterministically by original scope.
        for key in sorted(candidates, key=lambda key: (candidates[key] != key[-1], key)):
            candidate = candidates[key]
            alias = candidate
            if alias in used:
                suffix = 2
                alias = f"{candidate}_{suffix}"
                while alias in reserved or alias in used:
                    suffix += 1
                    alias = f"{candidate}_{suffix}"
            used.add(alias)
            node_ids[key] = alias
        return node_ids

    def _emit_workflow_mermaid(
        self,
        workflow: Workflow,
        lines: list[str],
        indent: str,
        node_ids: dict[tuple[str, ...], str],
        ns: tuple[str, ...] = (),
        include_internal_executors: bool = False,
    ) -> None:
        def map_id(x: str) -> str:
            return node_ids[("executor", *ns, x)]

        # Nodes
        start_executor_id = workflow.start_executor_id
        lines.append(f'{indent}{map_id(start_executor_id)}["{start_executor_id} (Start)"];')
        for executor_id in workflow.executors:
            if executor_id == start_executor_id:
                continue
            lines.append(f'{indent}{map_id(executor_id)}["{executor_id}"];')

        # Fan-in nodes
        fan_in_nodes_dot = self._compute_fan_in_descriptors(workflow)
        fan_in_nodes: list[tuple[str, list[str], str]] = []
        for dot_node_id, sources, target in fan_in_nodes_dot:
            fan_node_id = node_ids[("fan-in", *ns, dot_node_id)]
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
        for src, tgt, is_cond in self._compute_normal_edges(
            workflow, include_internal_executors=include_internal_executors
        ):
            s = map_id(src)
            t = map_id(tgt)
            if is_cond:
                lines.append(f"{indent}{s} -. conditional .-> {t};")
            else:
                lines.append(f"{indent}{s} --> {t};")

    def _emit_sub_workflows_mermaid(
        self,
        workflow: Workflow,
        lines: list[str],
        indent: str,
        node_ids: dict[tuple[str, ...], str],
        ns: tuple[str, ...] = (),
        include_internal_executors: bool = False,
    ) -> None:
        try:
            from ._workflow_executor import WorkflowExecutor
        except ImportError:  # pragma: no cover
            return

        for exec_id, exec_obj in workflow.executors.items():
            if isinstance(exec_obj, WorkflowExecutor) and hasattr(exec_obj, "workflow") and exec_obj.workflow:
                sg_id = node_ids[("subgraph", *ns, exec_id)] if ns else node_ids["executor", exec_id]
                lines.append(f"{indent}subgraph {sg_id}")
                # Render nested workflow within this subgraph using namespacing
                self._emit_workflow_mermaid(
                    exec_obj.workflow,
                    lines,
                    indent=f"{indent}  ",
                    node_ids=node_ids,
                    ns=(*ns, exec_id),
                    include_internal_executors=include_internal_executors,
                )
                # Recurse into deeper sub-workflows
                self._emit_sub_workflows_mermaid(
                    exec_obj.workflow,
                    lines,
                    indent=f"{indent}  ",
                    node_ids=node_ids,
                    ns=(*ns, exec_id),
                    include_internal_executors=include_internal_executors,
                )
                lines.append(f"{indent}end")

    # endregion
