


def test_prepare_options_tool_choice_auto_without_tools_omits_tool_config() -> None:
    """When tool_choice='auto' but no tools are provided, toolConfig must be omitted.

    Without tools, setting toolChoice would cause a ParamValidationError from Bedrock.
    """
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    options: dict[str, Any] = {
        "tool_choice": "auto",
    }

    request = client._prepare_options(messages, options)

    assert "toolConfig" not in request, (
        f"toolConfig should be omitted when no tools are provided, got: {request.get('toolConfig')}"
    )


def test_prepare_options_tool_choice_required_without_tools_omits_tool_config() -> None:
    """When tool_choice='required' but no tools are provided, toolConfig must be omitted."""
    client = _make_client()
    messages = [Message(role="user", contents=[Content.from_text(text="hello")])]

    options: dict[str, Any] = {
        "tool_choice": "required",
    }

    request = client._prepare_options(messages, options)

    assert "toolConfig" not in request, (
        f"toolConfig should be omitted when no tools are provided, got: {request.get('toolConfig')}"
    )
