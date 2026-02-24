# Copyright (c) Microsoft. All rights reserved.

import logging
from collections import deque
from dataclasses import dataclass

from _sample_validation.const import WORKER_COMPLETED
from _sample_validation.discovery import DiscoveryResult
from _sample_validation.models import (
    ExecutionResult,
    RunResult,
    RunStatus,
    SampleInfo,
    ValidationConfig,
    WorkflowCreationResult,
)
from agent_framework import (
    Executor,
    Message,
    Workflow,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    handler,
)
from agent_framework.github import GitHubCopilotAgent
from copilot.types import PermissionRequest, PermissionRequestResult
from pydantic import BaseModel
from typing_extensions import Never

logger = logging.getLogger(__name__)


class AgentResponseFormat(BaseModel):
    status: str
    output: str
    error: str


@dataclass
class CoordinatorStart:
    samples: list[SampleInfo]


@dataclass
class WorkerFreed:
    worker_id: str


class BatchCompletion:
    pass


AgentInstruction = (
    "You are validating exactly one Python sample.\n"
    "Analyze the sample code and execute it. Determine if it runs successfully, fails, or times out.\n"
    "The sample can be interactive. If it is interactive, respond to the sample when prompted "
    "based on your analysis of the code. You do not need to consult human on what to respond\n"
    "Return ONLY valid JSON with this schema:\n"
    "{\n"
    '  "status": "success|failure|timeout|error",\n'
    '  "output": "short summary of the result and what you did if the sample was interactive",\n'
    '  "error": "error details or empty string"\n'
    "}\n\n"
)


def parse_agent_json(text: str) -> AgentResponseFormat:
    """Parse JSON object from an agent response."""
    stripped = text.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        return AgentResponseFormat.model_validate_json(stripped)

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")

    return AgentResponseFormat.model_validate_json(stripped[start : end + 1])


def status_from_text(value: str) -> RunStatus:
    """Convert a string value to RunStatus with safe fallback."""
    normalized = value.strip().lower()
    for status in RunStatus:
        if status.value == normalized:
            return status
    return RunStatus.ERROR


def prompt_permission(request: PermissionRequest, context: dict[str, str]) -> PermissionRequestResult:
    """Permission handler that always approves."""
    kind = request.get("kind", "unknown")
    logger.debug(f"[Permission Request: {kind}] ({context})Automatically approved for sample validation.")
    return PermissionRequestResult(kind="approved")


class CustomAgentExecutor(Executor):
    """Executor that runs a GitHub Copilot agent and returns its response.

    We need the custom executor to wrap the agent call in a try/except to ensure that any exceptions are caught and
    returned as error responses, otherwise an exception in one agent could crash the entire workflow.
    """

    def __init__(self, agent: GitHubCopilotAgent):
        super().__init__(id=agent.id)
        self.agent = agent

    @handler
    async def handle_task(self, sample: SampleInfo, ctx: WorkflowContext[WorkerFreed | RunResult]) -> None:
        """Execute one sample task and notify collector + coordinator."""
        try:
            response = await self.agent.run([
                Message(role="user", text=f"Validate the following sample:\n\n{sample.relative_path}")
            ])
            result_payload = parse_agent_json(response.text)
            result = RunResult(
                sample=sample,
                status=status_from_text(result_payload.status),
                output=result_payload.output,
                error=result_payload.error,
            )
        except Exception as ex:
            logger.error(f"Error executing agent {self.agent.id}: {ex}")
            result = RunResult(
                sample=sample,
                status=RunStatus.ERROR,
                output="",
                error=str(ex),
            )

        await ctx.send_message(result, target_id="collector")
        await ctx.send_message(WorkerFreed(worker_id=self.id), target_id="coordinator")

        await ctx.add_event(WorkflowEvent(WORKER_COMPLETED, sample))  # type: ignore


class BatchCoordinatorExecutor(Executor):
    """Dispatch sample tasks to worker executors in bounded batches."""

    def __init__(self, worker_ids: list[str], max_parallel_workers: int) -> None:
        super().__init__(id="coordinator")
        self._worker_ids = worker_ids
        self._max_parallel_workers = max(1, max_parallel_workers)
        self._pending: deque[SampleInfo] = deque()
        self._inflight: set[str] = set()

    async def _assign_next(self, worker_id: str, ctx: WorkflowContext[SampleInfo | BatchCompletion]) -> None:
        if not self._pending:
            # No more samples to assign
            if not self._inflight:
                # All tasks are completed, notify collector and exit
                await ctx.send_message(BatchCompletion(), target_id="collector")
            return

        sample = self._pending.popleft()
        self._inflight.add(worker_id)
        # Messages will get queued in the runner until the next superstep when all workers are freed,
        # thus achieving automatic batching without needing complex synchronization logic
        await ctx.send_message(sample, target_id=worker_id)

    @handler
    async def on_start(self, start: CoordinatorStart, ctx: WorkflowContext[SampleInfo | BatchCompletion]) -> None:
        """Initialize queue and dispatch first wave of tasks."""
        self._pending = deque(start.samples)
        self._inflight.clear()

        for worker_id in self._worker_ids[: self._max_parallel_workers]:
            await self._assign_next(worker_id, ctx)

    @handler
    async def on_worker_freed(self, freed: WorkerFreed, ctx: WorkflowContext[SampleInfo | BatchCompletion]) -> None:
        """Dispatch next queued sample when a worker finishes."""
        self._inflight.discard(freed.worker_id)
        await self._assign_next(freed.worker_id, ctx)


class CollectorExecutor(Executor):
    """Collect per-sample results and emit the final execution result."""

    def __init__(self) -> None:
        super().__init__(id="collector")
        self._results: list[RunResult] = []

    @handler
    async def on_all(self, batch_completion: BatchCompletion, ctx: WorkflowContext[Never, ExecutionResult]) -> None:
        """Receive all results at once and emit final output."""
        await ctx.yield_output(ExecutionResult(results=self._results))

    @handler
    async def on_item(self, item: RunResult, ctx: WorkflowContext) -> None:
        """Record a result and emit output when all expected results arrive."""
        self._results.append(item)


class CreateConcurrentValidationWorkflowExecutor(Executor):
    """Executor that builds a nested concurrent workflow with one agent per sample."""

    def __init__(self, config: ValidationConfig):
        super().__init__(id="create_dynamic_workflow")
        self.config = config

    @handler
    async def create(
        self,
        discovery: DiscoveryResult,
        ctx: WorkflowContext[WorkflowCreationResult],
    ) -> None:
        """Create a nested workflow with a coordinator + worker fan-out/fan-in."""
        sample_count = len(discovery.samples)
        print(f"\nCreating nested batched workflow for {sample_count} samples...")

        if sample_count == 0:
            await ctx.send_message(WorkflowCreationResult(samples=[], workflow=None, agents=[]))
            return

        agents: list[GitHubCopilotAgent] = []
        workers: list[CustomAgentExecutor] = []

        for index, sample in enumerate(discovery.samples, start=1):
            agent_id = f"sample_validator_{index}({sample.relative_path})"
            agent = GitHubCopilotAgent(
                id=agent_id,
                name=agent_id,
                instructions=AgentInstruction,
                default_options={"on_permission_request": prompt_permission, "timeout": 180},  # type: ignore
            )
            agents.append(agent)

            workers.append(CustomAgentExecutor(agent))

        coordinator = BatchCoordinatorExecutor(
            worker_ids=[worker.id for worker in workers],
            max_parallel_workers=self.config.max_parallel_workers,
        )
        collector = CollectorExecutor()

        nested_builder = WorkflowBuilder(start_executor=coordinator, output_executors=[collector])
        nested_builder.add_edge(coordinator, collector)
        for worker in workers:
            nested_builder.add_edge(coordinator, worker)
            nested_builder.add_edge(worker, coordinator)
            nested_builder.add_edge(worker, collector)
        nested_workflow: Workflow = nested_builder.build()

        await ctx.send_message(
            WorkflowCreationResult(
                samples=discovery.samples,
                workflow=nested_workflow,
                agents=agents,
            )
        )
