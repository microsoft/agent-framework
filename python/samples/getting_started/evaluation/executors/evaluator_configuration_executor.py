from agent_framework.workflow import (
    Executor,
    WorkflowContext,
    handler,
)

from azure.ai.projects.models import (
    EvaluatorConfiguration,
)


class EvaluatorConfigurationExecutor(Executor):
    def __init__(self, id: str | None = None, evaluator_id: str | None = None):
        super().__init__(id)
        self._evaluator_id = evaluator_id
        self._name = ""
        self._init_params = None
        self._data_mapping = None

    def set_name(self, name: str | None) -> None:
        self._name = name
    
    def set_init_params(self, init_params: dict | None) -> None:
        self._init_params = init_params

    def set_data_mapping(self, data_mapping: dict | None) -> None:
        self._data_mapping = data_mapping

    @handler
    async def run(self, id: str, ctx: WorkflowContext[EvaluatorConfiguration]) -> None:
        evaluator_config = EvaluatorConfiguration(
            id=self._evaluator_id,
            init_params=self._init_params,
            data_mapping=self._data_mapping,
        )
        await ctx.send_message(evaluator_config)
