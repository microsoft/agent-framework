import os

from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from agent_framework.workflow import (
    Executor,
    WorkflowCompletedEvent,
    WorkflowContext,
    handler,
)

from azure.ai.projects.models import (
    Evaluation,
    InputDataset,
    EvaluatorConfiguration,
)


class EvaluationRunExecutor(Executor):
    @handler
    async def run(self, evaluator_configurations: list[EvaluatorConfiguration], ctx: WorkflowContext[WorkflowCompletedEvent]) -> None:
        azure_openai_endpoint = os.getenv("AOAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        project_endpoint = os.getenv("PROJECT_ENDPOINT")
        dataset_id = os.getenv("DATASET_ID")
        evaluators = { evaluator_configuration.id.rsplit('/', 1)[-1]: evaluator_configuration for evaluator_configuration in evaluator_configurations }

        evaluation = Evaluation(
            display_name=os.getenv("EVALUATION_ID"),
            evaluators=evaluators,
            data=InputDataset(id=dataset_id),
        )

        with DefaultAzureCredential(exclude_interactive_browser_credential=False) as credential:
            with AIProjectClient(endpoint=project_endpoint, credential=credential) as project_client:
                evaluation_response: Evaluation = project_client.evaluations.create(
                    evaluation,
                    headers={
                        "Content-Type": "application/json",
                        "model-endpoint": azure_openai_endpoint,
                        "api-key": api_key,
                    }
                )
                print(evaluation_response)

        await ctx.add_event(WorkflowCompletedEvent(data=evaluation_response))
        # await ctx.add_event(WorkflowCompletedEvent(data="[mock-evaluation_response.id]"))
