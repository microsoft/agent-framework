# Copyright (c) Microsoft. All rights reserved.

import asyncio
import inspect
from typing import Any

import pytest

from agent_framework._workflows._executor import Executor, handler
from agent_framework._workflows._request_info_mixin import RequestInfoMixin, response_handler
from agent_framework._workflows._workflow_context import WorkflowContext


class TestRequestInfoMixin:
    """Test cases for RequestInfoMixin functionality."""

    def test_request_info_mixin_initialization(self):
        """Test that RequestInfoMixin can be initialized."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

        executor = TestExecutor()
        # After calling _discover_response_handlers, it should have the attributes
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]
        assert hasattr(executor, "_response_handlers")
        assert hasattr(executor, "_response_handler_specs")
        assert hasattr(executor, "is_request_response_capable")
        assert executor.is_request_response_capable is False

    def test_response_handler_decorator_creates_metadata(self):
        """Test that the response_handler decorator creates proper metadata."""

        @response_handler
        async def test_handler(self: Any, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
            """Test handler docstring."""
            pass

        # Check that the decorator preserves function attributes
        assert test_handler.__name__ == "test_handler"
        assert test_handler.__doc__ == "Test handler docstring."
        assert hasattr(test_handler, "_response_handler_spec")

        # Check the spec attributes
        spec = test_handler._response_handler_spec  # type: ignore[reportAttributeAccessIssue]
        assert spec["name"] == "test_handler"
        assert spec["response_type"] is int
        assert spec["request_type"] is str

    def test_response_handler_with_workflow_context_types(self):
        """Test response handler with different WorkflowContext type parameters."""

        @response_handler
        async def handler_with_output_types(
            self: Any, original_request: str, response: int, ctx: WorkflowContext[str, bool]
        ) -> None:
            pass

        spec = handler_with_output_types._response_handler_spec  # type: ignore[reportAttributeAccessIssue]
        assert "output_types" in spec
        assert "workflow_output_types" in spec

    def test_response_handler_preserves_signature(self):
        """Test that response_handler preserves the original function signature."""

        async def original_handler(self: Any, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
            pass

        decorated = response_handler(original_handler)

        # Check that signature is preserved
        original_sig = inspect.signature(original_handler)
        decorated_sig = inspect.signature(decorated)

        # Both should have the same parameter names and types
        assert list(original_sig.parameters.keys()) == list(decorated_sig.parameters.keys())

    def test_executor_with_response_handlers(self):
        """Test an executor with valid response handlers."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_string_response(
                self, original_request: str, response: int, ctx: WorkflowContext[str]
            ) -> None:
                pass

            @response_handler
            async def handle_dict_response(
                self, original_request: dict[str, Any], response: bool, ctx: WorkflowContext[bool]
            ) -> None:
                pass

        executor = TestExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Should be request-response capable
        assert executor.is_request_response_capable is True

        # Should have registered handlers
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 2
        assert (str, int) in response_handlers
        assert (dict[str, Any], bool) in response_handlers

    def test_executor_without_response_handlers(self):
        """Test an executor without response handlers."""

        class PlainExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="plain_executor", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

        executor = PlainExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Should not be request-response capable
        assert executor.is_request_response_capable is False

        # Should have empty handlers
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 0

    def test_duplicate_response_handlers_raise_error(self):
        """Test that duplicate response handlers for the same message type raise an error."""

        class DuplicateExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="duplicate_executor", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_first(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

            @response_handler
            async def handle_second(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        executor = DuplicateExecutor()

        with pytest.raises(
            ValueError,
            match="Duplicate response handler for request type <class 'str'> and response type <class 'int'>",
        ):
            executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

    def test_response_handler_function_callable(self):
        """Test that response handlers can actually be called."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)
                self.handled_request = None
                self.handled_response = None

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_response(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                self.handled_request = original_request
                self.handled_response = response

        executor = TestExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Get the handler
        response_handler_func = executor._response_handlers[(str, int)]  # type: ignore[reportAttributeAccessIssue]

        # Create a mock context - we'll just use None since the handler doesn't use it
        asyncio.run(response_handler_func("test_request", 42, None))  # type: ignore[reportArgumentType]

        assert executor.handled_request == "test_request"
        assert executor.handled_response == 42

    def test_inheritance_with_response_handlers(self):
        """Test that response handlers work correctly with inheritance."""

        class BaseExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="base_executor", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def base_handler(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        class ChildExecutor(BaseExecutor):
            def __init__(self):
                super().__init__()
                self.id = "child_executor"

            @response_handler
            async def child_handler(self, original_request: str, response: bool, ctx: WorkflowContext[str]) -> None:
                pass

        child = ChildExecutor()
        child._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Should have both handlers
        response_handlers = child._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 2
        assert (str, int) in response_handlers
        assert (str, bool) in response_handlers
        assert child.is_request_response_capable is True

    def test_response_handler_spec_attributes(self):
        """Test that response handler specs contain expected attributes."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def test_handler(self, original_request: str, response: int, ctx: WorkflowContext[str, bool]) -> None:
                pass

        executor = TestExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        specs = executor._response_handler_specs  # type: ignore[reportAttributeAccessIssue]
        assert len(specs) == 1

        spec = specs[0]
        assert spec["name"] == "test_handler"
        assert spec["request_type"] is str
        assert spec["response_type"] is int
        assert "output_types" in spec
        assert "workflow_output_types" in spec
        assert "ctx_annotation" in spec
        assert spec["source"] == "class_method"

    def test_multiple_discovery_calls_raise_error(self):
        """Test that multiple calls to _discover_response_handlers raise an error for duplicates."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def test_handler(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        executor = TestExecutor()

        # First call should work fine
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]
        first_handlers = len(executor._response_handlers)  # type: ignore[reportAttributeAccessIssue]

        # Second call should raise an error due to duplicate registration
        with pytest.raises(
            ValueError,
            match="Duplicate response handler for request type <class 'str'> and response type <class 'int'>",
        ):
            executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Handlers count should remain the same
        assert first_handlers == 1

    def test_non_callable_attributes_ignored(self):
        """Test that non-callable attributes are ignored during discovery."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)

            some_variable = "not_a_function"
            another_attr = 42

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def valid_handler(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        executor = TestExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Should only have one handler despite other attributes
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 1
        assert (str, int) in response_handlers

    def test_same_request_type_different_response_types(self):
        """Test that handlers with same request type but different response types are distinct."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)
                self.str_int_handler_called = False
                self.str_bool_handler_called = False
                self.str_dict_handler_called = False

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_str_int(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                self.str_int_handler_called = True

            @response_handler
            async def handle_str_bool(self, original_request: str, response: bool, ctx: WorkflowContext[str]) -> None:
                self.str_bool_handler_called = True

            @response_handler
            async def handle_str_dict(
                self, original_request: str, response: dict[str, Any], ctx: WorkflowContext[str]
            ) -> None:
                self.str_dict_handler_called = True

        executor = TestExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Should have three distinct handlers
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 3
        assert (str, int) in response_handlers
        assert (str, bool) in response_handlers
        assert (str, dict[str, Any]) in response_handlers

        # Test that each handler can be found correctly
        str_int_handler = executor._find_response_handler("test", 42)  # pyright: ignore[reportPrivateUsage]
        str_bool_handler = executor._find_response_handler("test", True)  # pyright: ignore[reportPrivateUsage]
        str_dict_handler = executor._find_response_handler("test", {"key": "value"})  # pyright: ignore[reportPrivateUsage]

        assert str_int_handler is not None
        assert str_bool_handler is not None
        assert str_dict_handler is not None

        # Test that handlers are called correctly
        asyncio.run(str_int_handler(42, None))  # type: ignore[reportArgumentType]
        asyncio.run(str_bool_handler(True, None))  # type: ignore[reportArgumentType]
        asyncio.run(str_dict_handler({"key": "value"}, None))  # type: ignore[reportArgumentType]

        assert executor.str_int_handler_called
        assert executor.str_bool_handler_called
        assert executor.str_dict_handler_called

    def test_different_request_types_same_response_type(self):
        """Test that handlers with different request types but same response type are distinct."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)
                self.str_int_handler_called = False
                self.dict_int_handler_called = False
                self.list_int_handler_called = False

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_str_int(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                self.str_int_handler_called = True

            @response_handler
            async def handle_dict_int(
                self, original_request: dict[str, Any], response: int, ctx: WorkflowContext[str]
            ) -> None:
                self.dict_int_handler_called = True

            @response_handler
            async def handle_list_int(
                self, original_request: list[str], response: int, ctx: WorkflowContext[str]
            ) -> None:
                self.list_int_handler_called = True

        executor = TestExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Should have three distinct handlers
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 3
        assert (str, int) in response_handlers
        assert (dict[str, Any], int) in response_handlers
        assert (list[str], int) in response_handlers

        # Test that each handler can be found correctly
        str_int_handler = executor._find_response_handler("test", 42)  # pyright: ignore[reportPrivateUsage]
        dict_int_handler = executor._find_response_handler({"key": "value"}, 42)  # pyright: ignore[reportPrivateUsage]
        list_int_handler = executor._find_response_handler(["test"], 42)  # pyright: ignore[reportPrivateUsage]

        assert str_int_handler is not None
        assert dict_int_handler is not None
        assert list_int_handler is not None

        # Test that handlers are called correctly
        asyncio.run(str_int_handler(42, None))  # type: ignore[reportArgumentType]
        asyncio.run(dict_int_handler(42, None))  # type: ignore[reportArgumentType]
        asyncio.run(list_int_handler(42, None))  # type: ignore[reportArgumentType]

        assert executor.str_int_handler_called
        assert executor.dict_int_handler_called
        assert executor.list_int_handler_called

    def test_complex_type_combinations(self):
        """Test response handlers with complex type combinations."""

        class CustomRequest:
            pass

        class CustomResponse:
            pass

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)
                self.custom_custom_called = False
                self.custom_str_called = False
                self.str_custom_called = False

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_custom_custom(
                self, original_request: CustomRequest, response: CustomResponse, ctx: WorkflowContext[str]
            ) -> None:
                self.custom_custom_called = True

            @response_handler
            async def handle_custom_str(
                self, original_request: CustomRequest, response: str, ctx: WorkflowContext[str]
            ) -> None:
                self.custom_str_called = True

            @response_handler
            async def handle_str_custom(
                self, original_request: str, response: CustomResponse, ctx: WorkflowContext[str]
            ) -> None:
                self.str_custom_called = True

        executor = TestExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Should have three distinct handlers
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 3
        assert (CustomRequest, CustomResponse) in response_handlers
        assert (CustomRequest, str) in response_handlers
        assert (str, CustomResponse) in response_handlers

        # Test that each handler can be found correctly
        custom_request = CustomRequest()
        custom_response = CustomResponse()

        custom_custom_handler = executor._find_response_handler(custom_request, custom_response)  # pyright: ignore[reportPrivateUsage]
        custom_str_handler = executor._find_response_handler(custom_request, "test")  # pyright: ignore[reportPrivateUsage]
        str_custom_handler = executor._find_response_handler("test", custom_response)  # pyright: ignore[reportPrivateUsage]

        assert custom_custom_handler is not None
        assert custom_str_handler is not None
        assert str_custom_handler is not None

    def test_handler_key_uniqueness(self):
        """Test that handler keys (request_type, response_type) are truly unique."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle1(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

            @response_handler
            async def handle2(self, original_request: int, response: str, ctx: WorkflowContext[str]) -> None:
                pass

            @response_handler
            async def handle3(self, original_request: str, response: str, ctx: WorkflowContext[str]) -> None:
                pass

            @response_handler
            async def handle4(self, original_request: int, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        executor = TestExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Should have four distinct handlers based on different combinations
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 4

        # Verify all expected combinations exist
        expected_keys = {
            (str, int),  # handle1
            (int, str),  # handle2
            (str, str),  # handle3
            (int, int),  # handle4
        }

        actual_keys = set(response_handlers.keys())
        assert actual_keys == expected_keys

    def test_no_false_matches_with_similar_types(self):
        """Test that handlers don't match with similar but different types."""

        class TestExecutor(Executor, RequestInfoMixin):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_str_int(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

            @response_handler
            async def handle_list_str_float(
                self, original_request: list[str], response: float, ctx: WorkflowContext[str]
            ) -> None:
                pass

        executor = TestExecutor()
        executor._discover_response_handlers()  # type: ignore[reportAttributeAccessIssue]

        # Test that wrong combinations don't match
        assert executor._find_response_handler("test", 3.14) is None  # pyright: ignore[reportPrivateUsage] # str request, float response - no handler
        assert executor._find_response_handler(["test"], 42) is None  # pyright: ignore[reportPrivateUsage] # list request, int response - no handler
        assert executor._find_response_handler(42, "test") is None  # pyright: ignore[reportPrivateUsage] # int request, str response - no handler

        # Test that correct combinations do match
        assert executor._find_response_handler("test", 42) is not None  # pyright: ignore[reportPrivateUsage] # str request, int response - has handler
        assert executor._find_response_handler(["test"], 3.14) is not None  # pyright: ignore[reportPrivateUsage] # list request, float response - has handler
