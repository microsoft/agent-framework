# Copyright (c) Microsoft. All rights reserved.

"""A deterministic workflow used to demonstrate durable background requests.

The local pipeline has four stages:

``ingest -> transform -> validate -> finalize``

With ``resilient_background=True``, the hosting layer durably records workflow
progress. If the host stops while a request is running, a replacement host
continues the same request from its latest saved progress rather than starting
the entire workflow again.

``demo.py`` interrupts the host twice and verifies that completed stages are
preserved, interrupted work continues, and the original response completes
with the expected output. No model deployment, external service, or credential
is required.

Production note: a stage interrupted before its progress is saved may run
again. External side effects should therefore use idempotency keys or upsert
semantics.
"""

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

# Load configuration before importing the hosting stack, whose telemetry distro
# installs its default resource-detector list during import.
load_dotenv()

# Azure Monitor Statsbeat probes the Azure instance metadata endpoint after a
# short warmup. Disable only those internal SDK metrics when no Application
# Insights connection is configured, avoiding a noisy local-only connection
# error without disabling the sample's normal traces and metrics.
if not os.environ.get("APPLICATIONINSIGHTS_CONNECTION_STRING"):
    os.environ.setdefault("APPLICATIONINSIGHTS_STATSBEAT_DISABLED_ALL", "true")

from agent_framework import Message, WorkflowBuilder, WorkflowContext, executor  # noqa: E402
from agent_framework_foundry_hosting import ResponsesHostServer  # noqa: E402
from azure.ai.agentserver.responses import ResponsesServerOptions  # noqa: E402
from typing_extensions import Never  # noqa: E402

# Keep durable workflow state in built-in, serializable types.
PipelineState = dict[str, Any]


def _state_dir() -> Path:
    """Directory where audit.jsonl and stage markers are written.

    Defaults to a folder next to this file for ad-hoc manual runs, but
    ``demo.py`` always overrides ``WORKFLOW_STATE_DIR`` to an isolated
    temporary directory so demo runs never touch real user state.
    """
    raw = os.environ.get("WORKFLOW_STATE_DIR")
    path = Path(raw) if raw else Path(__file__).parent / ".workflow_state"
    (path / "markers").mkdir(parents=True, exist_ok=True)
    return path


def _stage_delay_seconds() -> float:
    """How long each stage sleeps to simulate work. See .env.example."""
    return float(os.environ.get("WORKFLOW_STAGE_DELAY_SECONDS", "4"))


async def _run_stage(stage_id: str) -> None:
    """Simulate work for *stage_id*, then durably record that it ran.

    The delay happens before the audit entry so the demo can interrupt a stage
    while it is still in progress. Only completed stage attempts are recorded.
    """
    await asyncio.sleep(_stage_delay_seconds())

    state_dir = _state_dir()
    pid = os.getpid()
    timestamp = datetime.now(timezone.utc).isoformat()
    record = {"stage": stage_id, "pid": pid, "timestamp": timestamp}

    # Append-only so the demo can detect if completed work was repeated.
    with (state_dir / "audit.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    # The marker lets demo.py reliably interrupt the following stage.
    (state_dir / "markers" / f"{stage_id}.json").write_text(json.dumps(record), encoding="utf-8")

    # Visible progress marker for anyone watching the server's stdout.
    print(f"[{stage_id}] complete (pid={pid})", flush=True)


@executor(id="ingest")
async def ingest(messages: list[Message], ctx: WorkflowContext[PipelineState, str]) -> None:
    """Stage 1: accept the incoming request and start the pipeline state."""
    await _run_stage("ingest")
    prompt = messages[0].text if messages else ""
    state: PipelineState = {"request_summary": prompt[:200], "stages_completed": ["ingest"]}
    await ctx.yield_output(f"[ingest] received request: {state['request_summary']!r}")
    await ctx.send_message(state)


@executor(id="transform")
async def transform(state: PipelineState, ctx: WorkflowContext[PipelineState, str]) -> None:
    """Stage 2: pretend to normalize/transform the request."""
    await _run_stage("transform")
    state["stages_completed"].append("transform")
    await ctx.yield_output(f"[transform] normalized request: {state['request_summary']!r}")
    await ctx.send_message(state)


@executor(id="validate")
async def validate(state: PipelineState, ctx: WorkflowContext[PipelineState, str]) -> None:
    """Stage 3: pretend to validate the transformed request."""
    await _run_stage("validate")
    state["stages_completed"].append("validate")
    await ctx.yield_output(f"[validate] validated request: {state['request_summary']!r}")
    await ctx.send_message(state)


@executor(id="finalize")
async def finalize(state: PipelineState, ctx: WorkflowContext[Never, str]) -> None:
    """Stage 4 (terminal): emit the single Workflow Output summary."""
    await _run_stage("finalize")
    state["stages_completed"].append("finalize")
    await ctx.yield_output(
        f"Pipeline complete for {state['request_summary']!r}. Stages executed: {', '.join(state['stages_completed'])}."
    )


def build_workflow():
    """Build the 4-stage deterministic pipeline with explicit output selection."""
    return (
        WorkflowBuilder(
            start_executor=ingest,
            # Only finalize's yield is the terminal Workflow Output.
            output_from=[finalize],
            # ingest/transform/validate yields are visible progress notes.
            intermediate_output_from=[ingest, transform, validate],
        )
        .add_chain([ingest, transform, validate, finalize])
        .build()
    )


def main() -> None:
    agent = build_workflow().as_agent(name="resilient-pipeline")

    # Durable background execution is host-managed; no workflow checkpoint
    # storage needs to be configured by the application.
    server = ResponsesHostServer(
        agent,
        options=ResponsesServerOptions(resilient_background=True),
    )
    server.run()


if __name__ == "__main__":
    main()
