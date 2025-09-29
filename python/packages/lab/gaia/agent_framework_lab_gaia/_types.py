# Copyright (c) Microsoft. All rights reserved.

"""Common types for agent evaluation."""

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

__all__ = [
    "Evaluation",
    "Evaluator",
    "Prediction",
    "Task",
    "TaskResult",
    "TaskRunner",
]


@dataclass
class Task:
    """Represents a task to be evaluated."""

    task_id: str
    question: str
    answer: str | None = None
    level: int | None = None
    file_name: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass
class Prediction:
    """Represents a prediction made by an agent for a task."""

    prediction: str
    messages: list[Any] | None = None
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.messages is None:
            self.messages = []


@dataclass
class Evaluation:
    """Represents the evaluation result of a prediction."""

    is_correct: bool
    score: float
    details: dict[str, Any] | None = None


@dataclass
class TaskResult:
    """Complete result for a single task evaluation."""

    task_id: str
    task: Task
    prediction: Prediction
    evaluation: Evaluation
    runtime_seconds: float | None = None
    error: str | None = None


@runtime_checkable
class TaskRunner(Protocol):
    """Protocol for running tasks."""

    async def __call__(self, task: Task) -> Prediction:
        """Run a single task and return the prediction."""
        ...


@runtime_checkable
class Evaluator(Protocol):
    """Protocol for evaluating predictions."""

    async def __call__(self, task: Task, prediction: Prediction) -> Evaluation:
        """Evaluate a prediction for a given task."""
        ...
