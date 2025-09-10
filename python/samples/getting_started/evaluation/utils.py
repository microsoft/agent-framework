import os

from agent_framework.workflow import (
    Workflow,
    WorkflowBuilder,
    WorkflowCompletedEvent,
)

from executors.evaluation_start_executor import EvaluationStartExecutor
from executors.evaluator_configuration_executor import EvaluatorConfigurationExecutor
from executors.evaluation_run_executor import EvaluationRunExecutor


def create_mock_evaluation_workflow() -> Workflow:
    evaluation_start_flow = EvaluationStartExecutor(id="evaluation_start_flow")
    evaluator_configs = _create_evaluator_config_executors()
    evaluation_run = EvaluationRunExecutor(id="evaluation_run")

    workflow = (
        WorkflowBuilder()
            .set_start_executor(evaluation_start_flow)
            .add_fan_out_edges(evaluation_start_flow, evaluator_configs)
            .add_fan_in_edges(evaluator_configs, evaluation_run)
            .build()
    )
    return workflow


async def run_evaluation_workflow(workflow: Workflow, thread_id: str, run_id: str) -> None:
    completion_event = None
    agent_eval_input = {
        "thread_id": thread_id,
        "run_id": run_id,
    }
    async for event in workflow.run_streaming(agent_eval_input):
        if isinstance(event, WorkflowCompletedEvent):
            completion_event = event

    if completion_event:
        print(f"Completion Event received for evaluation workflow: {completion_event}")
    return completion_event.data if completion_event else None


def _create_evaluator_config_executors() -> list[EvaluatorConfigurationExecutor]:
    relevance_evaluator_config = EvaluatorConfigurationExecutor(id="evaluator_configuration:relevance", evaluator_id="azureai://built-in/evaluators/relevance")
    fluency_evaluator_config = EvaluatorConfigurationExecutor(id="evaluator_configuration:fluency", evaluator_id="azureai://built-in/evaluators/fluency")
    coherence_evaluator_config = EvaluatorConfigurationExecutor(id="evaluator_configuration:coherence", evaluator_id="azureai://built-in/evaluators/coherence")
    evaluator_configs = [
        relevance_evaluator_config,
        fluency_evaluator_config,
        coherence_evaluator_config,
    ]

    shared_azure_openai_deployment = os.getenv("EVALUATION_MODEL_DEPLOYMENT_NAME")
    shared_data_mapping = {"query": "${data.query}", "response": "${data.response}", "context": "${data.context}", "ground_truth": "${data.ground_truth}" }

    relevance_evaluator_config.set_data_mapping(shared_data_mapping)
    relevance_evaluator_config.set_init_params({
        "deployment_name": shared_azure_openai_deployment,
    })
    fluency_evaluator_config.set_data_mapping(shared_data_mapping)
    fluency_evaluator_config.set_init_params({
        "deployment_name": shared_azure_openai_deployment,
    })
    coherence_evaluator_config.set_data_mapping(shared_data_mapping)
    coherence_evaluator_config.set_init_params({
        "deployment_name": shared_azure_openai_deployment,
    })

    return evaluator_configs
