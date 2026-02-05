# Copyright (c) Microsoft. All rights reserved.

import logging
from typing import Any, Literal

logger = logging.getLogger("agent_framework")


class AgentFrameworkException(Exception):
    """Base exceptions for the Agent Framework.

    Automatically logs the message as debug.
    """

    def __init__(
        self,
        message: str,
        inner_exception: Exception | None = None,
        log_level: Literal[0] | Literal[10] | Literal[20] | Literal[30] | Literal[40] | Literal[50] | None = 10,
        *args: Any,
        **kwargs: Any,
    ):
        """Create an AgentFrameworkException.

        This emits a debug log (by default), with the inner_exception if provided.
        """
        if log_level is not None:
            logger.log(log_level, message, exc_info=inner_exception)
        if inner_exception:
            super().__init__(message, inner_exception, *args)  # type: ignore
        super().__init__(message, *args)  # type: ignore


class AgentException(AgentFrameworkException):
    """Base class for all agent exceptions."""

    pass


class AgentExecutionException(AgentException):
    """An error occurred while executing the agent."""

    pass


class AgentInitializationError(AgentException):
    """An error occurred while initializing the agent."""

    pass


class AgentThreadException(AgentException):
    """An error occurred while managing the agent thread."""

    pass


class ChatClientException(AgentFrameworkException):
    """An error occurred while dealing with a chat client."""

    pass


class ChatClientInitializationError(ChatClientException):
    """An error occurred while initializing the chat client."""

    pass


# region Service Exceptions


class ServiceException(AgentFrameworkException):
    """Base class for all service exceptions."""

    pass


class ServiceInitializationError(ServiceException):
    """An error occurred while initializing the service."""

    pass


class ServiceResponseException(ServiceException):
    """Base class for all service response exceptions."""

    pass


class ServiceContentFilterException(ServiceResponseException):
    """An error was raised by the content filter of the service."""

    pass


class ServiceInvalidAuthError(ServiceException):
    """An error occurred while authenticating the service."""

    pass


class ServiceInvalidExecutionSettingsError(ServiceResponseException):
    """An error occurred while validating the execution settings of the service."""

    pass


class ServiceInvalidRequestError(ServiceResponseException):
    """An error occurred while validating the request to the service."""

    pass


class ServiceInvalidResponseError(ServiceResponseException):
    """An error occurred while validating the response from the service."""

    pass


class ToolException(AgentFrameworkException):
    """An error occurred while executing a tool."""

    pass


class ToolExecutionException(ToolException):
    """An error occurred while executing a tool."""

    pass


class AdditionItemMismatch(AgentFrameworkException):
    """An error occurred while adding two types."""

    pass


class MiddlewareException(AgentFrameworkException):
    """An error occurred during middleware execution."""

    pass


class ContentError(AgentFrameworkException):
    """An error occurred while processing content."""

    pass
