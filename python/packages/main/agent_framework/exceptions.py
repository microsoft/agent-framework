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
