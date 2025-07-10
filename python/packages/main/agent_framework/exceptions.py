# Copyright (c) Microsoft. All rights reserved.


class AgentFrameworkException(Exception):
    """Base class for exceptions in the Agent Framework."""

    pass


class AgentException(AgentFrameworkException):
    """Base class for all agent exceptions."""

    pass


class AgentExecutionException(AgentException):
    """An error occurred while executing the agent."""

    pass
