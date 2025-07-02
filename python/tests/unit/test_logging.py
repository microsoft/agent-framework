# Copyright (c) Microsoft. All rights reserved.

import pytest

from agent_framework import get_logger
from agent_framework.exceptions import AgentFrameworkException


def test_get_logger():
    """Test that the logger is created with the correct name."""
    logger = get_logger()
    assert logger.name == "agent_framework"


def test_get_logger_custom_name():
    """Test that the logger can be created with a custom name."""
    custom_name = "agent_framework.custom"
    logger = get_logger(custom_name)
    assert logger.name == custom_name


def test_get_logger_invalid_name():
    """Test that an exception is raised for an invalid logger name."""
    with pytest.raises(AgentFrameworkException, match="Logger name must start with 'agent_framework'."):
        get_logger("invalid_name")


def test_logger_format():
    """Test that the logger format is correctly set."""
    logger = get_logger()

    assert logger.config.formatter._fmt == "[%(asctime)s - %(name)s:%(lineno)d - %(levelname)s] %(message)s"
    assert logger.config.formatter.datefmt == "%Y-%m-%d %H:%M:%S"
