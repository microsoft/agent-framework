# Copyright (c) Microsoft. All rights reserved.

"""Exception hierarchy used across Agent Framework core and connectors.

See python/CODING_STANDARD.md § Exception Hierarchy for design rationale
and guidance on choosing the correct exception class.
"""

import logging
from typing import Any, Literal

logger = logging.getLogger("agent_framework")


class AgentFrameworkException(Exception):
    """Base exception for the Agent Framework.

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


# region Agent Exceptions


class AgentException(AgentFrameworkException):
    """Base class for all agent exceptions."""

    pass


class AgentInvalidAuthException(AgentException):
    """An authentication error occurred in an agent."""

    pass


class AgentInvalidRequestException(AgentException):
    """An invalid request was made to an agent."""

    pass


class AgentInvalidResponseException(AgentException):
    """An invalid or unexpected response was received from an agent."""

    pass


class AgentContentFilterException(AgentException):
    """A content filter was triggered by an agent."""

    pass


# endregion

# region Chat Client Exceptions


class ChatClientException(AgentFrameworkException):
    """Base class for all chat client exceptions."""

    pass


class ChatClientInvalidAuthException(ChatClientException):
    """An authentication error occurred in a chat client."""

    pass


class ChatClientInvalidRequestException(ChatClientException):
    """An invalid request was made to a chat client."""

    pass


class ChatClientInvalidResponseException(ChatClientException):
    """An invalid or unexpected response was received from a chat client."""

    pass


class ChatClientContentFilterException(ChatClientException):
    """A content filter was triggered by a chat client."""

    pass


# endregion

# region Integration Exceptions


class IntegrationException(AgentFrameworkException):
    """Base class for all external service/dependency integration exceptions."""

    pass


class IntegrationInitializationError(IntegrationException):
    """A wrapped dependency/service lifecycle failure occurred during setup."""

    pass


class IntegrationInvalidAuthException(IntegrationException):
    """An authentication error occurred in an external integration."""

    pass


class IntegrationInvalidRequestException(IntegrationException):
    """An invalid request was made to an external integration."""

    pass


class IntegrationInvalidResponseException(IntegrationException):
    """An invalid or unexpected response was received from an external integration."""

    pass


class IntegrationContentFilterException(IntegrationException):
    """A content filter was triggered by an external integration."""

    pass


# endregion

# region Content Exceptions


class ContentError(AgentFrameworkException):
    """An error occurred while processing content."""

    pass


class AdditionItemMismatch(ContentError):
    """A type mismatch occurred while merging content items."""

    pass


# endregion

# region Tool Exceptions


class ToolException(AgentFrameworkException):
    """Base class for all tool-related exceptions."""

    pass


class ToolExecutionException(ToolException):
    """A tool or prompt call failed at runtime."""

    pass


class UserInputRequiredException(ToolException):
    """Raised when a tool wrapping a sub-agent requires user input to proceed.

    This exception carries the ``user_input_request`` Content items emitted by
    the sub-agent (e.g., ``oauth_consent_request``, ``function_approval_request``)
    so the tool invocation layer can propagate them to the parent agent's response
    instead of swallowing them as a generic tool error.

    Args:
        contents: The user-input-request Content items from the sub-agent response.
        message: Human-readable description of why user input is needed.
    """

    def __init__(
        self,
        contents: list[Any],
        message: str = "Tool requires user input to proceed.",
    ) -> None:
        """Create a UserInputRequiredException.

        Args:
            contents: The user-input-request Content items from the sub-agent response.
            message: Human-readable description of why user input is needed.
        """
        super().__init__(message, log_level=None)
        self.contents = contents


# endregion

# region Middleware Exceptions


class MiddlewareException(AgentFrameworkException):
    """An error occurred during middleware execution."""

    pass


# endregion

# region Settings Exceptions


class SettingNotFoundError(AgentFrameworkException):
    """A required setting could not be resolved from any source."""

    pass


# endregion

# region Workflow Exceptions


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


# endregion
