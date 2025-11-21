# Copyright (c) Microsoft. All rights reserved.

import logging

from .exceptions import AgentFrameworkException

__all__ = ["get_logger", "setup_logging"]


def setup_logging() -> None:
    """Setup the logging configuration for the agent framework."""
    logging.basicConfig(
        format="[%(asctime)s - %(pathname)s:%(lineno)d - %(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def get_logger(name: str = "agent_framework") -> logging.Logger:
    """Get a logger with the specified name, defaulting to 'agent_framework'.

    Args:
        name (str): The name of the logger. Defaults to 'agent_framework'.

    Returns:
        logging.Logger: The configured logger instance.
    """
    if not name.startswith("agent_framework"):
        raise AgentFrameworkException("Logger name must start with 'agent_framework'.")
    return logging.getLogger(name)
