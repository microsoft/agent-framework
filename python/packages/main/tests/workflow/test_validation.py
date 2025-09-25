# Copyright (c) Microsoft. All rights reserved.

import logging
from typing import Any

import pytest

from agent_framework import (
    EdgeDuplicationError,
    Executor,
    ExecutorDuplicationError,
    GraphConnectivityError,
    TypeCompatibilityError,
    ValidationTypeEnum,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowValidationError,
    handler,
    validate_workflow_graph,
)
from agent_framework._workflow._edge import SingleEdgeGroup


class StringExecutor(Executor):
    @handler
    async def handle_string(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(message.upper())


class StringAggregator(Executor):
    """A mock executor that aggregates results from multiple executors."""

    @handler
    async def mock_handler(self, messages: list[str], ctx: WorkflowContext[str]) -> None:
        # This mock simply returns the data incremented by 1
        await ctx.send_message("Aggregated: " + ", ".join(messages))


class IntExecutor(Executor):
    @handler
    async def handle_int(self, message: int, ctx: WorkflowContext[int]) -> None:
        await ctx.send_message(message * 2)


class AnyExecutor(Executor):
    @handler
    async def handle_any(self, message: Any, ctx: WorkflowContext[Any]) -> None:
        await ctx.send_message(f"Processed: {message}")


class NoOutputTypesExecutor(Executor):
    @handler
    async def handle_message(self, message: str, ctx: WorkflowContext) -> None:
        await ctx.send_message("processed")  # type: ignore[arg-type]


class MultiTypeExecutor(Executor):
    @handler
    async def handle_string(self, message: str, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"String: {message}")

    @handler
    async def handle_int(self, message: int, ctx: WorkflowContext[str]) -> None:
        await ctx.send_message(f"Int: {message}")


def test_valid_workflow_passes_validation():
    executor1 = StringExecutor(id="string_executor")
    executor2 = StringExecutor(id="string_executor_2")

    # Create a valid workflow
    workflow = (
        WorkflowBuilder()
        .add_edge(executor1, executor2)
        .set_start_executor(executor1)
        .build()  # This should not raise any exceptions
    )

    assert workflow is not None


def test_duplicate_executor_ids_fail_validation():
    executor1 = StringExecutor(id="dup")
    executor2 = IntExecutor(id="dup")

    with pytest.raises(ExecutorDuplicationError) as exc_info:
        (WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build())

    assert exc_info.value.executor_id == "dup"
    assert exc_info.value.validation_type == ValidationTypeEnum.EXECUTOR_DUPLICATION


def test_edge_duplication_validation_fails():
    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")

    with pytest.raises(EdgeDuplicationError) as exc_info:
        WorkflowBuilder().add_edge(executor1, executor2).add_edge(executor1, executor2).set_start_executor(
            executor1
        ).build()

    assert "executor1->executor2" in str(exc_info.value)
    assert exc_info.value.validation_type == ValidationTypeEnum.EDGE_DUPLICATION


def test_type_compatibility_validation_fails():
    string_executor = StringExecutor(id="string_executor")
    int_executor = IntExecutor(id="int_executor")

    with pytest.raises(TypeCompatibilityError) as exc_info:
        WorkflowBuilder().add_edge(string_executor, int_executor).set_start_executor(string_executor).build()

    error = exc_info.value
    assert error.source_executor_id == "string_executor"
    assert error.target_executor_id == "int_executor"
    assert error.validation_type == ValidationTypeEnum.TYPE_COMPATIBILITY


def test_type_compatibility_with_any_type_passes():
    string_executor = StringExecutor(id="string_executor")
    any_executor = AnyExecutor(id="any_executor")

    # This should not raise an exception
    workflow = WorkflowBuilder().add_edge(string_executor, any_executor).set_start_executor(string_executor).build()

    assert workflow is not None


def test_type_compatibility_with_no_output_types():
    no_output_executor = NoOutputTypesExecutor(id="no_output")
    string_executor = StringExecutor(id="string_executor")

    # This should pass validation since no output types are specified
    workflow = (
        WorkflowBuilder().add_edge(no_output_executor, string_executor).set_start_executor(no_output_executor).build()
    )

    assert workflow is not None


def test_multi_type_executor_compatibility():
    string_executor = StringExecutor(id="string_executor")
    multi_type_executor = MultiTypeExecutor(id="multi_type")

    # String executor outputs strings, multi-type can handle strings
    workflow = (
        WorkflowBuilder().add_edge(string_executor, multi_type_executor).set_start_executor(string_executor).build()
    )

    assert workflow is not None


def test_graph_connectivity_unreachable_executors():
    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")
    executor3 = StringExecutor(id="executor3")  # This will be unreachable

    with pytest.raises(GraphConnectivityError) as exc_info:
        WorkflowBuilder().add_edge(executor1, executor2).add_edge(executor3, executor2).set_start_executor(
            executor1
        ).build()

    assert "unreachable" in str(exc_info.value).lower()
    assert "executor3" in str(exc_info.value)
    assert exc_info.value.validation_type == ValidationTypeEnum.GRAPH_CONNECTIVITY


def test_graph_connectivity_isolated_executors():
    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")
    executor3 = StringExecutor(id="executor3")  # This will be isolated

    # Create edges that include an isolated executor (self-loop that's not connected to main graph)
    edge_groups = [
        SingleEdgeGroup(executor1.id, executor2.id),
        SingleEdgeGroup(executor3.id, executor3.id),
    ]  # Self-loop to include in graph

    executors: dict[str, Executor] = {executor1.id: executor1, executor2.id: executor2, executor3.id: executor3}

    with pytest.raises(GraphConnectivityError) as exc_info:
        validate_workflow_graph(edge_groups, executors, executor1)

    assert "unreachable" in str(exc_info.value).lower()
    assert "executor3" in str(exc_info.value)


def test_start_executor_not_in_graph():
    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")
    executor3 = StringExecutor(id="executor3")  # Not in graph

    with pytest.raises(GraphConnectivityError) as exc_info:
        WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor3).build()

    assert "not present in the workflow graph" in str(exc_info.value)


def test_missing_start_executor():
    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")

    with pytest.raises(ValueError) as exc_info:
        WorkflowBuilder().add_edge(executor1, executor2).build()

    assert "Starting executor must be set" in str(exc_info.value)


def test_workflow_validation_error_base_class():
    error = WorkflowValidationError("Test message", ValidationTypeEnum.EDGE_DUPLICATION)
    assert str(error) == "[EDGE_DUPLICATION] Test message"
    assert error.message == "Test message"
    assert error.validation_type == ValidationTypeEnum.EDGE_DUPLICATION


def test_complex_workflow_validation():
    # Create a workflow with multiple paths
    executor1 = StringExecutor(id="executor1")
    executor2 = MultiTypeExecutor(id="executor2")
    executor3 = StringExecutor(id="executor3")
    executor4 = AnyExecutor(id="executor4")

    workflow = (
        WorkflowBuilder()
        .add_edge(executor1, executor2)  # str -> MultiType (compatible)
        .add_edge(executor2, executor3)  # MultiType -> str (compatible)
        .add_edge(executor2, executor4)  # MultiType -> Any (compatible)
        .add_edge(executor3, executor4)  # str -> Any (compatible)
        .set_start_executor(executor1)
        .build()
    )

    assert workflow is not None


def test_type_compatibility_inheritance():
    class BaseExecutor(Executor):
        @handler
        async def handle_base(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message("base")

    class DerivedExecutor(Executor):
        @handler
        async def handle_derived(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message("derived")

    base_executor = BaseExecutor(id="base")
    derived_executor = DerivedExecutor(id="derived")

    # This should pass since both handle str
    workflow = WorkflowBuilder().add_edge(base_executor, derived_executor).set_start_executor(base_executor).build()

    assert workflow is not None


def test_direct_validation_function():
    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")
    edge_groups = [SingleEdgeGroup(executor1.id, executor2.id)]
    executors: dict[str, Executor] = {executor1.id: executor1, executor2.id: executor2}

    # This should not raise any exceptions
    validate_workflow_graph(edge_groups, executors, executor1)

    # Test with invalid start executor
    executor3 = StringExecutor(id="executor3")
    with pytest.raises(GraphConnectivityError):
        validate_workflow_graph(edge_groups, executors, executor3)


def test_fan_out_validation():
    source = StringExecutor(id="source")
    target1 = StringExecutor(id="target1")
    target2 = AnyExecutor(id="target2")

    workflow = WorkflowBuilder().add_fan_out_edges(source, [target1, target2]).set_start_executor(source).build()

    assert workflow is not None


def test_fan_in_validation():
    start_executor = StringExecutor(id="start")
    source1 = StringExecutor(id="source1")
    source2 = StringExecutor(id="source2")
    target = StringAggregator(id="target")

    # Create a proper fan-in by having a start executor that connects to both sources
    workflow = (
        WorkflowBuilder()
        .add_edge(start_executor, source1)  # Start connects to source1
        .add_edge(start_executor, source2)  # Start connects to source2
        .add_fan_in_edges([source1, source2], target)  # Both sources fan-in to target
        .set_start_executor(start_executor)
        .build()
    )

    assert workflow is not None


def test_chain_validation():
    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")
    executor3 = AnyExecutor(id="executor3")

    workflow = WorkflowBuilder().add_chain([executor1, executor2, executor3]).set_start_executor(executor1).build()

    assert workflow is not None


def test_logging_for_missing_output_types(caplog: Any) -> None:
    caplog.set_level(logging.WARNING)

    # Create executor without output types
    no_output_executor = NoOutputTypesExecutor(id="no_output")
    string_executor = StringExecutor(id="string_executor")

    # This should trigger a warning log
    workflow = (
        WorkflowBuilder().add_edge(no_output_executor, string_executor).set_start_executor(no_output_executor).build()
    )

    assert workflow is not None
    assert "has no output type annotations" in caplog.text
    assert "Consider adding WorkflowContext[T] generics" in caplog.text


def test_logging_for_missing_input_types(caplog: Any) -> None:
    caplog.set_level(logging.WARNING)

    class NoInputTypesExecutor(Executor):
        # Handler without type annotation for input parameter
        async def handle_message(self, message: Any, ctx: WorkflowContext[Any]) -> None:
            await ctx.send_message("processed")

        def _discover_handlers(self) -> None:
            # Override to manually register handler without type info
            self._handlers[str] = self.handle_message

    string_executor = StringExecutor(id="string_executor")
    no_input_executor = NoInputTypesExecutor(id="no_input")

    # This should pass since NoInputTypesExecutor has no proper input types
    workflow = (
        WorkflowBuilder().add_edge(string_executor, no_input_executor).set_start_executor(string_executor).build()
    )

    assert workflow is not None


def test_self_loop_detection_warning(caplog: Any) -> None:
    caplog.set_level(logging.WARNING)

    executor = StringExecutor(id="self_loop_executor")

    # Create a self-loop
    workflow = WorkflowBuilder().add_edge(executor, executor).set_start_executor(executor).build()

    assert workflow is not None
    assert "Self-loop detected" in caplog.text
    assert "may cause infinite recursion" in caplog.text


def test_handler_validation_basic(caplog: Any) -> None:
    caplog.set_level(logging.WARNING)

    # Test basic handler validation - ensure the validation code runs without errors
    start_executor = StringExecutor(id="start")
    target_executor = StringExecutor(id="target")

    workflow = WorkflowBuilder().add_edge(start_executor, target_executor).set_start_executor(start_executor).build()

    assert workflow is not None
    # Just ensure the validation runs without errors


def test_dead_end_detection(caplog: Any) -> None:
    caplog.set_level(logging.INFO)

    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")  # This will be a dead end

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

    assert workflow is not None
    assert "Dead-end executors detected" in caplog.text
    assert "executor2" in caplog.text
    assert "Verify these are intended as final nodes" in caplog.text


def test_cycle_detection_warning(caplog: Any) -> None:
    caplog.set_level(logging.WARNING)

    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")
    executor3 = StringExecutor(id="executor3")

    # Create a cycle: executor1 -> executor2 -> executor3 -> executor1
    workflow = (
        WorkflowBuilder()
        .add_edge(executor1, executor2)
        .add_edge(executor2, executor3)
        .add_edge(executor3, executor1)
        .set_start_executor(executor1)
        .build()
    )

    assert workflow is not None
    assert "Cycle detected in the workflow graph" in caplog.text
    assert "Ensure proper termination conditions exist" in caplog.text


def test_successful_type_compatibility_logging(caplog: Any) -> None:
    caplog.set_level(logging.DEBUG)

    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")

    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

    assert workflow is not None
    assert "Type compatibility validated for edge" in caplog.text
    assert "Compatible type pairs" in caplog.text


def test_complex_cycle_detection(caplog: Any) -> None:
    caplog.set_level(logging.WARNING)

    # Create a more complex graph with multiple cycles
    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")
    executor3 = StringExecutor(id="executor3")
    executor4 = StringExecutor(id="executor4")

    # Create multiple paths and cycles
    workflow = (
        WorkflowBuilder()
        .add_edge(executor1, executor2)
        .add_edge(executor2, executor3)
        .add_edge(executor3, executor4)
        .add_edge(executor4, executor2)  # Creates cycle: executor2 -> executor3 -> executor4 -> executor2
        .set_start_executor(executor1)
        .build()
    )

    assert workflow is not None
    assert "Cycle detected in the workflow graph" in caplog.text


def test_no_cycles_in_simple_chain(caplog: Any) -> None:
    caplog.set_level(logging.WARNING)

    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")
    executor3 = StringExecutor(id="executor3")

    # Simple chain without cycles
    workflow = (
        WorkflowBuilder()
        .add_edge(executor1, executor2)
        .add_edge(executor2, executor3)
        .set_start_executor(executor1)
        .build()
    )

    assert workflow is not None
    # Should not log cycle detection
    assert "Cycle detected" not in caplog.text


def test_multiple_dead_ends_detection(caplog: Any) -> None:
    caplog.set_level(logging.INFO)

    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")  # Dead end
    executor3 = StringExecutor(id="executor3")  # Dead end

    workflow = (
        WorkflowBuilder()
        .add_edge(executor1, executor2)
        .add_edge(executor1, executor3)
        .set_start_executor(executor1)
        .build()
    )

    assert workflow is not None
    assert "Dead-end executors detected" in caplog.text
    assert "executor2" in caplog.text and "executor3" in caplog.text


def test_single_executor_workflow(caplog: Any) -> None:
    caplog.set_level(logging.INFO)

    # Test workflow with minimal structure
    executor1 = StringExecutor(id="executor1")
    executor2 = StringExecutor(id="executor2")

    # Create a simple two-executor workflow to avoid graph validation issues
    workflow = WorkflowBuilder().add_edge(executor1, executor2).set_start_executor(executor1).build()

    assert workflow is not None
    # Should detect executor2 as dead end
    assert "Dead-end executors detected" in caplog.text


def test_enhanced_type_compatibility_error_details():
    string_executor = StringExecutor(id="string_executor")
    int_executor = IntExecutor(id="int_executor")

    with pytest.raises(TypeCompatibilityError) as exc_info:
        WorkflowBuilder().add_edge(string_executor, int_executor).set_start_executor(string_executor).build()

    error = exc_info.value
    # Verify enhanced error contains detailed type information
    assert "Source executor outputs types" in str(error)
    assert "target executor can only handle types" in str(error)
    assert error.source_types is not None
    assert error.target_types is not None


def test_union_type_compatibility_validation() -> None:
    class UnionOutputExecutor(Executor):
        @handler
        async def handle_message(self, message: str, ctx: WorkflowContext[str | int]) -> None:
            await ctx.send_message("output")

    class UnionInputExecutor(Executor):
        @handler
        async def handle_message(self, message: str, ctx: WorkflowContext[str]) -> None:
            await ctx.send_message("processed")

    union_output = UnionOutputExecutor(id="union_output")
    union_input = UnionInputExecutor(id="union_input")

    # This should pass validation due to type compatibility (str)
    workflow = WorkflowBuilder().add_edge(union_output, union_input).set_start_executor(union_output).build()

    assert workflow is not None


def test_generic_type_compatibility() -> None:
    class ListOutputExecutor(Executor):
        @handler
        async def handle_message(self, message: str, ctx: WorkflowContext[list[str]]) -> None:
            await ctx.send_message(["output"])

    class ListInputExecutor(Executor):
        @handler
        async def handle_message(self, message: list[str], ctx: WorkflowContext[str]) -> None:
            await ctx.send_message("processed")

    list_output = ListOutputExecutor(id="list_output")
    list_input = ListInputExecutor(id="list_input")

    # This should pass validation for generic type compatibility
    workflow = WorkflowBuilder().add_edge(list_output, list_input).set_start_executor(list_output).build()

    assert workflow is not None


def test_validation_enum_usage() -> None:
    # Test that all validation types use the enum correctly
    edge_error = EdgeDuplicationError("test->test")
    assert edge_error.validation_type == ValidationTypeEnum.EDGE_DUPLICATION

    type_error = TypeCompatibilityError("source", "target", [str], [int])
    assert type_error.validation_type == ValidationTypeEnum.TYPE_COMPATIBILITY

    graph_error = GraphConnectivityError("test message")
    assert graph_error.validation_type == ValidationTypeEnum.GRAPH_CONNECTIVITY

    # Test enum string representation
    assert str(ValidationTypeEnum.EDGE_DUPLICATION) == "ValidationTypeEnum.EDGE_DUPLICATION"
    assert ValidationTypeEnum.EDGE_DUPLICATION.value == "EDGE_DUPLICATION"


def test_handler_ctx_missing_annotation_raises() -> None:
    # Validation now happens at handler registration time, not workflow build time
    with pytest.raises(ValueError) as exc:

        class BadExecutor(Executor):
            @handler
            async def handle(self, message: str, ctx) -> None:  # type: ignore[no-untyped-def]
                pass

    assert "must have a WorkflowContext" in str(exc.value)


def test_handler_ctx_invalid_t_out_entries_raises() -> None:
    # Validation now happens at handler registration time, not workflow build time
    with pytest.raises(ValueError) as exc:

        class BadExecutor(Executor):
            @handler
            async def handle(self, message: str, ctx: WorkflowContext[123]) -> None:  # type: ignore[valid-type]
                pass

    assert "invalid type entry" in str(exc.value)


def test_handler_ctx_none_is_allowed() -> None:
    class NoneExecutor(Executor):
        @handler
        async def handle(self, message: str, ctx: WorkflowContext) -> None:
            # does not emit
            return None

    start = StringExecutor(id="s")
    none_exec = NoneExecutor(id="n")

    # Should build successfully
    wf = WorkflowBuilder().add_edge(start, none_exec).set_start_executor(start).build()
    assert wf is not None


def test_handler_ctx_any_is_allowed_but_skips_type_checks(caplog: Any) -> None:
    caplog.set_level(logging.WARNING)

    class AnyOutExecutor(Executor):
        @handler
        async def handle(self, message: str, ctx: WorkflowContext[Any]) -> None:
            return None

    start = StringExecutor(id="s")
    any_out = AnyOutExecutor(id="a")

    # Builds; later edges from this executor will skip type compatibility when outputs are unspecified
    wf = WorkflowBuilder().add_edge(start, any_out).set_start_executor(start).build()
    assert wf is not None
