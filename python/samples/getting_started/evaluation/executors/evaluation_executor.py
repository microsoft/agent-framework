# Copyright (c) Microsoft. All rights reserved.

from enum import Enum

from agent_framework.workflow import (
    AgentExecutorResponse,
    Executor,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

from azure.ai.projects.models import (
    EvaluatorConfiguration,
)

from dataclasses import dataclass

from dotenv import load_dotenv
load_dotenv()

from utils import create_mock_evaluation_workflow, run_evaluation_workflow
from shared_types import EvaluationExecutorResponse


class EvaluationExecutorType(Enum):
    NONE = "none" # Not initialized
    LOCAL_CONFIG = "local_config" # Create and run evaluation workflow with configurations
    LOCAL_WORKFLOW = "local_workflow" # Run the evaluation workflow from YAML file
    REMOTE_WORKFLOW = "remote_workflow" # Run the evaluation workflow from agent framework


class EvaluationExecutor(Executor):
    def __init__(self, id: str | None = None):
        super().__init__(id)
        self._type = EvaluationExecutorType.NONE
        self._workflow_id = None
        self._workflow_file_path = None
        self._evaluators = None
        self._evaluation_config = None

    # Use case 1: workflow from agent service, it'll trigger an AgentExecutor
    def set_workflow_id(self, workflow_id: str) -> None:
        self._workflow_id = workflow_id
        self._type = EvaluationExecutorType.REMOTE_WORKFLOW

    # Use case 2: workflow from local YAML file
    def set_local_workflow(self, file_path: str) -> None:
        # Instead of loading YAML file, the demo uses a mock workflow
        self._workflow = create_mock_evaluation_workflow()
        self._type = EvaluationExecutorType.LOCAL_WORKFLOW

    # Use case 3: workflow from evaluator configs and evalaution config
    def add_workflow_evaluator(self, evaluator: EvaluatorConfiguration) -> None:
        self._evaluators = self.evaluators or []
        self._evaluators.append(evaluator)
        self._type = EvaluationExecutorType.LOCAL_CONFIG

    def set_workflow_evaluation_config(self, evaluation_config: EvaluatorConfiguration) -> None:
        self._evaluation_config = evaluation_config
        self._type = EvaluationExecutorType.LOCAL_CONFIG

    @handler
    async def run(self, request: AgentExecutorResponse, ctx: WorkflowContext[WorkflowCompletedEvent | EvaluationExecutorResponse]) -> None:
        match self._type:
            case EvaluationExecutorType.NONE:
                raise ValueError("EvaluationExecutor is not configured with a workflow.")
            case EvaluationExecutorType.LOCAL_CONFIG:
                raise NotImplementedError("Local configuration evaluation is not implemented in this demo.")
            case EvaluationExecutorType.LOCAL_WORKFLOW:
                request.thread_id = "[mock-thread-id]"
                request.run_id = "[mock-run-id]"
                result = await run_evaluation_workflow(self._workflow, request.thread_id, request.run_id)
                response = EvaluationExecutorResponse(
                    agent_thread_id=request.thread_id,
                    agent_run_id=request.run_id,
                    evaluation_run_id=result.name,
                )
                await ctx.send_message(response)
            case EvaluationExecutorType.REMOTE_WORKFLOW:
                raise NotImplementedError("Remote workflow evaluation is not implemented in this demo.")

        # await _run_workflow(request, TRAVEL_AGENT_EXECUTOR_ID)

        # shared_state = await ctx.get_shared_state(TRAVEL_AGENT_EXECUTOR_ID)
        # text = f"Request: {shared_state.get('request')}\nResponse: {shared_state.get('response')}"
        # await ctx.send_message(text)
