# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass

from a2a.types import Message as A2AMessage
from a2a.types import Part, Role
from agent_framework import (
    AgentResponse,
    AgentResponseUpdate,
    Content,
    Message,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowEvent,
    WorkflowRunResult,
    executor,
)
from google.protobuf.json_format import MessageToDict, ParseDict
from pytest import raises

from agent_framework_hosting_a2a import (
    a2a_from_run,
    a2a_from_workflow_run,
    a2a_to_run,
    a2a_to_workflow_run,
)


@dataclass
class WorkflowInput:
    text: str
    repeat: int


def create_workflow():
    @executor(id="repeat")
    async def repeat_text(value: WorkflowInput, ctx: WorkflowContext[object, str]) -> None:
        await ctx.yield_output(value.text * value.repeat)

    return WorkflowBuilder(
        start_executor=repeat_text,
        name="Repeat Workflow",
        description="Repeat text a requested number of times.",
        output_from=[repeat_text],
    ).build()


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


def test_a2a_to_run_omits_unsupported_parts() -> None:
    run = a2a_to_run(
        A2AMessage(
            message_id="message-1",
            role=Role.ROLE_USER,
            parts=[Part(), Part(text="hello")],
        )
    )

    messages = run["messages"]
    assert isinstance(messages, list)
    converted = messages[0]
    assert isinstance(converted, Message)
    assert converted.text == "hello"


def test_a2a_to_run_validates_advertised_input_modes() -> None:
    message = A2AMessage(
        message_id="message-1",
        role=Role.ROLE_USER,
        parts=[Part(raw=b"audio", media_type="audio/wav")],
    )

    with raises(ValueError, match="audio/wav"):
        a2a_to_run(message, input_modes=["text"])

    assert a2a_to_run(message, input_modes=["audio/*"])["messages"]


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


def test_a2a_from_run_omits_unsupported_content() -> None:
    parts = a2a_from_run(
        Message(
            "assistant",
            [
                Content(type="function_call", call_id="call-1", name="get_weather", arguments="{}"),
                Content.from_text("hello"),
            ],
        )
    )

    assert len(parts) == 1
    assert parts[0].text == "hello"


def test_a2a_from_run_omits_user_messages() -> None:
    assert a2a_from_run(AgentResponse(messages=[Message("user", ["omit me"])])) == []


def test_a2a_from_run_validates_advertised_output_modes() -> None:
    result = Message(
        "assistant",
        [Content.from_uri("https://example.com/image.png", media_type="image/png")],
    )

    with raises(ValueError, match="image/png"):
        a2a_from_run(result, output_modes=["text"])

    assert a2a_from_run(result, output_modes=["image/*"])[0].url == "https://example.com/image.png"


def test_a2a_from_run_parses_json_text_for_json_output_mode() -> None:
    parts = a2a_from_run(
        Message("assistant", ['{"answer":42}']),
        output_modes=["application/json"],
    )

    assert MessageToDict(parts[0].data) == {"answer": 42.0}

    with raises(ValueError, match="not valid JSON"):
        a2a_from_run(Message("assistant", ["not json"]), output_modes=["application/json"])


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


def test_a2a_to_workflow_run_validates_structured_input() -> None:
    data_part = Part()
    ParseDict({"text": "go", "repeat": 2}, data_part.data)

    value = a2a_to_workflow_run(
        A2AMessage(message_id="message-1", role=Role.ROLE_USER, parts=[data_part]),
        create_workflow(),
    )

    assert value == WorkflowInput(text="go", repeat=2)


def test_a2a_to_workflow_run_supports_text_and_binary_inputs() -> None:
    @executor(id="text")
    async def text_input(value: str, ctx: WorkflowContext[object, str]) -> None:
        await ctx.yield_output(value)

    @executor(id="binary")
    async def binary_input(value: bytes, ctx: WorkflowContext[object, bytes]) -> None:
        await ctx.yield_output(value)

    text_workflow = WorkflowBuilder(start_executor=text_input, output_from=[text_input]).build()
    binary_workflow = WorkflowBuilder(start_executor=binary_input, output_from=[binary_input]).build()

    assert (
        a2a_to_workflow_run(
            A2AMessage(message_id="text", role=Role.ROLE_USER, parts=[Part(text="hello")]),
            text_workflow,
        )
        == "hello"
    )
    assert (
        a2a_to_workflow_run(
            A2AMessage(message_id="binary", role=Role.ROLE_USER, parts=[Part(raw=b"data")]),
            binary_workflow,
        )
        == b"data"
    )


def test_a2a_to_workflow_run_requires_one_compatible_part() -> None:
    @executor(id="text")
    async def text_input(value: str, ctx: WorkflowContext[object, str]) -> None:
        await ctx.yield_output(value)

    with raises(ValueError, match="exactly one compatible"):
        a2a_to_workflow_run(
            A2AMessage(
                message_id="message-1",
                role=Role.ROLE_USER,
                parts=[Part(text="one"), Part(text="two")],
            ),
            WorkflowBuilder(start_executor=text_input, output_from=[text_input]).build(),
        )


def test_a2a_from_workflow_run_converts_public_outputs() -> None:
    result = WorkflowRunResult([
        WorkflowEvent("output", "hello", executor_id="text"),
        WorkflowEvent("output", b"data", executor_id="binary"),
        WorkflowEvent("output", {"count": 2}, executor_id="structured"),
        WorkflowEvent(
            "output",
            AgentResponse(messages=[Message("assistant", ["from agent"])]),
            executor_id="agent",
        ),
    ])

    parts = a2a_from_workflow_run(result)

    assert parts[0].text == "hello"
    assert parts[1].raw == b"data"
    assert parts[1].media_type == "application/octet-stream"
    assert MessageToDict(parts[2].data) == {"count": 2.0}
    assert parts[3].text == "from agent"


def test_a2a_from_workflow_run_serializes_structured_output_for_text_mode() -> None:
    result = WorkflowRunResult([WorkflowEvent("output", {"count": 2}, executor_id="structured")])

    text_parts = a2a_from_workflow_run(result, output_modes=["text"])
    json_parts = a2a_from_workflow_run(result, output_modes=["application/json"])

    assert text_parts[0].text == '{"count":2}'
    assert MessageToDict(json_parts[0].data) == {"count": 2.0}


def test_a2a_from_workflow_run_rejects_pending_input() -> None:
    result = WorkflowRunResult([
        WorkflowEvent.request_info(
            request_id="approval",
            source_executor_id="review",
            request_data={"question": "Approve?"},
            response_type=bool,
        )
    ])

    with raises(ValueError, match="requires external input"):
        a2a_from_workflow_run(result)
