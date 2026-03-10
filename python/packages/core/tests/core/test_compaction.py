# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
from typing import Any

from agent_framework import ChatResponse, Content, Message
from agent_framework._compaction import (
    EXCLUDED_KEY,
    GROUP_ANNOTATION_KEY,
    GROUP_HAS_REASONING_KEY,
    GROUP_ID_KEY,
    GROUP_KIND_KEY,
    GROUP_TOKEN_COUNT_KEY,
    SUMMARIZED_BY_SUMMARY_ID_KEY,
    SUMMARY_OF_GROUP_IDS_KEY,
    SUMMARY_OF_MESSAGE_IDS_KEY,
    CharacterEstimatorTokenizer,
    SelectiveToolCallCompactionStrategy,
    SlidingWindowStrategy,
    SummarizationStrategy,
    TokenBudgetComposedStrategy,
    TruncationStrategy,
    annotate_message_groups,
    append_compaction_message,
    apply_compaction,
    extend_compaction_messages,
    included_messages,
    included_token_count,
)


def _assistant_function_call(call_id: str) -> Message:
    return Message(
        role="assistant",
        contents=[Content.from_function_call(call_id=call_id, name="tool", arguments='{"value":"x"}')],
    )


def _assistant_reasoning_and_function_calls(*call_ids: str) -> Message:
    contents: list[Content] = [Content.from_text_reasoning(text="thinking")]
    for call_id in call_ids:
        contents.append(
            Content.from_function_call(
                call_id=call_id,
                name="tool",
                arguments='{"value":"x"}',
            )
        )
    return Message(role="assistant", contents=contents)


def _tool_result(call_id: str, result: str) -> Message:
    return Message(
        role="tool",
        contents=[Content.from_function_result(call_id=call_id, result=result)],
    )


def _group_id(message: Message) -> str | None:
    annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
    if not isinstance(annotation, dict):
        return None
    value = annotation.get(GROUP_ID_KEY)
    return value if isinstance(value, str) else None


def _group_kind(message: Message) -> str | None:
    annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
    if not isinstance(annotation, dict):
        return None
    value = annotation.get(GROUP_KIND_KEY)
    return value if isinstance(value, str) else None


def _group_has_reasoning(message: Message) -> bool | None:
    annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
    if not isinstance(annotation, dict):
        return None
    value = annotation.get(GROUP_HAS_REASONING_KEY)
    return value if isinstance(value, bool) else None


def _token_count(message: Message) -> int | None:
    annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
    if not isinstance(annotation, dict):
        return None
    value = annotation.get(GROUP_TOKEN_COUNT_KEY)
    return value if isinstance(value, int) else None


def _group_unknown_value(message: Message, key: str) -> Any:
    annotation = message.additional_properties.get(GROUP_ANNOTATION_KEY)
    if not isinstance(annotation, dict):
        return None
    return annotation.get(key)


def test_group_annotations_keep_tool_call_and_tool_result_atomic() -> None:
    messages = [
        Message(role="user", text="hello"),
        _assistant_function_call("c1"),
        _tool_result("c1", "ok"),
        Message(role="assistant", text="final"),
    ]

    annotate_message_groups(messages)

    call_group = _group_id(messages[1])
    assert call_group is not None
    assert call_group == _group_id(messages[2])
    assert _group_id(messages[1]) != _group_id(messages[0])


def test_group_annotations_include_reasoning_in_tool_call_group() -> None:
    messages = [
        _assistant_reasoning_and_function_calls("c2"),
        _tool_result("c2", "ok"),
    ]

    annotate_message_groups(messages)

    first_group = _group_id(messages[0])
    assert first_group is not None
    assert _group_id(messages[1]) == first_group
    assert _group_has_reasoning(messages[0]) is True
    assert _group_kind(messages[0]) == "tool_call"


def test_group_annotations_handle_same_message_reasoning_and_function_calls() -> None:
    messages = [
        Message(role="user", text="hello"),
        _assistant_reasoning_and_function_calls("c1", "c2"),
        _tool_result("c1", "ok1"),
        _tool_result("c2", "ok2"),
        Message(role="assistant", text="final"),
    ]

    annotate_message_groups(messages)

    call_group = _group_id(messages[1])
    assert call_group is not None
    assert _group_id(messages[2]) == call_group
    assert _group_id(messages[3]) == call_group
    assert _group_kind(messages[1]) == "tool_call"
    assert _group_has_reasoning(messages[1]) is True


def test_annotate_message_groups_with_tokenizer_adds_token_counts() -> None:
    messages = [
        Message(role="user", text="hello"),
        Message(role="assistant", text="world"),
    ]

    annotate_message_groups(
        messages,
        tokenizer=CharacterEstimatorTokenizer(),
    )

    assert isinstance(_token_count(messages[0]), int)
    assert isinstance(_token_count(messages[1]), int)


def test_extend_compaction_messages_preserves_existing_annotations_and_tokens() -> None:
    tokenizer = CharacterEstimatorTokenizer()
    messages = [_assistant_function_call("c3")]
    annotate_message_groups(messages)
    old_group_id = _group_id(messages[0])
    assert old_group_id is not None
    old_token_count = tokenizer.count_tokens("precomputed")
    annotation = messages[0].additional_properties.get(GROUP_ANNOTATION_KEY)
    if isinstance(annotation, dict):
        annotation[GROUP_TOKEN_COUNT_KEY] = old_token_count

    extend_compaction_messages(messages, [_tool_result("c3", "ok")], tokenizer=tokenizer)

    assert _group_id(messages[1]) == old_group_id
    assert _token_count(messages[0]) == old_token_count
    assert isinstance(_token_count(messages[1]), int)


def test_append_compaction_message_annotates_new_message() -> None:
    messages = [Message(role="user", text="hello")]
    annotate_message_groups(messages)
    append_compaction_message(messages, Message(role="assistant", text="world"))

    assert len(messages) == 2
    assert isinstance(_group_id(messages[1]), str)


async def test_truncation_strategy_keeps_system_anchor() -> None:
    messages = [
        Message(role="system", text="you are helpful"),
        Message(role="user", text="u1"),
        Message(role="assistant", text="a1"),
        Message(role="user", text="u2"),
        Message(role="assistant", text="a2"),
    ]
    strategy = TruncationStrategy(max_n=3, compact_to=3, preserve_system=True)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    projected = included_messages(messages)
    assert projected[0].role == "system"
    assert len(projected) <= 3


async def test_truncation_strategy_compacts_when_token_limit_exceeded() -> None:
    tokenizer = CharacterEstimatorTokenizer()
    messages = [
        Message(role="system", text="you are helpful"),
        Message(role="user", text="u1 " * 200),
        Message(role="assistant", text="a1 " * 200),
    ]
    strategy = TruncationStrategy(
        max_n=80,
        compact_to=40,
        tokenizer=tokenizer,
        preserve_system=True,
    )
    annotate_message_groups(messages, tokenizer=tokenizer)

    changed = await strategy(messages)

    assert changed is True
    projected = included_messages(messages)
    assert projected[0].role == "system"
    assert included_token_count(messages) <= 40


def test_truncation_strategy_validates_token_targets() -> None:
    try:
        TruncationStrategy(max_n=3, compact_to=4)
    except ValueError as exc:
        assert "compact_to must be less than or equal to max_n" in str(exc)
    else:
        raise AssertionError("Expected ValueError when compact_to is greater than max_n.")


async def test_selective_tool_call_strategy_excludes_older_tool_groups() -> None:
    messages = [
        Message(role="user", text="u"),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
        _assistant_function_call("call-2"),
        _tool_result("call-2", "r2"),
        Message(role="assistant", text="done"),
    ]
    strategy = SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=1)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    assert messages[1].additional_properties.get(EXCLUDED_KEY) is True
    assert messages[2].additional_properties.get(EXCLUDED_KEY) is True
    assert messages[3].additional_properties.get(EXCLUDED_KEY) is not True
    assert messages[4].additional_properties.get(EXCLUDED_KEY) is not True


async def test_selective_tool_call_strategy_with_zero_removes_assistant_tool_pair() -> None:
    messages = [
        Message(role="user", text="u"),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
        Message(role="assistant", text="done"),
    ]
    strategy = SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=0)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    assert messages[1].additional_properties.get(EXCLUDED_KEY) is True
    assert messages[2].additional_properties.get(EXCLUDED_KEY) is True
    assert messages[0].additional_properties.get(EXCLUDED_KEY) is not True
    assert messages[3].additional_properties.get(EXCLUDED_KEY) is not True


def test_selective_tool_call_strategy_rejects_negative_keep_count() -> None:
    try:
        SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=-1)
    except ValueError as exc:
        assert "must be greater than or equal to 0" in str(exc)
    else:
        raise AssertionError("Expected ValueError for negative keep_last_tool_call_groups.")


class _FakeSummarizer:
    async def get_response(
        self,
        messages: list[Message],
        *,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        return ChatResponse(messages=[Message(role="assistant", text="summarized context")])


class _FailingSummarizer:
    async def get_response(
        self,
        messages: list[Message],
        *,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        raise RuntimeError("summary failed")


class _EmptySummarizer:
    async def get_response(
        self,
        messages: list[Message],
        *,
        stream: bool = False,
        options: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ChatResponse:
        return ChatResponse(messages=[Message(role="assistant", text="   ")])


async def test_summarization_strategy_adds_bidirectional_trace_links() -> None:
    messages = [
        Message(role="user", text="u1"),
        Message(role="assistant", text="a1"),
        Message(role="user", text="u2"),
        Message(role="assistant", text="a2"),
        Message(role="user", text="u3"),
        Message(role="assistant", text="a3"),
    ]
    strategy = SummarizationStrategy(client=_FakeSummarizer(), target_count=2, threshold=0)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    summary_messages = [
        message for message in messages if _group_unknown_value(message, SUMMARY_OF_MESSAGE_IDS_KEY) is not None
    ]
    assert len(summary_messages) == 1
    summary = summary_messages[0]
    summary_id = summary.message_id
    assert summary_id is not None
    assert _group_unknown_value(summary, SUMMARY_OF_GROUP_IDS_KEY)
    summarized_message_ids = _group_unknown_value(summary, SUMMARY_OF_MESSAGE_IDS_KEY)
    assert isinstance(summarized_message_ids, list)
    for message in messages:
        if message.message_id in summarized_message_ids:
            assert _group_unknown_value(message, SUMMARIZED_BY_SUMMARY_ID_KEY) == summary_id
            assert message.additional_properties.get(EXCLUDED_KEY) is True


async def test_summarization_strategy_returns_false_when_summary_generation_fails(
    caplog: Any,
) -> None:
    messages = [
        Message(role="user", text="u1"),
        Message(role="assistant", text="a1"),
        Message(role="user", text="u2"),
        Message(role="assistant", text="a2"),
        Message(role="user", text="u3"),
        Message(role="assistant", text="a3"),
    ]
    strategy = SummarizationStrategy(client=_FailingSummarizer(), target_count=2, threshold=0)
    annotate_message_groups(messages)

    with caplog.at_level(logging.WARNING, logger="agent_framework"):
        changed = await strategy(messages)

    assert changed is False
    assert any("summary generation failed" in record.message for record in caplog.records)
    assert all(message.additional_properties.get(EXCLUDED_KEY) is not True for message in messages)


async def test_summarization_strategy_returns_false_when_summary_is_empty(
    caplog: Any,
) -> None:
    messages = [
        Message(role="user", text="u1"),
        Message(role="assistant", text="a1"),
        Message(role="user", text="u2"),
        Message(role="assistant", text="a2"),
        Message(role="user", text="u3"),
        Message(role="assistant", text="a3"),
    ]
    strategy = SummarizationStrategy(client=_EmptySummarizer(), target_count=2, threshold=0)
    annotate_message_groups(messages)

    with caplog.at_level(logging.WARNING, logger="agent_framework"):
        changed = await strategy(messages)

    assert changed is False
    assert any("returned no text" in record.message for record in caplog.records)
    assert all(message.additional_properties.get(EXCLUDED_KEY) is not True for message in messages)


async def test_token_budget_composed_strategy_meets_budget_or_falls_back() -> None:
    messages = [
        Message(role="system", text="system"),
        Message(role="user", text="user " * 200),
        Message(role="assistant", text="assistant " * 200),
    ]
    strategy = TokenBudgetComposedStrategy(
        token_budget=20,
        tokenizer=CharacterEstimatorTokenizer(),
        strategies=[SlidingWindowStrategy(keep_last_groups=1)],
    )

    changed = await strategy(messages)

    assert changed is True
    assert included_token_count(messages) <= 20


class _ExcludeOldestNonSystem:
    async def __call__(self, messages: list[Message]) -> bool:
        group_ids = annotate_message_groups(messages)
        kinds: dict[str, str] = {}
        for message in messages:
            group_id = _group_id(message)
            kind = _group_kind(message)
            if group_id is not None and kind is not None and group_id not in kinds:
                kinds[group_id] = kind
        for group_id in group_ids:
            if kinds.get(group_id) == "system":
                continue
            for message in messages:
                if _group_id(message) == group_id:
                    message.additional_properties[EXCLUDED_KEY] = True
            return True
        return False


async def test_apply_compaction_projects_included_messages_only() -> None:
    messages = [
        Message(role="system", text="sys"),
        Message(role="user", text="hello"),
        Message(role="assistant", text="world"),
    ]

    projected = await apply_compaction(messages, strategy=_ExcludeOldestNonSystem())

    assert len(projected) < len(messages)
    assert projected[0].role == "system"


# --- ToolResultCompactionStrategy tests ---

from agent_framework._compaction import (
    CompactionProvider,
    ToolResultCompactionStrategy,
)


async def test_tool_result_compaction_collapses_old_groups_into_summary() -> None:
    """Old tool-call groups are collapsed into summary messages, newest kept."""
    messages = [
        Message(role="user", text="u"),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
        _assistant_function_call("call-2"),
        _tool_result("call-2", "r2"),
        Message(role="assistant", text="done"),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=1)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    projected = included_messages(messages)
    texts = [m.text or "" for m in projected]
    summary_msgs = [t for t in texts if t.startswith("[Tool calls:")]
    assert len(summary_msgs) == 1
    assert "tool" in summary_msgs[0]
    assert any(m.role == "tool" for m in projected)


async def test_tool_result_compaction_zero_collapses_all() -> None:
    """With keep=0, all tool-call groups are collapsed into summaries."""
    messages = [
        Message(role="user", text="u"),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
        _assistant_function_call("call-2"),
        _tool_result("call-2", "r2"),
        Message(role="assistant", text="done"),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=0)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    projected = included_messages(messages)
    summary_msgs = [m for m in projected if (m.text or "").startswith("[Tool calls:")]
    assert len(summary_msgs) == 2
    assert not any(m.role == "tool" for m in projected)


async def test_tool_result_compaction_no_change_when_within_limit() -> None:
    """No compaction when tool groups count does not exceed keep limit."""
    messages = [
        Message(role="user", text="u"),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=1)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is False


def test_tool_result_compaction_rejects_negative() -> None:
    try:
        ToolResultCompactionStrategy(keep_last_tool_call_groups=-1)
    except ValueError as exc:
        assert "must be greater than or equal to 0" in str(exc)
    else:
        raise AssertionError("Expected ValueError for negative keep_last_tool_call_groups.")


async def test_tool_result_compaction_preserves_tool_names_in_summary() -> None:
    """Summary text should include all tool names from the collapsed group."""
    messages = [
        Message(role="user", text="u"),
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(call_id="c1", name="get_weather", arguments="{}"),
                Content.from_function_call(call_id="c2", name="search_docs", arguments="{}"),
            ],
        ),
        _tool_result("c1", "sunny"),
        _tool_result("c2", "found 3 docs"),
        Message(role="assistant", text="done"),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=0)
    annotate_message_groups(messages)

    await strategy(messages)

    projected = included_messages(messages)
    summary_msgs = [m for m in projected if (m.text or "").startswith("[Tool calls:")]
    assert len(summary_msgs) == 1
    assert "get_weather" in summary_msgs[0].text  # type: ignore[operator]
    assert "search_docs" in summary_msgs[0].text  # type: ignore[operator]


# --- CompactionProvider tests ---


class _MockSessionContext:
    """Minimal mock for SessionContext used in CompactionProvider tests."""

    def __init__(self) -> None:
        self.context_messages: dict[str, list[Message]] = {}
        self.input_messages: list[Message] = []
        self._response: Any = None

    @property
    def response(self) -> Any:
        return self._response

    def extend_messages(self, provider: Any, messages: list[Message]) -> None:
        source_id = getattr(provider, "source_id", "unknown")
        self.context_messages.setdefault(source_id, []).extend(messages)


class _MockResponse:
    def __init__(self, messages: list[Message]) -> None:
        self.messages = messages


async def test_compaction_provider_before_run_injects_projected_messages() -> None:
    """CompactionProvider.before_run loads, compacts, and injects messages."""
    state: dict[str, Any] = {
        "_compaction_messages": [
            Message(role="system", text="sys").to_dict(),
            Message(role="user", text="u1").to_dict(),
            Message(role="assistant", text="a1").to_dict(),
            Message(role="user", text="u2").to_dict(),
            Message(role="assistant", text="a2").to_dict(),
            Message(role="user", text="u3").to_dict(),
            Message(role="assistant", text="a3").to_dict(),
        ]
    }
    strategy = SlidingWindowStrategy(keep_last_groups=2, preserve_system=True)
    provider = CompactionProvider(strategy=strategy)

    context = _MockSessionContext()
    await provider.before_run(agent=None, session=None, context=context, state=state)

    injected = context.context_messages.get("compaction", [])
    assert len(injected) > 0
    assert injected[0].role == "system"
    assert len(injected) < 7


async def test_compaction_provider_after_run_appends_messages_to_state() -> None:
    """CompactionProvider.after_run appends new input/output messages."""
    state: dict[str, Any] = {"_compaction_messages": []}
    strategy = SlidingWindowStrategy(keep_last_groups=10)
    provider = CompactionProvider(strategy=strategy)

    context = _MockSessionContext()
    context.input_messages = [Message(role="user", text="hello")]
    context._response = _MockResponse([Message(role="assistant", text="hi")])

    await provider.after_run(agent=None, session=None, context=context, state=state)

    stored = state["_compaction_messages"]
    assert len(stored) == 2


async def test_compaction_provider_round_trip() -> None:
    """Full round trip: after_run stores, before_run loads and compacts."""
    strategy = SlidingWindowStrategy(keep_last_groups=2, preserve_system=True)
    provider = CompactionProvider(strategy=strategy)
    state: dict[str, Any] = {}

    for i in range(5):
        context = _MockSessionContext()
        context.input_messages = [Message(role="user", text=f"user turn {i}")]
        context._response = _MockResponse([Message(role="assistant", text=f"response {i}")])
        await provider.after_run(agent=None, session=None, context=context, state=state)

    inject_context = _MockSessionContext()
    await provider.before_run(agent=None, session=None, context=inject_context, state=state)

    injected = inject_context.context_messages.get("compaction", [])
    # 5 turns = 10 messages = 10 groups; sliding window keeps last 2 non-system groups
    assert len(injected) == 2


async def test_compaction_provider_empty_state_noop() -> None:
    """before_run with empty state should not inject any messages."""
    strategy = SlidingWindowStrategy(keep_last_groups=2)
    provider = CompactionProvider(strategy=strategy)
    state: dict[str, Any] = {}

    context = _MockSessionContext()
    await provider.before_run(agent=None, session=None, context=context, state=state)

    assert context.context_messages == {}
