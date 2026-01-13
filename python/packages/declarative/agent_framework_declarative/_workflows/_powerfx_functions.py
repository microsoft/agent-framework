# Copyright (c) Microsoft. All rights reserved.

"""Custom PowerFx-like functions for declarative workflows.

This module provides Python implementations of custom PowerFx functions
that are used in declarative workflows but may not be available in the
standard PowerFx Python package.

These functions can be used as fallbacks when PowerFx is not available,
or registered with the PowerFx engine when it is available.
"""

from typing import Any, cast


def message_text(messages: Any) -> str:
    """Extract text content from a message or list of messages.

    This is equivalent to the .NET MessageText() function.

    Args:
        messages: A message object, list of messages, or string

    Returns:
        The concatenated text content of all messages

    Examples:
        .. code-block:: python

            message_text([{"role": "assistant", "content": "Hello"}])
            # Returns: 'Hello'
    """
    if messages is None:
        return ""

    if isinstance(messages, str):
        return messages

    if isinstance(messages, dict):
        # Single message object
        messages_dict = cast(dict[str, Any], messages)
        content: Any = messages_dict.get("content", "")
        if isinstance(content, str):
            return content
        if hasattr(content, "text"):
            return str(content.text)
        return str(content) if content else ""

    if isinstance(messages, list):
        # List of messages - concatenate all text
        texts: list[str] = []
        for msg in messages:
            if isinstance(msg, str):
                texts.append(msg)
            elif isinstance(msg, dict):
                msg_dict = cast(dict[str, Any], msg)
                msg_content: Any = msg_dict.get("content", "")
                if isinstance(msg_content, str):
                    texts.append(msg_content)
                elif msg_content:
                    texts.append(str(msg_content))
            elif hasattr(msg, "content"):
                msg_obj_content: Any = msg.content
                if isinstance(msg_obj_content, str):
                    texts.append(msg_obj_content)
                elif hasattr(msg_obj_content, "text"):
                    texts.append(str(msg_obj_content.text))
                elif msg_obj_content:
                    texts.append(str(msg_obj_content))
        return " ".join(texts)

    # Try to get text attribute
    if hasattr(messages, "text"):
        return str(messages.text)
    if hasattr(messages, "content"):
        content_attr: Any = messages.content
        if isinstance(content_attr, str):
            return content_attr
        return str(content_attr) if content_attr else ""

    return str(messages) if messages else ""


def user_message(text: str) -> dict[str, str]:
    """Create a user message object.

    This is equivalent to the .NET UserMessage() function.

    Args:
        text: The text content of the message

    Returns:
        A message dictionary with role 'user'

    Examples:
        .. code-block:: python

            user_message("Hello")
            # Returns: {'role': 'user', 'content': 'Hello'}
    """
    return {"role": "user", "content": str(text) if text else ""}


def assistant_message(text: str) -> dict[str, str]:
    """Create an assistant message object.

    Args:
        text: The text content of the message

    Returns:
        A message dictionary with role 'assistant'

    Examples:
        .. code-block:: python

            assistant_message("Hello")
            # Returns: {'role': 'assistant', 'content': 'Hello'}
    """
    return {"role": "assistant", "content": str(text) if text else ""}


def agent_message(text: str) -> dict[str, str]:
    """Create an agent/assistant message object.

    This is equivalent to the .NET AgentMessage() function.
    It's an alias for assistant_message() for .NET compatibility.

    Args:
        text: The text content of the message

    Returns:
        A message dictionary with role 'assistant'

    Examples:
        .. code-block:: python

            agent_message("Hello")
            # Returns: {'role': 'assistant', 'content': 'Hello'}
    """
    return {"role": "assistant", "content": str(text) if text else ""}


def system_message(text: str) -> dict[str, str]:
    """Create a system message object.

    Args:
        text: The text content of the message

    Returns:
        A message dictionary with role 'system'

    Examples:
        .. code-block:: python

            system_message("You are a helpful assistant")
            # Returns: {'role': 'system', 'content': 'You are a helpful assistant'}
    """
    return {"role": "system", "content": str(text) if text else ""}


def if_func(condition: Any, true_value: Any, false_value: Any = None) -> Any:
    """Conditional expression - returns one value or another based on a condition.

    This is equivalent to the PowerFx If() function.

    Args:
        condition: The condition to evaluate (truthy/falsy)
        true_value: Value to return if condition is truthy
        false_value: Value to return if condition is falsy (defaults to None)

    Returns:
        true_value if condition is truthy, otherwise false_value
    """
    return true_value if condition else false_value


def is_blank(value: Any) -> bool:
    """Check if a value is blank (None, empty string, empty list, etc.).

    This is equivalent to the PowerFx IsBlank() function.

    Args:
        value: The value to check

    Returns:
        True if the value is considered blank
    """
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    if isinstance(value, list):
        return len(value) == 0
    if isinstance(value, dict):
        return len(value) == 0
    return False


def or_func(*args: Any) -> bool:
    """Logical OR - returns True if any argument is truthy.

    This is equivalent to the PowerFx Or() function.

    Args:
        *args: Variable number of values to check

    Returns:
        True if any argument is truthy
    """
    return any(bool(arg) for arg in args)


def and_func(*args: Any) -> bool:
    """Logical AND - returns True if all arguments are truthy.

    This is equivalent to the PowerFx And() function.

    Args:
        *args: Variable number of values to check

    Returns:
        True if all arguments are truthy
    """
    return all(bool(arg) for arg in args)


def not_func(value: Any) -> bool:
    """Logical NOT - returns the opposite boolean value.

    This is equivalent to the PowerFx Not() function.

    Args:
        value: The value to negate

    Returns:
        True if value is falsy, False if truthy
    """
    return not bool(value)


def count_rows(table: Any) -> int:
    """Count the number of rows/items in a table/list.

    This is equivalent to the PowerFx CountRows() function.

    Args:
        table: A list or table-like object

    Returns:
        The number of rows/items
    """
    if table is None:
        return 0
    if isinstance(table, (list, tuple)):
        return len(cast(list[Any], table))
    if isinstance(table, dict):
        return len(cast(dict[str, Any], table))
    return 0


def first(table: Any) -> Any:
    """Get the first item from a table/list.

    This is equivalent to the PowerFx First() function.

    Args:
        table: A list or table-like object

    Returns:
        The first item, or None if empty
    """
    if table is None:
        return None
    if isinstance(table, (list, tuple)):
        table_list = cast(list[Any], table)
        if len(table_list) > 0:
            return table_list[0]
    return None


def last(table: Any) -> Any:
    """Get the last item from a table/list.

    This is equivalent to the PowerFx Last() function.

    Args:
        table: A list or table-like object

    Returns:
        The last item, or None if empty
    """
    if table is None:
        return None
    if isinstance(table, (list, tuple)):
        table_list = cast(list[Any], table)
        if len(table_list) > 0:
            return table_list[-1]
    return None


def find(substring: str | None, text: str | None) -> int | None:
    """Find the position of a substring within text.

    This is equivalent to the PowerFx Find() function.
    Returns None (Blank) if not found, otherwise 1-based index.

    Args:
        substring: The substring to find
        text: The text to search in

    Returns:
        1-based index if found, None (Blank) if not found
    """
    if substring is None or text is None:
        return None
    try:
        index = str(text).find(str(substring))
        return index + 1 if index >= 0 else None
    except (TypeError, ValueError):
        return None


def upper(text: str | None) -> str:
    """Convert text to uppercase.

    This is equivalent to the PowerFx Upper() function.

    Args:
        text: The text to convert

    Returns:
        Uppercase text
    """
    if text is None:
        return ""
    return str(text).upper()


def lower(text: str | None) -> str:
    """Convert text to lowercase.

    This is equivalent to the PowerFx Lower() function.

    Args:
        text: The text to convert

    Returns:
        Lowercase text
    """
    if text is None:
        return ""
    return str(text).lower()


def concat_strings(*args: Any) -> str:
    """Concatenate multiple string arguments.

    This is equivalent to the PowerFx Concat() function for string concatenation.

    Args:
        *args: Variable number of values to concatenate

    Returns:
        Concatenated string
    """
    return "".join(str(arg) if arg is not None else "" for arg in args)


def concat_text(table: Any, field: str | None = None, separator: str = "") -> str:
    """Concatenate values from a table/list.

    This is equivalent to the PowerFx Concat() function.

    Args:
        table: A list of items
        field: Optional field name to extract from each item
        separator: Separator between values

    Returns:
        Concatenated string
    """
    if table is None:
        return ""
    if not isinstance(table, (list, tuple)):
        return str(table)

    values: list[str] = []
    for item in cast(list[Any], table):
        value: Any = None
        if field and isinstance(item, dict):
            item_dict = cast(dict[str, Any], item)
            value = item_dict.get(field, "")
        elif field and hasattr(item, field):
            value = getattr(item, field, "")
        else:
            value = item
        values.append(str(value) if value is not None else "")

    return separator.join(values)


def for_all(table: Any, expression: str, field_mapping: dict[str, str] | None = None) -> list[Any]:
    """Apply an expression to each row of a table.

    This is equivalent to the PowerFx ForAll() function.

    Args:
        table: A list of records
        expression: A string expression that references item fields
        field_mapping: Optional dict mapping placeholder names to field names

    Returns:
        List of results from applying expression to each row

    Note:
        The expression can use field names directly from the record.
        For example: ForAll(items, "$" & name & ": " & description)
    """
    if table is None or not isinstance(table, (list, tuple)):
        return []

    results: list[Any] = []
    for item in cast(list[Any], table):
        # If item is a dict, we can directly substitute field values
        if isinstance(item, dict):
            item_dict = cast(dict[str, Any], item)
            # The expression is typically already evaluated by the expression parser
            # This function primarily handles table iteration
            # Return the item itself for further processing
            results.append(item_dict)
        else:
            results.append(item)

    return results


def search_table(table: Any, value: Any, column: str) -> list[Any]:
    """Search for rows in a table where a column matches a value.

    This is equivalent to the PowerFx Search() function.

    Args:
        table: A list of records
        value: The value to search for
        column: The column name to search in

    Returns:
        List of matching records
    """
    if table is None or not isinstance(table, (list, tuple)):
        return []

    results: list[Any] = []
    search_value = str(value).lower() if value else ""

    for item in cast(list[Any], table):
        item_value: Any = None
        if isinstance(item, dict):
            item_dict = cast(dict[str, Any], item)
            item_value = item_dict.get(column, "")
        elif hasattr(item, column):
            item_value = getattr(item, column, "")
        else:
            continue

        # Case-insensitive contains search
        if search_value in str(item_value).lower():
            results.append(item)

    return results


# Registry of custom functions
CUSTOM_FUNCTIONS: dict[str, Any] = {
    "MessageText": message_text,
    "UserMessage": user_message,
    "AssistantMessage": assistant_message,
    "AgentMessage": agent_message,  # .NET compatibility alias for AssistantMessage
    "SystemMessage": system_message,
    "If": if_func,
    "IsBlank": is_blank,
    "Or": or_func,
    "And": and_func,
    "Not": not_func,
    "CountRows": count_rows,
    "First": first,
    "Last": last,
    "Find": find,
    "Upper": upper,
    "Lower": lower,
    "Concat": concat_strings,
    "Search": search_table,
    "ForAll": for_all,
}
