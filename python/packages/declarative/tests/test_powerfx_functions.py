# Copyright (c) Microsoft. All rights reserved.

"""Tests for custom PowerFx-like functions."""

from agent_framework_declarative._workflows._powerfx_functions import (
    CUSTOM_FUNCTIONS,
    assistant_message,
    concat_text,
    count_rows,
    find,
    first,
    is_blank,
    last,
    lower,
    message_text,
    search_table,
    system_message,
    upper,
    user_message,
)


class TestMessageText:
    """Tests for MessageText function."""

    def test_message_text_from_string(self):
        """Test extracting text from a plain string."""
        assert message_text("Hello") == "Hello"

    def test_message_text_from_single_dict(self):
        """Test extracting text from a single message dict."""
        msg = {"role": "assistant", "content": "Hello world"}
        assert message_text(msg) == "Hello world"

    def test_message_text_from_list(self):
        """Test extracting text from a list of messages."""
        msgs = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello"},
        ]
        assert message_text(msgs) == "Hi Hello"

    def test_message_text_from_none(self):
        """Test that None returns empty string."""
        assert message_text(None) == ""

    def test_message_text_empty_list(self):
        """Test that empty list returns empty string."""
        assert message_text([]) == ""


class TestUserMessage:
    """Tests for UserMessage function."""

    def test_user_message_creates_dict(self):
        """Test that UserMessage creates correct dict."""
        msg = user_message("Hello")
        assert msg == {"role": "user", "content": "Hello"}

    def test_user_message_with_none(self):
        """Test UserMessage with None."""
        msg = user_message(None)
        assert msg == {"role": "user", "content": ""}


class TestAssistantMessage:
    """Tests for AssistantMessage function."""

    def test_assistant_message_creates_dict(self):
        """Test that AssistantMessage creates correct dict."""
        msg = assistant_message("Hello")
        assert msg == {"role": "assistant", "content": "Hello"}


class TestSystemMessage:
    """Tests for SystemMessage function."""

    def test_system_message_creates_dict(self):
        """Test that SystemMessage creates correct dict."""
        msg = system_message("You are helpful")
        assert msg == {"role": "system", "content": "You are helpful"}


class TestIsBlank:
    """Tests for IsBlank function."""

    def test_is_blank_none(self):
        """Test that None is blank."""
        assert is_blank(None) is True

    def test_is_blank_empty_string(self):
        """Test that empty string is blank."""
        assert is_blank("") is True

    def test_is_blank_whitespace(self):
        """Test that whitespace-only string is blank."""
        assert is_blank("   ") is True

    def test_is_blank_empty_list(self):
        """Test that empty list is blank."""
        assert is_blank([]) is True

    def test_is_blank_non_empty(self):
        """Test that non-empty values are not blank."""
        assert is_blank("hello") is False
        assert is_blank([1, 2, 3]) is False
        assert is_blank(0) is False


class TestCountRows:
    """Tests for CountRows function."""

    def test_count_rows_list(self):
        """Test counting list items."""
        assert count_rows([1, 2, 3]) == 3

    def test_count_rows_empty(self):
        """Test counting empty list."""
        assert count_rows([]) == 0

    def test_count_rows_none(self):
        """Test counting None."""
        assert count_rows(None) == 0


class TestFirstLast:
    """Tests for First and Last functions."""

    def test_first_returns_first_item(self):
        """Test that First returns first item."""
        assert first([1, 2, 3]) == 1

    def test_last_returns_last_item(self):
        """Test that Last returns last item."""
        assert last([1, 2, 3]) == 3

    def test_first_empty_returns_none(self):
        """Test that First returns None for empty list."""
        assert first([]) is None

    def test_last_empty_returns_none(self):
        """Test that Last returns None for empty list."""
        assert last([]) is None


class TestFind:
    """Tests for Find function."""

    def test_find_substring(self):
        """Test finding a substring."""
        result = find("world", "Hello world")
        assert result == 7  # 1-based index

    def test_find_not_found(self):
        """Test when substring not found - returns Blank (None) per PowerFx semantics."""
        result = find("xyz", "Hello world")
        assert result is None

    def test_find_at_start(self):
        """Test finding at start of string."""
        result = find("Hello", "Hello world")
        assert result == 1


class TestUpperLower:
    """Tests for Upper and Lower functions."""

    def test_upper(self):
        """Test uppercase conversion."""
        assert upper("hello") == "HELLO"

    def test_lower(self):
        """Test lowercase conversion."""
        assert lower("HELLO") == "hello"

    def test_upper_none(self):
        """Test upper with None."""
        assert upper(None) == ""


class TestConcatText:
    """Tests for Concat function."""

    def test_concat_simple_list(self):
        """Test concatenating simple list."""
        assert concat_text(["a", "b", "c"], separator=", ") == "a, b, c"

    def test_concat_with_field(self):
        """Test concatenating with field extraction."""
        items = [{"name": "Alice"}, {"name": "Bob"}]
        assert concat_text(items, field="name", separator=", ") == "Alice, Bob"


class TestSearchTable:
    """Tests for Search function."""

    def test_search_finds_matching(self):
        """Test search finds matching items."""
        items = [
            {"name": "Alice", "age": 30},
            {"name": "Bob", "age": 25},
            {"name": "Charlie", "age": 35},
        ]
        result = search_table(items, "Bob", "name")
        assert len(result) == 1
        assert result[0]["name"] == "Bob"

    def test_search_case_insensitive(self):
        """Test search is case insensitive."""
        items = [{"name": "Alice"}]
        result = search_table(items, "alice", "name")
        assert len(result) == 1

    def test_search_partial_match(self):
        """Test search finds partial matches."""
        items = [{"name": "Alice Smith"}, {"name": "Bob Jones"}]
        result = search_table(items, "Smith", "name")
        assert len(result) == 1


class TestCustomFunctionsRegistry:
    """Tests for the CUSTOM_FUNCTIONS registry."""

    def test_all_functions_registered(self):
        """Test that all functions are in the registry."""
        expected = [
            "MessageText",
            "UserMessage",
            "AssistantMessage",
            "SystemMessage",
            "IsBlank",
            "CountRows",
            "First",
            "Last",
            "Find",
            "Upper",
            "Lower",
            "Concat",
            "Search",
        ]
        for name in expected:
            assert name in CUSTOM_FUNCTIONS
