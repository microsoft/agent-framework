from attr import dataclass


class TravelAgentCompleted:
    pass


@dataclass
class EvaluationExecutorResponse:
    agent_thread_id: str
    agent_run_id: str
    evaluation_run_id: str


@dataclass
class EvaluatorGuardRailExecutorResponse:
    should_retry: bool
    data: EvaluationExecutorResponse
