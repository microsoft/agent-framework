from agent_framework.workflow import (
    Executor,
    WorkflowContext,
    handler,
)


"""Prepare the required context for evaluation, e.g. download agent run information"""
class EvaluationStartExecutor(Executor):
    @handler
    async def run(self, input: dict, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message("executor_id")
