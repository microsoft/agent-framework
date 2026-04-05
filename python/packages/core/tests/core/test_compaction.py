# Copyright (c) Microsoft. All rights reserved.

from __future__ import annotations

import logging
from typing import Any

from agent_framework import (
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
    ChatResponse,
    CompactionProvider,
    Content,
    Message,
    SelectiveToolCallCompactionStrategy,
    SlidingWindowStrategy,
    SummarizationStrategy,
    TokenBudgetComposedStrategy,
    ToolResultCompactionStrategy,
    TruncationStrategy,
    annotate_message_groups,
    apply_compaction,
    included_messages,
    included_token_count,
)
from agent_framework._compaction import (
    append_compaction_message,
    extend_compaction_messages,
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
        Message(role="user", contents=["hello"]),
        _assistant_function_call("c1"),
        _tool_result("c1", "ok"),
        Message(role="assistant", contents=["final"]),
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
        Message(role="user", contents=["hello"]),
        _assistant_reasoning_and_function_calls("c1", "c2"),
        _tool_result("c1", "ok1"),
        _tool_result("c2", "ok2"),
        Message(role="assistant", contents=["final"]),
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
        Message(role="user", contents=["hello"]),
        Message(role="assistant", contents=["world"]),
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
    messages = [Message(role="user", contents=["hello"])]
    annotate_message_groups(messages)
    append_compaction_message(messages, Message(role="assistant", contents=["world"]))

    assert len(messages) == 2
    assert isinstance(_group_id(messages[1]), str)


async def test_truncation_strategy_keeps_system_anchor() -> None:
    messages = [
        Message(role="system", contents=["you are helpful"]),
        Message(role="user", contents=["u1"]),
        Message(role="assistant", contents=["a1"]),
        Message(role="user", contents=["u2"]),
        Message(role="assistant", contents=["a2"]),
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
        Message(role="system", contents=["you are helpful"]),
        Message(role="user", contents=["u1 " * 200]),
        Message(role="assistant", contents=["a1 " * 200]),
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
        Message(role="user", contents=["u"]),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
        _assistant_function_call("call-2"),
        _tool_result("call-2", "r2"),
        Message(role="assistant", contents=["done"]),
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
        Message(role="user", contents=["u"]),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
        Message(role="assistant", contents=["done"]),
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
        return ChatResponse(messages=[Message(role="assistant", contents=["summarized context"])])


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
        return ChatResponse(messages=[Message(role="assistant", contents=["   "])])


async def test_summarization_strategy_adds_bidirectional_trace_links() -> None:
    messages = [
        Message(role="user", contents=["u1"]),
        Message(role="assistant", contents=["a1"]),
        Message(role="user", contents=["u2"]),
        Message(role="assistant", contents=["a2"]),
        Message(role="user", contents=["u3"]),
        Message(role="assistant", contents=["a3"]),
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
        Message(role="user", contents=["u1"]),
        Message(role="assistant", contents=["a1"]),
        Message(role="user", contents=["u2"]),
        Message(role="assistant", contents=["a2"]),
        Message(role="user", contents=["u3"]),
        Message(role="assistant", contents=["a3"]),
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
        Message(role="user", contents=["u1"]),
        Message(role="assistant", contents=["a1"]),
        Message(role="user", contents=["u2"]),
        Message(role="assistant", contents=["a2"]),
        Message(role="user", contents=["u3"]),
        Message(role="assistant", contents=["a3"]),
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
        Message(role="system", contents=["system"]),
        Message(role="user", contents=["user " * 200]),
        Message(role="assistant", contents=["assistant " * 200]),
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
        Message(role="system", contents=["sys"]),
        Message(role="user", contents=["hello"]),
        Message(role="assistant", contents=["world"]),
    ]

    projected = await apply_compaction(messages, strategy=_ExcludeOldestNonSystem())

    assert len(projected) < len(messages)
    assert projected[0].role == "system"


# --- ToolResultCompactionStrategy tests ---


async def test_tool_result_compaction_collapses_old_groups_into_summary() -> None:
    """Old tool-call groups are collapsed into summary messages, newest kept."""
    messages = [
        Message(role="user", contents=["u"]),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
        _assistant_function_call("call-2"),
        _tool_result("call-2", "r2"),
        Message(role="assistant", contents=["done"]),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=1)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    projected = included_messages(messages)
    texts = [m.text or "" for m in projected]
    summary_msgs = [t for t in texts if t.startswith("[Tool results:")]
    assert len(summary_msgs) == 1
    assert "r1" in summary_msgs[0]
    assert any(m.role == "tool" for m in projected)


async def test_tool_result_compaction_zero_collapses_all() -> None:
    """With keep=0, all tool-call groups are collapsed into summaries."""
    messages = [
        Message(role="user", contents=["u"]),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
        _assistant_function_call("call-2"),
        _tool_result("call-2", "r2"),
        Message(role="assistant", contents=["done"]),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=0)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    projected = included_messages(messages)
    summary_msgs = [m for m in projected if (m.text or "").startswith("[Tool results:")]
    assert len(summary_msgs) == 2
    assert not any(m.role == "tool" for m in projected)


async def test_tool_result_compaction_no_change_when_within_limit() -> None:
    """No compaction when tool groups count does not exceed keep limit."""
    messages = [
        Message(role="user", contents=["u"]),
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


async def test_tool_result_compaction_preserves_tool_results_in_summary() -> None:
    """Summary text should include the tool results from the collapsed group."""
    messages = [
        Message(role="user", contents=["u"]),
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(call_id="c1", name="get_weather", arguments="{}"),
                Content.from_function_call(call_id="c2", name="search_docs", arguments="{}"),
            ],
        ),
        _tool_result("c1", "sunny"),
        _tool_result("c2", "found 3 docs"),
        Message(role="assistant", contents=["done"]),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=0)
    annotate_message_groups(messages)

    await strategy(messages)

    projected = included_messages(messages)
    summary_msgs = [m for m in projected if (m.text or "").startswith("[Tool results:")]
    assert len(summary_msgs) == 1
    assert "sunny" in summary_msgs[0].text  # type: ignore[operator]
    assert "found 3 docs" in summary_msgs[0].text  # type: ignore[operator]


async def test_tool_result_compaction_bidirectional_tracing() -> None:
    """Summary and originals should link to each other like SummarizationStrategy does."""
    messages = [
        Message(role="user", contents=["u"]),
        _assistant_function_call("call-1"),
        _tool_result("call-1", "r1"),
        Message(role="assistant", contents=["done"]),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=0)
    annotate_message_groups(messages)

    await strategy(messages)

    # Find the summary message.
    summary_msgs = [m for m in messages if _group_unknown_value(m, SUMMARY_OF_MESSAGE_IDS_KEY) is not None]
    assert len(summary_msgs) == 1
    summary = summary_msgs[0]
    summary_id = summary.message_id
    assert summary_id is not None

    # Forward link: summary knows which messages/groups it replaces.
    assert isinstance(_group_unknown_value(summary, SUMMARY_OF_MESSAGE_IDS_KEY), list)
    assert isinstance(_group_unknown_value(summary, SUMMARY_OF_GROUP_IDS_KEY), list)

    # Back link: excluded originals know which summary replaced them.
    for m in messages:
        if m.additional_properties.get(EXCLUDED_KEY):
            assert _group_unknown_value(m, SUMMARIZED_BY_SUMMARY_ID_KEY) == summary_id

    # Core compaction annotations must be present on the summary message.
    assert _group_id(summary) is not None
    assert _group_kind(summary) is not None
    assert summary.additional_properties.get(EXCLUDED_KEY) is False


async def test_tool_result_compaction_summary_has_full_annotations() -> None:
    """Summary messages inserted by ToolResultCompactionStrategy must have all compaction annotations."""
    messages = [
        Message(role="user", contents=["u"]),
        _assistant_function_call("c1"),
        _tool_result("c1", "r1"),
        Message(role="assistant", contents=["done"]),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=0)
    annotate_message_groups(messages)

    await strategy(messages)

    summary = next(m for m in messages if (m.text or "").startswith("[Tool results:"))
    annotation = summary.additional_properties.get(GROUP_ANNOTATION_KEY)
    assert isinstance(annotation, dict)
    assert GROUP_ID_KEY in annotation
    assert GROUP_KIND_KEY in annotation
    assert GROUP_HAS_REASONING_KEY in annotation
    assert SUMMARY_OF_MESSAGE_IDS_KEY in annotation
    assert summary.additional_properties.get(EXCLUDED_KEY) is False


async def test_summarization_strategy_summary_has_full_annotations() -> None:
    """Summary messages inserted by SummarizationStrategy must have all compaction annotations."""
    messages = [
        Message(role="user", contents=["u1"]),
        Message(role="assistant", contents=["a1"]),
        Message(role="user", contents=["u2"]),
        Message(role="assistant", contents=["a2"]),
        Message(role="user", contents=["u3"]),
        Message(role="assistant", contents=["a3"]),
    ]
    strategy = SummarizationStrategy(client=_FakeSummarizer(), target_count=2, threshold=0)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    summary = next(m for m in messages if _group_unknown_value(m, SUMMARY_OF_MESSAGE_IDS_KEY) is not None)
    annotation = summary.additional_properties.get(GROUP_ANNOTATION_KEY)
    assert isinstance(annotation, dict)
    assert GROUP_ID_KEY in annotation
    assert GROUP_KIND_KEY in annotation
    assert GROUP_HAS_REASONING_KEY in annotation
    assert SUMMARY_OF_MESSAGE_IDS_KEY in annotation
    assert summary.additional_properties.get(EXCLUDED_KEY) is False


async def test_tool_result_compaction_multiple_groups_combined() -> None:
    """Multiple tool-call groups collapsed independently, each with its own summary.

    Scenario: 3 tool-call groups, keep_last=1 → groups 1 and 2 each get a
    separate summary, group 3 stays verbatim.
    """
    messages = [
        Message(role="user", contents=["Compare weather in London, Paris, and Tokyo"]),
        # Group 1: get_weather for London
        Message(
            role="assistant",
            contents=[Content.from_function_call(call_id="c1", name="get_weather", arguments='{"city":"London"}')],
        ),
        _tool_result("c1", '{"temp":12,"condition":"cloudy","wind":"NW 15km/h"}'),
        Message(role="assistant", contents=["London is cloudy at 12°C."]),
        # Group 2: get_weather for Paris + search_hotels
        Message(
            role="assistant",
            contents=[
                Content.from_function_call(call_id="c2", name="get_weather", arguments='{"city":"Paris"}'),
                Content.from_function_call(call_id="c3", name="search_hotels", arguments='{"city":"Paris"}'),
            ],
        ),
        _tool_result("c2", '{"temp":18,"condition":"sunny"}'),
        _tool_result("c3", "Grand Hotel (€120), Le Petit (€85)"),
        Message(role="assistant", contents=["Paris is sunny at 18°C. Found 2 hotels."]),
        # Group 3: get_weather for Tokyo (most recent — should be kept)
        Message(
            role="assistant",
            contents=[Content.from_function_call(call_id="c4", name="get_weather", arguments='{"city":"Tokyo"}')],
        ),
        _tool_result("c4", '{"temp":22,"condition":"rainy"}'),
        Message(role="assistant", contents=["Tokyo is rainy at 22°C."]),
    ]
    strategy = ToolResultCompactionStrategy(keep_last_tool_call_groups=1)
    annotate_message_groups(messages)

    changed = await strategy(messages)

    assert changed is True
    projected = included_messages(messages)
    summary_msgs = [m for m in projected if (m.text or "").startswith("[Tool results:")]

    # Two summaries: one for group 1, one for group 2.
    assert len(summary_msgs) == 2

    # Group 1 summary: London weather result.
    g1_text = summary_msgs[0].text or ""
    assert "12" in g1_text
    assert "cloudy" in g1_text

    # Group 2 summary: Paris weather + hotel results combined.
    g2_text = summary_msgs[1].text or ""
    assert "18" in g2_text
    assert "Grand Hotel" in g2_text

    # Group 3 (Tokyo) stays verbatim — tool role messages still present.
    verbatim_tool_msgs = [m for m in projected if m.role == "tool"]
    assert len(verbatim_tool_msgs) == 1
    assert "rainy" in (verbatim_tool_msgs[0].contents[0].result or "")

    # All text assistant messages should still be present.
    text_msgs = [m for m in projected if m.role == "assistant" and m.text and not m.text.startswith("[Tool results:")]
    texts = [m.text for m in text_msgs]
    assert "London is cloudy at 12°C." in texts
    assert "Paris is sunny at 18°C. Found 2 hotels." in texts
    assert "Tokyo is rainy at 22°C." in texts

    # Final projected shape: 8 messages in order.
    assert len(projected) == 8
    assert projected[0].role == "user"  # original user message
    assert projected[1].text == '[Tool results: get_weather: {"temp":12,"condition":"cloudy","wind":"NW 15km/h"}]'
    assert projected[2].text == "London is cloudy at 12°C."
    expected_g2 = (
        '[Tool results: get_weather: {"temp":18,"condition":"sunny"};'
        " search_hotels: Grand Hotel (€120), Le Petit (€85)]"
    )
    assert projected[3].text == expected_g2
    assert projected[4].text == "Paris is sunny at 18°C. Found 2 hotels."  # group 2 assistant text
    assert projected[5].role == "assistant"  # group 3 function_call (verbatim)
    assert projected[6].role == "tool"  # group 3 tool result (verbatim)
    assert projected[7].text == "Tokyo is rainy at 22°C."  # group 3 assistant text


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

    def get_messages(self) -> list[Message]:
        result: list[Message] = []
        for msgs in self.context_messages.values():
            result.extend(msgs)
        return result


async def test_compaction_provider_compacts_existing_context_messages() -> None:
    """CompactionProvider.before_run compacts messages already in context from earlier providers."""
    provider = CompactionProvider(
        before_strategy=SlidingWindowStrategy(keep_last_groups=2, preserve_system=True),
    )

    context = _MockSessionContext()
    context.context_messages["history"] = [
        Message(role="system", contents=["sys"]),
        Message(role="user", contents=["u1"]),
        Message(role="assistant", contents=["a1"]),
        Message(role="user", contents=["u2"]),
        Message(role="assistant", contents=["a2"]),
        Message(role="user", contents=["u3"]),
        Message(role="assistant", contents=["a3"]),
    ]

    await provider.before_run(agent=None, session=None, context=context, state={})

    remaining = context.context_messages["history"]
    assert len(remaining) == 3
    assert remaining[0].role == "system"
    assert remaining[1].text == "u3"
    assert remaining[2].text == "a3"


async def test_compaction_provider_noop_when_no_context_messages() -> None:
    """before_run with no context messages does nothing."""
    provider = CompactionProvider(
        before_strategy=SlidingWindowStrategy(keep_last_groups=2),
    )

    context = _MockSessionContext()
    await provider.before_run(agent=None, session=None, context=context, state={})

    assert context.context_messages == {}


async def test_compaction_provider_preserves_messages_from_multiple_sources() -> None:
    """CompactionProvider correctly filters across multiple provider sources."""
    provider = CompactionProvider(
        before_strategy=SlidingWindowStrategy(keep_last_groups=2, preserve_system=True),
    )

    context = _MockSessionContext()
    context.context_messages["history"] = [
        Message(role="system", contents=["sys"]),
        Message(role="user", contents=["old_user"]),
        Message(role="assistant", contents=["old_assistant"]),
    ]
    context.context_messages["rag"] = [
        Message(role="user", contents=["recent_rag_context"]),
        Message(role="assistant", contents=["recent_rag_answer"]),
    ]

    await provider.before_run(agent=None, session=None, context=context, state={})

    all_remaining = context.get_messages()
    assert any(m.role == "system" for m in all_remaining)
    assert len(all_remaining) < 5


class _MockSession:
    """Minimal mock for AgentSession used in CompactionProvider after_run tests."""

    def __init__(self) -> None:
        self.state: dict[str, Any] = {}


async def test_compaction_provider_after_run_compacts_stored_history() -> None:
    """after_run annotates exclusions on stored messages without removing them."""
    provider = CompactionProvider(
        after_strategy=SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=0),
        history_source_id="in_memory_history",
    )

    session = _MockSession()
    session.state["in_memory_history"] = {
        "messages": [
            Message(role="user", contents=["old question"]),
            Message(role="assistant", contents=["old answer"]),
            _assistant_function_call("c1"),
            _tool_result("c1", "result"),
            Message(role="assistant", contents=["final answer"]),
        ]
    }

    context = _MockSessionContext()
    await provider.after_run(agent=None, session=session, context=context, state={})

    stored = session.state["in_memory_history"]["messages"]
    # All messages are kept; tool-call group is excluded via annotation.
    assert len(stored) == 5
    excluded = [m for m in stored if m.additional_properties.get("_excluded", False)]
    assert len(excluded) == 2  # assistant function_call + tool result
    assert any(m.text == "final answer" for m in stored if not m.additional_properties.get("_excluded", False))


async def test_compaction_provider_after_run_noop_without_history() -> None:
    """after_run does nothing when there is no history state."""
    provider = CompactionProvider(
        after_strategy=SlidingWindowStrategy(keep_last_groups=2),
        history_source_id="in_memory_history",
    )

    session = _MockSession()
    context = _MockSessionContext()
    await provider.after_run(agent=None, session=session, context=context, state={})

    assert "in_memory_history" not in session.state


async def test_compaction_provider_both_strategies() -> None:
    """Both before_strategy and after_strategy work independently."""
    provider = CompactionProvider(
        before_strategy=SlidingWindowStrategy(keep_last_groups=2, preserve_system=True),
        after_strategy=SelectiveToolCallCompactionStrategy(keep_last_tool_call_groups=0),
        history_source_id="history",
    )

    # before_run: compact loaded context
    context = _MockSessionContext()
    context.context_messages["history"] = [
        Message(role="system", contents=["sys"]),
        Message(role="user", contents=["u1"]),
        Message(role="assistant", contents=["a1"]),
        Message(role="user", contents=["u2"]),
        Message(role="assistant", contents=["a2"]),
    ]
    await provider.before_run(agent=None, session=None, context=context, state={})
    assert len(context.get_messages()) == 3

    # after_run: compact stored history
    session = _MockSession()
    session.state["history"] = {
        "messages": [
            Message(role="user", contents=["q"]),
            _assistant_function_call("c1"),
            _tool_result("c1", "ok"),
            Message(role="assistant", contents=["done"]),
        ]
    }
    await provider.after_run(agent=None, session=session, context=_MockSessionContext(), state={})
    stored = session.state["history"]["messages"]
    excluded = [m for m in stored if m.additional_properties.get("_excluded", False)]
    assert len(excluded) == 2  # tool-call group excluded


async def test_compaction_provider_none_strategies_are_noop() -> None:
    """When both strategies are None, before_run and after_run are no-ops."""
    provider = CompactionProvider()

    context = _MockSessionContext()
    context.context_messages["history"] = [
        Message(role="user", contents=["hello"]),
        Message(role="assistant", contents=["hi"]),
    ]

    await provider.before_run(agent=None, session=None, context=context, state={})
    assert len(context.get_messages()) == 2

    session = _MockSession()
    await provider.after_run(agent=None, session=session, context=context, state={})
    assert "in_memory_history" not in session.state


async def test_in_memory_history_provider_skip_excluded() -> None:
    """InMemoryHistoryProvider with skip_excluded=True omits excluded messages."""
    from agent_framework._compaction import EXCLUDED_KEY
    from agent_framework._sessions import InMemoryHistoryProvider as _InMemoryHistoryProvider

    provider = _InMemoryHistoryProvider(skip_excluded=True)
    state: dict[str, Any] = {
        "messages": [
            Message(role="user", contents=["u1"]),
            Message(role="assistant", contents=["a1"], additional_properties={EXCLUDED_KEY: True}),
            Message(role="user", contents=["u2"]),
            Message(role="assistant", contents=["a2"]),
        ]
    }

    loaded = await provider.get_messages(session_id="test", state=state)
    assert len(loaded) == 3
    assert all(m.text != "a1" for m in loaded)


async def test_in_memory_history_provider_default_loads_all() -> None:
    """InMemoryHistoryProvider with default settings loads all messages including excluded."""
    from agent_framework._compaction import EXCLUDED_KEY
    from agent_framework._sessions import InMemoryHistoryProvider as _InMemoryHistoryProvider

    provider = _InMemoryHistoryProvider()
    state: dict[str, Any] = {
        "messages": [
            Message(role="user", contents=["u1"]),
            Message(role="assistant", contents=["a1"], additional_properties={EXCLUDED_KEY: True}),
            Message(role="user", contents=["u2"]),
        ]
    }

    loaded = await provider.get_messages(session_id="test", state=state)
    assert len(loaded) == 3
