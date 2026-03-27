# Copyright (c) Microsoft. All rights reserved.

"""Tests for evaluator checks and LocalEvaluator."""

from __future__ import annotations

import inspect

import pytest

from agent_framework._evaluation import (
    CheckResult,
    EvalItem,
    ExpectedToolCall,
    LocalEvaluator,
    _coerce_result,
    evaluator,
    keyword_check,
    tool_call_args_match,
    tool_called_check,
    tool_calls_present,
)
from agent_framework._types import Content, Message

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_item(
    query: str = "What's the weather in Paris?",
    response: str = "It's sunny and 75°F",
    expected_output: str | None = None,
    conversation: list | None = None,
    tools: list | None = None,
    context: str | None = None,
) -> EvalItem:
    if conversation is None:
        conversation = [Message("user", [query]), Message("assistant", [response])]
    return EvalItem(
        conversation=conversation,
        expected_output=expected_output,
        tools=tools,
        context=context,
    )


# ---------------------------------------------------------------------------
# Tier 1: (query, response) -> result
# ---------------------------------------------------------------------------


class TestTier1SimpleChecks:
    @pytest.mark.asyncio
    async def test_bool_return_true(self):
        @evaluator
        def has_temperature(query: str, response: str) -> bool:
            return "°F" in response

        result = await has_temperature(_make_item())
        assert result.passed is True
        assert result.check_name == "has_temperature"

    @pytest.mark.asyncio
    async def test_bool_return_false(self):
        @evaluator
        def has_celsius(query: str, response: str) -> bool:
            return "°C" in response

        result = await has_celsius(_make_item())
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_float_return_passing(self):
        @evaluator
        def length_score(response: str) -> float:
            return min(len(response) / 10, 1.0)

        result = await length_score(_make_item())
        assert result.passed is True
        assert "score=" in result.reason

    @pytest.mark.asyncio
    async def test_float_return_failing(self):
        @evaluator
        def always_low(response: str) -> float:
            return 0.1

        result = await always_low(_make_item())
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_response_only(self):
        """Function with only 'response' param should work."""

        @evaluator
        def is_short(response: str) -> bool:
            return len(response) < 1000

        result = await is_short(_make_item())
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_query_only(self):
        """Function with only 'query' param should work."""

        @evaluator
        def is_question(query: str) -> bool:
            return "?" in query

        result = await is_question(_make_item())
        assert result.passed is True


# ---------------------------------------------------------------------------
# Tier 2: (query, response, expected_output) -> result
# ---------------------------------------------------------------------------


class TestTier2GroundTruth:
    @pytest.mark.asyncio
    async def test_exact_match(self):
        @evaluator
        def exact_match(response: str, expected_output: str) -> bool:
            return response.strip() == expected_output.strip()

        item = _make_item(response="42", expected_output="42")
        assert (await exact_match(item)).passed is True

        item2 = _make_item(response="43", expected_output="42")
        assert (await exact_match(item2)).passed is False

    @pytest.mark.asyncio
    async def test_expected_output_defaults_to_empty(self):
        """When expected_output is None on the item, it should be passed as ''."""

        @evaluator
        def check_expected(expected_output: str) -> bool:
            return expected_output == ""

        result = await check_expected(_make_item(expected_output=None))
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_similarity_score(self):
        @evaluator
        def word_overlap(response: str, expected_output: str) -> float:
            r_words = set(response.lower().split())
            e_words = set(expected_output.lower().split())
            if not e_words:
                return 1.0
            return len(r_words & e_words) / len(e_words)

        item = _make_item(response="sunny warm day", expected_output="warm sunny afternoon")
        result = await word_overlap(item)
        assert result.passed is True  # 2/3 overlap ≥ 0.5


# ---------------------------------------------------------------------------
# Tier 3: full context (conversation, tools, context)
# ---------------------------------------------------------------------------


class TestTier3FullContext:
    @pytest.mark.asyncio
    async def test_conversation_access(self):
        @evaluator
        def multi_turn(query: str, response: str, *, conversation: list) -> bool:
            return len(conversation) >= 2

        item = _make_item(conversation=[Message("user", []), Message("assistant", [])])
        assert (await multi_turn(item)).passed is True

        item2 = _make_item(conversation=[Message("user", [])])
        assert (await multi_turn(item2)).passed is False

    @pytest.mark.asyncio
    async def test_tools_access(self):
        @evaluator
        def has_tools(tools: list) -> bool:
            return len(tools) > 0

        mock_tool = type(
            "MockTool",
            (),
            {"name": "get_weather", "description": "Get weather", "parameters": lambda self: {}},
        )()
        item = _make_item(tools=[mock_tool])
        assert (await has_tools(item)).passed is True

    @pytest.mark.asyncio
    async def test_context_access(self):
        @evaluator
        def grounded(response: str, context: str) -> bool:
            if not context:
                return True
            return any(word in response.lower() for word in context.lower().split())

        item = _make_item(response="It's sunny", context="sunny warm")
        assert (await grounded(item)).passed is True

    @pytest.mark.asyncio
    async def test_all_params(self):
        @evaluator
        def full_check(
            query: str,
            response: str,
            expected_output: str,
            conversation: list,
            tools: list,
            context: str,
        ) -> bool:
            return all([query, response, expected_output is not None, isinstance(conversation, list)])

        item = _make_item(expected_output="foo", context="bar")
        assert (await full_check(item)).passed is True


# ---------------------------------------------------------------------------
# Return type coercion
# ---------------------------------------------------------------------------


class TestReturnTypeCoercion:
    @pytest.mark.asyncio
    async def test_dict_with_score(self):
        @evaluator
        def scored(response: str) -> dict:
            return {"score": 0.9, "reason": "good answer"}

        result = await scored(_make_item())
        assert result.passed is True
        assert result.reason == "good answer"

    @pytest.mark.asyncio
    async def test_dict_with_score_below_threshold(self):
        @evaluator
        def low_scored(response: str) -> dict:
            return {"score": 0.3}

        result = await low_scored(_make_item())
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_dict_with_custom_threshold(self):
        @evaluator
        def custom_threshold(response: str) -> dict:
            return {"score": 0.3, "threshold": 0.2}

        result = await custom_threshold(_make_item())
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_dict_with_passed(self):
        @evaluator
        def explicit_pass(response: str) -> dict:
            return {"passed": True, "reason": "all good"}

        result = await explicit_pass(_make_item())
        assert result.passed is True
        assert result.reason == "all good"

    @pytest.mark.asyncio
    async def test_check_result_passthrough(self):
        @evaluator
        def returns_check_result(response: str) -> CheckResult:
            return CheckResult(True, "direct result", "custom")

        result = await returns_check_result(_make_item())
        assert result.passed is True
        assert result.reason == "direct result"
        assert result.check_name == "custom"

    @pytest.mark.asyncio
    async def test_unsupported_return_type(self):
        @evaluator
        def bad_return(response: str) -> str:
            return "oops"

        with pytest.raises(TypeError, match="unsupported type"):
            await bad_return(_make_item())

    @pytest.mark.asyncio
    async def test_int_return(self):
        @evaluator
        def int_score(response: str) -> int:
            return 1

        result = await int_score(_make_item())
        assert result.passed is True


# ---------------------------------------------------------------------------
# Decorator variants
# ---------------------------------------------------------------------------


class TestDecoratorVariants:
    @pytest.mark.asyncio
    async def test_decorator_no_parens(self):
        @evaluator
        def my_check(response: str) -> bool:
            return True

        assert (await my_check(_make_item())).passed is True

    @pytest.mark.asyncio
    async def test_decorator_with_name(self):
        @evaluator(name="custom_name")
        def my_check(response: str) -> bool:
            return True

        assert my_check.__name__ == "custom_name"
        result = await my_check(_make_item())
        assert result.check_name == "custom_name"

    @pytest.mark.asyncio
    async def test_direct_call(self):
        def raw_fn(query: str, response: str) -> bool:
            return len(response) > 0

        check = evaluator(raw_fn, name="direct")
        result = await check(_make_item())
        assert result.passed is True
        assert result.check_name == "direct"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_unknown_required_param_raises(self):
        with pytest.raises(TypeError, match="unknown required parameter"):

            @evaluator
            def bad_params(query: str, unknown_param: str) -> bool:
                return True

    @pytest.mark.asyncio
    async def test_unknown_optional_param_ok(self):
        @evaluator
        def optional_unknown(query: str, foo: str = "default") -> bool:
            return foo == "default"

        result = await optional_unknown(_make_item())
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_async_function_works_with_evaluator(self):
        """Using an async function with @evaluator should work."""

        @evaluator
        async def async_fn(response: str) -> bool:
            return True

        result = async_fn(_make_item())
        # Should return an awaitable
        assert inspect.isawaitable(result)
        check_result = await result
        assert check_result.passed is True


# ---------------------------------------------------------------------------
# Integration with LocalEvaluator
# ---------------------------------------------------------------------------


class TestLocalEvaluatorIntegration:
    @pytest.mark.asyncio
    async def test_mixed_checks(self):
        """Function evaluators mix with built-in checks in LocalEvaluator."""

        @evaluator
        def length_ok(response: str) -> bool:
            return len(response) > 5

        local = LocalEvaluator(
            keyword_check("sunny"),
            length_ok,
        )
        items = [_make_item()]
        results = await local.evaluate(items, eval_name="mixed test")

        assert results.status == "completed"
        assert results.result_counts["passed"] == 1
        assert results.result_counts["failed"] == 0

    @pytest.mark.asyncio
    async def test_evaluator_failure_counted(self):
        @evaluator
        def always_fail(response: str) -> bool:
            return False

        local = LocalEvaluator(always_fail)
        results = await local.evaluate([_make_item()])

        assert results.result_counts["failed"] == 1

    @pytest.mark.asyncio
    async def test_multiple_evaluators(self):
        @evaluator
        def check_a(response: str) -> float:
            return 0.9

        @evaluator
        def check_b(query: str, response: str, expected_output: str) -> bool:
            return True

        @evaluator(name="check_c")
        def check_c(response: str, conversation: list) -> dict:
            return {"score": 0.8, "reason": "looks good"}

        local = LocalEvaluator(check_a, check_b, check_c)
        results = await local.evaluate([_make_item(expected_output="test")])

        assert results.result_counts["passed"] == 1
        assert "check_a" in results.per_evaluator
        assert "check_b" in results.per_evaluator
        assert "check_c" in results.per_evaluator


# ---------------------------------------------------------------------------
# Async evaluator (via @evaluator which handles async automatically)
# ---------------------------------------------------------------------------


class TestAsyncFunctionEvaluator:
    @pytest.mark.asyncio
    async def test_async_evaluator_in_local(self):
        @evaluator
        async def async_check(query: str, response: str) -> bool:
            return len(response) > 0

        local = LocalEvaluator(async_check)
        results = await local.evaluate([_make_item()])
        assert results.result_counts["passed"] == 1

    @pytest.mark.asyncio
    async def test_async_with_name(self):
        @evaluator(name="named_async")
        async def my_async(response: str) -> float:
            return 0.75

        result = await my_async(_make_item())
        assert result.passed is True
        assert result.check_name == "named_async"


# ---------------------------------------------------------------------------
# Auto-wrapping bare checks in evaluate_agent
# ---------------------------------------------------------------------------


class TestAutoWrapEvalChecks:
    @pytest.mark.asyncio
    async def test_bare_check_in_evaluators_list(self):
        """Bare EvalCheck callables are auto-wrapped in LocalEvaluator."""
        from agent_framework._evaluation import _run_evaluators

        @evaluator
        def is_long(response: str) -> bool:
            return len(response.split()) > 2

        items = [_make_item(response="It is sunny and warm today")]
        results = await _run_evaluators(is_long, items, eval_name="test")
        assert len(results) == 1
        assert results[0].result_counts["passed"] == 1

    @pytest.mark.asyncio
    async def test_mixed_evaluators_and_checks(self):
        """Mix of Evaluator instances and bare checks works."""
        from agent_framework._evaluation import _run_evaluators

        @evaluator
        def has_words(response: str) -> bool:
            return len(response.split()) > 0

        local = LocalEvaluator(keyword_check("sunny"))

        items = [_make_item(response="It is sunny")]
        results = await _run_evaluators([local, has_words], items, eval_name="test")
        assert len(results) == 2
        assert all(r.result_counts["passed"] == 1 for r in results)

    @pytest.mark.asyncio
    async def test_adjacent_checks_grouped(self):
        """Adjacent bare checks are grouped into a single LocalEvaluator."""
        from agent_framework._evaluation import _run_evaluators

        @evaluator
        def check_a(response: str) -> bool:
            return True

        @evaluator
        def check_b(response: str) -> bool:
            return True

        items = [_make_item()]
        results = await _run_evaluators([check_a, check_b], items, eval_name="test")
        # Two adjacent checks → one LocalEvaluator → one result
        assert len(results) == 1
        assert results[0].result_counts["passed"] == 1


# ---------------------------------------------------------------------------
# Expected Tool Calls
# ---------------------------------------------------------------------------


def _make_tool_call_item(
    calls: list[tuple[str, dict | None]],
    expected: list[ExpectedToolCall] | None = None,
) -> EvalItem:
    """Build an EvalItem with tool calls in the conversation."""
    msgs: list[Message] = [Message("user", ["Do something"])]
    for name, args in calls:
        msgs.append(Message("assistant", [Content.from_function_call("call_" + name, name, arguments=args)]))
    msgs.append(Message("assistant", ["Done"]))
    return EvalItem(conversation=msgs, expected_tool_calls=expected)


class TestExpectedToolCallType:
    def test_name_only(self):
        tc = ExpectedToolCall("get_weather")
        assert tc.name == "get_weather"
        assert tc.arguments is None

    def test_name_and_args(self):
        tc = ExpectedToolCall("get_weather", {"location": "NYC"})
        assert tc.name == "get_weather"
        assert tc.arguments == {"location": "NYC"}


class TestToolCallsPresent:
    def test_all_present(self):
        item = _make_tool_call_item(
            calls=[("get_weather", None), ("get_news", None)],
            expected=[ExpectedToolCall("get_weather"), ExpectedToolCall("get_news")],
        )
        result = tool_calls_present(item)
        assert result.passed is True
        assert result.check_name == "tool_calls_present"

    def test_missing_tool(self):
        item = _make_tool_call_item(
            calls=[("get_weather", None)],
            expected=[ExpectedToolCall("get_weather"), ExpectedToolCall("get_news")],
        )
        result = tool_calls_present(item)
        assert result.passed is False
        assert "get_news" in result.reason

    def test_extras_ok(self):
        item = _make_tool_call_item(
            calls=[("get_weather", None), ("get_news", None), ("get_stock", None)],
            expected=[ExpectedToolCall("get_weather")],
        )
        result = tool_calls_present(item)
        assert result.passed is True

    def test_no_expected(self):
        item = _make_tool_call_item(calls=[("get_weather", None)])
        result = tool_calls_present(item)
        assert result.passed is True
        assert "No expected" in result.reason


class TestToolCallArgsMatch:
    def test_name_only_match(self):
        item = _make_tool_call_item(
            calls=[("get_weather", {"location": "NYC"})],
            expected=[ExpectedToolCall("get_weather")],
        )
        result = tool_call_args_match(item)
        assert result.passed is True

    def test_args_exact_match(self):
        item = _make_tool_call_item(
            calls=[("get_weather", {"location": "NYC", "units": "fahrenheit"})],
            expected=[ExpectedToolCall("get_weather", {"location": "NYC"})],
        )
        # Subset match — extra "units" key is OK
        result = tool_call_args_match(item)
        assert result.passed is True

    def test_args_mismatch(self):
        item = _make_tool_call_item(
            calls=[("get_weather", {"location": "LA"})],
            expected=[ExpectedToolCall("get_weather", {"location": "NYC"})],
        )
        result = tool_call_args_match(item)
        assert result.passed is False
        assert "args mismatch" in result.reason

    def test_tool_not_called(self):
        item = _make_tool_call_item(
            calls=[("get_news", None)],
            expected=[ExpectedToolCall("get_weather", {"location": "NYC"})],
        )
        result = tool_call_args_match(item)
        assert result.passed is False
        assert "not called" in result.reason

    def test_multiple_expected(self):
        item = _make_tool_call_item(
            calls=[
                ("get_weather", {"location": "NYC"}),
                ("book_flight", {"destination": "LA", "date": "tomorrow"}),
            ],
            expected=[
                ExpectedToolCall("get_weather", {"location": "NYC"}),
                ExpectedToolCall("book_flight", {"destination": "LA"}),
            ],
        )
        result = tool_call_args_match(item)
        assert result.passed is True

    def test_no_expected(self):
        item = _make_tool_call_item(calls=[("get_weather", None)])
        result = tool_call_args_match(item)
        assert result.passed is True


class TestExpectedToolCallsFieldInjection:
    """Test that @evaluator can receive expected_tool_calls via parameter injection."""

    @pytest.mark.asyncio
    async def test_injection(self):
        @evaluator
        def check_tools(expected_tool_calls: list) -> bool:
            return len(expected_tool_calls) == 2

        item = _make_tool_call_item(
            calls=[],
            expected=[ExpectedToolCall("a"), ExpectedToolCall("b")],
        )
        result = await check_tools(item)
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_injection_empty_default(self):
        @evaluator
        def check_tools(expected_tool_calls: list) -> bool:
            return len(expected_tool_calls) == 0

        item = _make_tool_call_item(calls=[])
        result = await check_tools(item)
        assert result.passed is True


# ---------------------------------------------------------------------------
# Per-item results (auditing)
# ---------------------------------------------------------------------------


class TestPerItemResults:
    """LocalEvaluator should produce per-item EvalItemResult with query/response."""

    @pytest.mark.asyncio
    async def test_items_populated_with_query_and_response(self):
        @evaluator
        def is_sunny(response: str) -> bool:
            return "sunny" in response.lower()

        item = _make_item(query="Weather?", response="It's sunny!")
        local = LocalEvaluator(is_sunny)
        results = await local.evaluate([item])

        assert len(results.items) == 1
        ri = results.items[0]
        assert ri.item_id == "0"
        assert ri.status == "pass"
        assert ri.input_text == "Weather?"
        assert ri.output_text == "It's sunny!"
        assert len(ri.scores) == 1
        assert ri.scores[0].name == "is_sunny"
        assert ri.scores[0].passed is True

    @pytest.mark.asyncio
    async def test_items_populated_on_failure(self):
        @evaluator
        def always_fail(response: str) -> bool:
            return False

        item = _make_item(query="Hello", response="World")
        local = LocalEvaluator(always_fail)
        results = await local.evaluate([item])

        assert len(results.items) == 1
        ri = results.items[0]
        assert ri.status == "fail"
        assert ri.input_text == "Hello"
        assert ri.output_text == "World"
        assert ri.scores[0].passed is False
        assert ri.scores[0].score == 0.0

    @pytest.mark.asyncio
    async def test_multiple_items_indexed(self):
        @evaluator
        def pass_all(response: str) -> bool:
            return True

        items = [
            _make_item(query="Q1", response="R1"),
            _make_item(query="Q2", response="R2"),
        ]
        local = LocalEvaluator(pass_all)
        results = await local.evaluate(items)

        assert len(results.items) == 2
        assert results.items[0].item_id == "0"
        assert results.items[0].input_text == "Q1"
        assert results.items[0].output_text == "R1"
        assert results.items[1].item_id == "1"
        assert results.items[1].input_text == "Q2"
        assert results.items[1].output_text == "R2"


# ---------------------------------------------------------------------------
# num_repetitions validation
# ---------------------------------------------------------------------------


class TestNumRepetitions:
    """Tests for the num_repetitions parameter on evaluate_agent."""

    @pytest.mark.asyncio
    async def test_num_repetitions_validation_rejects_zero(self):
        from agent_framework._evaluation import evaluate_agent

        with pytest.raises(ValueError, match="num_repetitions must be >= 1"):
            await evaluate_agent(
                queries=["Hello"],
                evaluators=LocalEvaluator(keyword_check("hello")),
                num_repetitions=0,
            )

    @pytest.mark.asyncio
    async def test_num_repetitions_validation_rejects_negative(self):
        from agent_framework._evaluation import evaluate_agent

        with pytest.raises(ValueError, match="num_repetitions must be >= 1"):
            await evaluate_agent(
                queries=["Hello"],
                evaluators=LocalEvaluator(keyword_check("hello")),
                num_repetitions=-1,
            )

    @pytest.mark.asyncio
    async def test_num_repetitions_multiplies_items(self):
        """num_repetitions=2 produces 2× the eval items."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._evaluation import evaluate_agent
        from agent_framework._types import AgentResponse, Message

        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.default_options = {}
        mock_agent.run = AsyncMock(return_value=AgentResponse(messages=[Message("assistant", ["reply"])]))

        results = await evaluate_agent(
            agent=mock_agent,
            queries=["Q1", "Q2"],
            evaluators=LocalEvaluator(keyword_check("reply")),
            num_repetitions=2,
        )
        # 2 queries × 2 reps = 4 items
        assert results[0].total == 4
        assert mock_agent.run.call_count == 4

    @pytest.mark.asyncio
    async def test_num_repetitions_with_expected_output(self):
        """num_repetitions > 1 correctly stamps expected_output via modulo."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._evaluation import evaluate_agent
        from agent_framework._types import AgentResponse, Message

        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.default_options = {}
        mock_agent.run = AsyncMock(return_value=AgentResponse(messages=[Message("assistant", ["reply"])]))

        @evaluator
        def check_expected(response: str, expected_output: str) -> dict:
            return {"passed": expected_output in ("A", "B"), "reason": f"expected={expected_output}"}

        results = await evaluate_agent(
            agent=mock_agent,
            queries=["Q1", "Q2"],
            expected_output=["A", "B"],
            evaluators=LocalEvaluator(check_expected),
            num_repetitions=2,
        )
        # 2 queries × 2 reps = 4 items, all should pass
        assert results[0].total == 4
        assert results[0].passed == 4

    @pytest.mark.asyncio
    async def test_num_repetitions_with_expected_tool_calls(self):
        """num_repetitions > 1 correctly stamps expected_tool_calls via modulo."""
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._evaluation import evaluate_agent
        from agent_framework._types import AgentResponse, Content, Message

        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.default_options = {}
        mock_agent.run = AsyncMock(
            return_value=AgentResponse(
                messages=[
                    Message(
                        "assistant",
                        [Content.from_function_call("c1", "get_weather", arguments={"location": "NYC"})],
                    ),
                    Message("tool", [Content.from_function_result("c1", result="Sunny")]),
                    Message("assistant", ["It's sunny"]),
                ]
            )
        )

        results = await evaluate_agent(
            agent=mock_agent,
            queries=["Q1"],
            expected_tool_calls=[[ExpectedToolCall("get_weather")]],
            evaluators=LocalEvaluator(tool_calls_present),
            num_repetitions=2,
        )
        # 1 query × 2 reps = 2 items
        assert results[0].total == 2
        assert results[0].passed == 2


# ---------------------------------------------------------------------------
# r3 review: additional test coverage
# ---------------------------------------------------------------------------


class TestToolCalledCheckModeAny:
    """Tests for tool_called_check with mode='any'."""

    async def test_any_mode_one_tool_called(self):
        """mode='any' passes when at least one expected tool is called."""
        item = _make_item(
            conversation=[
                Message("user", ["Do something"]),
                Message("assistant", [Content.from_function_call("c1", "tool_a", arguments={})]),
                Message("tool", [Content.from_function_result("c1", result="ok")]),
                Message("assistant", ["Done"]),
            ]
        )
        check = tool_called_check("tool_a", "tool_b", mode="any")
        result = check(item)
        assert result.passed is True

    async def test_any_mode_none_called(self):
        """mode='any' fails when no expected tools are called."""
        item = _make_item(
            conversation=[
                Message("user", ["Do something"]),
                Message("assistant", ["I can't use tools"]),
            ]
        )
        check = tool_called_check("tool_a", "tool_b", mode="any")
        result = check(item)
        assert result.passed is False
        assert "None of expected tools" in result.reason


class TestCoerceResultScoreError:
    """Tests for _coerce_result handling non-numeric score."""

    def test_non_numeric_score_raises(self):
        """Dict with non-numeric score raises TypeError."""
        with pytest.raises(TypeError, match="non-numeric 'score'"):
            _coerce_result({"score": "high"}, "test_check")

    def test_none_score_raises(self):
        with pytest.raises(TypeError, match="non-numeric 'score'"):
            _coerce_result({"score": None}, "test_check")


class TestBareCheckViaEvaluateAgent:
    """Test bare callable check functions through the public evaluate_agent API."""

    async def test_bare_check_through_evaluate_agent(self):
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._evaluation import evaluate_agent
        from agent_framework._types import AgentResponse

        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.default_options = {}
        mock_agent.run = AsyncMock(
            return_value=AgentResponse(messages=[Message("assistant", ["The weather is sunny"])])
        )

        is_long = keyword_check("weather")

        results = await evaluate_agent(
            agent=mock_agent,
            queries=["Q"],
            evaluators=is_long,
        )
        assert results[0].total == 1
        assert results[0].passed == 1


class TestEvaluateAgentModuloWrapping:
    """Test that expected_output stamps correctly with num_repetitions > 1 and multiple queries."""

    async def test_modulo_stamps_correct_expected_output(self):
        from unittest.mock import AsyncMock, MagicMock

        from agent_framework._evaluation import evaluate_agent
        from agent_framework._types import AgentResponse

        mock_agent = MagicMock()
        mock_agent.name = "test"
        mock_agent.default_options = {}
        mock_agent.run = AsyncMock(return_value=AgentResponse(messages=[Message("assistant", ["reply"])]))

        # Track which expected_output each item gets
        seen_expected: list[str] = []

        @evaluator
        def capture_expected(response: str, expected_output: str) -> dict:
            seen_expected.append(expected_output)
            return {"passed": True, "reason": "ok"}

        await evaluate_agent(
            agent=mock_agent,
            queries=["Q1", "Q2", "Q3"],
            expected_output=["A", "B", "C"],
            evaluators=LocalEvaluator(capture_expected),
            num_repetitions=2,
        )
        # 3 queries × 2 reps = 6 items; modulo wrapping: A,B,C,A,B,C
        assert seen_expected == ["A", "B", "C", "A", "B", "C"]


class TestEvaluateAgentQueriesWithoutAgent:
    """Test error message when queries provided without agent."""

    async def test_queries_without_agent_gives_clear_error(self):
        from agent_framework._evaluation import evaluate_agent

        with pytest.raises(ValueError, match="Provide 'agent' when using 'queries'"):
            await evaluate_agent(
                queries=["hello"],
                evaluators=LocalEvaluator(keyword_check("x")),
            )


# ---------------------------------------------------------------------------
# r5 review: all_passed with result_counts=None + sub_results
# ---------------------------------------------------------------------------


class TestAllPassedSubResults:
    """Tests for EvalResults.all_passed with sub_results."""

    def test_all_passed_ignores_own_counts_when_none(self):
        """When result_counts is None (aggregate), all_passed delegates to sub_results."""
        from agent_framework._evaluation import EvalResults

        sub_pass = EvalResults(
            provider="Local",
            eval_id="e1",
            run_id="r1",
            status="completed",
            result_counts={"passed": 2, "failed": 0, "errored": 0},
        )
        parent = EvalResults(
            provider="Local",
            eval_id="e0",
            run_id="r0",
            status="completed",
            result_counts=None,
            sub_results={"agent1": sub_pass},
        )
        assert parent.all_passed is True

    def test_all_passed_parent_fails_when_own_counts_fail(self):
        """When parent has result_counts with failures, all_passed is False even if sub_results pass."""
        from agent_framework._evaluation import EvalResults

        sub_pass = EvalResults(
            provider="Local",
            eval_id="e1",
            run_id="r1",
            status="completed",
            result_counts={"passed": 2, "failed": 0, "errored": 0},
        )
        parent = EvalResults(
            provider="Local",
            eval_id="e0",
            run_id="r0",
            status="completed",
            result_counts={"passed": 1, "failed": 1, "errored": 0},
            sub_results={"agent1": sub_pass},
        )
        assert parent.all_passed is False


# ---------------------------------------------------------------------------
# r5 review: _build_overall_item with empty outputs
# ---------------------------------------------------------------------------


class TestBuildOverallItemEmpty:
    """Test _build_overall_item returns None for empty workflow outputs."""

    def test_returns_none_for_empty_outputs(self):
        from unittest.mock import MagicMock

        from agent_framework._evaluation import _build_overall_item

        mock_result = MagicMock()
        mock_result.get_outputs.return_value = []
        item = _build_overall_item("Hello", mock_result)
        assert item is None
