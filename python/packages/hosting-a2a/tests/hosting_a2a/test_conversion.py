# Copyright (c) Microsoft. All rights reserved.

from a2a.types import Message as A2AMessage
from a2a.types import Part, Role
from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message
from google.protobuf.json_format import MessageToDict
from pytest import raises

from agent_framework_hosting_a2a import a2a_from_run, a2a_to_run


def test_a2a_to_run_converts_supported_parts() -> None:
    data_part = Part()
    data_part.data.string_value = "structured"
    message = A2AMessage(
        message_id="message-1",
        role=Role.ROLE_USER,
        parts=[
            Part(text="hello", metadata={"source": "text"}),
            Part(url="https://example.com/image.png", media_type="image/png"),
            Part(raw=b"audio", media_type="audio/wav"),
            data_part,
        ],
        metadata={"tenant_value": "kept"},
    )

    run = a2a_to_run(message, stream=True)

    messages = run["messages"]
    assert isinstance(messages, list)
    converted = messages[0]
    assert isinstance(converted, Message)
    assert run["stream"] is True
    assert run["options"] == {}
    assert converted.message_id == "message-1"
    assert converted.additional_properties == {"a2a_metadata": {"tenant_value": "kept"}}
    assert [content.type for content in converted.contents] == ["text", "uri", "data", "text"]
    assert converted.contents[0].additional_properties == {"source": "text"}
    assert converted.contents[1].uri == "https://example.com/image.png"
    assert converted.contents[2].uri == "data:audio/wav;base64,YXVkaW8="
    assert converted.contents[3].text == '"structured"'


def test_a2a_to_run_rejects_empty_message() -> None:
    with raises(ValueError, match="no supported"):
        a2a_to_run(A2AMessage(message_id="message-1", role=Role.ROLE_USER))


def test_a2a_from_run_converts_final_response() -> None:
    response = AgentResponse(
        messages=[
            Message("user", ["omit me"]),
            Message(
                "assistant",
                [
                    Content.from_text("hello", additional_properties={"source": "agent"}),
                    Content.from_uri("https://example.com/image.png", media_type="image/png"),
                    Content.from_data(b"audio", "audio/wav"),
                ],
            ),
        ]
    )

    parts = a2a_from_run(response)

    assert len(parts) == 3
    assert parts[0].text == "hello"
    assert MessageToDict(parts[0].metadata) == {"source": "agent"}
    assert parts[1].url == "https://example.com/image.png"
    assert parts[1].media_type == "image/png"
    assert parts[2].raw == b"audio"
    assert parts[2].media_type == "audio/wav"


def test_a2a_from_run_converts_streaming_update() -> None:
    update = AgentResponseUpdate(
        role="assistant",
        contents=[Content.from_text("chunk")],
        message_id="message-1",
    )

    parts = a2a_from_run(update)

    assert len(parts) == 1
    assert parts[0].text == "chunk"


def test_a2a_from_run_preserves_empty_text_part() -> None:
    parts = a2a_from_run(Message("assistant", [Content.from_text("")]))

    assert len(parts) == 1
    assert parts[0].WhichOneof("content") == "text"
    assert parts[0].text == ""


def test_a2a_from_run_rejects_invalid_data_uri() -> None:
    content = Content("data", uri="not-a-data-uri", media_type="application/octet-stream")

    with raises(ValueError, match="base64 data URI"):
        a2a_from_run(Message("assistant", [content]))


def test_a2a_from_run_rejects_invalid_base64_data() -> None:
    content = Content(
        "data",
        uri="data:application/octet-stream;base64,not valid base64",
        media_type="application/octet-stream",
    )

    with raises(ValueError, match="invalid base64"):
        a2a_from_run(Message("assistant", [content]))
