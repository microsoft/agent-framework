# Copyright (c) Microsoft. All rights reserved.

from agent_framework.workflow import (
    Executor,
    WorkflowContext,
    handler,
)

from dotenv import load_dotenv
load_dotenv()


class EvaluatorAgentExecutor(Executor):
    @handler
    async def run(self, id: str, ctx: WorkflowContext[str]) -> None:
        # await ctx.send_message(id)
        raise NotImplementedError("EvaluatorAgentExecutor is not implemented")
