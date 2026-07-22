# Copyright (c) Microsoft. All rights reserved.

from agent_framework import AgentResponse, Content, Message
from mcp import types
from pytest import raises

from agent_framework_hosting_mcp import mcp_from_run, mcp_to_run


def test_mcp_to_run_converts_selected_argument() -> None:
    arguments = {
        "prompt": "hello",
        "temperature": 0.2,
        "max_tokens": 100,
        "tenant": "example",
    }

    run = mcp_to_run(
        arguments,
        argument_name="prompt",
        chat_option_arguments=("temperature", "max_tokens", "top_p"),
    )

    messages = run["messages"]
    assert isinstance(messages, list)
    converted = messages[0]
    assert isinstance(converted, Message)
    assert converted.text == "hello"
    assert converted.raw_representation == arguments
    assert run["stream"] is False
    assert run["options"] == {"temperature": 0.2, "max_tokens": 100}


def test_mcp_to_run_rejects_missing_argument() -> None:
    with raises(ValueError, match="'task' string"):
        mcp_to_run({})


def test_mcp_to_run_rejects_non_string_argument() -> None:
    with raises(ValueError, match="'task' must be a string"):
        mcp_to_run({"task": 42})


def test_mcp_from_run_converts_final_response() -> None:
    response = AgentResponse(
        messages=[
            Message("user", ["omit me"]),
            Message(
                "assistant",
                [
                    Content.from_text("hello", additional_properties={"source": "agent"}),
                    Content.from_uri("https://example.com/image.png", media_type="image/png"),
                    Content.from_data(b"image", "image/png", additional_properties={"source": "image"}),
                    Content.from_data(b"audio", "audio/wav"),
                    Content.from_data(b"bytes", "application/octet-stream"),
                ],
            ),
        ]
    )

    blocks = mcp_from_run(response)

    assert len(blocks) == 5
    assert isinstance(blocks[0], types.TextContent)
    assert blocks[0].text == "hello"
    assert blocks[0].meta == {"source": "agent"}
    assert isinstance(blocks[1], types.ResourceLink)
    assert str(blocks[1].uri) == "https://example.com/image.png"
    assert blocks[1].name == "image.png"
    assert isinstance(blocks[2], types.ImageContent)
    assert blocks[2].data == "aW1hZ2U="
    assert blocks[2].mimeType == "image/png"
    assert blocks[2].meta == {"source": "image"}
    assert isinstance(blocks[3], types.AudioContent)
    assert blocks[3].data == "YXVkaW8="
    assert blocks[3].mimeType == "audio/wav"
    assert isinstance(blocks[4], types.EmbeddedResource)
    assert isinstance(blocks[4].resource, types.BlobResourceContents)
    assert str(blocks[4].resource.uri) == "af://binary"
    assert blocks[4].resource.blob == "Ynl0ZXM="


def test_mcp_from_run_uses_app_owned_binary_resource_uri() -> None:
    blocks = mcp_from_run(
        Message(
            "assistant",
            [
                Content.from_data(
                    b"document",
                    "application/pdf",
                    additional_properties={"uri": "af://documents/report"},
                )
            ],
        )
    )

    assert len(blocks) == 1
    assert isinstance(blocks[0], types.EmbeddedResource)
    assert str(blocks[0].resource.uri) == "af://documents/report"


def test_mcp_from_run_preserves_empty_text() -> None:
    blocks = mcp_from_run(Message("assistant", [Content.from_text("")]))

    assert len(blocks) == 1
    assert isinstance(blocks[0], types.TextContent)
    assert blocks[0].text == ""


def test_mcp_from_run_omits_content_not_supported_in_tool_results() -> None:
    blocks = mcp_from_run(
        Message(
            "assistant",
            [
                Content.from_function_call(call_id="call-1", name="get_weather", arguments="{}"),
                Content.from_text("hello"),
            ],
        )
    )

    assert len(blocks) == 1
    assert isinstance(blocks[0], types.TextContent)


def test_mcp_from_run_omits_user_messages() -> None:
    assert mcp_from_run(AgentResponse(messages=[Message("user", ["omit me"])])) == []


def test_mcp_from_run_rejects_invalid_data_uri() -> None:
    content = Content("data", uri="not-a-data-uri", media_type="application/octet-stream")

    with raises(ValueError, match="base64 data URI"):
        mcp_from_run(Message("assistant", [content]))


def test_mcp_from_run_rejects_invalid_base64_data() -> None:
    content = Content(
        "data",
        uri="data:application/octet-stream;base64,not valid base64",
        media_type="application/octet-stream",
    )

    with raises(ValueError, match="invalid base64"):
        mcp_from_run(Message("assistant", [content]))
