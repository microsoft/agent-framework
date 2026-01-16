# Copyright (c) Microsoft. All rights reserved.

from ..exceptions import AgentFrameworkException


class WorkflowException(AgentFrameworkException):
    """Base exception for workflow errors."""

    pass


class WorkflowRunnerException(WorkflowException):
    """Base exception for workflow runner errors."""

    pass


class WorkflowConvergenceException(WorkflowRunnerException):
    """Exception raised when a workflow runner fails to converge within the maximum iterations."""

    pass


class WorkflowCheckpointException(WorkflowRunnerException):
    """Exception raised for errors related to workflow checkpoints."""

    pass
