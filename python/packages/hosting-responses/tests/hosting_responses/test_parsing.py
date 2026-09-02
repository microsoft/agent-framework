# Copyright (c) Microsoft. All rights reserved.

"""Tests for the OpenAI Responses request-body parser."""

from __future__ import annotations

import json
import warnings
from collections.abc import AsyncIterator, Sequence
from types import SimpleNamespace
from typing import cast

import pytest
from agent_framework import AgentResponse, AgentResponseUpdate, Content, Message, ResponseStream, UsageDetails
from openai.types.responses.response_usage import InputTokensDetails, ResponseUsage

from agent_framework_hosting_responses import (
    create_conversation_id,
    create_response_id,
    messages_from_responses_input,
    responses_from_run,
    responses_from_streaming_run,
    responses_session_id,
    responses_to_run,
)


def _sse_payload(event: str) -> dict[str, object]:
    data_line = next(line for line in event.splitlines() if line.startswith("data: "))
    return cast("dict[str, object]", json.loads(data_line.removeprefix("data: ")))


def _native_usage_payload() -> dict[str, object]:
    input_tokens_details = {"cached_tokens": 1}
    if "cache_write_tokens" in InputTokensDetails.model_fields:
        input_tokens_details["cache_write_tokens"] = 0
    return {
        "input_tokens": 7,
        "input_tokens_details": input_tokens_details,
        "output_tokens": 2,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": 9,
    }


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

    @pytest.mark.parametrize("text", [None, "", 42])
    def test_text_items_require_non_empty_string_text(self, text: object) -> None:
        with pytest.raises(ValueError, match="non-empty string `text`"):
            messages_from_responses_input([{"type": "input_text", "text": text}])

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

    @pytest.mark.parametrize("role", [None, "", "moderator", 42])
    def test_message_envelope_requires_supported_role(self, role: object) -> None:
        with pytest.raises(ValueError, match="message `role`"):
            messages_from_responses_input([{"type": "message", "role": role, "content": "hello"}])

    @pytest.mark.parametrize(
        "item",
        [
            {"type": "message", "role": "user"},
            {"type": "message", "role": "user", "content": ""},
            {"type": "message", "role": "user", "content": []},
        ],
    )
    def test_message_envelope_requires_non_empty_content(self, item: dict[str, object]) -> None:
        with pytest.raises(ValueError, match="content"):
            messages_from_responses_input([item])

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

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            messages_from_responses_input("")

    def test_non_string_non_list_raises(self) -> None:
        with pytest.raises(ValueError):
            messages_from_responses_input(42)  # type: ignore[arg-type]

    def test_image_url_missing_raises(self) -> None:
        with pytest.raises(ValueError, match="image_url"):
            messages_from_responses_input([{"type": "input_image"}])


class TestResponsesRunHelpers:
    def test_create_conversation_id_shape(self) -> None:
        conversation_id = create_conversation_id()

        assert len(conversation_id) == 37
        assert conversation_id.startswith("conv_")
        assert all(character in "0123456789abcdef" for character in conversation_id.removeprefix("conv_"))

    def test_create_response_id_shape(self) -> None:
        response_id = create_response_id()

        assert response_id.startswith("resp_")

    def test_responses_session_id_valid_ids_do_not_warn(self) -> None:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            assert responses_session_id({"previous_response_id": "resp_1"}) == ("resp_1", False)
            assert responses_session_id({"conversation": "conv_1"}) == ("conv_1", True)
            assert responses_session_id({"conversation": {"id": "conv_2"}}) == ("conv_2", True)

    def test_responses_session_id_warns_for_nonstandard_previous_response_id(self) -> None:
        with pytest.warns(UserWarning, match="previous_response_id.*resp_"):
            assert responses_session_id({"previous_response_id": "custom-response"}) == ("custom-response", False)

    def test_responses_session_id_warns_for_nonstandard_conversation(self) -> None:
        with pytest.warns(UserWarning, match="conversation.*conv_"):
            assert responses_session_id({"conversation": "custom-conversation"}) == ("custom-conversation", True)

    def test_responses_session_id_accepts_deprecated_conversation_id_alone(self) -> None:
        with pytest.warns(DeprecationWarning, match="conversation_id.*deprecated.*conversation"):
            assert responses_session_id({"conversation_id": "conv_legacy"}) == ("conv_legacy", True)

    @pytest.mark.parametrize(
        "body",
        [
            {"previous_response_id": "resp_1", "conversation": "conv_1"},
            {"previous_response_id": "resp_1", "conversation_id": "conv_1"},
            {"conversation": "conv_1", "conversation_id": "conv_1"},
        ],
    )
    def test_responses_session_id_rejects_conflicting_continuation_mechanisms(
        self,
        body: dict[str, object],
    ) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            responses_session_id(body)

    @pytest.mark.parametrize(
        "body",
        [
            {"previous_response_id": ""},
            {"previous_response_id": 42},
            {"conversation": ""},
            {"conversation": {}},
            {"conversation": {"id": ""}},
            {"conversation": {"id": 42}},
            {"conversation_id": ""},
            {"conversation_id": 42},
        ],
    )
    def test_responses_session_id_rejects_invalid_continuation_values(self, body: dict[str, object]) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            responses_session_id(body)

    def test_responses_session_id_returns_none_when_absent(self) -> None:
        assert responses_session_id({"input": "hi"}) == (None, None)

    def test_responses_to_run_returns_messages_options_and_stream(self) -> None:
        run = responses_to_run({
            "input": "hi",
            "stream": True,
            "conversation": {"id": "conv_1"},
            "max_output_tokens": 32,
            "model": "gpt-x",
        })

        # `responses_to_run` always produces a `list[Message]`; the TypedDict
        # field is typed as the wider `Agent.run` input shape, so narrow here.
        messages = cast("list[Message]", run["messages"])
        assert messages[0].text == "hi"
        assert run["stream"] is True
        assert run["options"] == {"max_tokens": 32, "model": "gpt-x"}

    def test_responses_to_run_rejects_conflicting_continuation_mechanisms(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            responses_to_run({
                "input": "hi",
                "previous_response_id": "resp_1",
                "conversation": "conv_1",
            })

    def test_responses_from_run_returns_response_payload(self) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            additional_properties={"model": "test-model"},
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert payload["id"] == "resp_new"
        assert payload["model"] == "test-model"
        assert payload["output"][0]["content"][0]["text"] == "hello"

    def test_responses_from_run_preserves_message_boundaries(self) -> None:
        result = AgentResponse(
            messages=[
                Message(role="assistant", contents=[Content.from_text("first")]),
                Message(role="assistant", contents=[Content.from_text("second")]),
            ]
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert [item["content"][0]["text"] for item in payload["output"]] == ["first", "second"]

    def test_responses_from_run_rejects_non_assistant_message_role(self) -> None:
        result = AgentResponse(messages=Message(role="user", contents=[Content.from_text("hello")]))

        with pytest.raises(ValueError, match="require.*assistant.*user"):
            responses_from_run(result, response_id="resp_new")

    def test_responses_from_run_preserves_tool_role_function_result(self) -> None:
        result = AgentResponse(
            messages=Message(
                role="tool",
                contents=[Content.from_function_result("call_1", result="sunny")],
            )
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert len(payload["output"]) == 1
        assert payload["output"][0]["type"] == "function_call_output"
        assert payload["output"][0]["call_id"] == "call_1"
        assert payload["output"][0]["output"] == [{"type": "input_text", "text": "sunny"}]
        assert payload["output"][0]["status"] == "completed"

    def test_responses_from_run_rejects_standalone_media(self) -> None:
        result = AgentResponse(
            messages=Message(
                role="assistant",
                contents=[Content.from_uri("https://example.com/cat.png", media_type="image/png")],
            )
        )

        with pytest.raises(ValueError, match="no standard representation.*uri"):
            responses_from_run(result, response_id="resp_new")

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

    def test_responses_from_run_preserves_status_metadata_and_usage(self) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("truncated")]),
            finish_reason="length",
            usage_details={
                "input_token_count": 10,
                "output_token_count": 4,
                "total_token_count": 14,
                "cache_read_input_token_count": 3,
                "cache_creation_input_token_count": 1,
                "reasoning_output_token_count": 2,
            },
            additional_properties={"metadata": {"tenant": "contoso"}},
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert payload["status"] == "incomplete"
        assert payload["incomplete_details"] == {"reason": "max_output_tokens"}
        assert payload["metadata"] == {"tenant": "contoso"}
        assert payload["usage"] == {
            "input_tokens": 10,
            "input_tokens_details": {"cached_tokens": 3, "cache_write_tokens": 1},
            "output_tokens": 4,
            "output_tokens_details": {"reasoning_tokens": 2},
            "total_tokens": 14,
        }
        assert payload["output"][0]["status"] == "incomplete"

    def test_responses_from_run_uses_raw_response_fields_as_fallback(self) -> None:
        earlier_response = SimpleNamespace(status="completed")
        terminal_response = SimpleNamespace(
            object="response",
            status="failed",
            metadata={"source": "raw"},
            error={"code": "server_error", "message": "provider failed"},
            usage=_native_usage_payload(),
        )
        raw = [
            SimpleNamespace(raw_representation=SimpleNamespace(response=earlier_response)),
            SimpleNamespace(raw_representation=SimpleNamespace(response=terminal_response)),
        ]
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("partial")]),
            raw_representation=raw,
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert payload["status"] == "failed"
        assert payload["metadata"] == {"source": "raw"}
        assert payload["error"] == {"code": "server_error", "message": "provider failed"}
        assert payload["usage"]["total_tokens"] == 9

    def test_responses_from_run_prefers_valid_raw_usage_without_merging_af_counts(self) -> None:
        raw_usage = ResponseUsage.model_validate(_native_usage_payload())
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            usage_details=cast("UsageDetails", {"input_token_count": True}),
            raw_representation=SimpleNamespace(object="response", usage=raw_usage),
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert payload["usage"] == raw_usage.model_dump(mode="json", exclude_none=True)

    def test_responses_from_run_falls_back_to_complete_af_usage_when_raw_usage_is_invalid(self) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            usage_details={
                "input_token_count": 5,
                "output_token_count": 3,
                "cache_read_input_token_count": 2,
                "cache_creation_input_token_count": 1,
                "reasoning_output_token_count": 1,
            },
            raw_representation=SimpleNamespace(object="response", usage={"input_tokens": 99}),
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert payload["usage"]["input_tokens"] == 5
        assert payload["usage"]["total_tokens"] == 8

    def test_responses_from_run_omits_invalid_raw_and_partial_af_usage(self) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            usage_details={"input_token_count": 5},
            raw_representation=SimpleNamespace(object="response", usage={"input_tokens": 99}),
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert "usage" not in payload

    def test_responses_from_run_does_not_treat_lookalike_raw_usage_as_responses_usage(self) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            usage_details={"input_token_count": 5},
            raw_representation=SimpleNamespace(usage=_native_usage_payload()),
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert "usage" not in payload

    def test_responses_from_run_does_not_treat_user_metadata_status_as_transport_status(self) -> None:
        raw_response = SimpleNamespace(status="completed", metadata={"status": "gold"})
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            additional_properties={"status": "gold"},
            raw_representation=SimpleNamespace(raw_representation=raw_response),
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert payload["status"] == "completed"
        assert payload["metadata"] == {"status": "gold"}

    def test_responses_from_run_rejects_invalid_metadata(self) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            additional_properties={"metadata": {"attempt": 1}},
        )

        with pytest.raises(ValueError):
            responses_from_run(result, response_id="resp_new")

    @pytest.mark.parametrize(
        ("usage_details", "expected_usage"),
        [
            (
                {
                    "input_token_count": 5,
                    "output_token_count": 3,
                    "cache_read_input_token_count": 2,
                    "cache_creation_input_token_count": 1,
                    "reasoning_output_token_count": 1,
                },
                {
                    "input_tokens": 5,
                    "input_tokens_details": {"cached_tokens": 2, "cache_write_tokens": 1},
                    "output_tokens": 3,
                    "output_tokens_details": {"reasoning_tokens": 1},
                    "total_tokens": 8,
                },
            ),
            (
                {
                    "input_token_count": 0,
                    "output_token_count": 0,
                    "total_token_count": 0,
                    "cache_read_input_token_count": 0,
                    "cache_creation_input_token_count": 0,
                    "reasoning_output_token_count": 0,
                },
                {
                    "input_tokens": 0,
                    "input_tokens_details": {"cached_tokens": 0, "cache_write_tokens": 0},
                    "output_tokens": 0,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 0,
                },
            ),
        ],
    )
    def test_responses_from_run_maps_complete_usage_without_cross_filling(
        self,
        usage_details: UsageDetails,
        expected_usage: dict[str, object],
    ) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            usage_details=usage_details,
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert payload["usage"] == expected_usage

    @pytest.mark.parametrize(
        "usage_details",
        [
            pytest.param({"input_token_count": 2}, id="input-only"),
            pytest.param({"output_token_count": 3}, id="output-only"),
            pytest.param({"total_token_count": 5}, id="total-only"),
            pytest.param(
                {
                    "cache_read_input_token_count": 1,
                    "cache_creation_input_token_count": 1,
                    "reasoning_output_token_count": 1,
                },
                id="details-only",
            ),
            pytest.param({"input_token_count": 2, "output_token_count": 3}, id="parents-only"),
            pytest.param(
                {
                    "output_token_count": 0,
                    "cache_read_input_token_count": 0,
                    "cache_creation_input_token_count": 0,
                    "reasoning_output_token_count": 0,
                },
                id="missing-input",
            ),
            pytest.param(
                {
                    "input_token_count": 0,
                    "cache_read_input_token_count": 0,
                    "cache_creation_input_token_count": 0,
                    "reasoning_output_token_count": 0,
                },
                id="missing-output",
            ),
            pytest.param(
                {
                    "input_token_count": 0,
                    "output_token_count": 0,
                    "cache_creation_input_token_count": 0,
                    "reasoning_output_token_count": 0,
                },
                id="missing-cache-read",
            ),
            pytest.param(
                {
                    "input_token_count": 0,
                    "output_token_count": 0,
                    "cache_read_input_token_count": 0,
                    "cache_creation_input_token_count": 0,
                },
                id="missing-reasoning",
            ),
        ],
    )
    def test_responses_from_run_omits_partial_usage(
        self,
        usage_details: UsageDetails,
    ) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            usage_details=usage_details,
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert "usage" not in payload

    def test_responses_from_run_uses_installed_sdk_usage_detail_schema(self) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            usage_details={
                "input_token_count": 5,
                "output_token_count": 1,
                "cache_read_input_token_count": 1,
                "reasoning_output_token_count": 0,
            },
        )

        payload = responses_from_run(result, response_id="resp_new")

        if "cache_write_tokens" in InputTokensDetails.model_fields:
            assert "usage" not in payload
        else:
            assert payload["usage"] == {
                "input_tokens": 5,
                "input_tokens_details": {"cached_tokens": 1},
                "output_tokens": 1,
                "output_tokens_details": {"reasoning_tokens": 0},
                "total_tokens": 6,
            }

    @pytest.mark.parametrize(
        "usage_details",
        [
            pytest.param(
                {
                    "input_token_count": 5,
                    "output_token_count": 1,
                    "total_token_count": 6,
                    "cache_read_input_token_count": 100,
                    "cache_creation_input_token_count": 0,
                    "reasoning_output_token_count": 0,
                },
                id="provider-exclusive-cache-count",
            ),
            pytest.param(
                {
                    "input_token_count": 5,
                    "output_token_count": 1,
                    "total_token_count": 6,
                    "cache_read_input_token_count": 3,
                    "cache_creation_input_token_count": 3,
                    "reasoning_output_token_count": 0,
                },
                id="combined-cache-details-exceed-input",
            ),
            pytest.param(
                {
                    "input_token_count": 1,
                    "output_token_count": 1,
                    "total_token_count": 2,
                    "cache_read_input_token_count": 0,
                    "cache_creation_input_token_count": 0,
                    "reasoning_output_token_count": 2,
                },
                id="reasoning-exceeds-output",
            ),
            pytest.param(
                {
                    "input_token_count": 2,
                    "output_token_count": 3,
                    "total_token_count": 4,
                    "cache_read_input_token_count": 0,
                    "cache_creation_input_token_count": 0,
                    "reasoning_output_token_count": 0,
                },
                id="total-under-counts",
            ),
            pytest.param(
                {
                    "input_token_count": 2,
                    "output_token_count": 3,
                    "total_token_count": 6,
                    "cache_read_input_token_count": 0,
                    "cache_creation_input_token_count": 0,
                    "reasoning_output_token_count": 0,
                },
                id="total-over-counts",
            ),
        ],
    )
    def test_responses_from_run_omits_usage_that_cannot_map_consistently(
        self,
        usage_details: UsageDetails,
    ) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            usage_details=usage_details,
        )

        payload = responses_from_run(result, response_id="resp_new")

        assert "usage" not in payload

    @pytest.mark.parametrize(
        "key",
        [
            "input_token_count",
            "output_token_count",
            "total_token_count",
            "cache_read_input_token_count",
            "cache_creation_input_token_count",
            "reasoning_output_token_count",
        ],
    )
    @pytest.mark.parametrize("count", [-1, True, 1.5])
    def test_responses_from_run_rejects_invalid_usage_count(self, key: str, count: object) -> None:
        result = AgentResponse(
            messages=Message(role="assistant", contents=[Content.from_text("hello")]),
            usage_details=cast("UsageDetails", {key: count}),
        )

        with pytest.raises(ValueError, match="non-negative integer"):
            responses_from_run(result, response_id="resp_new")

    def test_responses_from_run_maps_conversation_id(self) -> None:
        result = AgentResponse(messages=Message(role="assistant", contents=[Content.from_text("hello")]))

        payload = responses_from_run(result, response_id="resp_new", conversation_id="conv_1")

        assert payload["conversation"] == {"id": "conv_1"}

    def test_responses_from_run_omits_conversation_when_absent(self) -> None:
        result = AgentResponse(messages=Message(role="assistant", contents=[Content.from_text("hello")]))

        payload = responses_from_run(result, response_id="resp_new")

        assert "conversation" not in payload

    async def test_responses_from_streaming_run(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text("hel")], role="assistant")
            yield AgentResponseUpdate(contents=[Content.from_text("lo")], role="assistant")

        def finalizer(items: Sequence[AgentResponseUpdate]) -> AgentResponse:
            return AgentResponse.from_updates(items)

        stream = ResponseStream(updates(), finalizer=finalizer)

        events = [
            event
            async for event in responses_from_streaming_run(
                stream,
                response_id="resp_new",
                conversation_id="conv_1",
            )
        ]

        assert events[0].startswith("event: response.created")
        assert '"conversation":{"id":"conv_1"}' in events[0]
        assert "response.output_text.delta" in events[1]
        assert "hel" in events[1]
        assert "lo" in events[2]
        assert events[-1].startswith("event: response.completed")
        assert '"conversation":{"id":"conv_1"}' in events[-1]

    async def test_responses_from_streaming_run_emits_failed_when_iteration_raises(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text("partial")], role="assistant")
            raise RuntimeError("upstream blew up")

        stream = ResponseStream(updates(), finalizer=AgentResponse.from_updates)

        events = [
            event
            async for event in responses_from_streaming_run(
                stream,
                response_id="resp_new",
                conversation_id="conv_1",
            )
        ]

        assert events[0].startswith("event: response.created")
        assert "response.output_text.delta" in events[1]
        assert events[-1].startswith("event: response.failed")
        payload = _sse_payload(events[-1])
        response = cast("dict[str, object]", payload["response"])
        error = cast("dict[str, object]", response["error"])
        assert payload["type"] == "response.failed"
        assert response["status"] == "failed"
        assert response["conversation"] == {"id": "conv_1"}
        assert error["message"] == "upstream blew up"
        assert "partial" in events[-1]

    async def test_responses_from_streaming_run_preserves_final_metadata_and_usage(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text("hello")], role="assistant")

        def finalizer(items: Sequence[AgentResponseUpdate]) -> AgentResponse:
            response = AgentResponse.from_updates(items)
            response.usage_details = UsageDetails(
                input_token_count=5,
                output_token_count=1,
                total_token_count=6,
                cache_read_input_token_count=0,
                cache_creation_input_token_count=0,
                reasoning_output_token_count=0,
            )
            response.additional_properties["metadata"] = {"source": "stream"}
            return response

        stream = ResponseStream(updates(), finalizer=finalizer)

        events = [event async for event in responses_from_streaming_run(stream, response_id="resp_new")]
        payload = _sse_payload(events[-1])
        response = cast("dict[str, object]", payload["response"])

        assert response["metadata"] == {"source": "stream"}
        usage = cast("dict[str, object]", response["usage"])
        assert usage["total_tokens"] == 6

    @pytest.mark.parametrize("status", ["completed", "incomplete", "failed"])
    async def test_responses_from_streaming_run_emits_matching_terminal_event(self, status: str) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text("hello")], role="assistant")

        def finalizer(items: Sequence[AgentResponseUpdate]) -> AgentResponse:
            response = AgentResponse.from_updates(items)
            response.raw_representation = SimpleNamespace(status=status)
            return response

        stream = ResponseStream(updates(), finalizer=finalizer)

        events = [event async for event in responses_from_streaming_run(stream, response_id="resp_new")]
        payload = _sse_payload(events[-1])
        response = cast("dict[str, object]", payload["response"])

        assert events[-1].startswith(f"event: response.{status}")
        assert payload["type"] == f"response.{status}"
        assert response["status"] == status

    async def test_responses_from_streaming_run_preserves_failed_transport_error(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text("partial")], role="assistant")

        def finalizer(items: Sequence[AgentResponseUpdate]) -> AgentResponse:
            response = AgentResponse.from_updates(items)
            response.raw_representation = SimpleNamespace(
                response=SimpleNamespace(
                    status="failed",
                    error={"code": "server_error", "message": "provider failed"},
                )
            )
            return response

        stream = ResponseStream(updates(), finalizer=finalizer)

        events = [event async for event in responses_from_streaming_run(stream, response_id="resp_new")]
        payload = _sse_payload(events[-1])
        response = cast("dict[str, object]", payload["response"])

        assert events[-1].startswith("event: response.failed")
        assert response["error"] == {"code": "server_error", "message": "provider failed"}

    @pytest.mark.parametrize("status", ["in_progress", "queued"])
    async def test_responses_from_streaming_run_rejects_nonterminal_final_status(self, status: str) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text("partial")], role="assistant")

        def finalizer(items: Sequence[AgentResponseUpdate]) -> AgentResponse:
            response = AgentResponse.from_updates(items)
            response.raw_representation = SimpleNamespace(status=status)
            return response

        stream = ResponseStream(updates(), finalizer=finalizer)

        events = [event async for event in responses_from_streaming_run(stream, response_id="resp_new")]
        payload = _sse_payload(events[-1])
        response = cast("dict[str, object]", payload["response"])
        error = cast("dict[str, object]", response["error"])

        assert events[-1].startswith("event: response.failed")
        assert response["status"] == "failed"
        assert f"unsupported status {status!r}" in cast(str, error["message"])

    async def test_responses_from_streaming_run_emits_failed_when_finalizer_raises(self) -> None:
        async def updates() -> AsyncIterator[AgentResponseUpdate]:
            yield AgentResponseUpdate(contents=[Content.from_text("partial")], role="assistant")

        def finalizer(items: Sequence[AgentResponseUpdate]) -> AgentResponse:
            raise RuntimeError("finalizer blew up")

        stream = ResponseStream(updates(), finalizer=finalizer)

        events = [event async for event in responses_from_streaming_run(stream, response_id="resp_new")]

        assert events[0].startswith("event: response.created")
        assert "response.output_text.delta" in events[1]
        assert events[-1].startswith("event: response.failed")
        payload = _sse_payload(events[-1])
        response = cast("dict[str, object]", payload["response"])
        error = cast("dict[str, object]", response["error"])
        assert response["status"] == "failed"
        assert error["message"] == "finalizer blew up"
