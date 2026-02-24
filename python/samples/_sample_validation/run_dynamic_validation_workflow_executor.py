# Copyright (c) Microsoft. All rights reserved.

from collections.abc import Sequence

from _sample_validation.const import WORKER_COMPLETED
from _sample_validation.create_dynamic_workflow_executor import CoordinatorStart
from _sample_validation.models import ExecutionResult, RunResult, RunStatus, SampleInfo, WorkflowCreationResult
from agent_framework import Executor, WorkflowContext, handler
from agent_framework.github import GitHubCopilotAgent


async def stop_agents(agents: Sequence[GitHubCopilotAgent]) -> None:
    """Stop all GitHub Copilot agents used by the nested workflow."""
    for agent in agents:
        try:
            await agent.stop()
        except Exception:
            continue


class RunDynamicValidationWorkflowExecutor(Executor):
    """Executor that runs the nested workflow created in the previous step."""

    def __init__(self) -> None:
        super().__init__(id="run_dynamic_workflow")

    @handler
    async def run(self, creation: WorkflowCreationResult, ctx: WorkflowContext[ExecutionResult]) -> None:
        """Run the nested workflow and emit execution results."""
        if creation.workflow is None:
            await ctx.send_message(ExecutionResult(results=[]))
            return

        print("\nRunning nested batched workflow...")
        print("-" * 80)

        try:
            remaining_sample_counts = len(creation.samples)
            result: ExecutionResult | None = None
            async for event in creation.workflow.run(CoordinatorStart(samples=creation.samples), stream=True):
                if event.type == "output" and isinstance(event.data, ExecutionResult):
                    result = event.data  # type: ignore
                elif event.type == WORKER_COMPLETED and isinstance(event.data, SampleInfo):  # type: ignore
                    remaining_sample_counts -= 1
                    print(
                        f"Completed validation for sample: {event.data.relative_path:<80} | "
                        f"Remaining: {remaining_sample_counts:>4}"
                    )

            if result is not None:
                await ctx.send_message(result)
            else:
                fallback_results = [
                    RunResult(
                        sample=sample,
                        status=RunStatus.ERROR,
                        output="",
                        error="Nested workflow did not return an ExecutionResult.",
                    )
                    for sample in creation.samples
                ]
                await ctx.send_message(ExecutionResult(results=fallback_results))
        finally:
            await stop_agents(creation.agents)
