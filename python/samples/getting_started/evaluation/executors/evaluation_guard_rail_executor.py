# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from agent_framework.workflow import (
    Executor,
    WorkflowContext,
    handler,
)

from dotenv import load_dotenv
load_dotenv()

from shared_types import TravelAgentCompleted, EvaluatorGuardRailExecutorResponse, EvaluationExecutorResponse
from executors.evaluation_executor import EvaluationExecutor


"""Question: how to implement this class to make it generic?"""
class EvaluationGuardRailExecutor(EvaluationExecutor):
    def __init__(self, id = None):
        super().__init__(id)
        self._mock_should_retry = True   # mock retry for the first time

    @handler
    async def run(self, data: EvaluationExecutorResponse, ctx: WorkflowContext[EvaluatorGuardRailExecutorResponse]) -> None:
        should_retry = self._mock_should_retry
        self._mock_should_retry = False  # reset mock after first use

        # TODO: should poll for evaluation results here

        response = EvaluatorGuardRailExecutorResponse(
            should_retry=should_retry,
            data=data
        )
        await ctx.send_message(response)
