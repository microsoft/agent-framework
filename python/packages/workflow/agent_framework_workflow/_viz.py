# Copyright (c) Microsoft. All rights reserved.

"""Workflow visualization and simple web UI serving.

This module contains:
- WorkflowViz.to_digraph/export: Graphviz-based exporters.
- WorkflowViz.serve: A minimal web UI to visualize and run a workflow.

The web UI is intentionally simple:
- Text box to enter a string message and a "Run" button.
- A static graph view rendered client-side with Cytoscape.js (via CDN).
- Live updates over WebSocket:
    - Active node outlined blue when invoked.
    - Completed node outlined black when finished.
    - Unvisited nodes outlined gray by default.
- Only one run at a time; subsequent triggers are blocked until completion.
"""

import contextlib
import hashlib
import tempfile
from pathlib import Path
from typing import Any, Literal, TypedDict

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

        # Build fan-in groups:
        # - key: sorted tuple of edge IDs in the group (including self)
        # - value: info about target, sources set, and a synthetic node id
        class _FanInGroup(TypedDict):
            target: str
            sources: set[str]
            node_id: str

        groups: dict[tuple[str, ...], _FanInGroup] = {}
        for edge in self._workflow.edges:
            if edge.has_edge_group():
                group_ids = tuple(sorted([*edge._edge_group_ids, edge.id]))
                if group_ids not in groups:
                    # Deterministic node id based on target + group ids
                    digest = hashlib.sha256((edge.target_id + "|" + "|".join(group_ids)).encode("utf-8")).hexdigest()[
                        :8
                    ]
                    node_id = f"fan_in::{edge.target_id}::{digest}"
                    groups[group_ids] = {"target": edge.target_id, "sources": set(), "node_id": node_id}
                # Track the source for this group
                sources = groups[group_ids]["sources"]
                if not isinstance(sources, set):
                    raise TypeError("Internal error: 'sources' is expected to be a set of str.")
                sources.add(edge.source_id)

        lines.append("")

        # Add intermediate fan-in nodes with special styling and label on the node
        for group in groups.values():
            node_id = group["node_id"]
            # Use a distinct shape/color to differentiate aggregation nodes
            lines.append(f'  "{node_id}" [shape=ellipse, fillcolor=lightgoldenrod, label="fan-in"];')

        # Add edges
        for edge in self._workflow.edges:
            edge_attr = ""
            if edge._condition is not None:
                edge_attr = ' [style=dashed, label="conditional"]'
            # Skip direct rendering of grouped edges; they'll be routed via the fan-in node below
            if edge.has_edge_group():
                continue

            lines.append(f'  "{edge.source_id}" -> "{edge.target_id}"{edge_attr};')

        # Route grouped edges through the intermediate fan-in node
        for group in groups.values():
            node_id = group["node_id"]
            target_id = group["target"]
            sources = group["sources"]
            for src in sorted(sources):
                lines.append(f'  "{src}" -> "{node_id}";')
            lines.append(f'  "{node_id}" -> "{target_id}";')

        lines.append("}")
        return "\n".join(lines)

    # --- Simple Web UI ----------------------------------------------------
    async def serve(self, port: int = 8000) -> None:
        """Start a minimal web UI to view and run the workflow.

        Args:
            port: Port to bind the HTTP server.

        Notes:
            - Requires optional extra: pip install agent-framework-workflow[serve]
            - Uses Starlette + Uvicorn. The client renders the graph with Cytoscape.js.
            - Only a single run is allowed at a time (no cancellation yet).
        """
        try:
            import uvicorn
            from starlette.applications import Starlette
            from starlette.responses import HTMLResponse, JSONResponse
            from starlette.routing import Route, WebSocketRoute
            from starlette.websockets import WebSocket
        except Exception as e:  # pragma: no cover - import-time dependency guard
            raise ImportError(
                "serve extra is required. Install with: pip install agent-framework-workflow[serve]"
            ) from e

        # Serialize workflow to Cytoscape format (nodes/edges)
        def _graph_json() -> dict[str, Any]:
            nodes: list[dict[str, Any]] = [{"data": {"id": ex.id, "label": ex.id}} for ex in self._workflow.executors]

            # Build fan-in groups using same logic as to_digraph
            class _FanInGroup(TypedDict):
                target: str
                sources: set[str]
                node_id: str

            groups: dict[tuple[str, ...], _FanInGroup] = {}
            for edge in self._workflow.edges:
                if edge.has_edge_group():
                    group_ids = tuple(sorted([*edge._edge_group_ids, edge.id]))
                    if group_ids not in groups:
                        digest = hashlib.sha256(
                            (edge.target_id + "|" + "|".join(group_ids)).encode("utf-8")
                        ).hexdigest()[:8]
                        node_id = f"fan_in::{edge.target_id}::{digest}"
                        groups[group_ids] = {"target": edge.target_id, "sources": set(), "node_id": node_id}
                    sources = groups[group_ids]["sources"]
                    if not isinstance(sources, set):  # defensive
                        raise TypeError("Internal error: 'sources' is expected to be a set of str.")
                    sources.add(edge.source_id)

            # Add fan-in nodes
            for group in groups.values():
                nodes.append({"data": {"id": group["node_id"], "label": "fan-in"}, "classes": "fanin"})

            # Edges
            edges: list[dict[str, Any]] = []
            # Direct edges (non-grouped)
            for e in self._workflow.edges:
                if e.has_edge_group():
                    continue
                classes = "conditional" if e._condition is not None else ""
                edges.append({"data": {"source": e.source_id, "target": e.target_id}, "classes": classes})

            # Grouped edges: src -> fanin, then fanin -> target
            for group in groups.values():
                node_id = group["node_id"]
                target_id = group["target"]
                for src in sorted(group["sources"]):
                    edges.append({"data": {"source": src, "target": node_id}})
                edges.append({"data": {"source": node_id, "target": target_id}})

            return {"nodes": nodes, "edges": edges, "start": self._workflow.start_executor.id}

        # Basic, dependency-free HTML with Cytoscape via CDN and a WS client
        INDEX_HTML = """
<!doctype html>
<html lang="en">
    <head>
        <meta charset="utf-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1" />
        <title>Workflow UI</title>
        <style>
            body { font-family: system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif; margin: 0; }
            header {
                padding: 12px 16px;
                border-bottom: 1px solid #eee;
                display: flex; gap: 8px; align-items: center;
            }
            #message { flex: 1; padding: 8px; font-size: 14px; }
            #runBtn { padding: 8px 12px; font-size: 14px; }
            main { display: grid; grid-template-columns: 2fr 1fr; height: calc(100vh - 54px); }
            #graph { border-right: 1px solid #eee; }
            #events {
                padding: 8px; overflow: auto;
                font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                font-size: 12px;
            }
            .chip {
                display: inline-block; padding: 2px 6px;
                border-radius: 999px; border: 1px solid #ddd; margin-right: 4px;
            }
        </style>
        <script src="https://unpkg.com/cytoscape@3.28.0/dist/cytoscape.min.js"></script>
    </head>
    <body>
        <header>
            <input id="message" placeholder="Type a message (string only)" />
            <button id="runBtn">Run</button>
            <span id="status" class="chip">Idle</span>
        </header>
        <main>
            <div id="graph"></div>
            <pre id="events"></pre>
        </main>
        <script>
            const eventsEl = document.getElementById('events');
            const statusEl = document.getElementById('status');
            const runBtn = document.getElementById('runBtn');
            const messageEl = document.getElementById('message');
            let cy;
            let ws;
            let running = false;

            function log(line){
                const ts = new Date().toISOString();
                eventsEl.textContent += `[${ts}] ${line}\n`;
                eventsEl.scrollTop = eventsEl.scrollHeight;
            }

            function setRunning(v){
                running = v;
                runBtn.disabled = v;
                statusEl.textContent = v ? 'Running' : 'Idle';
            }

            async function fetchGraph(){
                const res = await fetch('/api/graph');
                if(!res.ok) throw new Error('Failed to load graph');
                return await res.json();
            }

            function buildGraph(g){
                        cy = cytoscape({
                    container: document.getElementById('graph'),
                    elements: [
                        ...g.nodes.map(n => ({ data: n.data, classes: n.classes || '' })),
                        ...g.edges.map(e => ({ data: e.data, classes: e.classes || '' })),
                    ],
                            layout: {
                                name: 'breadthfirst', directed: true,
                                spacingFactor: 1.2, animate: false,
                                roots: `#${g.start}`
                            },
                    style: [
                                { selector: 'node', style: {
                                    'label': 'data(label)',
                                    'text-valign': 'center', 'text-halign': 'center',
                                    'shape': 'round-rectangle',
                                    'background-color': '#f0f7ff',
                                    'border-width': 2, 'border-color': '#aaa',
                                    'width': 'label', 'height': 'label', 'padding': '6px'
                                }},
                                { selector: 'node.fanin', style: {
                                    'shape': 'ellipse',
                                    'background-color': '#faebaf',
                                }},
                                { selector: 'edge', style: {
                                    'curve-style': 'bezier', 'target-arrow-shape': 'triangle', 'width': 1,
                                    'line-color': '#999', 'target-arrow-color': '#999'
                                }},
                                { selector: 'edge.conditional', style: {
                                    'line-style': 'dashed'
                                }},
                                { selector: 'edge.edge-active', style: {
                                    'width': 3,
                                    'line-color': '#2563eb', 'target-arrow-color': '#2563eb'
                                }},
                        { selector: 'node.pending', style: { 'border-color': '#b0b0b0' }},
                        { selector: 'node.active', style: { 'border-color': '#2563eb' }},
                        { selector: 'node.finished', style: { 'border-color': '#111827' }},
                        { selector: `#${g.start}`, style: { 'background-color': '#dcfce7' }},
                    ],
                });
                // initialize all nodes as pending
                cy.nodes().addClass('pending');
            }

            function connectWS(){
                const protocol = location.protocol === 'https:' ? 'wss' : 'ws';
                ws = new WebSocket(`${protocol}://${location.host}/ws`);
                ws.onopen = () => log('WebSocket connected');
                ws.onclose = () => log('WebSocket closed');
                ws.onerror = (e) => log('WebSocket error: ' + (e?.message || 'unknown'));
                ws.onmessage = (ev) => {
                    try {
                        const msg = JSON.parse(ev.data);
                        if(msg.type === 'log') log(msg.message);
                        else if(msg.type === 'ExecutorInvokeEvent') {
                            const n = cy.$(`#${msg.executorId}`);
                            n.removeClass('pending finished');
                            n.addClass('active');
                            // highlight edges incoming to this node (either direct or via fan-in)
                            cy.edges(`[target = "${msg.executorId}"]`).addClass('edge-active');
                        } else if(msg.type === 'ExecutorCompletedEvent') {
                            const n = cy.$(`#${msg.executorId}`);
                            n.removeClass('pending active');
                            n.addClass('finished');
                            // highlight edges outgoing from this node
                            cy.edges(`[source = "${msg.executorId}"]`).addClass('edge-active');
                        } else if(msg.type === 'done') {
                            setRunning(false);
                            log('Workflow completed');
                        } else {
                            // generic display
                            log(JSON.stringify(msg));
                        }
                    } catch(err){ log('Bad message: ' + err); }
                };
            }

            async function init(){
                const g = await fetchGraph();
                buildGraph(g);
                connectWS();
            }

            runBtn.addEventListener('click', () => {
                if (!ws || ws.readyState !== WebSocket.OPEN) { log('WebSocket not ready'); return; }
                if (running) { log('Run already in progress'); return; }
                const text = messageEl.value || '';
                ws.send(JSON.stringify({ action: 'run', message: text }));
                setRunning(true);
                log('Run triggered');
            });

            init();
        </script>
    </body>
</html>
        """

        running_flag: dict[str, bool] = {"running": False}

        def index(_: Any) -> HTMLResponse:
            return HTMLResponse(INDEX_HTML)

        def graph(_: Any) -> JSONResponse:
            return JSONResponse(_graph_json())

        async def ws_endpoint(websocket: WebSocket) -> None:
            await websocket.accept()
            try:
                while True:
                    data = await websocket.receive_json()
                    if not isinstance(data, dict):
                        await websocket.send_json({"type": "log", "message": "Invalid message"})
                        continue
                    if data.get("action") != "run":
                        await websocket.send_json({"type": "log", "message": "Unknown action"})
                        continue
                    if running_flag["running"]:
                        await websocket.send_json({"type": "log", "message": "Run already in progress"})
                        continue

                    running_flag["running"] = True
                    message = str(data.get("message", ""))

                    async def _run_and_stream(_message: str) -> None:
                        try:
                            async for event in self._workflow.run_streaming(_message):
                                # Stream minimal, structured updates
                                etype = event.__class__.__name__
                                payload: dict[str, Any] = {"type": etype}
                                # Executor events expose executor_id
                                if hasattr(event, "executor_id"):
                                    payload["executorId"] = event.executor_id  # type: ignore[attr-defined]
                                # Include request info for potential future use
                                if etype == "RequestInfoEvent":
                                    payload.update({
                                        "requestId": getattr(event, "request_id", None),
                                        "sourceExecutorId": getattr(event, "source_executor_id", None),
                                        "requestType": getattr(getattr(event, "request_type", None), "__name__", None),
                                    })
                                await websocket.send_json(payload)
                        except Exception as ex:  # pragma: no cover - defensive
                            await websocket.send_json({"type": "log", "message": f"Error: {ex}"})
                        finally:
                            running_flag["running"] = False
                            with contextlib.suppress(Exception):
                                await websocket.send_json({"type": "done"})

                    # Kick off without overlapping runs; await directly to serialize per client
                    await _run_and_stream(message)
            except Exception:
                # Client disconnected or server shutting down
                running_flag["running"] = False
            finally:
                with contextlib.suppress(Exception):
                    await websocket.close()

        app = Starlette(
            routes=[
                Route("/", endpoint=index),
                Route("/api/graph", endpoint=graph),
                WebSocketRoute("/ws", endpoint=ws_endpoint),
            ]
        )

        # Run the ASGI server until cancelled
        config = uvicorn.Config(app=app, host="127.0.0.1", port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

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
