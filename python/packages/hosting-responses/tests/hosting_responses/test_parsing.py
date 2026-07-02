# Copyright (c) Microsoft. All rights reserved.

"""Tests for the OpenAI Responses request-body parser."""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence

import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, ResponseStream

from agent_framework_hosting_responses import (
    create_response_id,
    messages_from_responses_input,
    parse_responses_identity,
    parse_responses_request,
    responses_from_run,
    responses_session_id,
    responses_stream_events_from_run,
    responses_to_run,
)


class TestMessagesFromResponsesInput:
    def test_string_input_becomes_single_user_message(self) -> None:
        msgs = messages_from_responses_input("hello")
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].text == "hello"

    def test_input_text_items_collapse_into_one_user_message(self) -> None:
        msgs = messages_from_responses_input([{"type": "input_text", "text": "a"}, {"type": "input_text", "text": "b"}])
        assert len(msgs) == 1
        assert msgs[0].role == "user"
        assert msgs[0].text == "a b"

    def test_message_envelope_with_string_content(self) -> None:
        msgs = messages_from_responses_input([
            {"type": "message", "role": "system", "content": "be brief"},
            {"type": "message", "role": "user", "content": "hi"},
        ])
        assert [m.role for m in msgs] == ["system", "user"]
        assert msgs[0].text == "be brief"

    def test_message_envelope_with_content_parts(self) -> None:
        msgs = messages_from_responses_input([
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "describe this"}],
            }
        ])
        assert msgs[0].text == "describe this"

    def test_message_envelope_rejects_non_object_content_item(self) -> None:
        with pytest.raises(ValueError, match="content.*object"):
            messages_from_responses_input([{"type": "message", "role": "user", "content": ["bad"]}])

    def test_message_envelope_rejects_invalid_content_shape(self) -> None:
        with pytest.raises(ValueError, match="content.*string or list"):
            messages_from_responses_input([{"type": "message", "role": "user", "content": 42}])

    def test_input_file_via_url(self) -> None:
        msgs = messages_from_responses_input([
            {"type": "input_file", "file_url": "https://example.com/report.pdf", "mime_type": "application/pdf"}
        ])
        assert msgs[0].contents[0].uri == "https://example.com/report.pdf"

    def test_input_file_via_file_id(self) -> None:
        msgs = messages_from_responses_input([{"type": "input_file", "file_id": "file_123"}])
        assert msgs[0].contents[0].file_id == "file_123"

    def test_input_file_missing_anchor_raises(self) -> None:
        with pytest.raises(ValueError, match="input_file"):
            messages_from_responses_input([{"type": "input_file"}])

    def test_pending_text_flushes_before_message_envelope(self) -> None:
        msgs = messages_from_responses_input([
            {"type": "input_text", "text": "first"},
            {"type": "message", "role": "user", "content": "second"},
        ])
        assert len(msgs) == 2
        assert msgs[0].text == "first"
        assert msgs[1].text == "second"

    def test_image_url_via_string(self) -> None:
        msgs = messages_from_responses_input([{"type": "input_image", "image_url": "https://example.com/cat.png"}])
        assert len(msgs) == 1
        # Image content present.
        assert any(getattr(c, "uri", None) == "https://example.com/cat.png" for c in msgs[0].contents)

    def test_image_url_via_object(self) -> None:
        msgs = messages_from_responses_input([
            {"type": "input_image", "image_url": {"url": "https://example.com/cat.png"}}
        ])
        assert any(getattr(c, "uri", None) == "https://example.com/cat.png" for c in msgs[0].contents)

    def test_unknown_input_type_raises(self) -> None:
        with pytest.raises(ValueError, match="Unsupported"):
            messages_from_responses_input([{"type": "weird"}])

    def test_empty_list_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            messages_from_responses_input([])

    def test_non_string_non_list_raises(self) -> None:
        with pytest.raises(ValueError):
            messages_from_responses_input(42)  # type: ignore[arg-type]

    def test_image_url_missing_raises(self) -> None:
        with pytest.raises(ValueError, match="image_url"):
            messages_from_responses_input([{"type": "input_image"}])


class TestParseResponsesRequest:
    def test_known_fields_remapped_and_unknown_forwarded(self) -> None:
        _, opts, _ = parse_responses_request({
            "input": "hi",
            "instructions": "be brief",
            "temperature": 0.4,
            "top_p": 0.9,
            "tool_choice": "auto",
            "max_output_tokens": 256,
            "parallel_tool_calls": False,
            "truncation": "auto",
            "reasoning": {"effort": "low"},
        })
        # Known remaps applied.
        assert opts["max_tokens"] == 256
        assert opts["allow_multiple_tool_calls"] is False
        # Straight-through fields present.
        assert opts["temperature"] == 0.4
        assert opts["instructions"] == "be brief"
        assert opts["truncation"] == "auto"
        # Transport/session keys excluded.
        for key in ("input", "stream", "previous_response_id"):
            assert key not in opts

    def test_model_passes_through_transport_keys_excluded(self) -> None:
        _, opts, _ = parse_responses_request({
            "input": "x",
            "model": "gpt-x",
            "stream": True,
            "previous_response_id": "r",
        })
        for key in ("input", "stream", "previous_response_id"):
            assert key not in opts
        # model passes through — not a transport key; run_hook decides what to do with it.
        assert opts["model"] == "gpt-x"

    def test_none_values_dropped(self) -> None:
        _, opts, _ = parse_responses_request({"input": "x", "temperature": None})
        assert "temperature" not in opts

    def test_previous_response_id_becomes_session(self) -> None:
        _, _, sess = parse_responses_request({"input": "x", "previous_response_id": "resp_42"})
        assert sess is not None
        assert sess.isolation_key == "resp_42"


class TestParseResponsesIdentity:
    def test_safety_identifier_preferred(self) -> None:
        ident = parse_responses_identity({"safety_identifier": "abc", "user": "legacy"}, "responses")
        assert ident is not None
        assert ident.native_id == "abc"
        assert ident.channel == "responses"

    def test_fallback_to_user(self) -> None:
        ident = parse_responses_identity({"user": "legacy"}, "responses")
        assert ident is not None
        assert ident.native_id == "legacy"

    def test_returns_none_when_absent(self) -> None:
        assert parse_responses_identity({}, "responses") is None

    def test_returns_none_for_non_string(self) -> None:
        assert parse_responses_identity({"safety_identifier": 42}, "responses") is None


class TestResponsesRunHelpers:
    def test_create_response_id_shape(self) -> None:
        response_id = create_response_id()

        assert response_id.startswith("resp_")

    def test_responses_session_id_prefers_previous_response(self) -> None:
        assert responses_session_id({"previous_response_id": "resp_1", "conversation_id": "conv_1"}) == "resp_1"

    def test_responses_session_id_uses_conversation_id(self) -> None:
        assert responses_session_id({"conversation_id": "conv_1"}) == "conv_1"

    def test_responses_session_id_returns_none_when_absent(self) -> None:
        assert responses_session_id({"input": "hi"}) is None

    def test_responses_to_run_returns_messages_options_and_stream(self) -> None:
        run = responses_to_run({
            "input": "hi",
            "stream": True,
            "previous_response_id": "resp_1",
            "conversation_id": "conv_1",
            "max_output_tokens": 32,
            "model": "gpt-x",
        })

        assert run["messages"][0].text == "hi"
        assert run["stream"] is True
        assert run["options"] == {"max_tokens": 32, "model": "gpt-x"}

    def test_responses_from_run_returns_response_payload(self) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            additional_properties={"model": "test-model"},
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert payload["id"] == "resp_new"
        assert payload["model"] == "test-model"
        assert payload["output"][0]["content"][0]["text"] == "hello"

    def test_responses_from_run_preserves_multimodal_output_items(self) -> None:
        result = AgentResponse(
            messages=Message(
                role="assistant",
                contents=[
                    Content.from_text_reasoning(id="rs_1", text="checking"),
                    Content.from_function_call("call_1", "collect_media", arguments={"city": "Seattle"}),
                    Content.from_function_result(
                        "call_1",
                        result=[
                            Content.from_text("caption"),
                            Content.from_uri("https://example.com/cat.png", media_type="image/png"),
                            Content.from_hosted_file("file_pdf", media_type="application/pdf"),
                        ],
                    ),
                    Content.from_text("done"),
                ],
            )
        )

        payload = responses_from_run(result, response_id="resp_new")

        output = payload["output"]
        assert [item["type"] for item in output] == [
            "reasoning",
            "function_call",
            "function_call_output",
            "message",
        ]
        assert output[0]["content"][0]["text"] == "checking"
        assert output[1]["name"] == "collect_media"
        assert output[1]["arguments"] == '{"city": "Seattle"}'
        assert output[2]["output"] == [
            {"text": "caption", "type": "input_text"},
            {"detail": "auto", "type": "input_image", "image_url": "https://example.com/cat.png"},
            {"type": "input_file", "file_id": "file_pdf"},
        ]
        assert output[3]["content"][0]["text"] == "done"

    def test_responses_from_run_maps_conversation_session(self) -> None:
        result = AgentResponse(messages=Message(role="assistant", contents=[Content.from_text("hello")]))

        payload = responses_from_run(result, response_id="resp_new", session_id="conv_1")

        assert payload["conversation"] == {"id": "conv_1"}

    def test_responses_from_run_omits_previous_response_session(self) -> None:
        result = AgentResponse(messages=Message(role="assistant", contents=[Content.from_text("hello")]))

        payload = responses_from_run(result, response_id="resp_new", session_id="resp_1")

        assert "conversation" not in payload

    async def test_responses_stream_events_from_run(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text("hel")], role="assistant")
            yield AgentResponseUpdate(contents=[Content.from_text("lo")], role="assistant")

        def finalizer(items: Sequence[AgentResponseUpdate]) -> AgentResponse:
            return AgentResponse.from_updates(items)

        stream = ResponseStream(updates(), finalizer=finalizer)

        events = [
            event
            async for event in responses_stream_events_from_run(
                stream,
                response_id="resp_new",
                session_id="conv_1",
            )
        ]

        assert events[0].startswith("event: response.created")
        assert "response.output_text.delta" in events[1]
        assert "hel" in events[1]
        assert "lo" in events[2]
        assert events[-1].startswith("event: response.completed")
        assert '"conversation":{"id":"conv_1"}' in events[-1]
