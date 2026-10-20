# Copyright (c) Microsoft. All rights reserved.

"""AG-UI 1.0 behaviour that holds on every supported ag-ui-protocol release."""

import json
from typing import Any

import pytest
from ag_ui.core import (
    EventType,
    MessagesSnapshotEvent,
    TextMessageContentEvent,
    TextMessageEndEvent,
    TextMessageStartEvent,
    ToolCallResultEvent,
    ToolCallStartEvent,
)
from agent_framework import Content, Message

from agent_framework_ag_ui._agent_run import _resolved_tool_result_snapshot_messages
from agent_framework_ag_ui._event_converters import AGUIEventConverter
from agent_framework_ag_ui._message_adapters import (
    _deduplicate_messages,
    agent_framework_messages_to_agui,
    agui_messages_to_agent_framework,
    snapshot_messages_for_wire,
)
from agent_framework_ag_ui._run_common import _build_run_started_event
from agent_framework_ag_ui._snapshot_session import ThreadSnapshotSession
from agent_framework_ag_ui._snapshots import AGUIThreadSnapshot
from agent_framework_ag_ui._utils import _AGUI_PROTOCOL_VERSION
from agent_framework_ag_ui._workflow import _WorkflowSnapshotBuilder

requires_1_0 = pytest.mark.skipif(_AGUI_PROTOCOL_VERSION is None, reason="needs ag-ui-protocol >= 1.0")


def test_run_started_declares_the_protocol_version() -> None:
    """RUN_STARTED declares the installed protocol version; releases before 1.0 have none to declare."""
    event = _build_run_started_event("run-1", "thread-1").model_dump(by_alias=True, exclude_none=True)

    assert event["type"] == EventType.RUN_STARTED
    if _AGUI_PROTOCOL_VERSION is None:
        assert "protocolVersion" not in event
    else:
        assert event["protocolVersion"] == _AGUI_PROTOCOL_VERSION


async def test_thread_saved_with_legacy_media_replays() -> None:
    """A thread snapshot holding legacy ``binary`` media replays with whichever ag-ui-protocol is installed."""
    stored = AGUIThreadSnapshot(
        messages=[
            {
                "id": "u1",
                "role": "user",
                "content": [
                    {"type": "text", "text": "look"},
                    {"type": "binary", "url": "https://example.com/cat.png", "mimeType": "image/png"},
                ],
            }
        ]
    )
    session = ThreadSnapshotSession(store=None, scope=None, thread_id="t1", stored=stored)

    events = [event async for event in session.hydrate_events(run_id="r1")]

    assert events[0].type == EventType.RUN_STARTED
    snapshot = next(event for event in events if isinstance(event, MessagesSnapshotEvent))
    content = snapshot.messages[0].model_dump(by_alias=True, exclude_none=True)["content"]
    if _AGUI_PROTOCOL_VERSION is None:
        assert content[1]["type"] == "binary"
    else:
        assert content[1] == {
            "type": "image",
            "source": {"type": "url", "value": "https://example.com/cat.png", "mimeType": "image/png"},
        }


@requires_1_0
def test_wire_snapshot_maps_legacy_media_by_mime_type() -> None:
    """Legacy media becomes the 1.0 part its MIME type names; a bare id reference has no 1.0 form."""
    messages: list[dict[str, Any]] = [
        {
            "id": "u1",
            "role": "user",
            "content": [
                {"type": "binary", "data": "YXVkaW8=", "mimeType": "audio/wav"},
                {"type": "binary", "url": "https://example.com/report.pdf", "mimeType": "application/pdf"},
                {"type": "binary", "id": "upload-1", "mimeType": "image/png"},
                {"type": "text", "text": "after"},
            ],
        },
        {"id": "a1", "role": "assistant", "content": "unchanged"},
    ]

    wire = snapshot_messages_for_wire(messages)

    assert wire[0]["content"] == [
        {"type": "audio", "source": {"type": "data", "value": "YXVkaW8=", "mimeType": "audio/wav"}},
        {
            "type": "document",
            "source": {"type": "url", "value": "https://example.com/report.pdf", "mimeType": "application/pdf"},
        },
        {"type": "text", "text": "after"},
    ]
    assert wire[1] is messages[1]
    assert messages[0]["content"][0]["type"] == "binary", "the stored messages are not modified"


def _tool_turn(content: Any) -> list[dict[str, Any]]:
    return [
        {
            "id": "a1",
            "role": "assistant",
            "content": "",
            "toolCalls": [{"id": "call-1", "type": "function", "function": {"name": "chart", "arguments": "{}"}}],
        },
        {"id": "t1", "role": "tool", "toolCallId": "call-1", "content": content},
    ]


def _function_result(messages: list[dict[str, Any]]) -> Any:
    converted = agui_messages_to_agent_framework(messages)
    tool_message = next(message for message in converted if message.role == "tool")
    return tool_message.contents[0]


def test_tool_result_media_reaches_the_function_result() -> None:
    """Media in a 1.0 tool result is passed on as content, not as the text of the raw parts."""
    result = _function_result(
        _tool_turn(
            [
                {"type": "text", "text": "chart:"},
                {
                    "type": "image",
                    "source": {"type": "url", "value": "https://example.com/chart.png", "mimeType": "image/png"},
                },
            ]
        )
    )

    # Function results carry their output as Content items; ``result`` is only their text.
    assert [item.type for item in result.items] == ["text", "uri"]
    assert result.items[0].text == "chart:"
    assert result.items[1].uri == "https://example.com/chart.png"
    assert result.items[1].media_type == "image/png"


def test_text_only_tool_result_stays_text() -> None:
    """A tool result of text parts only is passed on as its text."""
    result = _function_result(_tool_turn([{"type": "text", "text": "4"}, {"type": "text", "text": "2"}]))

    assert result.result == "42"
    assert [item.type for item in result.items] == ["text"]


def test_file_source_is_an_unresolved_reference() -> None:
    """A 1.0 file source is a provider-issued handle: it is rejected like an id reference, never read as data."""
    message = {
        "role": "user",
        "content": [
            {"type": "image", "source": {"type": "file", "value": "file-abc123", "provider": "openai"}},
        ],
    }

    with pytest.raises(ValueError, match="Unresolved AG-UI multimodal binary references"):
        agui_messages_to_agent_framework([message])


def test_stored_tool_result_media_converts_on_replay() -> None:
    """Tool media kept as ``binary`` parts in a stored snapshot reaches the function result when replayed."""
    result = _function_result(
        _tool_turn(
            [
                {"type": "text", "text": "chart:"},
                {"type": "binary", "url": "https://example.com/chart.png", "mimeType": "image/png"},
            ]
        )
    )

    assert [item.type for item in result.items] == ["text", "uri"]
    assert result.items[1].uri == "https://example.com/chart.png"


def test_streamed_tool_result_media_reaches_the_function_result() -> None:
    """A TOOL_CALL_RESULT event with content parts gives the client the same Content items as a tool message."""
    update = AGUIEventConverter().convert_event(
        {
            "type": "TOOL_CALL_RESULT",
            "toolCallId": "call-1",
            "content": [
                {"type": "text", "text": "chart:"},
                {
                    "type": "image",
                    "source": {"type": "url", "value": "https://example.com/chart.png", "mimeType": "image/png"},
                },
            ],
        }
    )

    assert update is not None
    items = update.contents[0].items
    assert items is not None
    assert [item.type for item in items] == ["text", "uri"]
    assert items[1].uri == "https://example.com/chart.png"


def test_streamed_text_only_tool_result_stays_text() -> None:
    """A TOOL_CALL_RESULT event of text parts gives its text, not the string form of the list."""
    update = AGUIEventConverter().convert_event(
        {
            "type": "TOOL_CALL_RESULT",
            "toolCallId": "call-1",
            "content": [{"type": "text", "text": "4"}, {"type": "text", "text": "2"}],
        }
    )

    assert update is not None
    assert update.contents[0].result == "42"


def test_workflow_text_without_a_role_snapshots_as_assistant() -> None:
    """A text message started without a role (1.0's default) is stored, and replays, as the assistant's."""
    builder = _WorkflowSnapshotBuilder([])
    builder.observe(TextMessageStartEvent(message_id="text-1"))
    builder.observe(TextMessageContentEvent(message_id="text-1", delta="hello"))
    builder.observe(TextMessageEndEvent(message_id="text-1"))

    messages = builder.build().messages

    assert [(message["role"], message["content"]) for message in messages] == [("assistant", "hello")]
    MessagesSnapshotEvent(messages=snapshot_messages_for_wire(messages))  # type: ignore[arg-type]


@requires_1_0
def test_workflow_tool_media_snapshots_as_wire_parts() -> None:
    """Tool media from a workflow is stored as wire dictionaries, so it serializes and replays as media."""
    image = {
        "type": "image",
        "source": {"type": "url", "value": "https://example.com/chart.png", "mimeType": "image/png"},
    }
    builder = _WorkflowSnapshotBuilder([])
    builder.observe(ToolCallStartEvent(tool_call_id="call-1", tool_call_name="chart"))
    builder.observe(
        ToolCallResultEvent.model_validate(
            {
                "messageId": "result-1",
                "toolCallId": "call-1",
                "content": [{"type": "text", "text": "chart:"}, image],
            }
        )
    )

    messages = builder.build().messages
    tool_message = next(message for message in messages if message["role"] == "tool")

    assert tool_message["content"] == [{"type": "text", "text": "chart:"}, image]
    json.dumps(messages)
    replayed = _function_result([*_tool_turn("")[:1], {**tool_message, "toolCallId": "call-1"}])
    assert [item.type for item in replayed.items] == ["text", "uri"]


@requires_1_0
def test_client_history_keeps_tool_result_media() -> None:
    """Tool media received by AGUIChatClient goes back out as content parts in the next request's history."""
    update = AGUIEventConverter().convert_event(
        {
            "type": "TOOL_CALL_RESULT",
            "toolCallId": "call-1",
            "content": [
                {"type": "text", "text": "chart:"},
                {
                    "type": "image",
                    "source": {"type": "url", "value": "https://example.com/chart.png", "mimeType": "image/png"},
                },
            ],
        }
    )
    assert update is not None
    history = [
        Message(
            role="assistant", contents=[Content.from_function_call(call_id="call-1", name="chart", arguments="{}")]
        ),
        Message(role="tool", contents=update.contents),
    ]

    outgoing = agent_framework_messages_to_agui(history)

    tool_message = next(message for message in outgoing if message["role"] == "tool")
    assert tool_message["content"] == [
        {"type": "text", "text": "chart:"},
        {"type": "image", "source": {"type": "url", "value": "https://example.com/chart.png", "mimeType": "image/png"}},
    ]


def _image_result(call_id: str) -> Content:
    return Content.from_function_result(
        call_id=call_id,
        result=[Content.from_uri(uri="https://example.com/chart.png", media_type="image/png")],
    )


def test_dedupe_keeps_an_image_only_result_over_an_empty_placeholder() -> None:
    """A completed image-only result replaces an earlier empty result for the same call; it is not dropped."""
    placeholder = Message(role="tool", contents=[Content.from_function_result(call_id="call-1", result="")])
    completed = Message(role="tool", contents=[_image_result("call-1")])

    deduplicated = _deduplicate_messages([placeholder, completed])

    assert len(deduplicated) == 1
    items = deduplicated[0].contents[0].items
    assert items is not None
    assert [item.type for item in items] == ["uri"]


@requires_1_0
def test_approval_snapshot_rebuild_keeps_tool_result_media() -> None:
    """Rebuilding tool messages for an approval snapshot keeps an earlier result's media as content parts."""
    rebuilt = _resolved_tool_result_snapshot_messages([Message(role="tool", contents=[_image_result("call-1")])])

    assert rebuilt[("call-1", 1)][0]["content"] == [
        {"type": "image", "source": {"type": "url", "value": "https://example.com/chart.png", "mimeType": "image/png"}}
    ]
