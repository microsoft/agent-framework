# Copyright (c) Microsoft. All rights reserved.

from dataclasses import dataclass
from typing import Any, cast

from agent_framework._workflow._executor import RequestInfoMessage, RequestResponse
from agent_framework._workflow._runner_context import _decode_checkpoint_value, _encode_checkpoint_value  # type: ignore
from agent_framework._workflow._typing_utils import is_instance_of


@dataclass(kw_only=True)
class SampleRequest(RequestInfoMessage):
    prompt: str


def test_decode_dataclass_with_nested_request() -> None:
    original = RequestResponse[SampleRequest, str].handled("approve")
    original = RequestResponse[SampleRequest, str].with_correlation(
        original,
        SampleRequest(request_id="abc", prompt="prompt"),
        "abc",
    )

    encoded = _encode_checkpoint_value(original)
    decoded = cast(RequestResponse[SampleRequest, str], _decode_checkpoint_value(encoded))

    assert isinstance(decoded, RequestResponse)
    assert decoded.data == "approve"
    assert decoded.request_id == "abc"
    assert isinstance(decoded.original_request, SampleRequest)
    assert decoded.original_request.prompt == "prompt"


def test_is_instance_of_coerces_request_response_original_request_dict() -> None:
    response = RequestResponse[SampleRequest, str].handled("approve")
    response = RequestResponse[SampleRequest, str].with_correlation(
        response,
        SampleRequest(request_id="req-1", prompt="prompt"),
        "req-1",
    )

    # Simulate checkpoint decode fallback leaving a dict
    response.original_request = cast(
        Any,
        {
            "request_id": "req-1",
            "prompt": "prompt",
        },
    )

    assert is_instance_of(response, RequestResponse[SampleRequest, str])
    assert isinstance(response.original_request, SampleRequest)
