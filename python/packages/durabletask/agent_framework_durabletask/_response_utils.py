# Copyright (c) Microsoft. All rights reserved.

"""Shared utilities for handling AgentRunResponse parsing and validation."""

from typing import Any

from agent_framework import AgentRunResponse, get_logger
from pydantic import BaseModel

logger = get_logger("agent_framework.durabletask.response_utils")


def load_agent_response(agent_response: AgentRunResponse | dict[str, Any] | None) -> AgentRunResponse:
    """Convert raw payloads into AgentRunResponse instance.

    Args:
        agent_response: The response to convert, can be an AgentRunResponse, dict, or None

    Returns:
        AgentRunResponse: The converted response object

    Raises:
        ValueError: If agent_response is None
        TypeError: If agent_response is an unsupported type
    """
    if agent_response is None:
        raise ValueError("agent_response cannot be None")

    logger.debug("[load_agent_response] Loading agent response of type: %s", type(agent_response))

    if isinstance(agent_response, AgentRunResponse):
        return agent_response
    if isinstance(agent_response, dict):
        logger.debug("[load_agent_response] Converting dict payload using AgentRunResponse.from_dict")
        return AgentRunResponse.from_dict(agent_response)

    raise TypeError(f"Unsupported type for agent_response: {type(agent_response)}")


def ensure_response_format(
    response_format: type[BaseModel] | None,
    correlation_id: str,
    response: AgentRunResponse,
) -> None:
    """Ensure the AgentRunResponse value is parsed into the expected response_format.

    This function modifies the response in-place by parsing its value attribute
    into the specified Pydantic model format.

    Args:
        response_format: Optional Pydantic model class to parse the response value into
        correlation_id: Correlation ID for logging purposes
        response: The AgentRunResponse object to validate and parse

    Raises:
        ValueError: If response_format is specified but response.value cannot be parsed
    """
    if response_format is not None and not isinstance(response.value, response_format):
        response.try_parse_value(response_format)

        # Validate that parsing succeeded
        if not isinstance(response.value, response_format):
            raise ValueError(
                f"Response value could not be parsed into required format {response_format.__name__} "
                f"for correlation_id {correlation_id}"
            )

        logger.debug(
            "[ensure_response_format] Loaded AgentRunResponse.value for correlation_id %s with type: %s",
            correlation_id,
            type(response.value).__name__,
        )
