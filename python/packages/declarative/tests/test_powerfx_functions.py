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
            "If",
            "Or",
            "And",
            "Not",
            "AgentMessage",
            "ForAll",
        ]
        for name in expected:
            assert name in CUSTOM_FUNCTIONS


class TestMessageTextEdgeCases:
    """Additional tests for message_text edge cases."""

    def test_message_text_dict_with_text_attr_content(self):
        """Test message with content that has text attribute."""

        class ContentWithText:  # noqa: B903
            def __init__(self, text: str):
                self.text = text

        msg = {"role": "assistant", "content": ContentWithText("Hello from text attr")}
        assert message_text(msg) == "Hello from text attr"

    def test_message_text_dict_content_non_string(self):
        """Test message with non-string content."""
        msg = {"role": "assistant", "content": 42}
        assert message_text(msg) == "42"

    def test_message_text_list_with_string_items(self):
        """Test message_text with list of strings."""
        result = message_text(["Hello", "World"])
        assert result == "Hello World"

    def test_message_text_list_with_content_objects(self):
        """Test message_text with list items having content attribute."""

        class MessageObj:  # noqa: B903
            def __init__(self, content: str):
                self.content = content

        msgs = [MessageObj("Hello"), MessageObj("World")]
        result = message_text(msgs)
        assert result == "Hello World"

    def test_message_text_list_with_content_text_attr(self):
        """Test message_text with content having text attribute."""

        class ContentWithText:  # noqa: B903
            def __init__(self, text: str):
                self.text = text

        class MessageObj:
            def __init__(self, content):
                self.content = content

        msgs = [MessageObj(ContentWithText("Part1")), MessageObj(ContentWithText("Part2"))]
        result = message_text(msgs)
        assert result == "Part1 Part2"

    def test_message_text_list_with_non_string_content(self):
        """Test message_text with non-string content in dicts."""
        msgs = [{"content": 123}, {"content": 456}]
        result = message_text(msgs)
        assert result == "123 456"

    def test_message_text_object_with_text_attr(self):
        """Test message_text with object having text attribute."""

        class ObjWithText:
            text = "Direct text"

        result = message_text(ObjWithText())
        assert result == "Direct text"

    def test_message_text_object_with_content_attr(self):
        """Test message_text with object having content attribute."""

        class ObjWithContent:
            content = "Direct content"

        result = message_text(ObjWithContent())
        assert result == "Direct content"

    def test_message_text_object_with_non_string_content(self):
        """Test message_text with object having non-string content."""

        class ObjWithContent:
            content = None

        result = message_text(ObjWithContent())
        assert result == ""

    def test_message_text_list_with_empty_content_object(self):
        """Test message with content object that evaluates to empty."""

        class MessageObj:
            content = None

        result = message_text([MessageObj()])
        assert result == ""


class TestAgentMessage:
    """Tests for agent_message function."""

    def test_agent_message_creates_dict(self):
        """Test that AgentMessage creates correct dict."""
        from agent_framework_declarative._workflows._powerfx_functions import agent_message

        msg = agent_message("Hello")
        assert msg == {"role": "assistant", "content": "Hello"}

    def test_agent_message_with_none(self):
        """Test AgentMessage with None."""
        from agent_framework_declarative._workflows._powerfx_functions import agent_message

        msg = agent_message(None)
        assert msg == {"role": "assistant", "content": ""}


class TestIfFunc:
    """Tests for if_func conditional function."""

    def test_if_true_condition(self):
        """Test If with true condition."""
        from agent_framework_declarative._workflows._powerfx_functions import if_func

        assert if_func(True, "yes", "no") == "yes"

    def test_if_false_condition(self):
        """Test If with false condition."""
        from agent_framework_declarative._workflows._powerfx_functions import if_func

        assert if_func(False, "yes", "no") == "no"

    def test_if_truthy_value(self):
        """Test If with truthy value."""
        from agent_framework_declarative._workflows._powerfx_functions import if_func

        assert if_func(1, "yes", "no") == "yes"
        assert if_func("non-empty", "yes", "no") == "yes"

    def test_if_falsy_value(self):
        """Test If with falsy value."""
        from agent_framework_declarative._workflows._powerfx_functions import if_func

        assert if_func(0, "yes", "no") == "no"
        assert if_func("", "yes", "no") == "no"
        assert if_func(None, "yes", "no") == "no"

    def test_if_no_false_value(self):
        """Test If with no false value defaults to None."""
        from agent_framework_declarative._workflows._powerfx_functions import if_func

        assert if_func(False, "yes") is None


class TestOrFunc:
    """Tests for or_func function."""

    def test_or_all_false(self):
        """Test Or with all false values."""
        from agent_framework_declarative._workflows._powerfx_functions import or_func

        assert or_func(False, False, False) is False

    def test_or_one_true(self):
        """Test Or with one true value."""
        from agent_framework_declarative._workflows._powerfx_functions import or_func

        assert or_func(False, True, False) is True

    def test_or_all_true(self):
        """Test Or with all true values."""
        from agent_framework_declarative._workflows._powerfx_functions import or_func

        assert or_func(True, True, True) is True

    def test_or_empty(self):
        """Test Or with no arguments."""
        from agent_framework_declarative._workflows._powerfx_functions import or_func

        assert or_func() is False


class TestAndFunc:
    """Tests for and_func function."""

    def test_and_all_true(self):
        """Test And with all true values."""
        from agent_framework_declarative._workflows._powerfx_functions import and_func

        assert and_func(True, True, True) is True

    def test_and_one_false(self):
        """Test And with one false value."""
        from agent_framework_declarative._workflows._powerfx_functions import and_func

        assert and_func(True, False, True) is False

    def test_and_all_false(self):
        """Test And with all false values."""
        from agent_framework_declarative._workflows._powerfx_functions import and_func

        assert and_func(False, False, False) is False

    def test_and_empty(self):
        """Test And with no arguments."""
        from agent_framework_declarative._workflows._powerfx_functions import and_func

        assert and_func() is True


class TestNotFunc:
    """Tests for not_func function."""

    def test_not_true(self):
        """Test Not with true."""
        from agent_framework_declarative._workflows._powerfx_functions import not_func

        assert not_func(True) is False

    def test_not_false(self):
        """Test Not with false."""
        from agent_framework_declarative._workflows._powerfx_functions import not_func

        assert not_func(False) is True

    def test_not_truthy(self):
        """Test Not with truthy values."""
        from agent_framework_declarative._workflows._powerfx_functions import not_func

        assert not_func(1) is False
        assert not_func("text") is False

    def test_not_falsy(self):
        """Test Not with falsy values."""
        from agent_framework_declarative._workflows._powerfx_functions import not_func

        assert not_func(0) is True
        assert not_func("") is True
        assert not_func(None) is True


class TestIsBlankEdgeCases:
    """Additional tests for is_blank edge cases."""

    def test_is_blank_empty_dict(self):
        """Test that empty dict is blank."""
        assert is_blank({}) is True

    def test_is_blank_non_empty_dict(self):
        """Test that non-empty dict is not blank."""
        assert is_blank({"key": "value"}) is False


class TestCountRowsEdgeCases:
    """Additional tests for count_rows edge cases."""

    def test_count_rows_dict(self):
        """Test counting dict items."""
        assert count_rows({"a": 1, "b": 2, "c": 3}) == 3

    def test_count_rows_tuple(self):
        """Test counting tuple items."""
        assert count_rows((1, 2, 3, 4)) == 4

    def test_count_rows_non_iterable(self):
        """Test counting non-iterable returns 0."""
        assert count_rows(42) == 0
        assert count_rows("string") == 0


class TestFirstLastEdgeCases:
    """Additional tests for first/last edge cases."""

    def test_first_none(self):
        """Test first with None."""
        assert first(None) is None

    def test_last_none(self):
        """Test last with None."""
        assert last(None) is None

    def test_first_tuple(self):
        """Test first with tuple."""
        assert first((1, 2, 3)) == 1

    def test_last_tuple(self):
        """Test last with tuple."""
        assert last((1, 2, 3)) == 3


class TestFindEdgeCases:
    """Additional tests for find edge cases."""

    def test_find_none_substring(self):
        """Test find with None substring."""
        assert find(None, "text") is None

    def test_find_none_text(self):
        """Test find with None text."""
        assert find("sub", None) is None

    def test_find_both_none(self):
        """Test find with both None."""
        assert find(None, None) is None


class TestLowerEdgeCases:
    """Additional tests for lower edge cases."""

    def test_lower_none(self):
        """Test lower with None."""
        assert lower(None) == ""


class TestConcatStrings:
    """Tests for concat_strings function."""

    def test_concat_strings_basic(self):
        """Test basic string concatenation."""
        from agent_framework_declarative._workflows._powerfx_functions import concat_strings

        assert concat_strings("Hello", " ", "World") == "Hello World"

    def test_concat_strings_with_none(self):
        """Test concat with None values."""
        from agent_framework_declarative._workflows._powerfx_functions import concat_strings

        assert concat_strings("Hello", None, "World") == "HelloWorld"

    def test_concat_strings_empty(self):
        """Test concat with no arguments."""
        from agent_framework_declarative._workflows._powerfx_functions import concat_strings

        assert concat_strings() == ""


class TestConcatTextEdgeCases:
    """Additional tests for concat_text edge cases."""

    def test_concat_text_none(self):
        """Test concat_text with None."""
        assert concat_text(None) == ""

    def test_concat_text_non_list(self):
        """Test concat_text with non-list."""
        assert concat_text("single value") == "single value"

    def test_concat_text_with_field_attr(self):
        """Test concat_text with field as object attribute."""

        class Item:  # noqa: B903
            def __init__(self, name: str):
                self.name = name

        items = [Item("Alice"), Item("Bob")]
        assert concat_text(items, field="name", separator=", ") == "Alice, Bob"

    def test_concat_text_with_none_values(self):
        """Test concat_text with None values in list."""
        items = [{"name": "Alice"}, {"name": None}, {"name": "Bob"}]
        result = concat_text(items, field="name", separator=", ")
        assert result == "Alice, , Bob"


class TestForAll:
    """Tests for for_all function."""

    def test_for_all_with_list_of_dicts(self):
        """Test ForAll with list of dictionaries."""
        from agent_framework_declarative._workflows._powerfx_functions import for_all

        items = [{"name": "Alice"}, {"name": "Bob"}]
        result = for_all(items, "expression")
        assert result == items

    def test_for_all_with_non_dict_items(self):
        """Test ForAll with non-dict items."""
        from agent_framework_declarative._workflows._powerfx_functions import for_all

        items = [1, 2, 3]
        result = for_all(items, "expression")
        assert result == [1, 2, 3]

    def test_for_all_with_none(self):
        """Test ForAll with None."""
        from agent_framework_declarative._workflows._powerfx_functions import for_all

        assert for_all(None, "expression") == []

    def test_for_all_with_non_list(self):
        """Test ForAll with non-list."""
        from agent_framework_declarative._workflows._powerfx_functions import for_all

        assert for_all("not a list", "expression") == []

    def test_for_all_empty_list(self):
        """Test ForAll with empty list."""
        from agent_framework_declarative._workflows._powerfx_functions import for_all

        assert for_all([], "expression") == []


class TestSearchTableEdgeCases:
    """Additional tests for search_table edge cases."""

    def test_search_table_none(self):
        """Test search_table with None."""
        assert search_table(None, "value", "column") == []

    def test_search_table_non_list(self):
        """Test search_table with non-list."""
        assert search_table("not a list", "value", "column") == []

    def test_search_table_with_object_attr(self):
        """Test search_table with object attributes."""

        class Item:  # noqa: B903
            def __init__(self, name: str):
                self.name = name

        items = [Item("Alice"), Item("Bob"), Item("Charlie")]
        result = search_table(items, "Bob", "name")
        assert len(result) == 1
        assert result[0].name == "Bob"

    def test_search_table_no_matching_column(self):
        """Test search_table when items don't have the column."""
        items = [{"other": "value"}]
        result = search_table(items, "value", "name")
        assert result == []

    def test_search_table_empty_value(self):
        """Test search_table with empty search value."""
        items = [{"name": "Alice"}, {"name": "Bob"}]
        result = search_table(items, "", "name")
        # Empty string matches everything
        assert len(result) == 2
