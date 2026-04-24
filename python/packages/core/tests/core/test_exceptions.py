# Copyright (c) Microsoft. All rights reserved.

"""Tests for the agent_framework.exceptions module."""

from __future__ import annotations

import logging
from typing import Any

import pytest

from agent_framework.exceptions import (
    AdditionItemMismatch,
    AgentContentFilterException,
    AgentException,
    AgentFrameworkException,
    AgentInvalidAuthException,
    AgentInvalidRequestException,
    AgentInvalidResponseException,
    ChatClientContentFilterException,
    ChatClientException,
    ChatClientInvalidAuthException,
    ChatClientInvalidRequestException,
    ChatClientInvalidResponseException,
    ContentError,
    IntegrationContentFilterException,
    IntegrationException,
    IntegrationInitializationError,
    IntegrationInvalidAuthException,
    IntegrationInvalidRequestException,
    IntegrationInvalidResponseException,
    MiddlewareException,
    SettingNotFoundError,
    ToolException,
    ToolExecutionException,
    UserInputRequiredException,
    WorkflowCheckpointException,
    WorkflowConvergenceException,
    WorkflowException,
    WorkflowRunnerException,
)


class TestAgentFrameworkExceptionBase:
    """Tests for the AgentFrameworkException base class."""

    def test_is_instance_of_exception(self) -> None:
        exc = AgentFrameworkException("test")
        assert isinstance(exc, Exception)

    def test_message_is_preserved(self) -> None:
        exc = AgentFrameworkException("something went wrong")
        assert str(exc) == "something went wrong"

    def test_args_contains_message(self) -> None:
        exc = AgentFrameworkException("msg")
        assert "msg" in exc.args

    def test_inner_exception_is_included_in_args(self) -> None:
        inner = ValueError("inner error")
        exc = AgentFrameworkException("outer", inner_exception=inner)
        assert "outer" in exc.args

    def test_no_inner_exception_by_default(self) -> None:
        exc = AgentFrameworkException("msg")
        # When no inner_exception, args should just contain the message
        assert exc.args == ("msg",)

    def test_default_log_level_is_debug(self, caplog: pytest.LogRecaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger="agent_framework"):
            AgentFrameworkException("debug message")
        assert "debug message" in caplog.text

    def test_log_level_warning(self, caplog: pytest.LogRecaptureFixture) -> None:
        with caplog.at_level(logging.WARNING, logger="agent_framework"):
            AgentFrameworkException("warn message", log_level=logging.WARNING)
        assert "warn message" in caplog.text

    def test_log_level_error(self, caplog: pytest.LogRecaptureFixture) -> None:
        with caplog.at_level(logging.ERROR, logger="agent_framework"):
            AgentFrameworkException("error message", log_level=logging.ERROR)
        assert "error message" in caplog.text

    def test_log_level_none_suppresses_logging(self, caplog: pytest.LogRecaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger="agent_framework"):
            AgentFrameworkException("silent message", log_level=None)
        assert "silent message" not in caplog.text

    def test_inner_exception_is_logged(self, caplog: pytest.LogRecaptureFixture) -> None:
        inner = RuntimeError("root cause")
        with caplog.at_level(logging.DEBUG, logger="agent_framework"):
            AgentFrameworkException("wrapper", inner_exception=inner)
        assert "wrapper" in caplog.text

    def test_extra_args_passed_through(self) -> None:
        exc = AgentFrameworkException("msg", None, 10, "extra1", "extra2")
        assert "extra1" in exc.args
        assert "extra2" in exc.args


# -- Hierarchy tests --------------------------------------------------------
# Each region verifies that every exception is catchable by its parent(s),
# all the way up to AgentFrameworkException and Exception.


class TestAgentExceptionHierarchy:
    """Tests for Agent exception inheritance chain."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            AgentException,
            AgentInvalidAuthException,
            AgentInvalidRequestException,
            AgentInvalidResponseException,
            AgentContentFilterException,
        ],
    )
    def test_is_subclass_of_agent_framework_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, AgentFrameworkException)

    @pytest.mark.parametrize(
        "exc_class",
        [
            AgentInvalidAuthException,
            AgentInvalidRequestException,
            AgentInvalidResponseException,
            AgentContentFilterException,
        ],
    )
    def test_is_subclass_of_agent_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, AgentException)

    def test_catch_child_with_agent_exception(self) -> None:
        with pytest.raises(AgentException):
            raise AgentInvalidAuthException("auth failed")

    def test_catch_child_with_agent_framework_exception(self) -> None:
        with pytest.raises(AgentFrameworkException):
            raise AgentContentFilterException("filtered")


class TestChatClientExceptionHierarchy:
    """Tests for ChatClient exception inheritance chain."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ChatClientException,
            ChatClientInvalidAuthException,
            ChatClientInvalidRequestException,
            ChatClientInvalidResponseException,
            ChatClientContentFilterException,
        ],
    )
    def test_is_subclass_of_agent_framework_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, AgentFrameworkException)

    @pytest.mark.parametrize(
        "exc_class",
        [
            ChatClientInvalidAuthException,
            ChatClientInvalidRequestException,
            ChatClientInvalidResponseException,
            ChatClientContentFilterException,
        ],
    )
    def test_is_subclass_of_chat_client_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, ChatClientException)

    def test_catch_child_with_chat_client_exception(self) -> None:
        with pytest.raises(ChatClientException):
            raise ChatClientInvalidResponseException("bad response")


class TestIntegrationExceptionHierarchy:
    """Tests for Integration exception inheritance chain."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            IntegrationException,
            IntegrationInitializationError,
            IntegrationInvalidAuthException,
            IntegrationInvalidRequestException,
            IntegrationInvalidResponseException,
            IntegrationContentFilterException,
        ],
    )
    def test_is_subclass_of_agent_framework_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, AgentFrameworkException)

    @pytest.mark.parametrize(
        "exc_class",
        [
            IntegrationInitializationError,
            IntegrationInvalidAuthException,
            IntegrationInvalidRequestException,
            IntegrationInvalidResponseException,
            IntegrationContentFilterException,
        ],
    )
    def test_is_subclass_of_integration_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, IntegrationException)

    def test_catch_child_with_integration_exception(self) -> None:
        with pytest.raises(IntegrationException):
            raise IntegrationInitializationError("init failed")


class TestContentExceptionHierarchy:
    """Tests for Content exception inheritance chain."""

    def test_content_error_is_agent_framework_exception(self) -> None:
        assert issubclass(ContentError, AgentFrameworkException)

    def test_addition_item_mismatch_is_content_error(self) -> None:
        assert issubclass(AdditionItemMismatch, ContentError)

    def test_catch_addition_item_mismatch_with_content_error(self) -> None:
        with pytest.raises(ContentError):
            raise AdditionItemMismatch("type mismatch")


class TestToolExceptionHierarchy:
    """Tests for Tool exception inheritance chain."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            ToolException,
            ToolExecutionException,
            UserInputRequiredException,
        ],
    )
    def test_is_subclass_of_agent_framework_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, AgentFrameworkException)

    def test_tool_execution_exception_is_tool_exception(self) -> None:
        assert issubclass(ToolExecutionException, ToolException)

    def test_user_input_required_is_tool_exception(self) -> None:
        assert issubclass(UserInputRequiredException, ToolException)

    def test_catch_tool_execution_with_tool_exception(self) -> None:
        with pytest.raises(ToolException):
            raise ToolExecutionException("exec failed")


class TestWorkflowExceptionHierarchy:
    """Tests for Workflow exception inheritance chain."""

    @pytest.mark.parametrize(
        "exc_class",
        [
            WorkflowException,
            WorkflowRunnerException,
            WorkflowConvergenceException,
            WorkflowCheckpointException,
        ],
    )
    def test_is_subclass_of_agent_framework_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, AgentFrameworkException)

    @pytest.mark.parametrize(
        "exc_class",
        [
            WorkflowRunnerException,
            WorkflowConvergenceException,
            WorkflowCheckpointException,
        ],
    )
    def test_is_subclass_of_workflow_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, WorkflowException)

    @pytest.mark.parametrize(
        "exc_class",
        [
            WorkflowConvergenceException,
            WorkflowCheckpointException,
        ],
    )
    def test_is_subclass_of_workflow_runner_exception(self, exc_class: type) -> None:
        assert issubclass(exc_class, WorkflowRunnerException)

    def test_catch_checkpoint_with_workflow_exception(self) -> None:
        with pytest.raises(WorkflowException):
            raise WorkflowCheckpointException("checkpoint error")

    def test_catch_convergence_with_workflow_runner_exception(self) -> None:
        with pytest.raises(WorkflowRunnerException):
            raise WorkflowConvergenceException("did not converge")


class TestStandaloneExceptions:
    """Tests for MiddlewareException and SettingNotFoundError."""

    def test_middleware_exception_is_agent_framework_exception(self) -> None:
        assert issubclass(MiddlewareException, AgentFrameworkException)

    def test_setting_not_found_error_is_agent_framework_exception(self) -> None:
        assert issubclass(SettingNotFoundError, AgentFrameworkException)

    def test_middleware_exception_catchable(self) -> None:
        with pytest.raises(AgentFrameworkException):
            raise MiddlewareException("middleware broke")

    def test_setting_not_found_error_catchable(self) -> None:
        with pytest.raises(AgentFrameworkException):
            raise SettingNotFoundError("missing KEY")


class TestUserInputRequiredException:
    """Tests for UserInputRequiredException special behavior."""

    def test_contents_attribute_stored(self) -> None:
        contents: list[Any] = [{"type": "oauth_consent_request", "url": "https://example.com"}]
        exc = UserInputRequiredException(contents)
        assert exc.contents is contents

    def test_default_message(self) -> None:
        exc = UserInputRequiredException([])
        assert "user input" in str(exc).lower() or "user input" in exc.args[0].lower()

    def test_custom_message(self) -> None:
        exc = UserInputRequiredException([], message="Please approve OAuth.")
        assert "Please approve OAuth." in exc.args[0]

    def test_does_not_log(self, caplog: pytest.LogRecaptureFixture) -> None:
        with caplog.at_level(logging.DEBUG, logger="agent_framework"):
            UserInputRequiredException([{"type": "test"}])
        assert caplog.text == ""

    def test_empty_contents_list(self) -> None:
        exc = UserInputRequiredException([])
        assert exc.contents == []

    def test_multiple_content_items(self) -> None:
        items: list[Any] = [
            {"type": "oauth_consent_request"},
            {"type": "function_approval_request"},
        ]
        exc = UserInputRequiredException(items)
        assert len(exc.contents) == 2

    def test_is_catchable_as_tool_exception(self) -> None:
        with pytest.raises(ToolException):
            raise UserInputRequiredException([{"type": "test"}])


class TestAllExceptionsInstantiable:
    """Verify every exception class can be instantiated with a simple message."""

    ALL_EXCEPTION_CLASSES = [
        AgentFrameworkException,
        AgentException,
        AgentInvalidAuthException,
        AgentInvalidRequestException,
        AgentInvalidResponseException,
        AgentContentFilterException,
        ChatClientException,
        ChatClientInvalidAuthException,
        ChatClientInvalidRequestException,
        ChatClientInvalidResponseException,
        ChatClientContentFilterException,
        IntegrationException,
        IntegrationInitializationError,
        IntegrationInvalidAuthException,
        IntegrationInvalidRequestException,
        IntegrationInvalidResponseException,
        IntegrationContentFilterException,
        ContentError,
        AdditionItemMismatch,
        ToolException,
        ToolExecutionException,
        MiddlewareException,
        SettingNotFoundError,
        WorkflowException,
        WorkflowRunnerException,
        WorkflowConvergenceException,
        WorkflowCheckpointException,
    ]

    @pytest.mark.parametrize("exc_class", ALL_EXCEPTION_CLASSES, ids=lambda c: c.__name__)
    def test_instantiation_with_message(self, exc_class: type) -> None:
        exc = exc_class("test message")
        assert isinstance(exc, Exception)
        assert isinstance(exc, AgentFrameworkException)

    @pytest.mark.parametrize("exc_class", ALL_EXCEPTION_CLASSES, ids=lambda c: c.__name__)
    def test_raise_and_catch(self, exc_class: type) -> None:
        with pytest.raises(exc_class):
            raise exc_class("test")
