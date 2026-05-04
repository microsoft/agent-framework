# Copyright (c) Microsoft. All rights reserved.

"""Tests for the OpenAI Responses request-body parser."""

from __future__ import annotations

import pytest
from agent_framework_hosting import ResponseTarget, ResponseTargetKind

from agent_framework_hosting_responses import (
    messages_from_responses_input,
    parse_response_target,
    parse_responses_identity,
    parse_responses_request,
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
    def test_instructions_become_system_message_prefix(self) -> None:
        msgs, opts, sess = parse_responses_request({"input": "hi", "instructions": "be brief"})
        assert msgs[0].role == "system"
        assert msgs[0].text == "be brief"
        assert msgs[1].role == "user"
        # 'instructions' is consumed, not forwarded as an option.
        assert "instructions" not in opts
        assert sess is None

    def test_options_passthrough(self) -> None:
        _, opts, _ = parse_responses_request({"input": "x", "temperature": 0.4, "top_p": 0.9, "tool_choice": "auto"})
        assert opts["temperature"] == 0.4
        assert opts["top_p"] == 0.9
        assert opts["tool_choice"] == "auto"

    def test_options_remap(self) -> None:
        _, opts, _ = parse_responses_request({"input": "x", "max_output_tokens": 256, "parallel_tool_calls": False})
        assert opts == {"max_tokens": 256, "allow_multiple_tool_calls": False}

    def test_transport_keys_not_forwarded(self) -> None:
        _, opts, _ = parse_responses_request({
            "input": "x",
            "model": "gpt-x",
            "stream": True,
            "previous_response_id": "r",
        })
        for key in ("input", "model", "stream", "previous_response_id"):
            assert key not in opts

    def test_unknown_keys_silently_dropped(self) -> None:
        _, opts, _ = parse_responses_request({"input": "x", "truncation": "auto", "reasoning": {"effort": "low"}})
        assert opts == {}

    def test_none_values_dropped(self) -> None:
        _, opts, _ = parse_responses_request({"input": "x", "temperature": None})
        assert "temperature" not in opts

    def test_previous_response_id_becomes_session(self) -> None:
        _, _, sess = parse_responses_request({"input": "x", "previous_response_id": "resp_42"})
        assert sess is not None
        assert sess.isolation_key == "resp_42"


class TestParseResponseTarget:
    def test_default_originating_when_missing(self) -> None:
        assert parse_response_target({}).kind is ResponseTargetKind.ORIGINATING

    @pytest.mark.parametrize(
        "value,expected_kind",
        [
            ("originating", ResponseTargetKind.ORIGINATING),
            ("active", ResponseTargetKind.ACTIVE),
            ("all_linked", ResponseTargetKind.ALL_LINKED),
            ("none", ResponseTargetKind.NONE),
        ],
    )
    def test_bare_string_kinds(self, value: str, expected_kind: ResponseTargetKind) -> None:
        assert parse_response_target({"response_target": value}).kind is expected_kind

    def test_bare_string_other_becomes_channel(self) -> None:
        target = parse_response_target({"response_target": "telegram"})
        assert target == ResponseTarget.channel("telegram")

    def test_bare_string_with_native_id_becomes_channel(self) -> None:
        target = parse_response_target({"response_target": "telegram:42"})
        assert target.kind is ResponseTargetKind.CHANNELS
        assert target.targets == ("telegram:42",)

    def test_list_form(self) -> None:
        target = parse_response_target({"response_target": ["telegram:42", "originating"]})
        assert target == ResponseTarget.channels(["telegram:42", "originating"])

    def test_list_drops_non_strings(self) -> None:
        target = parse_response_target({"response_target": ["telegram", 42, ""]})
        assert target.targets == ("telegram",)

    def test_empty_list_falls_back_to_originating(self) -> None:
        target = parse_response_target({"response_target": []})
        assert target.kind is ResponseTargetKind.ORIGINATING

    def test_dict_with_channels(self) -> None:
        target = parse_response_target({"response_target": {"channels": ["a", "b"]}})
        assert target == ResponseTarget.channels(["a", "b"])

    @pytest.mark.parametrize(
        "kind,expected",
        [
            ("active", ResponseTargetKind.ACTIVE),
            ("all_linked", ResponseTargetKind.ALL_LINKED),
            ("none", ResponseTargetKind.NONE),
            ("originating", ResponseTargetKind.ORIGINATING),
        ],
    )
    def test_dict_kind(self, kind: str, expected: ResponseTargetKind) -> None:
        assert parse_response_target({"response_target": {"kind": kind}}).kind is expected

    def test_malformed_falls_back_to_originating(self) -> None:
        target = parse_response_target({"response_target": 42})
        assert target.kind is ResponseTargetKind.ORIGINATING


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
