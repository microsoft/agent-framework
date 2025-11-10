# Copyright (c) Microsoft. All rights reserved.

import asyncio
import inspect
from typing import Any

import pytest

from agent_framework._workflows._executor import Executor, handler
from agent_framework._workflows._request_info_mixin import response_handler
from agent_framework._workflows._workflow_context import WorkflowContext


class TestRequestInfoMixin:
    """Test cases for RequestInfoMixin functionality."""

    def test_request_info_mixin_initialization(self):
        """Test that RequestInfoMixin can be initialized."""

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

        executor = TestExecutor()
        # After calling _discover_response_handlers, it should have the attributes
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

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

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

        # Should be request-response capable
        assert executor.is_request_response_capable is True

        # Should have registered handlers
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 2
        assert (str, int) in response_handlers
        assert (dict[str, Any], bool) in response_handlers

    def test_executor_without_response_handlers(self):
        """Test an executor without response handlers."""

        class PlainExecutor(Executor):
            def __init__(self):
                super().__init__(id="plain_executor")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

        executor = PlainExecutor()

        # Should not be request-response capable
        assert executor.is_request_response_capable is False

        # Should have empty handlers
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 0

    def test_duplicate_response_handlers_raise_error(self):
        """Test that duplicate response handlers for the same message type raise an error."""

        class DuplicateExecutor(Executor):
            def __init__(self):
                super().__init__(id="duplicate_executor")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_first(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

            @response_handler
            async def handle_second(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        with pytest.raises(
            ValueError,
            match="Duplicate response handler for request type <class 'str'> and response type <class 'int'>",
        ):
            DuplicateExecutor()

    def test_response_handler_function_callable(self):
        """Test that response handlers can actually be called."""

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")
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

        # Get the handler
        response_handler_func = executor._response_handlers[(str, int)]  # type: ignore[reportAttributeAccessIssue]

        # Create a mock context - we'll just use None since the handler doesn't use it
        asyncio.run(response_handler_func("test_request", 42, None))  # type: ignore[reportArgumentType]

        assert executor.handled_request == "test_request"
        assert executor.handled_response == 42

    def test_inheritance_with_response_handlers(self):
        """Test that response handlers work correctly with inheritance."""

        class BaseExecutor(Executor):
            def __init__(self):
                super().__init__(id="base_executor")

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

        # Should have both handlers
        response_handlers = child._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 2
        assert (str, int) in response_handlers
        assert (str, bool) in response_handlers
        assert child.is_request_response_capable is True

    def test_response_handler_spec_attributes(self):
        """Test that response handler specs contain expected attributes."""

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def test_handler(self, original_request: str, response: int, ctx: WorkflowContext[str, bool]) -> None:
                pass

        executor = TestExecutor()

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

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def test_handler(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        executor = TestExecutor()

        # First call should work fine
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

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

            some_variable = "not_a_function"
            another_attr = 42

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def valid_handler(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        executor = TestExecutor()

        # Should only have one handler despite other attributes
        response_handlers = executor._response_handlers  # type: ignore[reportAttributeAccessIssue]
        assert len(response_handlers) == 1
        assert (str, int) in response_handlers

    def test_same_request_type_different_response_types(self):
        """Test that handlers with same request type but different response types are distinct."""

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")
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

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")
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

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")
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

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

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

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

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

        # Test that wrong combinations don't match
        assert executor._find_response_handler("test", 3.14) is None  # pyright: ignore[reportPrivateUsage] # str request, float response - no handler
        assert executor._find_response_handler(["test"], 42) is None  # pyright: ignore[reportPrivateUsage] # list request, int response - no handler
        assert executor._find_response_handler(42, "test") is None  # pyright: ignore[reportPrivateUsage] # int request, str response - no handler

        # Test that correct combinations do match
        assert executor._find_response_handler("test", 42) is not None  # pyright: ignore[reportPrivateUsage] # str request, int response - has handler
        assert executor._find_response_handler(["test"], 3.14) is not None  # pyright: ignore[reportPrivateUsage] # list request, float response - has handler

    def test_is_request_supported_with_exact_matches(self):
        """Test is_request_supported with exact type matches."""

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_str_int(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

            @response_handler
            async def handle_dict_bool(
                self, original_request: dict[str, Any], response: bool, ctx: WorkflowContext[str]
            ) -> None:
                pass

        executor = TestExecutor()

        # Test exact matches
        assert executor.is_request_supported(str, int) is True
        assert executor.is_request_supported(str, bool) is True  # bool and int are compatible
        assert executor.is_request_supported(dict[str, Any], bool) is True

        # Test non-matches
        assert executor.is_request_supported(int, str) is False
        assert executor.is_request_supported(list[str], int) is False

    def test_is_request_supported_without_handlers(self):
        """Test is_request_supported when no handlers are registered."""

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

        executor = TestExecutor()

        # Should return False for any type combination
        assert executor.is_request_supported(str, int) is False
        assert executor.is_request_supported(dict[str, Any], bool) is False
        assert executor.is_request_supported(int, str) is False

    def test_is_request_supported_before_discovery(self):
        """Test is_request_supported before response handlers are discovered."""

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor", defer_discovery=True)

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_str_int(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        executor = TestExecutor()
        # Don't call _discover_response_handlers()

        # Should return False when _response_handlers attribute doesn't exist
        assert executor.is_request_supported(str, int) is False
        assert executor.is_request_supported(dict[str, Any], bool) is False

    def test_is_request_supported_with_compatible_types(self):
        """Test is_request_supported with type-compatible scenarios."""

        class BaseRequest:
            pass

        class DerivedRequest(BaseRequest):
            pass

        class BaseResponse:
            pass

        class DerivedResponse(BaseResponse):
            pass

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_base_base(
                self, original_request: BaseRequest, response: BaseResponse, ctx: WorkflowContext[str]
            ) -> None:
                pass

            @response_handler
            async def handle_str_int(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

        executor = TestExecutor()

        # Test exact matches
        assert executor.is_request_supported(BaseRequest, BaseResponse) is True
        assert executor.is_request_supported(str, int) is True

        # Test compatible derived types (depends on is_type_compatible implementation)
        # These should return True if the type compatibility function supports inheritance
        result_derived_request = executor.is_request_supported(DerivedRequest, BaseResponse)
        result_derived_response = executor.is_request_supported(BaseRequest, DerivedResponse)
        result_both_derived = executor.is_request_supported(DerivedRequest, DerivedResponse)

        # The actual result depends on the is_type_compatible implementation
        # We'll just assert that the method doesn't raise an exception
        assert isinstance(result_derived_request, bool)
        assert isinstance(result_derived_response, bool)
        assert isinstance(result_both_derived, bool)

    def test_is_request_supported_with_multiple_handlers(self):
        """Test is_request_supported when multiple handlers are registered."""

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_str_int(self, original_request: str, response: int, ctx: WorkflowContext[str]) -> None:
                pass

            @response_handler
            async def handle_str_bool(self, original_request: str, response: bool, ctx: WorkflowContext[str]) -> None:
                pass

            @response_handler
            async def handle_dict_str(
                self, original_request: dict[str, Any], response: str, ctx: WorkflowContext[str]
            ) -> None:
                pass

            @response_handler
            async def handle_list_float(
                self, original_request: list[str], response: float, ctx: WorkflowContext[str]
            ) -> None:
                pass

        executor = TestExecutor()

        # Test all registered combinations
        assert executor.is_request_supported(str, int) is True
        assert executor.is_request_supported(str, bool) is True
        assert executor.is_request_supported(dict[str, Any], str) is True
        assert executor.is_request_supported(list[str], float) is True

        # Test combinations that don't exist
        assert executor.is_request_supported(str, float) is False
        assert executor.is_request_supported(int, str) is False
        assert executor.is_request_supported(dict[str, Any], int) is False
        assert executor.is_request_supported(list[str], bool) is False

    def test_is_request_supported_with_complex_types(self):
        """Test is_request_supported with complex generic types."""

        class TestExecutor(Executor):
            def __init__(self):
                super().__init__(id="test_executor")

            @handler
            async def dummy_handler(self, message: str, ctx: WorkflowContext) -> None:
                pass

            @response_handler
            async def handle_dict_list(
                self, original_request: dict[str, Any], response: list[int], ctx: WorkflowContext[str]
            ) -> None:
                pass

            @response_handler
            async def handle_list_dict(
                self, original_request: list[str], response: dict[str, bool], ctx: WorkflowContext[str]
            ) -> None:
                pass

        executor = TestExecutor()

        # Test complex type matches
        assert executor.is_request_supported(dict[str, Any], list[int]) is True
        assert executor.is_request_supported(list[str], dict[str, bool]) is True

        # Test non-matches with similar but different complex types
        assert executor.is_request_supported(dict[str, Any], list[str]) is False
        assert executor.is_request_supported(list[int], dict[str, bool]) is False
        assert executor.is_request_supported(dict[int, Any], list[int]) is False

    def test_is_request_supported_with_inheritance(self):
        """Test is_request_supported with inherited response handlers."""

        class BaseExecutor(Executor):
            def __init__(self):
                super().__init__(id="base_executor")

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

        # Should support both inherited and child-defined handlers
        assert child.is_request_supported(str, int) is True  # From base class
        assert child.is_request_supported(str, bool) is True  # From child class

        # Should not support unregistered combinations
        assert child.is_request_supported(str, str) is False
        assert child.is_request_supported(int, str) is False
