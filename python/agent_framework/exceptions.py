# Copyright (c) Microsoft. All rights reserved.


class AgentFrameworkException(Exception):
    """Base class for exceptions in the Agent Framework."""

    pass


class ContentException(AgentFrameworkException):
    """Base class for all content exceptions."""

    pass


class ContentInitializationError(ContentException):
    """An error occurred while initializing the content."""

    pass


class ContentAdditionException(ContentException):
    """An error occurred while adding content."""

    pass


class FunctionCallInvalidArgumentsException(ContentException):
    """An error occurred while validating the function arguments."""

    pass


class FunctionCallInvalidNameException(ContentException):
    """An error occurred while validating the function name."""

    pass


class AgentException(AgentFrameworkException):
    """Base class for all agent exceptions."""

    pass


class AgentExecutionException(AgentException):
    """An error occurred while executing the agent."""

    pass
